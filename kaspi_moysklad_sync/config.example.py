# -*- coding: utf-8 -*-
"""
Скопируйте этот файл в config.py и заполните своими данными.
config.py НЕ публикуйте и не передавайте третьим лицам — в нём хранятся токены доступа.

Все значения ниже можно задать ДВУМЯ способами:
1. Впишите значение прямо здесь (вместо плейсхолдера) - удобно для запуска
   на своём сервере/компьютере, где config.py просто лежит локально.
2. Задайте переменную окружения с тем же именем - тогда она имеет приоритет
   над значением в файле. Это используется для запуска через GitHub Actions
   (см. GITHUB_SETUP.md): секреты передаются как переменные окружения, а сам
   config.example.py (без секретов) спокойно лежит в публичном репозитории.
"""
import json
import os


def _env(name, default):
    return os.environ.get(name, default)


# ---------- МойСклад ----------
# Логин и пароль рекомендуется создать отдельные, специально для интеграции.
MOYSKLAD_LOGIN = _env("MOYSKLAD_LOGIN", "your-login@example.com")
MOYSKLAD_PASSWORD = _env("MOYSKLAD_PASSWORD", "your-password")

# Если вместо логина/пароля используете присоединённое приложение и токен.
MOYSKLAD_TOKEN = _env("MOYSKLAD_TOKEN", "")

MOYSKLAD_API_URL = "https://api.moysklad.ru/api/remap/1.2"

# ID организации (нужен только для приёма заказов).
MOYSKLAD_ORGANIZATION_ID = _env("MOYSKLAD_ORGANIZATION_ID", "00000000-0000-0000-0000-000000000000")

# Контрагент по умолчанию для заказов Kaspi (пусто = создавать нового по покупателю).
MOYSKLAD_DEFAULT_AGENT_ID = _env("MOYSKLAD_DEFAULT_AGENT_ID", "")

# Группа контрагентов для авто-создаваемых покупателей Kaspi (можно пусто).
MOYSKLAD_AGENT_GROUP_ID = _env("MOYSKLAD_AGENT_GROUP_ID", "")

# Сопоставление складов МойСклад -> точка продаж Kaspi (storeId).
# Для GitHub Actions задайте секрет STORE_MAP_JSON вида {"uuid": "PP2"}.
_default_store_map = {
    # Склад Астана (МойСклад) -> точка продаж Kaspi "PP2".
    "67787641-f0db-11ee-0a80-10a7000edd8f": "PP2",
}
STORE_MAP = json.loads(_env("STORE_MAP_JSON", "null") or "null") or _default_store_map

# Склад МойСклад для создания заказов покупателей (откуда списываем при отгрузке).
MOYSKLAD_DEFAULT_STORE_ID = _env("MOYSKLAD_DEFAULT_STORE_ID", "67787641-f0db-11ee-0a80-10a7000edd8f")

# ---------- Kaspi Магазин: ДВА аккаунта ----------
# Новые карточки заводятся на аккаунте A, остатки/продажи идут с аккаунта B.
# Токен API формируется в кабинете каждого аккаунта: Настройки -> Токен API.
KASPI_API_URL = "https://kaspi.kz/shop/api/v2"

# Аккаунт A — заведение карточек (products/import).
KASPI_CARDS_API_TOKEN = _env("KASPI_CARDS_API_TOKEN", "your-cards-account-token")
KASPI_CARDS_MERCHANT_ID = _env("KASPI_CARDS_MERCHANT_ID", "your-cards-merchant-id")

# Аккаунт B — продажи: остатки/цены (XML-фид) и приём заказов.
KASPI_SALES_API_TOKEN = _env("KASPI_SALES_API_TOKEN", "your-sales-account-token")
KASPI_SALES_MERCHANT_ID = _env("KASPI_SALES_MERCHANT_ID", "your-sales-merchant-id")

# Краткое название компании для XML прайс-листа (аккаунт B).
KASPI_COMPANY_NAME = _env("KASPI_COMPANY_NAME", "Your Company")

# Обратная совместимость: единый токен/merchantId = аккаунт продаж (B).
KASPI_API_TOKEN = KASPI_SALES_API_TOKEN
KASPI_MERCHANT_ID = KASPI_SALES_MERCHANT_ID

# Бренд по умолчанию, если у товара не заполнено поле "Бренд".
DEFAULT_BRAND = "Без бренда"

# Какой тип цены из МойСклад использовать как цену Kaspi (розница).
KASPI_PRICE_TYPE = _env("KASPI_PRICE_TYPE", "Цена продажи")

# Название доп. поля товара с брендом (тег <brand> в фиде).
BRAND_ATTRIBUTE_NAME = "Бренд"

# Бренд по умолчанию для КОМПЛЕКТОВ (если у комплекта нет доп. поля «Бренд»).
KASPI_BUNDLE_BRAND = _env("KASPI_BUNDLE_BRAND", "Arto")

# Куда сохранять сгенерированный XML-файл прайс-листа.
KASPI_FEED_FILE_PATH = _env("KASPI_FEED_FILE_PATH", "kaspi_feed.xml")

# ---------- Доп. поля МойСклад ----------
# Флажок отбора товаров на Kaspi (на справочнике "Товары", тип "Флажок").
REQUIRE_EXPORT_FLAG = True
EXPORT_FLAG_ATTRIBUTE_NAME = "Выгружать в каспи"

# Доп. поле товара с Kaspi-SKU (можно несколько через запятую). Для модификаций
# Kaspi-SKU задаётся стандартным полем «Артикул» (доп. полей у модификаций нет).
KASPI_SKU_ATTRIBUTE_NAME = "Каспи артикулы"

# ---------- Фото товаров ----------
KASPI_IMAGES_DIR = _env("KASPI_IMAGES_DIR", "kaspi_images")

# Публичный адрес папки с фото, БЕЗ слэша на конце. Для GitHub Pages —
# https://<ваш-github-логин>.github.io/<имя-репозитория>/kaspi_images
KASPI_IMAGES_BASE_URL = _env("KASPI_IMAGES_BASE_URL", "https://your-site.kz/kaspi_images")
