#!/usr/bin/env python3
"""Confere os arquivos gerenciados contra .harness/MANIFEST.

Uso: manifest_check.py [raiz do projeto]
Sai 0 se tudo bate; sai 1 e lista, um por linha, o que foi alterado ou sumiu.
"""
import hashlib
import json
import os
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hooks"))
from managed_guard import region  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def drift(root: str):
    with open(os.path.join(root, ".harness", "MANIFEST"), encoding="utf-8") as f:
        manifest = json.load(f)
    changed = []
    for rel, expected in sorted(manifest.get("files", {}).items()):
        try:
            with open(os.path.join(root, rel), "rb") as f:
                if sha256(f.read()) != expected:
                    changed.append(rel)
        except OSError:
            changed.append(rel)
    for rel, expected in sorted(manifest.get("regions", {}).items()):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                managed = region(f.read())
        except OSError:
            managed = None
        if managed is None or sha256(managed.encode("utf-8")) != expected:
            changed.append(rel)
    return changed


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(HERE)
    try:
        changed = drift(root)
    except (OSError, ValueError) as exc:
        print(f".harness/MANIFEST ilegível: {exc}")
        return 1
    for rel in changed:
        print(rel)
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
