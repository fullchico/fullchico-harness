#!/usr/bin/env python3
"""Injeta o mapa no Codex com nomes das skills do próprio Codex."""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(__file__))
import session_context


def main():
    payload = json.load(sys.stdin)
    value = session_context.context(payload.get("cwd") or os.getcwd())
    if value:
        value = value.replace("/tr:memory-map", "$tr-memory-map")
        value = value.replace("/tr:memory-dream", "$tr-memory-dream")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": value}},
                         ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
