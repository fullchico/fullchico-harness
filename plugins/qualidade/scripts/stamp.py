#!/usr/bin/env python3
"""Assina o carimbo `qualidade` depois que `qualidade-check` terminou bem numa árvore limpa.

Roda em `PostToolUse` de Bash (só dispara quando o comando terminou bem). Nunca quebra a sessão.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402

PASSED = "qualidade: passou"


def version():
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude-plugin", "plugin.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)["version"]
    except (OSError, ValueError, KeyError):
        return "desconhecida"


def output_text(response):
    """O texto de saída do comando em `tool_response`, ou None se o formato não for reconhecido.

    Para o Bash o campo é `stdout` (e `stderr`); aceita também a resposta como texto puro.
    """
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        parts = [response[k] for k in ("stdout", "output", "content") if isinstance(response.get(k), str)]
        return "\n".join(parts) if parts else None
    return None


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash" or payload.get("hook_event_name") != "PostToolUse":
        return 0
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or command.strip() != "qualidade-check":
        return 0
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    text = output_text(payload.get("tool_response"))
    # ponytail: se a saída não vier no formato conhecido, vale só o evento de sucesso
    if text is not None:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines or lines[-1] != PASSED:
            ledger.log(cwd, "qualidade", "não assinou", "a saída não termina em 'qualidade: passou'")
            return 0
    commit = ledger.head(cwd)
    if not commit:
        return 0
    status = subprocess.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True)
    if status.returncode != 0 or status.stdout.strip():
        ledger.log(cwd, "qualidade", "não assinou", f"árvore suja em {commit[:10]}: o carimbo mentiria sobre o commit")
        print("qualidade: a árvore tem alterações sem commit, então não carimbei: "
              "faça o commit antes de rodar qualidade-check.", file=sys.stderr)
        return 2
    ledger.sign(cwd, "qualidade", commit, "qualidade", version(), "qualidade-check", "qualidade-check passou")
    ledger.log(cwd, "qualidade", "assinou", commit[:10])
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # um hook de carimbo nunca derruba a sessão
        code = 0
    sys.exit(code)
