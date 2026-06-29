# -*- coding: utf-8 -*-
"""
Подготовка фото товаров для Kaspi: скачивает изображения из МойСклад и
сохраняет их в локальную папку, чтобы их можно было раздавать по публичной
ссылке (https://.../kaspi_images/<sku>_1.jpg). Эту папку публикуем на том же
хостинге, что и kaspi_feed.xml (GitHub Pages).

ПОЧЕМУ ОТДЕЛЬНЫЙ ШАГ: полноразмерное фото в МойСклад доступно только по
авторизованной ссылке — Kaspi по ней ничего не скачает. Поэтому фото один раз
скачиваем и кладём на публичный хостинг.

Что делает (решения по проекту, см. STATUS.md):
- берёт только товары с галочкой «Выгружать в каспи» (флаг наследуется
  модификациями — своих доп. полей у модификаций нет);
- выгружает КАЖДУЮ модификацию отдельно (для мебели модификация = карточка),
  ключ — её SKU (артикул/код); если у модификации нет своих фото, берёт фото
  родительского товара;
- сохраняет ВСЕ фото галереи (а не только главное);
- пишет kaspi_images_map.json вида {"SKU": ["https://.../sku_1.jpg", ...]},
  его читает create_cards_from_template.py.

Запуск: python export_images_to_kaspi.py
"""
import json
import os

import config
import moysklad_client


def _ext(image):
    filename = image.get("filename", "")
    if "." in filename:
        return "." + filename.rsplit(".", 1)[-1].lower()
    return ".jpg"


def _flagged(product):
    return bool(moysklad_client._attr_value(product, config.EXPORT_FLAG_ATTRIBUTE_NAME))


def _save_images(sku, images):
    """Скачивает и сохраняет все фото; возвращает список публичных URL."""
    urls = []
    for i, image in enumerate(images, start=1):
        data = moysklad_client.download_image_bytes(image)
        if not data:
            continue
        filename = f"{sku}_{i}{_ext(image)}"
        with open(os.path.join(config.KASPI_IMAGES_DIR, filename), "wb") as f:
            f.write(data)
        urls.append(f"{config.KASPI_IMAGES_BASE_URL.rstrip('/')}/{filename}")
    return urls


def _fetch_variants():
    rows, offset, limit = [], 0, 1000
    while True:
        data = moysklad_client._get("/entity/variant", params={"limit": limit, "offset": offset})
        page = data.get("rows", [])
        rows.extend(page)
        if len(page) < limit:
            break
        offset += limit
    return rows


def main():
    os.makedirs(config.KASPI_IMAGES_DIR, exist_ok=True)

    print("Загружаю товары и модификации...")
    products = moysklad_client.list_products()
    by_id = {p["id"]: p for p in products}
    variants = _fetch_variants()

    images_map = {}
    skipped = []
    saved = 0

    # модификации товаров с галочкой
    for v in variants:
        parent_id = moysklad_client._extract_id(v.get("product", {}).get("meta", {}).get("href", ""))
        parent = by_id.get(parent_id)
        if not parent or not _flagged(parent):
            continue
        sku = v.get("code") or v.get("article")
        if not sku:
            continue
        images = moysklad_client.get_variant_images(v["id"])
        if not images:  # нет своих фото — берём фото родительского товара
            images = moysklad_client.get_product_images(parent_id)
        if not images:
            skipped.append(f"{sku} (нет фото)")
            continue
        urls = _save_images(sku, images)
        if urls:
            images_map[sku] = urls
            saved += 1

    # товары без модификаций с галочкой
    for p in products:
        if (p.get("variantsCount") or 0) > 0 or not _flagged(p):
            continue
        sku = p.get("article") or p.get("code")
        if not sku:
            continue
        images = moysklad_client.get_product_images(p["id"])
        if not images:
            skipped.append(f"{sku} (нет фото)")
            continue
        urls = _save_images(sku, images)
        if urls:
            images_map[sku] = urls
            saved += 1

    map_path = os.path.join(config.KASPI_IMAGES_DIR, "kaspi_images_map.json")
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(images_map, f, ensure_ascii=False, indent=2)

    print(f"SKU с фото: {saved}; всего файлов сохранено в {config.KASPI_IMAGES_DIR}")
    if skipped:
        print(f"Без фото: {len(skipped)}")
        for s in skipped[:15]:
            print(f"  - {s}")
    print(f"Карта SKU -> ссылки: {map_path}")


if __name__ == "__main__":
    main()
