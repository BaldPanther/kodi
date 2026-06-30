#!/usr/bin/env python3
"""
Генератор Kodi-репозитория.

Сканирует папки аддонов (каждая с addon.xml), пакует их в zip,
собирает каталог repo/addons.xml и repo/addons.xml.md5.

Запуск:
    python _repo_generator.py

После запуска: git add -A && git commit -m "..." && git push
GitHub Pages раздаёт папку repo/ — обновление видно ~через минуту.
"""
import os
import hashlib
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "repo")
SKIP_DIRS = {".git", "repo", "__pycache__"}


def find_addons():
    """Папки верхнего уровня, содержащие addon.xml."""
    result = []
    for name in sorted(os.listdir(HERE)):
        path = os.path.join(HERE, name)
        if not os.path.isdir(path) or name in SKIP_DIRS or name.startswith("."):
            continue
        if os.path.isfile(os.path.join(path, "addon.xml")):
            result.append(name)
    return result


def addon_version(addon_id):
    root = ET.parse(os.path.join(HERE, addon_id, "addon.xml")).getroot()
    return root.get("version")


def make_zip(addon_id, version):
    dest_dir = os.path.join(OUT, addon_id)
    os.makedirs(dest_dir, exist_ok=True)
    zip_path = os.path.join(dest_dir, "{}-{}.zip".format(addon_id, version))
    src = os.path.join(HERE, addon_id)
    base = os.path.dirname(src)  # верхняя папка в zip = addon_id
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
            for f in sorted(files):
                if f.endswith(".pyc"):
                    continue
                full = os.path.join(root, f)
                zf.write(full, os.path.relpath(full, base))
    return zip_path


def build_addons_xml(addon_ids):
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "<addons>"]
    for aid in addon_ids:
        with open(os.path.join(HERE, aid, "addon.xml"), "r", encoding="utf-8") as fh:
            text = fh.read()
        start = text.find("<addon")
        parts.append(text[start:].strip())
    parts.append("</addons>")
    return "\n".join(parts) + "\n"


def main():
    addons = find_addons()
    if not addons:
        print("Аддоны не найдены.")
        return
    os.makedirs(OUT, exist_ok=True)
    print("Аддоны:")
    for aid in addons:
        ver = addon_version(aid)
        zp = make_zip(aid, ver)
        print("  {} {} -> {}".format(aid, ver, os.path.relpath(zp, HERE)))

    xml = build_addons_xml(addons)
    xml_path = os.path.join(OUT, "addons.xml")
    # явный LF, чтобы md5 совпадал на любой ОС (см. .gitattributes)
    with open(xml_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(xml)
    md5 = hashlib.md5(xml.encode("utf-8")).hexdigest()
    with open(xml_path + ".md5", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(md5)
    print("addons.xml + addons.xml.md5 ({}) записаны в repo/".format(md5))


if __name__ == "__main__":
    main()
