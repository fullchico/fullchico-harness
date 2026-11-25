#!/usr/bin/env python3
"""PostToolUse do Agent: o executor voltou, o ticket dele fica livre para outro disparo."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry  # noqa: E402
import tasks  # noqa: E402


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") not in ("Agent", "Task"):
        return
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    tasks.finish_executor(root, (payload.get("tool_input") or {}).get("prompt"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
