#!/usr/bin/env python3
"""Adapta SubagentStop do Codex ao registro de candidatos da memória."""
import io
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(__file__))
import candidates


def main():
    data = json.load(sys.stdin)
    if data.get("agent_type") == "memoria-extrator":
        data["agent_type"] = candidates.AGENT
    old = sys.stdin
    try:
        sys.stdin = io.StringIO(json.dumps(data))
        candidates.main()
    finally:
        sys.stdin = old
    print("{}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("{}")
