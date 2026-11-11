"""Резервное копирование папки в zip с ротацией старых архивов."""

import argparse
import hashlib
import json
import os
import time
import zipfile
from pathlib import Path

STATE_FILE = ".backup_state.json"


def file_digest(path, block=65536):
    h = hashlib.md5()
    with open(path, "rb") as stream:
        while chunk := stream.read(block):
            h.update(chunk)
    return h.hexdigest()


def scan(source, ignore):
    result = {}
    for root, dirs, names in os.walk(source):
        dirs[:] = [d for d in dirs if d not in ignore]
        for name in names:
            full = Path(root) / name
            result[str(full.relative_to(source))] = file_digest(full)
    return result


def changed_files(current, previous):
    return [p for p, d in current.items() if previous.get(p) != d]


def make_archive(source, target_dir, files, full):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    kind = "full" if full else "diff"
    target = Path(target_dir) / f"backup-{kind}-{stamp}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel in files:
            archive.write(Path(source) / rel, rel)
    return target


def rotate(target_dir, keep):
    archives = sorted(Path(target_dir).glob("backup-*.zip"), key=lambda p: p.stat().st_mtime)
    removed = []
    while len(archives) > keep:
        old = archives.pop(0)
        old.unlink()
        removed.append(old.name)
    return removed


def run(args):
    source, target = Path(args.source), Path(args.target)
    target.mkdir(parents=True, exist_ok=True)
    state_path = target / STATE_FILE
    previous = json.loads(state_path.read_text()) if state_path.exists() and not args.full else {}
    current = scan(source, set(args.ignore))
    files = list(current) if args.full or not previous else changed_files(current, previous)
    if not files:
        print("Изменений нет, архив не создан")
        return
    archive = make_archive(source, target, files, args.full or not previous)
    state_path.write_text(json.dumps(current, ensure_ascii=False, indent=1))
    print(f"Создан {archive.name}: файлов {len(files)}")
    for name in rotate(target, args.keep):
        print(f"Удалён старый архив {name}")


def parse():
    p = argparse.ArgumentParser(description="Резервное копирование папки")
    p.add_argument("source")
    p.add_argument("target")
    p.add_argument("--keep", type=int, default=10)
    p.add_argument("--full", action="store_true")
    p.add_argument("--ignore", nargs="*", default=[".git", "node_modules", "__pycache__"])
    return p.parse_args()


if __name__ == "__main__":
    run(parse())
