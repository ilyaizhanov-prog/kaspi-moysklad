# -*- coding: utf-8 -*-
"""
Получение новых заказов из Kaspi Магазина и создание "Заказов покупателей"
в МойСклад.

Запускайте по расписанию (cron / планировщик), например каждые 5-15 минут.

Что делает скрипт:
1. Запрашивает в Kaspi заказы со статусом NEW (новые, не принятые продавцом).
2. Для каждого заказа получает состав (товарные позиции).
3. Находит соответствующие товары в МойСклад по артикулу (SKU из Kaspi).
4. Создаёт документ "Заказ покупателя" в МойСклад (с externalCode = код
   заказа Kaspi, чтобы не создать дубликат при повторном запуске).
5. Принимает заказ в Kaspi (переводит в статус ACCEPTED_BY_MERCHANT).
"""
import config
import kaspi_client
import moysklad_client


def resolve_agent(customer):
    """Находит или создаёт контрагента в МойСклад для покупателя Kaspi."""
    if config.MOYSKLAD_DEFAULT_AGENT_ID:
        return {
            "href": f"{config.MOYSKLAD_API_URL}/entity/counterparty/{config.MOYSKLAD_DEFAULT_AGENT_ID}",
            "type": "counterparty",
            "mediaType": "application/json",
        }

    phone = customer.get("cellPhone", "")
    existing = moysklad_client.find_counterparty_by_phone(phone) if phone else None
    if existing:
        return existing["meta"]

    created = moysklad_client.create_counterparty(
        first_name=customer.get("firstName", ""),
        last_name=customer.get("lastName", ""),
        phone=phone,
    )
    return created["meta"]


def build_positions(entries_response):
    positions = []
    not_found = []
    for entry in entries_response.get("data", []):
        attrs = entry.get("attributes", {})
        sku = attrs.get("article") or attrs.get("code") or attrs.get("sku")
        quantity = attrs.get("quantity", 1)
        unit_price = attrs.get("unitPrice") or attrs.get("basePrice") or 0

        product = moysklad_client.find_product_by_article(sku) if sku else None
        if not product:
            not_found.append(sku or "<нет SKU>")
            continue

        positions.append({
            "quantity": quantity,
            "price": round(unit_price * 100),  # тенге -> копейки/тиыны
            "assortment_meta": product["meta"],
        })
    return positions, not_found


def process_order(order):
    order_id = order["id"]
    attrs = order["attributes"]
    code = attrs["code"]
    external_code = f"kaspi-{code}"

    existing = moysklad_client.find_customerorder_by_external_code(external_code)
    if existing:
        print(f"Заказ {code} уже создан в МойСклад, пропускаю.")
    else:
        entries = kaspi_client.get_order_entries(order_id)
        positions, not_found = build_positions(entries)
        if not_found:
            print(f"  ВНИМАНИЕ: не найдены в МойСклад товары с артикулами: {not_found}")
        if not positions:
            print(f"  Пропускаю заказ {code}: ни одна позиция не сопоставлена с МойСклад.")
            return

        customer = order.get("customer", {})
        agent_meta = resolve_agent(customer)
        store_meta = moysklad_client.store_meta_by_id(config.MOYSKLAD_DEFAULT_STORE_ID)

        moysklad_client.create_customer_order(
            external_code=external_code,
            agent_meta=agent_meta,
            store_meta=store_meta,
            positions=positions,
            description=f"Заказ Kaspi.kz №{code}",
        )
        print(f"  Создан заказ покупателя в МойСклад для Kaspi-заказа {code}")

    kaspi_client.accept_order(order_id, code)
    print(f"  Заказ {code} принят в Kaspi (ACCEPTED_BY_MERCHANT)")


def main():
    print("Запрашиваю новые заказы из Kaspi...")
    response = kaspi_client.get_new_orders()
    orders = response.get("data", [])
    print(f"Новых заказов: {len(orders)}")

    for order in orders:
        order_id = order["id"]
        attrs = order["attributes"]
        print(f"Обрабатываю заказ {attrs.get('code')} (id={order_id})")
        try:
            process_order({"id": order_id, "attributes": attrs})
        except Exception as exc:
            print(f"  ОШИБКА при обработке заказа {attrs.get('code')}: {exc}")


if __name__ == "__main__":
    main()
