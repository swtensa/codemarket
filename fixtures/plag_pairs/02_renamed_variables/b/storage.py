# Программа складского учёта

import csv
import sys
from collections import defaultdict
from datetime import date


class Storage:
    def __init__(self, title):
        self.title = title
        self.balance = defaultdict(int)
        self.journal = []

    def put_in(self, code, amount, when):
        if amount <= 0:
            raise ValueError("Неверное количество")
        self.balance[code] += amount
        self.journal.append((when, code, amount))

    def take_out(self, code, amount, when):
        have = self.balance.get(code, 0)
        if amount > have:
            raise ValueError(f"Недостаточно товара {code}: есть {have}, нужно {amount}")
        self.balance[code] = have - amount
        self.journal.append((when, code, -amount))

    def shortage(self, limit):
        return sorted(code for code, count in self.balance.items() if count < limit)

    def rotation(self, code):
        plus = sum(q for _, s, q in self.journal if s == code and q > 0)
        minus = -sum(q for _, s, q in self.journal if s == code and q < 0)
        if plus == 0:
            return 0.0
        return round(minus / plus, 2)


def read_moves(filename):
    moves = []
    with open(filename, encoding="utf-8") as f:
        for record in csv.DictReader(f, delimiter=";"):
            when = date.fromisoformat(record["date"])
            moves.append((when, record["type"], record["code"], int(record["count"])))
    moves.sort(key=lambda entry: entry[0])
    return moves


def process_moves(store, moves):
    problems = []
    for when, direction, code, count in moves:
        try:
            if direction == "in":
                store.put_in(code, count, when)
            elif direction == "out":
                store.take_out(code, count, when)
            else:
                problems.append(f"{when}: неизвестная операция {direction}")
        except ValueError as err:
            problems.append(f"{when}: {err}")
    return problems


def show_summary(store, limit=5):
    print(f"Склад: {store.title}")
    print("-" * 40)
    for code in sorted(store.balance):
        count = store.balance[code]
        suffix = " (мало)" if count < limit else ""
        print(f"{code:<15}{count:>8}  оборот {store.rotation(code):.2f}{suffix}")
    missing = store.shortage(limit)
    if missing:
        print("\nДозаказать: " + ", ".join(missing))


def main(args):
    if len(args) < 2:
        print("Использование: python inventory.py moves.csv [порог]")
        return 1
    limit = int(args[2]) if len(args) > 2 else 5
    store = Storage("Основной")
    problems = process_moves(store, read_moves(args[1]))
    show_summary(store, limit)
    for line in problems:
        print("Ошибка:", line, file=sys.stderr)
    return 0 if not problems else 2


if __name__ == "__main__":
    sys.exit(main(sys.args))
