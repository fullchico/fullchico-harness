#!/usr/bin/env python3
"""Fronteira entre módulos, por lista branca.

Uso: arch_check.py <raiz do projeto>

Lê MODULE_ROOTS e CONTRACT_PATHS do harness.conf. Cada pasta logo abaixo de uma raiz de
módulos é um módulo. Arquivo de um módulo só importa de dentro do próprio módulo, do que é
comum (CONTRACT_PATHS), de pacotes e da entrada pública (index) de outro módulo. Todo o resto é recusado: importação de tipo, reexportação,
require e import dinâmico contam igual.
"""
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "hooks"))
import common  # noqa: E402

SOURCES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
# ponytail: casa por texto, então um import dentro de comentário também conta. Trocar por
# um analisador da linguagem se isso der falso positivo de verdade.
SPECIFIER = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"']+)["']""")


INSIDE = ('entra por dentro do módulo "{other}" ({specifier}). De outro módulo só se importa a entrada '
          "pública dele (o index); o que ele não exporta ali não é para uso de fora.")


def _is_entry(rest: list) -> bool:
    """O que sobra do caminho depois do nome do módulo: nada, ou o index dele."""
    return not rest or (len(rest) == 1 and rest[0].split(".")[0] == "index")


def _inside(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder + os.sep)


def violations(root: str) -> list:
    conf = common.read_conf(os.path.join(root, "harness.conf"))
    module_roots = [os.path.normpath(os.path.join(root, p)) for p in conf.get("MODULE_ROOTS", "").split()]
    shared = [os.path.normpath(os.path.join(root, p)) for p in conf.get("CONTRACT_PATHS", "").split()]
    found = []
    for modules_dir in module_roots:
        if not os.path.isdir(modules_dir):
            continue
        names = sorted(n for n in os.listdir(modules_dir) if os.path.isdir(os.path.join(modules_dir, n)))
        for name in names:
            own = os.path.join(modules_dir, name)
            others = [n for n in names if n != name]
            for folder, dirs, files in os.walk(own):
                dirs[:] = [d for d in dirs if d != "node_modules"]
                for file in files:
                    if not file.endswith(SOURCES):
                        continue
                    path = os.path.join(folder, file)
                    with open(path, encoding="utf-8", errors="replace") as f:
                        text = f.read()
                    for match in SPECIFIER.finditer(text):
                        reason = _reason(match.group(1), folder, own, modules_dir, others, shared)
                        if reason:
                            line = text.count("\n", 0, match.start()) + 1
                            found.append(f"{os.path.relpath(path, root)}:{line}: {reason}")
    return found


def _reason(specifier, folder, own, modules_dir, others, shared):
    if specifier.startswith("."):
        target = os.path.normpath(os.path.join(folder, specifier))
        if _inside(target, own) or any(_inside(target, s) for s in shared):
            return ""
        if _inside(target, modules_dir):
            parts = os.path.relpath(target, modules_dir).split(os.sep)
            return "" if _is_entry(parts[1:]) else INSIDE.format(other=parts[0], specifier=specifier)
        return f"importa de fora do módulo e fora do que é comum ({specifier}). O que mais de um módulo usa fica num caminho de CONTRACT_PATHS."
    marker = os.path.basename(modules_dir) + "/"
    for other in others:
        head, found, rest = (specifier + "/").partition(marker + other + "/")
        if found and not _is_entry([p for p in rest.split("/") if p]):
            return INSIDE.format(other=other, specifier=specifier)
    return ""


def main() -> int:
    if len(sys.argv) != 2:
        print("uso: arch_check.py <raiz do projeto>", file=sys.stderr)
        return 2
    found = violations(os.path.realpath(sys.argv[1]))
    for line in found:
        print(line, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
