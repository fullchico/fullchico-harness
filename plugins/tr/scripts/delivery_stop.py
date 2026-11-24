#!/usr/bin/env python3
"""Confere o portão final quando o modelo anuncia uma entrega concluída."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry  # noqa: E402
import tasks  # noqa: E402


def main():
    payload = json.load(sys.stdin)
    message = payload.get("last_assistant_message") or ""
    if not isinstance(message, str) or not any(line.strip() == "ENTREGA: concluída" for line in message.splitlines()):
        return 0
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    try:
        reg = registry.load(root)
    except registry.RegistryError as error:
        print(json.dumps({"decision": "block", "reason": f"Registro de portões inválido: {error}"}, ensure_ascii=False))
        return 0
    if not reg:
        print(json.dumps({"decision": "block", "reason": "Configure os portões antes de declarar ENTREGA."}, ensure_ascii=False))
        return 0
    missing = registry.missing(root, "inicio", reg) + registry.missing(root, "fim", reg)
    problems, _ = tasks.audit(root, reg)
    if missing or problems:
        reason = "Entrega ainda não validada: " + "; ".join([f"portão {name}" for name in missing] + problems)
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
