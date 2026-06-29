# -*- coding: utf-8 -*-
"""
Выгрузка товаров (включая модификации - размеры/цвета) и остатков из
МойСклад в XML-прайс-лист формата Kaspi.kz.

Запускайте по расписанию (cron / планировщик), например каждые 15-30 минут.
Файл, который генерирует этот скрипт, должен быть доступен по постоянной
http(s)-ссылке — её один раз указываете в кабинете продавца Kaspi:
Товары -> Загрузить прайс-лист -> Автоматическая загрузка.
Сам Kaspi скачивает файл по этой ссылке примерно раз в 60 минут.

Формат XML описан здесь:
https://guide.kaspi.kz/partner/ru/shop/goods/price_list/q3251

Какие товары попадают в выгрузку:
- только те, у которых установлен склад из STORE_MAP (см. config.py);
- если config.REQUIRE_EXPORT_FLAG = True (по умолчанию) - дополнительно
  только те, у которых в МойСклад стоит галочка в доп. поле
  config.EXPORT_FLAG_ATTRIBUTE_NAME ("Выгружать в Kaspi" по умолчанию).
  У модификаций (размеров/цветов) галочка проверяется отдельно на самой
  модификации, а если там поле не создано/не заполнено - используется
  галочка родительского товара;
- SKU в выгрузке берётся из доп. поля config.KASPI_SKU_ATTRIBUTE_NAME
  (отдельно для товара и для каждой модификации), если оно заполнено,
  иначе - из обычного Артикула товара/модификации в МойСклад.

Про объединение нескольких модификаций в одну карточку на Kaspi (как у
одежды/обуви с выбором размера) - этот скрипт только обновляет цену и
остатки уже существующих на Kaspi SKU. Чтобы изначально объединить
несколько SKU в одну карточку, используйте add_modifications_to_kaspi.py.
"""
import argparse
import datetime
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom

import config
import moysklad_client


def _resolve_export(info, index):
    """Флаг выгрузки позиции: у модификации (export=None) берём флаг товара."""
    export = info.get("export")
    if export is None:
        parent = index.get(info.get("parent_id")) or {}
        export = bool(parent.get("export"))
    return export


def build_offers(stock_rows, index, require_flag=True):
    """
    stock_rows  - строки отчёта /report/stock/bystore (meta + stockByStore).
    index       - справочник из moysklad_client.build_assortment_index().
    Возвращает (offers, skipped, stats) — stats для диагностики причин пропуска.
    """
    offers = []
    skipped = []
    stats = {"no_info": 0, "no_flag": 0, "no_sku": 0, "no_price": 0,
             "no_store": 0, "ok": 0}

    for row in stock_rows:
        aid = moysklad_client._extract_id(row.get("meta", {}).get("href", ""))
        info = index.get(aid)
        if not info:
            stats["no_info"] += 1
            skipped.append(f"<id {aid}> (нет в справочнике товаров)")
            continue

        name = info.get("name") or aid

        if require_flag and not _resolve_export(info, index):
            stats["no_flag"] += 1
            skipped.append(name + " (нет галочки «Выгружать в каспи»)")
            continue

        skus = info.get("skus") or []
        if not skus:
            stats["no_sku"] += 1
            skipped.append(name + " (нет артикула/кода для SKU)")
            continue

        price_tiyn = info.get("price")
        if not price_tiyn:
            stats["no_price"] += 1
            skipped.append(name + f" (нет цены «{config.KASPI_PRICE_TYPE}»)")
            continue
        price = round(price_tiyn / 100)  # тиыны -> тенге

        availabilities = []
        for entry in row.get("stockByStore", []):
            store_id = moysklad_client._extract_id(entry.get("meta", {}).get("href", ""))
            kaspi_point = config.STORE_MAP.get(store_id)
            if not kaspi_point:
                continue  # склад не привязан к точке Kaspi
            stock_count = int(entry.get("stock", 0))
            availabilities.append({
                "storeId": kaspi_point,
                "available": "yes" if stock_count > 0 else "no",
                "stockCount": stock_count,
            })

        if not availabilities:
            stats["no_store"] += 1
            skipped.append(name + " (нет остатка по привязанным складам STORE_MAP)")
            continue

        stats["ok"] += 1
        # один offer на каждый Каспи-SKU (несколько SKU = привязка к нескольким
        # карточкам Kaspi с одинаковой ценой и остатком этой позиции)
        for sku in skus:
            offers.append({
                "sku": sku,
                "model": name,
                "brand": info.get("brand") or config.DEFAULT_BRAND,
                "price": price,
                "availabilities": availabilities,
            })

    return offers, skipped, stats


def build_bundle_offers(store_stock_map, require_flag=True):
    """
    Предложения для КОМПЛЕКТОВ (обеденные группы и собранные изделия). Остаток
    комплекта в МойСклад в отчётах не лежит — считаем его сами как минимум по
    компонентам: для каждого склада из STORE_MAP остаток = min по компонентам
    от floor(остаток_компонента / нужное_количество).

    SKU комплекта — «Артикул» (можно несколько через запятую) или «Код».
    Отбор — по тому же флажку «Выгружать в каспи» (он есть и у комплектов).
    """
    offers, skipped = [], []
    stats = {"ok": 0, "no_flag": 0, "no_sku": 0, "no_price": 0, "no_store": 0}

    for b in moysklad_client.list_bundles():
        name = b.get("name") or b.get("code")
        if require_flag and not bool(moysklad_client._attr_value(b, config.EXPORT_FLAG_ATTRIBUTE_NAME)):
            stats["no_flag"] += 1
            continue
        skus = moysklad_client._split_skus(b.get("article"), b.get("code"))
        if not skus:
            stats["no_sku"] += 1
            skipped.append(name + " (нет артикула/кода)")
            continue
        price_tiyn = moysklad_client._sale_price(b, config.KASPI_PRICE_TYPE)
        if not price_tiyn:
            stats["no_price"] += 1
            skipped.append(name + f" (нет цены «{config.KASPI_PRICE_TYPE}»)")
            continue
        price = round(price_tiyn / 100)
        brand = moysklad_client._attr_value(b, config.BRAND_ATTRIBUTE_NAME) or config.KASPI_BUNDLE_BRAND

        components = moysklad_client.get_bundle_components(b["id"])
        availabilities = []
        for store_id, kaspi_point in config.STORE_MAP.items():
            can = None
            for c in components:
                cid = moysklad_client._extract_id(c.get("assortment", {}).get("meta", {}).get("href", ""))
                qty = c.get("quantity") or 0
                cstock = store_stock_map.get(cid, {}).get(store_id, 0)
                cap = int(cstock // qty) if qty else 0
                can = cap if can is None else min(can, cap)
            count = int(can or 0)
            availabilities.append({
                "storeId": kaspi_point,
                "available": "yes" if count > 0 else "no",
                "stockCount": count,
            })

        if not availabilities:
            stats["no_store"] += 1
            skipped.append(name + " (нет складов в STORE_MAP)")
            continue

        stats["ok"] += 1
        for sku in skus:
            offers.append({
                "sku": sku, "model": name,
                "brand": brand, "price": price,
                "availabilities": availabilities,
            })

    return offers, skipped, stats


def render_xml(offers):
    root = ET.Element("kaspi_catalog", {
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "xmlns": "kaspiShopping",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "kaspiShopping http://kaspi.kz/kaspishopping.xsd",
    })
    ET.SubElement(root, "company").text = config.KASPI_COMPANY_NAME
    ET.SubElement(root, "merchantid").text = config.KASPI_MERCHANT_ID
    offers_el = ET.SubElement(root, "offers")

    for offer in offers:
        offer_el = ET.SubElement(offers_el, "offer", {"sku": str(offer["sku"])})
        ET.SubElement(offer_el, "model").text = str(offer["model"])
        ET.SubElement(offer_el, "brand").text = str(offer["brand"])

        avail_el = ET.SubElement(offer_el, "availabilities")
        for a in offer["availabilities"]:
            ET.SubElement(avail_el, "availability", {
                "available": a["available"],
                "storeId": str(a["storeId"]),
                "stockCount": str(a["stockCount"]),
            })

        ET.SubElement(offer_el, "price").text = str(offer["price"])

    raw = ET.tostring(root, encoding="utf-8")
    return minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Выгрузка остатков МойСклад -> Kaspi XML")
    parser.add_argument("--all", action="store_true",
                        help="игнорировать флаг «Выгружать в каспи» (для диагностики)")
    parser.add_argument("--report", action="store_true",
                        help="только статистика, без записи XML-файла")
    args = parser.parse_args()

    require_flag = config.REQUIRE_EXPORT_FLAG and not args.all

    print("Собираю справочник товаров и модификаций (название/цена/SKU/флаг)...")
    index = moysklad_client.build_assortment_index()
    print(f"  позиций в справочнике: {len(index)}")

    print("Получаю остатки из МойСклад (stock/bystore)...")
    stock_rows = moysklad_client.get_stock_by_store()
    print(f"  строк отчёта: {len(stock_rows)}")

    offers, skipped, stats = build_offers(stock_rows, index, require_flag=require_flag)

    # Комплекты (обеденные группы): остаток считаем из компонентов.
    store_stock_map = {}
    for row in stock_rows:
        aid = moysklad_client._extract_id(row.get("meta", {}).get("href", ""))
        per = {}
        for e in row.get("stockByStore", []):
            per[moysklad_client._extract_id(e.get("meta", {}).get("href", ""))] = e.get("stock", 0)
        store_stock_map[aid] = per
    print("Считаю остатки комплектов из компонентов...")
    b_offers, b_skipped, b_stats = build_bundle_offers(store_stock_map, require_flag=require_flag)
    offers += b_offers
    skipped += b_skipped

    print("\n=== Статистика ===")
    print(f"  Товары/модификации: {stats['ok']} позиций")
    print(f"  Комплекты: {b_stats['ok']} позиций (остаток из компонентов)")
    print(f"  Итого offer'ов в фиде: {len(offers)} (с учётом нескольких SKU)")
    print(f"  Пропущено — нет флага:      {stats['no_flag']}")
    print(f"  Пропущено — нет цены:       {stats['no_price']}")
    print(f"  Пропущено — нет SKU:        {stats['no_sku']}")
    print(f"  Пропущено — нет склада:     {stats['no_store']}")
    print(f"  Пропущено — нет в справочн: {stats['no_info']}")
    if require_flag:
        print("  (учитывается флаг «Выгружать в каспи»; для прогона без него: --all)")
    if skipped:
        print("\nПримеры пропущенных:")
        for s in skipped[:15]:
            print(f"  - {s}")
        if len(skipped) > 15:
            print(f"  ...и ещё {len(skipped) - 15}")

    if args.report:
        print("\n[--report] XML-файл не записан.")
        return

    xml_bytes = render_xml(offers)
    with open(config.KASPI_FEED_FILE_PATH, "wb") as f:
        f.write(xml_bytes)
    print(f"\nФайл сохранён: {config.KASPI_FEED_FILE_PATH} ({len(offers)} offer'ов)")


if __name__ == "__main__":
    main()
