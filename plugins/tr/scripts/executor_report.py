#!/usr/bin/env python3
"""SubagentStop: grava no quadro o `DONE:`/`BLOCKED:` do executor e o tira da lista de ativos."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry  # noqa: E402
import tasks  # noqa: E402


def main():
    payload = json.load(sys.stdin)
    if not payload.get("agent_id"):
        return
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    tasks.report(root, payload["agent_id"], payload.get("last_assistant_message") or "")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
