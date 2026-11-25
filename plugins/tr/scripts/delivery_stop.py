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
    if not isinstance(message, str) or not any(line.strip() == "DELIVERY: done" for line in message.splitlines()):
        return 0
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    try:
        reg = registry.load(root)
    except registry.RegistryError as error:
        print(json.dumps({"decision": "block", "reason": f"Invalid gate registry: {error}"}, ensure_ascii=False))
        return 0
    if not reg:
        print(json.dumps({"decision": "block", "reason": "Configure the gates before declaring the delivery."}, ensure_ascii=False))
        return 0
    missing = registry.missing(root, "start", reg) + registry.missing(root, "end", reg)
    problems, _ = tasks.audit(root, reg)
    if missing or problems:
        reason = "Delivery not validated yet: " + "; ".join([f"gate {name}" for name in missing] + problems)
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
