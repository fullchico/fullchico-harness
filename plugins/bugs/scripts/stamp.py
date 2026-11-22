#!/usr/bin/env python3
"""Assina o carimbo `bugs` quando o caçador aprova o commit do topo.

Roda em `SubagentStop` e em `PreToolUse` de `SubagentHandback`: o relatório final do subagente pode
sair por um ou por outro, então o carimbo é ligado nos dois. Nunca bloqueia e nunca quebra.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402

AGENT = "bugs:cacador"


def version():
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude-plugin", "plugin.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)["version"]
    except (OSError, ValueError, KeyError):
        return "desconhecida"


def once(pattern, text):
    """O valor da linha que casa com `pattern`, só se houver exatamente uma."""
    found = re.findall(pattern, text, re.M)
    return found[0] if len(found) == 1 else None


def main():
    payload = json.load(sys.stdin)
    if payload.get("agent_type") != AGENT:
        return
    event = payload.get("hook_event_name")
    if event == "PreToolUse":
        if payload.get("tool_name") != "SubagentHandback":
            return
        text = (payload.get("tool_input") or {}).get("message")
    else:
        text = payload.get("last_assistant_message")
    if not isinstance(text, str):
        return
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    verdict = once(r"^[ \t]*VEREDITO: (APPROVED|REJECTED)[ \t]*$", text)
    commit = once(r"^[ \t]*COMMIT: ([0-9a-f]{40})[ \t]*$", text)
    summary = once(r"^[ \t]*RESUMO: (\S.*?)[ \t]*$", text)
    if not (verdict and commit and summary):
        # No SubagentStop vem só o fecho: se o relatório já assinou o topo na entrega, não é falha.
        if event == "SubagentStop" and ledger.has(cwd, "bugs", ledger.head(cwd) or ""):
            return
        ledger.log(cwd, "bugs", "não assinou", "bloco de três linhas ausente ou ambíguo")
        return
    top = ledger.head(cwd)
    if commit != top:
        ledger.log(cwd, "bugs", "não assinou", f"o commit {commit[:10]} não é o topo ({(top or '?')[:10]})")
        return
    if verdict == "APPROVED":
        ledger.sign(cwd, "bugs", commit, "bugs", version(), AGENT, summary)
        ledger.log(cwd, "bugs", "assinou", f"{commit[:10]}: {summary}")
    else:
        ledger.forget(cwd, "bugs", commit)
        ledger.log(cwd, "bugs", "reprovou", f"{commit[:10]}: {summary}")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # um hook de carimbo nunca derruba a sessão
        pass
    sys.exit(0)
