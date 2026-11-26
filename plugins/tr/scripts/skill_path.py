#!/usr/bin/env python3
"""`tr-harness skill <nome>`: o SKILL.md instalado de uma skill da comunidade, para seguir o texto dela.

Algumas skills maduras não deixam o modelo chamá-las (`disable-model-invocation`); o tr lê o arquivo instalado
e segue o processo dela, sem cópia. Procura no projeto (`.agents/skills`, `.claude/skills`) e no cache de
plugins do Claude; a versão mais nova ganha."""
import glob
import os
import re
import sys


def find(name, root="."):
    home = os.path.expanduser("~")
    patterns = [os.path.join(root, ".agents", "skills", name, "SKILL.md"),
                os.path.join(root, ".claude", "skills", name, "SKILL.md"),
                os.path.join(home, ".claude", "plugins", "cache", "*", "*", "*", "skills", "**", name, "SKILL.md"),
                os.path.join(home, ".claude", "skills", name, "SKILL.md")]
    for pattern in patterns:
        found = glob.glob(pattern, recursive=True)
        if found:
            version = lambda p: [int(n) for n in re.findall(r"/(\d+(?:\.\d+)+)/", p)[-1:][0].split(".")] \
                if re.findall(r"/(\d+(?:\.\d+)+)/", p) else []
            return sorted(found, key=version)[-1]
    return None


def main(argv):
    if len(argv) != 1 or not re.fullmatch(r"[\w-]+", argv[0]):
        print("uso: tr-harness skill <nome>", file=sys.stderr)
        return 2
    path = find(argv[0])
    if not path:
        print(f"skill `{argv[0]}` não instalada; o dono roda `npx @fullchico/harness install`", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
