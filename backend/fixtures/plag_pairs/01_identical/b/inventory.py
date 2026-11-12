"""Учёт остатков на складе: читает приход и расход из CSV и печатает отчёт."""

import csv
import sys
from collections import defaultdict
from datetime import date


class Warehouse:
    def __init__(self, name):
        self.name = name
        self.stock = defaultdict(int)
        self.history = []

    def receive(self, sku, quantity, day):
        if quantity <= 0:
            raise ValueError("Количество прихода должно быть положительным")
        self.stock[sku] += quantity
        self.history.append((day, sku, quantity))

    def ship(self, sku, quantity, day):
        available = self.stock.get(sku, 0)
        if quantity > available:
            raise ValueError(f"Недостаточно товара {sku}: есть {available}, нужно {quantity}")
        self.stock[sku] = available - quantity
        self.history.append((day, sku, -quantity))

    def low_stock(self, threshold):
        return sorted(sku for sku, qty in self.stock.items() if qty < threshold)

    def turnover(self, sku):
        incoming = sum(q for _, s, q in self.history if s == sku and q > 0)
        outgoing = -sum(q for _, s, q in self.history if s == sku and q < 0)
        if incoming == 0:
            return 0.0
        return round(outgoing / incoming, 2)


def load_operations(path):
    operations = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            day = date.fromisoformat(row["date"])
            operations.append((day, row["type"], row["sku"], int(row["qty"])))
    operations.sort(key=lambda item: item[0])
    return operations


def apply_operations(warehouse, operations):
    errors = []
    for day, kind, sku, qty in operations:
        try:
            if kind == "in":
                warehouse.receive(sku, qty, day)
            elif kind == "out":
                warehouse.ship(sku, qty, day)
            else:
                errors.append(f"{day}: неизвестная операция {kind}")
        except ValueError as exc:
            errors.append(f"{day}: {exc}")
    return errors


def print_report(warehouse, threshold=5):
    print(f"Склад: {warehouse.name}")
    print("-" * 40)
    for sku in sorted(warehouse.stock):
        qty = warehouse.stock[sku]
        mark = " (мало)" if qty < threshold else ""
        print(f"{sku:<15}{qty:>8}  оборот {warehouse.turnover(sku):.2f}{mark}")
    low = warehouse.low_stock(threshold)
    if low:
        print("\nНужно заказать: " + ", ".join(low))


def main(argv):
    if len(argv) < 2:
        print("Использование: python inventory.py operations.csv [порог]")
        return 1
    threshold = int(argv[2]) if len(argv) > 2 else 5
    warehouse = Warehouse("Основной")
    errors = apply_operations(warehouse, load_operations(argv[1]))
    print_report(warehouse, threshold)
    for line in errors:
        print("Ошибка:", line, file=sys.stderr)
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
