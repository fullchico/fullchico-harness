#!/usr/bin/env python3
"""Vaga de executor por ticket.

- `PostToolUse`, `PostToolUseFailure` e `PermissionDenied` do Agent: o executor voltou, ou o disparo não chegou
  a rodar; o ticket fica livre para outro disparo.
- `SubagentStart`: um subagente abriu; o disparo pendente mais antigo deixa de expirar em minutos.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry  # noqa: E402
import tasks  # noqa: E402


def main():
    payload = json.load(sys.stdin)
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if payload.get("hook_event_name") == "SubagentStart":
        kind = payload.get("agent_type") or ""
        if kind not in tasks.READ_ONLY_AGENTS and kind not in registry.ORCHESTRATORS \
                and kind not in registry.validators(registry.load(root)):
            tasks.executor_opened(root)
        return
    if payload.get("tool_name") not in ("Agent", "Task"):
        return
    tasks.finish_executor(root, (payload.get("tool_input") or {}).get("prompt"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
