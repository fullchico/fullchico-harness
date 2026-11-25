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
import guard
import sign
import orchestrator_stop
import write_watch

AGENTS = {"tr-quality-checker": "tr:quality-checker",
          "tr-bug-hunter": "tr:bug-hunter",
          "tr-scope-checker": "tr:scope-checker"}
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


def opaque(message):
    """O Codex 0.171 entrega a mensagem do `spawn_agent` cifrada: sem texto, não há fronteira nem
    pedido canônico a conferir, e reescrever quebraria o disparo. O disparo segue sem conferência."""
    return isinstance(message, str) and message.startswith("gAAAA") and " " not in message


def heartbeat():
    """Sinal de que os hooks rodam: o `models run` recusa a execução Codex que não o deixou."""
    folder = os.environ.get("FULLCHICO_RUN_DIR")
    if folder and os.path.isdir(folder):
        open(os.path.join(folder, "hooks-alive"), "a").close()


def normalize(payload):
    data = dict(payload, harness_client="codex")
    tool = data.get("tool_name")
    ti = data.get("tool_input") or {}
    if tool == "apply_patch":
        data["tool_name"] = "Edit"
    elif tool in ("spawn_agent", "collaboration.spawn_agent", "collaborationspawn_agent") and not opaque(ti.get("message")):
        data["tool_name"] = "Agent"
        kind = ti.get("agent_type") or ti.get("task_name")
        data["tool_input"] = {"subagent_type": AGENTS.get(kind, kind),
                              "prompt": ti.get("message", "")}
    if data.get("agent_type") in AGENTS:
        data["agent_type"] = AGENTS[data["agent_type"]]
    if data.get("hook_event_name") == "PostToolUse":
        command = ti.get("command", "")
        match = re.fullmatch(r"python3 -I \.codex/harness/tr/scripts/gate_cli\.py ([\w.-]+)(?: --ticket ([^\s]+))?", command.strip())
        if match:
            data["tool_input"] = {"command": "gate " + match.group(1) +
                                  (" --ticket " + match.group(2) if match.group(2) else "")}
        response = data.get("tool_response")
        if isinstance(response, dict):
            data["tool_response"] = {"stdout": response.get("stdout") or response.get("output") or ""}
    return data


def main():
    global LAST_EVENT
    payload = json.load(sys.stdin)
    LAST_EVENT = payload.get("hook_event_name")
    heartbeat()
    data = normalize(payload)
    event = data.get("hook_event_name")
    if event == "PreToolUse":
        if payload.get("tool_name") == "apply_patch":
            for path in patch_paths((payload.get("tool_input") or {}).get("command", "")):
                one = dict(data, tool_input={"file_path": path})
                result = invoke(guard, one)
                if result and result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny":
                    print(json.dumps(result, ensure_ascii=False))
                    return
        elif data.get("tool_name") == "Agent":
            result = invoke(guard, data)
            if result:
                spec = result.get("hookSpecificOutput", {})
                if spec.get("updatedInput"):
                    updated = dict(payload.get("tool_input") or {})
                    updated["message"] = spec["updatedInput"].get("prompt", updated.get("message"))
                    spec["updatedInput"] = updated
                print(json.dumps(result, ensure_ascii=False))
            return
        else:
            result = invoke(guard, data)
            if result:
                print(json.dumps(result, ensure_ascii=False))
    elif event in ("PostToolUse", "SubagentStop"):
        if event == "PostToolUse" and data.get("tool_name") != "Bash":
            return
        result = invoke(sign, data)
        if event == "PostToolUse" and not result:
            result = invoke(write_watch, data)
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
