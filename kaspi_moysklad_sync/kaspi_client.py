# -*- coding: utf-8 -*-
"""
Простой клиент для API Магазина на Kaspi.kz.
Документация: https://guide.kaspi.kz/partner/ru/shop/api/general
"""
import requests

import config


def _headers():
    return {
        "X-Auth-Token": config.KASPI_API_TOKEN,
        "Content-Type": "application/vnd.api+json",
    }


def get_new_orders(page_number=0, page_size=50):
    """
    GET /orders?filter[orders][state]=NEW
    Возвращает заказы, которые продавец ещё не принял.
    """
    url = f"{config.KASPI_API_URL}/orders"
    params = {
        "page[number]": page_number,
        "page[size]": page_size,
        "filter[orders][state]": "NEW",
        "include[orders]": "user",
    }
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_order_entries(order_id):
    """GET /orders/{id}/entries — состав заказа (товарные позиции)."""
    url = f"{config.KASPI_API_URL}/orders/{order_id}/entries"
    params = {"include": "product"}
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _classification_url(path):
    # эти эндпоинты живут не под /v2, а прямо под /shop/api/...
    base = config.KASPI_API_URL.split("/shop/api")[0] + "/shop/api"
    return f"{base}/{path}"


def get_categories():
    """
    GET /products/classification/categories
    Список всех категорий товаров на Kaspi: [{"code": ..., "title": ...}, ...]
    code - то, что нужно указывать в поле "category" при добавлении товара.
    """
    url = _classification_url("products/classification/categories")
    resp = requests.get(url, headers={"X-Auth-Token": config.KASPI_API_TOKEN, "Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_category_attributes(category_code):
    """
    GET /products/classification/attributes?c=<category_code>
    Список характеристик категории: код, тип (boolean/enum/string/number),
    можно ли указать несколько значений (multiValued), обязательна ли
    характеристика (mandatory). Характеристика с кодом, заканчивающимся на
    "*Manufacturer code", и есть тот самый код для объединения модификаций.
    """
    url = _classification_url("products/classification/attributes")
    params = {"c": category_code}
    resp = requests.get(url, headers={"X-Auth-Token": config.KASPI_API_TOKEN, "Accept": "application/json"}, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_attribute_values(category_code, attribute_code):
    """
    GET /products/classification/attribute/values?c=<category_code>&a=<attribute_code>
    Для характеристик типа enum - список допустимых значений: [{"code":.., "name":..}, ...]
    Значение, которое нужно передавать в attributes[].value - это поле "code".
    """
    url = _classification_url("products/classification/attribute/values")
    params = {"c": category_code, "a": attribute_code}
    resp = requests.get(url, headers={"X-Auth-Token": config.KASPI_API_TOKEN, "Accept": "application/json"}, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def accept_order(order_id, order_code):
    """POST /orders — перевод заказа в статус ACCEPTED_BY_MERCHANT."""
    url = f"{config.KASPI_API_URL}/orders"
    payload = {
        "data": {
            "type": "orders",
            "id": order_id,
            "attributes": {
                "code": order_code,
                "status": "ACCEPTED_BY_MERCHANT",
            },
        }
    }
    resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Kaspi API error {resp.status_code}: {resp.text}")
    return resp.json()
