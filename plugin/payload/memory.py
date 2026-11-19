#!/usr/bin/env python3
"""Memória derivada do projeto, ancorada em git.

Cada item guarda o commit em que foi escrito e os caminhos que descreve. Saber se
envelheceu é uma pergunta ao git, sem IA: o commit ainda existe, e os caminhos
estão iguais desde então? Quem escreve o conteúdo (o resumo de um módulo) é um
subagente, conduzido pela skill `mapear`; este script só guarda e confere.

Uso: memory.py <raiz> <comando> [argumentos]
"""
import json
import os
import subprocess
import sys
import urllib.parse

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hooks"))
import common  # noqa: E402

SUMMARY_LIMIT = 1500
DEFAULT_EXCLUDE = "docs .harness .claude .github"
STALE = " (envelhecido: o código mudou desde o resumo)"


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def _conf(root):
    return common.read_conf(os.path.join(root, "harness.conf"))


def _store(root):
    folder = common.memory_dir(root)
    if not folder:
        raise ValueError("fora de um repositório git")
    return folder


def _load(root, name):
    try:
        with open(os.path.join(_store(root), name), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(root, name, data):
    folder = _store(root)
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, os.path.join(folder, name))


def _summary_path(root, unit):
    return os.path.join(_store(root), "map", urllib.parse.quote(unit, safe="") + ".md")


def units(root) -> list:
    conf = _conf(root)
    try:
        depth = max(1, int(conf.get("MAP_DEPTH", "2")))
    except ValueError:
        depth = 2
    excluded = set(conf.get("MAP_EXCLUDE", DEFAULT_EXCLUDE).split())
    found = {"."}
    for path in _git(root, "ls-files", "-z").stdout.split("\0"):
        folders = path.split("/")[:-1]
        if folders and folders[0] not in excluded:
            found.add("/".join(folders[:depth]))
    return sorted(found)


def _pathspec(unit):
    # A unidade "." são só os arquivos soltos na raiz.
    return [":(glob)*"] if unit == "." else [unit]


def changed_since(root, commit, paths) -> bool:
    """O commit sumiu, ou algum dos caminhos está diferente dele (inclusive sem commit)?"""
    if not commit or _git(root, "cat-file", "-e", commit + "^{commit}").returncode != 0:
        return True
    return _git(root, "diff", "--quiet", commit, "--", *paths).returncode != 0


def status(root) -> dict:
    recorded = _load(root, "map.json").get("units", {})
    current = units(root)
    result = {"fresh": [], "stale": [], "missing": [], "orphan": sorted(u for u in recorded if u not in current)}
    for unit in current:
        if unit not in recorded or not os.path.exists(_summary_path(root, unit)):
            result["missing"].append(unit)
        elif changed_since(root, recorded[unit].get("commit"), _pathspec(unit)):
            result["stale"].append(unit)
        else:
            result["fresh"].append(unit)
    return result


def record(root, unit, text) -> None:
    if unit not in units(root):
        raise ValueError(f"`{unit}` não é uma unidade do mapa. Veja `memory units`.")
    text = (text or "").strip()
    if not text:
        raise ValueError("o resumo está vazio")
    if len(text) > SUMMARY_LIMIT:
        raise ValueError(f"o resumo tem {len(text)} caracteres; o limite é {SUMMARY_LIMIT}")
    commit = common.head_sha(root)
    if not commit:
        raise ValueError("o repositório ainda não tem commit")
    path = _summary_path(root, unit)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(text + "\n")
    os.replace(path + ".tmp", path)
    data = _load(root, "map.json")
    data.setdefault("units", {})[unit] = {"commit": commit}
    _save(root, "map.json", data)


def forget(root, unit) -> None:
    data = _load(root, "map.json")
    data.get("units", {}).pop(unit, None)
    _save(root, "map.json", data)
    try:
        os.remove(_summary_path(root, unit))
    except OSError:
        pass


def summary(root, unit):
    try:
        with open(_summary_path(root, unit), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def _unit_of(path, known):
    path = os.path.normpath(path).replace(os.sep, "/")
    if path.startswith("../") or os.path.isabs(path):
        return []
    path = "" if path == "." else path
    hits = [u for u in known if u != "." and (path == u or path.startswith(u + "/") or u.startswith(path + "/"))]
    if hits:
        return hits
    return ["."] if "/" not in path else []


def slice_for(root, paths) -> str:
    state = status(root)
    known = units(root)
    wanted = []
    for path in paths:
        for unit in _unit_of(path, known):
            if unit not in wanted:
                wanted.append(unit)
    parts = []
    for unit in wanted:
        text = summary(root, unit)
        if text is None:
            parts.append(f"## {unit}\n(sem resumo: rode /harness:mapear)")
        else:
            parts.append(f"## {unit}{STALE if unit in state['stale'] else ''}\n{text}")
    return "\n\n".join(parts)


def index(root) -> str:
    state = status(root)
    lines = []
    for unit in state["fresh"] + state["stale"]:
        first = (summary(root, unit) or "").splitlines()[0:1]
        lines.append((unit, f"{unit}: {first[0] if first else ''}{' (envelhecido)' if unit in state['stale'] else ''}"))
    return "\n".join(line for _, line in sorted(lines))


def _print_check(root) -> int:
    state = status(root)
    labels = (("stale", "envelhecido, o código mudou"), ("missing", "sem resumo"),
              ("orphan", "a unidade não existe mais"))
    dirty = False
    for key, label in labels:
        for unit in state[key]:
            print(f"mapa: {unit}: {label}")
            dirty = True
    print(f"mapa: {len(state['fresh'])} em dia, {len(state['stale'])} envelhecidos, "
          f"{len(state['missing'])} sem resumo, {len(state['orphan'])} órfãos")
    return 1 if dirty else 0


def main(argv) -> int:
    if len(argv) < 2:
        sys.stderr.write("uso: memory <units|check|record|show|slice|index|forget> ...\n")
        return 2
    root, command, args = argv[0], argv[1], [a for a in argv[2:] if a != "--"]
    try:
        if command == "units":
            print("\n".join(units(root)))
        elif command == "check":
            return _print_check(root)
        elif command == "record" and len(args) == 2:
            with open(args[1], encoding="utf-8") as f:
                record(root, args[0], f.read())
            print(f"mapa: {args[0]} gravado")
        elif command == "show" and len(args) == 1:
            print(summary(root, args[0]) or "(sem resumo)")
        elif command == "slice" and args:
            print(slice_for(root, args))
        elif command == "index":
            print(index(root))
        elif command == "forget" and len(args) == 1:
            forget(root, args[0])
        else:
            sys.stderr.write("uso: memory <units|check|record|show|slice|index|forget> ...\n")
            return 2
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"memory: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
