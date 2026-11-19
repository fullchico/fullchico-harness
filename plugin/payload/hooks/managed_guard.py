#!/usr/bin/env python3
"""PreToolUse (Edit|Write): a região gerenciada do AGENTS.md só muda por atualização do harness.

Os outros arquivos gerenciados são negados por `permissions.deny`. O AGENTS.md é
meio do projeto, meio do harness, então a edição é aplicada em memória e negada
só se a região entre os marcadores mudar. Erro do hook vira negação.
"""
import json
import os
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

BEGIN = "<!-- harness:begin -->"
END = "<!-- harness:end -->"
DENY = ("A região entre os marcadores harness:begin e harness:end do AGENTS.md é gerenciada. "
        "Ela muda no repositório do harness e chega por .harness/update. "
        "Edite só o que está fora dos marcadores.")
DENY_GIT = ("Agentes não escrevem dentro do diretório do git: é onde ficam a configuração dos "
            "hooks e o estado dos portões de push.")


def region(text: str):
    start = text.find(BEGIN)
    end = text.find(END)
    if start == -1 or end == -1 or end < start:
        return None
    return text[start:end + len(END)]


def result_of(tool: str, tool_input: dict, before: str) -> str:
    if tool == "Write":
        content = tool_input["content"]
        if not isinstance(content, str):
            raise ValueError("content ausente")
        return content
    old, new = tool_input["old_string"], tool_input["new_string"]
    if not isinstance(old, str) or not isinstance(new, str):
        raise ValueError("old_string ou new_string ausente")
    if old not in before:
        return before
    return before.replace(old, new) if tool_input.get("replace_all") else before.replace(old, new, 1)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        common.deny("managed-guard: entrada do hook inválida; edição negada.")
    if not isinstance(payload, dict):
        common.deny("managed-guard: entrada do hook inválida; edição negada.")
    tool = payload.get("tool_name")
    if tool not in ("Edit", "Write"):
        return
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd")
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not isinstance(cwd, str):
        common.deny("managed-guard: caminho ausente na entrada do hook; edição negada.")
    root = common.repo_root(cwd)
    if not root:
        return
    target = os.path.realpath(os.path.join(cwd, file_path))
    for git_dir in common.git_dirs(cwd):
        if target == git_dir or target.startswith(git_dir + os.sep):
            common.deny(DENY_GIT)
    if target != os.path.realpath(os.path.join(root, "AGENTS.md")):
        return
    after = None
    try:
        with open(target, encoding="utf-8") as f:
            before = f.read()
    except OSError:
        return
    try:
        after = result_of(tool, tool_input, before)
    except (KeyError, ValueError):
        common.deny("managed-guard: edição incompleta na entrada do hook; negada.")
    managed = region(before)
    if managed is not None and region(after) != managed:
        common.deny(DENY)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        common.deny(f"managed-guard: erro interno ({exc}); edição negada.")
