#!/usr/bin/env python3
"""SessionStart: o projeto que se declara puro foi aberto no modo puro?

Lê a linha de comando do processo que iniciou a sessão (o `claude`) e confere as opções que o
lançador do harness liga. Se faltam, avisa o dono e o agente: o global do usuário entrou na
sessão, e o projeto não garante mais o que ela usa. Avisa, não impede. Nunca quebra a sessão.
"""
import json
import os
import subprocess
import sys

WARNING = ("Este projeto se declara puro (.claude/puro), mas a sessão foi aberta sem o lançador "
           "`claude --setting-sources project,local --strict-mcp-config`: plugins, hooks, skills e instruções do escopo global do usuário entraram nela. "
           "Feche e abra de novo com essas opções; se usar .claude/mcp.json, acrescente `--mcp-config .claude/mcp.json`.")


def parent_args() -> str:
    given = os.environ.get("TRILHO_PARENT_ARGS")
    if given is not None:
        return given
    out = subprocess.run(["ps", "-o", "args=", "-p", str(os.getppid())], capture_output=True, text=True, timeout=5)
    return out.stdout


def is_pure(args: str) -> bool:
    """As fontes de configuração não incluem a do usuário, e os MCP de fora estão cortados."""
    words = args.replace("=", " ").split()
    if "--strict-mcp-config" not in words or "--setting-sources" not in words:
        return False
    index = words.index("--setting-sources")
    sources = words[index + 1].split(",") if index + 1 < len(words) else []
    return "user" not in sources and "project" in sources


def main() -> None:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or ""
    if not root or not os.path.isfile(os.path.join(root, ".claude", "puro")):
        return
    if is_pure(parent_args()):
        return
    print(json.dumps({"systemMessage": WARNING,
                      "hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": "Aviso do harness: " + WARNING}},
                     ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
