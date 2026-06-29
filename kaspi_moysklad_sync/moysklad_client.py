# -*- coding: utf-8 -*-
"""
Простой клиент для JSON API МойСклад (https://dev.moysklad.ru/doc/api/remap/1.2/).

Перед использованием в продакшене сверьте имена полей в ответах с актуальной
документацией — МойСклад иногда добавляет/переименовывает поля. Там, где это
важно, в коде ниже указано, что нужно проверить вручную одним тестовым запросом.
"""
import base64
import requests

import config


def _auth_header():
    if config.MOYSKLAD_TOKEN:
        return {"Authorization": f"Bearer {config.MOYSKLAD_TOKEN}"}
    raw = f"{config.MOYSKLAD_LOGIN}:{config.MOYSKLAD_PASSWORD}".encode("utf-8")
    return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}


def _headers():
    h = _auth_header()
    h.update({
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip",
    })
    return h


def _get(path, params=None):
    url = f"{config.MOYSKLAD_API_URL}{path}"
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _post(path, payload):
    url = f"{config.MOYSKLAD_API_URL}{path}"
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"MoySklad API error {resp.status_code}: {resp.text}")
    return resp.json()


def get_stock_by_store():
    """
    Возвращает список товаров и модификаций с остатками по каждому складу.
    GET /report/stock/bystore

    По умолчанию этот отчёт отдаёт строки и по обычным товарам, и по их
    модификациям (размерам/цветам), и по комплектам - каждая позиция со
    своим артикулом и своими остатками. Различить их можно по ссылке в
    "meta.href": для товара это .../entity/product/<id>, для модификации -
    .../entity/variant/<id>.

    Ожидаемая структура одной строки ответа (проверьте по факту первым тестовым
    запросом и поправьте парсинг в export_stock_to_kaspi.py при необходимости):
    {
        "meta": {...},              # ссылка на товар/модификацию
        "name": "Название товара",
        "code": "арт-001",
        "article": "арт-001",
        "price": 123000,           # в копейках
        "stockByStore": [
            {"stock": 5, "store": {"meta": {"href": ".../entity/store/<id>"}}},
            ...
        ]
    }
    """
    results = []
    offset = 0
    limit = 1000
    while True:
        data = _get("/report/stock/bystore", params={"limit": limit, "offset": offset})
        rows = data.get("rows", data.get("data", []))
        results.extend(rows)
        if len(rows) < limit:
            break
        offset += limit
    return results


def get_product_attributes_map():
    """
    Возвращает словарь {product_id: {"export": bool, "kaspi_sku": str|None}},
    собранный из доп. полей товаров (см. config.EXPORT_FLAG_ATTRIBUTE_NAME и
    config.KASPI_SKU_ATTRIBUTE_NAME).

    GET /entity/product отдаёт доп. поля каждого товара в массиве "attributes"
    (id, name, type, value) без необходимости отдельного expand.
    """
    result = {}
    offset = 0
    limit = 1000
    while True:
        data = _get("/entity/product", params={"limit": limit, "offset": offset})
        rows = data.get("rows", [])
        for row in rows:
            product_id = row.get("id")
            export_flag = False
            kaspi_sku = None
            for attr in row.get("attributes", []):
                name = attr.get("name")
                if name == config.EXPORT_FLAG_ATTRIBUTE_NAME:
                    export_flag = bool(attr.get("value"))
                elif name == config.KASPI_SKU_ATTRIBUTE_NAME and attr.get("value"):
                    kaspi_sku = str(attr.get("value")).strip()
            result[product_id] = {"export": export_flag, "kaspi_sku": kaspi_sku}
        if len(rows) < limit:
            break
        offset += limit
    return result


def get_variant_attributes_map():
    """
    Возвращает словарь {variant_id: {"product_id": str|None, "export": bool|None,
    "kaspi_sku": str|None}} для всех модификаций (размеров/цветов) товаров.

    "export" = None означает, что у самой модификации доп. поле
    EXPORT_FLAG_ATTRIBUTE_NAME не создано/не заполнено - в этом случае нужно
    использовать флажок родительского товара (см. build_offers в
    export_stock_to_kaspi.py). Если поле явно создано на модификациях и
    заполнено (true/false) - используется именно оно, в приоритете перед
    флажком товара.

    GET /entity/variant отдаёт в каждой строке ссылку на родительский товар
    в поле "product" (meta), а также собственные доп. поля в "attributes".
    """
    result = {}
    offset = 0
    limit = 1000
    while True:
        data = _get("/entity/variant", params={"limit": limit, "offset": offset})
        rows = data.get("rows", [])
        for row in rows:
            variant_id = row.get("id")
            product_href = row.get("product", {}).get("meta", {}).get("href", "")
            product_id = product_href.rstrip("/").split("/")[-1] if product_href else None

            export_flag = None  # "не задано на модификации"
            kaspi_sku = None
            for attr in row.get("attributes", []):
                name = attr.get("name")
                if name == config.EXPORT_FLAG_ATTRIBUTE_NAME:
                    export_flag = bool(attr.get("value"))
                elif name == config.KASPI_SKU_ATTRIBUTE_NAME and attr.get("value"):
                    kaspi_sku = str(attr.get("value")).strip()

            result[variant_id] = {
                "product_id": product_id,
                "export": export_flag,
                "kaspi_sku": kaspi_sku,
            }
        if len(rows) < limit:
            break
        offset += limit
    return result


def _extract_id(href):
    """Достаёт id из href, отбрасывая query-строку (напр. ?expand=supplier)."""
    if not href:
        return None
    return href.split("?")[0].rstrip("/").split("/")[-1]


def _attr_value(entity, name):
    for a in entity.get("attributes", []):
        if a.get("name") == name:
            return a.get("value")
    return None


def _sale_price(entity, price_type_name):
    """Возвращает значение нужного типа цены (в тиынах) или None."""
    for sp in entity.get("salePrices", []):
        if sp.get("priceType", {}).get("name") == price_type_name:
            return sp.get("value")
    return None


def _split_skus(override, fallback_code):
    """Список SKU для Kaspi. Если задан override (Каспи-артикул(ы)) — можно
    указать несколько через запятую (привязка к нескольким карточкам Kaspi),
    тогда возвращаем их все. Иначе — внутренний код одной позицией."""
    if override:
        parts = [s.strip() for s in str(override).split(",") if s.strip()]
        if parts:
            return parts
    return [fallback_code] if fallback_code else []


def build_assortment_index():
    """
    Единый справочник по товарам и модификациям, ключ — id ассортимента
    (совпадает с id в meta.href отчёта stock/bystore).

    Значение: {
        "name": str, "sku": str|None, "price": int|None (в тиынах),
        "brand": str|None, "export": bool|None, "kaspi_sku": str|None,
        "kind": "product"|"variant", "parent_id": str|None
    }

    "export" = None у модификаций (своих доп. полей у них нет) — берётся флаг
    родительского товара (см. export_stock_to_kaspi.build_offers).
    Цена берётся по типу config.KASPI_PRICE_TYPE; у модификации без своей цены
    наследуется цена родительского товара.
    SKU: доп. поле KASPI_SKU -> article -> code.
    """
    index = {}
    limit = 1000

    # --- Товары ---
    offset = 0
    while True:
        data = _get("/entity/product", params={"limit": limit, "offset": offset})
        rows = data.get("rows", [])
        for r in rows:
            pid = r.get("id")
            kaspi_sku = _attr_value(r, config.KASPI_SKU_ATTRIBUTE_NAME)
            kaspi_sku = str(kaspi_sku).strip() if kaspi_sku else None
            export = _attr_value(r, config.EXPORT_FLAG_ATTRIBUTE_NAME)
            # Каспи-SKU товара: доп. поле «Каспи артикулы» (можно несколько через
            # запятую) — привязка к существующим карточкам; иначе артикул/код.
            index[pid] = {
                "name": r.get("name"),
                "skus": _split_skus(kaspi_sku, r.get("article") or r.get("code")),
                "override": bool(kaspi_sku),
                "price": _sale_price(r, config.KASPI_PRICE_TYPE),
                "brand": _attr_value(r, config.BRAND_ATTRIBUTE_NAME),
                "export": bool(export) if export is not None else False,
                "kaspi_sku": kaspi_sku,
                "kind": "product",
                "parent_id": None,
            }
        if len(rows) < limit:
            break
        offset += limit

    # --- Модификации ---
    offset = 0
    while True:
        data = _get("/entity/variant", params={"limit": limit, "offset": offset})
        rows = data.get("rows", [])
        for r in rows:
            vid = r.get("id")
            parent_id = _extract_id(r.get("product", {}).get("meta", {}).get("href", ""))
            parent = index.get(parent_id, {})
            kaspi_sku = _attr_value(r, config.KASPI_SKU_ATTRIBUTE_NAME)
            kaspi_sku = str(kaspi_sku).strip() if kaspi_sku else None
            own_price = _sale_price(r, config.KASPI_PRICE_TYPE)
            # У модификаций нет доп. полей, поэтому Каспи-SKU задаётся в
            # стандартном поле «Артикул» (можно несколько через запятую —
            # привязка к нескольким карточкам Kaspi); иначе используется «Код».
            index[vid] = {
                "name": r.get("name"),
                "skus": _split_skus(r.get("article"), r.get("code")),
                "override": bool(r.get("article")),
                "price": own_price if own_price else parent.get("price"),
                "brand": parent.get("brand"),
                "export": None,  # наследуется от родительского товара
                "kaspi_sku": kaspi_sku,
                "kind": "variant",
                "parent_id": parent_id,
            }
        if len(rows) < limit:
            break
        offset += limit

    return index


def find_product_by_article(article):
    """Найти товар в МойСклад по артикулу (article) или коду (code)."""
    data = _get("/entity/product", params={"filter": f"article={article}"})
    rows = data.get("rows", [])
    if rows:
        return rows[0]
    data = _get("/entity/product", params={"filter": f"code={article}"})
    rows = data.get("rows", [])
    return rows[0] if rows else None


def find_counterparty_by_phone(phone):
    data = _get("/entity/counterparty", params={"filter": f"phone={phone}"})
    rows = data.get("rows", [])
    return rows[0] if rows else None


def create_counterparty(first_name, last_name, phone):
    payload = {
        "name": f"{last_name} {first_name}".strip() or phone,
        "companyType": "individual",
        "phone": phone,
        "legalFirstName": first_name,
        "legalLastName": last_name,
    }
    if config.MOYSKLAD_AGENT_GROUP_ID:
        payload["group"] = {"meta": _group_meta(config.MOYSKLAD_AGENT_GROUP_ID)}
    return _post("/entity/counterparty", payload)


def find_customerorder_by_external_code(external_code):
    """Используется, чтобы не создавать дубликат заказа при повторном запуске."""
    data = _get("/entity/customerorder", params={"filter": f"externalCode={external_code}"})
    rows = data.get("rows", [])
    return rows[0] if rows else None


def create_customer_order(external_code, agent_meta, store_meta, positions, description=""):
    """
    positions: список словарей вида
        {"quantity": 1, "price": 123000, "assortment_meta": {...meta товара...}}
    """
    payload = {
        "externalCode": external_code,
        "organization": {"meta": _organization_meta()},
        "agent": {"meta": agent_meta},
        "store": {"meta": store_meta},
        "description": description,
        "positions": [
            {
                "quantity": p["quantity"],
                "price": p["price"],
                "assortment": {"meta": p["assortment_meta"]},
            }
            for p in positions
        ],
    }
    return _post("/entity/customerorder", payload)


def list_products():
    """Возвращает все товары (/entity/product) постранично, без фильтра."""
    result = []
    offset = 0
    limit = 1000
    while True:
        data = _get("/entity/product", params={"limit": limit, "offset": offset})
        rows = data.get("rows", [])
        result.extend(rows)
        if len(rows) < limit:
            break
        offset += limit
    return result


def get_product_images(product_id):
    """
    GET /entity/product/{id}/images
    Возвращает список изображений товара. У каждого изображения есть имя
    файла и ссылка для скачивания самого файла (требует авторизации, как и
    остальные запросы к МойСклад - просто URL без авторизации не отдаст файл).

    Поле со ссылкой на скачивание называется по-разному в разных версиях
    ответа МойСклад - функция проверяет несколько вариантов. Если для вашего
    аккаунта ни один не сработает, проверьте реальный ответ одним тестовым
    запросом и поправьте _image_download_href ниже.
    """
    data = _get(f"/entity/product/{product_id}/images")
    return data.get("rows", [])


def list_bundles():
    """Все комплекты (/entity/bundle) постранично."""
    result, offset, limit = [], 0, 1000
    while True:
        data = _get("/entity/bundle", params={"limit": limit, "offset": offset})
        rows = data.get("rows", [])
        result.extend(rows)
        if len(rows) < limit:
            break
        offset += limit
    return result


def get_bundle_components(bundle_id):
    """Состав комплекта: список {quantity, assortment{meta}} компонентов."""
    data = _get(f"/entity/bundle/{bundle_id}/components")
    return data.get("rows", [])


def build_store_stock_map():
    """Карта {assortment_id: {store_id: stock}} из /report/stock/bystore —
    нужна для расчёта остатка комплектов по их компонентам."""
    result = {}
    for row in get_stock_by_store():
        aid = _extract_id(row.get("meta", {}).get("href", ""))
        per_store = {}
        for e in row.get("stockByStore", []):
            sid = _extract_id(e.get("meta", {}).get("href", ""))
            per_store[sid] = e.get("stock", 0)
        result[aid] = per_store
    return result


def get_variant_images(variant_id):
    """GET /entity/variant/{id}/images — фото конкретной модификации."""
    data = _get(f"/entity/variant/{variant_id}/images")
    return data.get("rows", [])


def _image_download_href(image):
    return (
        image.get("downloadHref")
        or image.get("meta", {}).get("downloadHref")
        or image.get("miniature", {}).get("downloadHref")
    )


def download_image_bytes(image):
    """Скачивает содержимое одного изображения (см. get_product_images)."""
    href = _image_download_href(image)
    if not href:
        return None
    resp = requests.get(href, headers=_auth_header(), timeout=30)
    resp.raise_for_status()
    return resp.content


def _organization_meta():
    return {
        "href": f"{config.MOYSKLAD_API_URL}/entity/organization/{config.MOYSKLAD_ORGANIZATION_ID}",
        "type": "organization",
        "mediaType": "application/json",
    }


def _group_meta(group_id):
    return {
        "href": f"{config.MOYSKLAD_API_URL}/entity/group/{group_id}",
        "type": "group",
        "mediaType": "application/json",
    }


def store_meta_by_id(store_id):
    return {
        "href": f"{config.MOYSKLAD_API_URL}/entity/store/{store_id}",
        "type": "store",
        "mediaType": "application/json",
    }
