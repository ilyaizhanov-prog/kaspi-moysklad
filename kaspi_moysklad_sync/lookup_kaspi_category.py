# -*- coding: utf-8 -*-
"""
Вспомогательный CLI для поиска кодов категории и характеристик на Kaspi -
того, что нужно один раз узнать, чтобы заполнить MODIFICATION_FAMILIES в
add_modifications_to_kaspi.py (см. раздел 15 инструкции). Без Postman -
просто запускайте этот скрипт с разными аргументами.

Примеры использования:

  # 1. Найти код своей категории по названию (поиск без учёта регистра)
  python lookup_kaspi_category.py --search кроссовки

  # 2. Посмотреть все характеристики категории (коды, типы, обязательность)
  python lookup_kaspi_category.py --category "Master - Sneakers"

  # 3. Посмотреть допустимые значения конкретной характеристики (для enum)
  python lookup_kaspi_category.py --category "Master - Sneakers" --attribute "Shoes*Colour"

Без аргументов выводит список ВСЕХ категорий (их может быть несколько сотен).
"""
import argparse

import kaspi_client


def cmd_list_categories(search=None):
    categories = kaspi_client.get_categories()
    if search:
        search_lower = search.lower()
        categories = [c for c in categories if search_lower in c.get("title", "").lower()]
    if not categories:
        print("Ничего не найдено. Попробуйте другой поисковый запрос.")
        return
    for c in categories:
        print(f"{c['code']!r:60s} {c.get('title', '')}")


def cmd_list_attributes(category_code):
    attributes = kaspi_client.get_category_attributes(category_code)
    print(f"Характеристики категории {category_code!r}:\n")
    manufacturer_code_candidates = []
    for a in attributes:
        code = a.get("code", "")
        flags = []
        if a.get("mandatory"):
            flags.append("обязательна")
        if a.get("multiValued"):
            flags.append("несколько значений")
        flags_str = f" ({', '.join(flags)})" if flags else ""
        print(f"  {code:60s} тип={a.get('type'):8s}{flags_str}")
        if code.endswith("*Manufacturer code"):
            manufacturer_code_candidates.append(code)

    if manufacturer_code_candidates:
        print("\nДля объединения модификаций в одну карточку используйте manufacturer_code_attr:")
        for code in manufacturer_code_candidates:
            print(f"  {code}")
    else:
        print("\nВНИМАНИЕ: характеристика '*Manufacturer code' не найдена в этой категории.")
        print("Возможно, объединение модификаций для неё работает только через familyId")
        print("(см. q4817) - тогда отдельная характеристика-код не нужна, но объединение")
        print("действует только в рамках одной загрузки, без сохранения между запусками.")


def cmd_list_values(category_code, attribute_code):
    values = kaspi_client.get_attribute_values(category_code, attribute_code)
    print(f"Допустимые значения характеристики {attribute_code!r}:\n")
    for v in values:
        print(f"  code={v.get('code')!r:30s} name={v.get('name')}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--search", help="Найти категории по подстроке в названии")
    parser.add_argument("--category", help="Код категории (атрибут 'code' из списка категорий)")
    parser.add_argument("--attribute", help="Код характеристики (требует --category)")
    args = parser.parse_args()

    if args.category and args.attribute:
        cmd_list_values(args.category, args.attribute)
    elif args.category:
        cmd_list_attributes(args.category)
    else:
        cmd_list_categories(args.search)


if __name__ == "__main__":
    main()
