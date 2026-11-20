#!/usr/bin/env python3
"""Fronteira entre módulos, por lista branca.

Uso: arch_check.py <raiz do projeto>

Lê MODULE_ROOTS e CONTRACT_PATHS do harness.conf. Cada pasta logo abaixo de uma raiz de
módulos é um módulo. Arquivo de um módulo só importa de dentro do próprio módulo, do que é
comum (CONTRACT_PATHS) e de pacotes. Todo o resto é recusado: importação de tipo, reexportação,
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
            other = os.path.relpath(target, modules_dir).split(os.sep)[0]
            return f'importa do módulo "{other}" ({specifier}). Um módulo fala com outro pela porta definida no contrato.'
        return f"importa de fora do módulo e fora do que é comum ({specifier}). O que mais de um módulo usa fica num caminho de CONTRACT_PATHS."
    marker = os.path.basename(modules_dir) + "/"
    for other in others:
        if (marker + other + "/") in specifier + "/":
            return f'importa do módulo "{other}" ({specifier}). Um módulo fala com outro pela porta definida no contrato.'
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
