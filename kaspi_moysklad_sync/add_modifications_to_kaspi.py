# -*- coding: utf-8 -*-
"""
Создание карточки товара на Kaspi с несколькими модификациями (размерами,
цветами) - например, как у одежды и обуви, где покупатель выбирает размер
в одной карточке.

ЭТО НЕ ТО ЖЕ САМОЕ, что export_stock_to_kaspi.py. Тот скрипт только
обновляет цену/остатки у уже существующих на Kaspi SKU. А этот скрипт нужен
ОДИН РАЗ (или при добавлении новых размеров/цветов к уже заведённой модели) -
он отправляет товары через API "Товары" (POST /shop/api/products/import) с
характеристиками (размер, цвет и т.д.), и Kaspi сам объединяет их в одну
карточку, если у всех модификаций совпадает специальный признак
"Manufacturer code" внутри категории.

ВАЖНО - то, что скрипт не может сделать автоматически:
Какие именно атрибуты (характеристики) нужно передать и под какими кодами -
зависит от категории товара на Kaspi (для обуви это один набор полей, для
одежды - другой, и т.д.). Эти коды нужно один раз узнать для каждой
категории, которой вы пользуетесь. Сделать это проще всего приложенным
скриптом lookup_kaspi_category.py (он сам ходит в API Kaspi и печатает
коды) - см. раздел 15 инструкции и подсказку --help в самом скрипте.
Альтернативно коды описаны и в документации Kaspi:
- код категории: https://guide.kaspi.kz/partner/ru/shop/api/goods/q3216
- список характеристик категории: https://guide.kaspi.kz/partner/ru/shop/api/goods/q3217
- допустимые значения характеристик: https://guide.kaspi.kz/partner/ru/shop/api/goods/q3218
- сам механизм объединения (Manufacturer code / familyId):
  https://guide.kaspi.kz/partner/ru/shop/api/goods/q4817

ФОТО: каждой модификации можно явно указать "image_url" в её описании ниже,
или указать общее "image_url" на уровне модели (family). Если ни то, ни
другое не указано, скрипт сам попробует найти фото по артикулу/SKU в
kaspi_images_map.json, который готовит export_images_to_kaspi.py - так что
обычно фото можно вообще не прописывать вручную, если предварительно
запустить export_images_to_kaspi.py.

Ниже - конфигурация по образцу примера Kaspi (категория "обувь"). Скопируйте
блок MODIFICATION_FAMILIES и адаптируйте под свои товары и категории.
"""
import json
import os

import requests

import config


def _load_images_map():
    """
    Читает kaspi_images_map.json, который готовит export_images_to_kaspi.py
    (артикул -> публичная ссылка на фото). Если файла нет - просто вернёт {},
    тогда у вариантов без явного image_url фото не будет.
    """
    path = os.path.join(config.KASPI_IMAGES_DIR, "kaspi_images_map.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Каждый элемент описывает одну "модель" (родительский товар в МойСклад),
# у которой несколько модификаций должны объединиться в одну карточку.
#
# product_article   - артикул товара в МойСклад (используется и как
#                      "Manufacturer code" - значение, которое должно
#                      быть ОДИНАКОВЫМ у всех модификаций этой модели,
#                      чтобы Kaspi связал их в одну карточку, в том числе
#                      при повторных запусках в будущем);
# category           - точное название категории Kaspi (см. q3216);
# fixed_attributes    - характеристики, общие для всех модификаций модели
#                       (код характеристики -> значение). Коды смотрите в q3217;
# manufacturer_code_attr - код характеристики "Manufacturer code" для этой
#                       категории (для обуви - "Shoes*Manufacturer code",
#                       для одежды - "Clothes*Manufacturer code" и т.д.);
# variant_attribute_map - какая характеристика МойСклад (название
#                       характеристики модификации) соответствует какому
#                       коду атрибута Kaspi, например {"Размер": "Shoes*Size",
#                       "Цвет": "Shoes*Colour"};
# variants            - список модификаций: артикул в МойСклад + значения их
#                       характеристик (название характеристики -> значение).
#                       Можно добавить свой "image_url" у конкретной модификации.
MODIFICATION_FAMILIES = [
    {
        "product_article": "BOOT-001",
        "title": "Сапоги зимние",
        "brand": "Brand",
        "category": "Master - Girl knee boots",
        "manufacturer_code_attr": "Shoes*Manufacturer code",
        "fixed_attributes": {
            "Shoes*Model": "валенки",
            "Shoes*Gender": "для девочек",
            "Shoes*Material": "войлок",
            "Shoes*Season": "зима",
            "Shoes*Country": "Россия",
        },
        "variant_attribute_map": {
            "Размер": "Shoes*Size",
            "Цвет": "Shoes*Colour",
        },
        "variants": [
            {"sku": "BOOT-001-25-BEIGE", "characteristics": {"Размер": "25", "Цвет": "бежевый"}},
            {"sku": "BOOT-001-26-BEIGE", "characteristics": {"Размер": "26", "Цвет": "бежевый"}},
        ],
        # Необязательно: общее фото для всех модификаций модели. Если не
        # указать - скрипт попробует найти фото по sku в kaspi_images_map.json.
        "image_url": "https://resources.cdn-kaspi.kz/img/m/p/h44/h88/63854412398622.jpg",
    },
]


def _headers():
    # Карточки заводятся на аккаунте A (заведение карточек), поэтому здесь
    # используется отдельный токен KASPI_CARDS_API_TOKEN, а не токен продаж.
    token = config.KASPI_CARDS_API_TOKEN or config.KASPI_API_TOKEN
    return {
        "X-Auth-Token": token,
        "Accept": "application/json",
        "Content-Type": "text/plain",
    }


def build_payload(family, images_map=None):
    images_map = images_map or {}
    items = []
    for variant in family["variants"]:
        attributes = []
        for code, value in family["fixed_attributes"].items():
            attributes.append({"code": code, "value": value})
        for char_name, kaspi_code in family["variant_attribute_map"].items():
            if char_name in variant["characteristics"]:
                attributes.append({"code": kaspi_code, "value": variant["characteristics"][char_name]})
        attributes.append({
            "code": family["manufacturer_code_attr"],
            "value": family["product_article"],
        })

        # Фото по приоритету: своё на модификации -> общее на модели ->
        # автоматически найденное по артикулу в kaspi_images_map.json
        # (см. export_images_to_kaspi.py).
        image_url = (
            variant.get("image_url")
            or family.get("image_url")
            or images_map.get(variant["sku"])
        )

        items.append({
            "sku": variant["sku"],
            "title": family["title"],
            "brand": family["brand"],
            "category": family["category"],
            "attributes": attributes,
            "images": [{"url": image_url}] if image_url else [],
        })
    return items


def main():
    url = f"{config.KASPI_API_URL.replace('/v2', '')}/products/import"
    images_map = _load_images_map()
    for family in MODIFICATION_FAMILIES:
        payload = build_payload(family, images_map)
        print(f"Отправляю {len(payload)} модификаций модели «{family['title']}» (Manufacturer code={family['product_article']})...")
        resp = requests.post(url, headers=_headers(), json=payload, timeout=30)
        print(f"  Статус ответа: {resp.status_code}")
        print(f"  Ответ: {resp.text[:500]}")


if __name__ == "__main__":
    main()
