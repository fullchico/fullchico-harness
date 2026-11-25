#!/usr/bin/env python3
"""Adaptador dos hooks do Codex para os portões compartilhados com Claude Code."""
import io
import json
import os
import re
import sys
from contextlib import redirect_stdout

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(__file__))
import gate
import sign
import orchestrator_stop

AGENTS = {"tr-qualidade-verificador": "tr:qualidade-verificador",
          "tr-bugs-cacador": "tr:bugs-cacador"}
LAST_EVENT = None


def patch_paths(command):
    return re.findall(r"(?m)^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", command)


def invoke(module, payload):
    old = sys.stdin
    output = io.StringIO()
    try:
        sys.stdin = io.StringIO(json.dumps(payload))
        with redirect_stdout(output):
            module.main()
    finally:
        sys.stdin = old
    value = output.getvalue().strip()
    return json.loads(value) if value else None


def normalize(payload):
    data = dict(payload)
    tool = data.get("tool_name")
    ti = data.get("tool_input") or {}
    if tool == "apply_patch":
        data["tool_name"] = "Edit"
    elif tool in ("spawn_agent", "collaboration.spawn_agent"):
        data["tool_name"] = "Agent"
        kind = ti.get("agent_type") or ti.get("task_name")
        data["tool_input"] = {"subagent_type": AGENTS.get(kind, kind),
                              "prompt": ti.get("message", "")}
    if data.get("agent_type") in AGENTS:
        data["agent_type"] = AGENTS[data["agent_type"]]
    if data.get("hook_event_name") == "PostToolUse":
        command = ti.get("command", "")
        match = re.fullmatch(r"python3 -I \.codex/harness/tr/scripts/portao\.py ([\w.-]+)(?: --ticket ([^\s]+))?", command.strip())
        if match:
            data["tool_input"] = {"command": "portao " + match.group(1) +
                                  (" --ticket " + match.group(2) if match.group(2) else "")}
        response = data.get("tool_response")
        if isinstance(response, dict):
            data["tool_response"] = {"stdout": response.get("stdout") or response.get("output") or ""}
    return data


def main():
    global LAST_EVENT
    payload = json.load(sys.stdin)
    LAST_EVENT = payload.get("hook_event_name")
    data = normalize(payload)
    event = data.get("hook_event_name")
    if event == "PreToolUse":
        if payload.get("tool_name") == "apply_patch":
            for path in patch_paths((payload.get("tool_input") or {}).get("command", "")):
                one = dict(data, tool_input={"file_path": path})
                result = invoke(gate, one)
                if result and result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny":
                    print(json.dumps(result, ensure_ascii=False))
                    return
        elif data.get("tool_name") == "Agent":
            result = invoke(gate, data)
            if result:
                spec = result.get("hookSpecificOutput", {})
                if spec.get("updatedInput"):
                    updated = dict(payload.get("tool_input") or {})
                    updated["message"] = spec["updatedInput"].get("prompt", updated.get("message"))
                    spec["updatedInput"] = updated
                print(json.dumps(result, ensure_ascii=False))
            return
        else:
            result = invoke(gate, data)
            if result:
                print(json.dumps(result, ensure_ascii=False))
    elif event in ("PostToolUse", "SubagentStop"):
        if event == "PostToolUse" and data.get("tool_name") != "Bash":
            return
        result = invoke(sign, data)
        if result:
            print(json.dumps(result, ensure_ascii=False))
        elif event == "SubagentStop":
            continuation = invoke(orchestrator_stop, data)
            print(json.dumps(continuation or {}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if LAST_EVENT == "PreToolUse":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": f"Hook do trilho falhou: {error}"}}, ensure_ascii=False))
        elif LAST_EVENT == "SubagentStop":
            print("{}")
