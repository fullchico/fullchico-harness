#!/usr/bin/env python3
"""SessionStart: diz à sessão em que ponto do fluxo o projeto está, antes de qualquer pedido.

Sem isso, um pedido livre cai no processo de outro plugin (o brainstorming de um plugin global, por
exemplo) e a entrevista do tr nunca acontece. Só informa; quem barra é o guard.py. Nunca quebra a sessão.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry  # noqa: E402
import tasks  # noqa: E402

RULE = ("Other skills (brainstorming, TDD, review) are tools inside this flow, not a replacement for it.")


def context(root, source=None):
    try:
        reg = registry.load(root)
    except registry.RegistryError as error:
        return f"FullChico harness: the gate registry is invalid ({error}). Ask the owner to fix it before any work."
    if not reg:
        return ("FullChico harness is installed in this project, but its gates are not configured yet. Before "
                "planning or writing any code, run /tr:configure (diagnosis, grilling interview (Matt Pocock), proposed gates "
                "that the owner writes in the terminal). Code writes are blocked until then. " + RULE)
    open_tickets = tasks.open_tickets(root)
    released = tasks.release_if_idle(root) if source in ("startup", "resume") else []
    if open_tickets and released:
        names = ", ".join(os.path.basename(r) for r in released)
        return (f"FullChico harness: the delivery stopped mid-way ({len(open_tickets)} open tickets; nothing has run for "
                f"10 min, so {names} were released). Resume it: dispatch the tr:orchestrator in the background to "
                "continue from the board (`tr-harness status`). Leftover worktrees in `.claude/worktrees/` whose branch "
                "has commits are integrated; the rest are discarded and their tickets rerun. " + RULE)
    if open_tickets:
        return (f"FullChico harness: a demand is in progress ({len(open_tickets)} open tickets). The main session "
                "plans and talks to the owner; the tr:orchestrator and its executors write the code. Check the "
                "state with `gate`. " + RULE)
    return ("FullChico harness: every change request in this project starts with /tr:process-plan "
            "(grilling interview (Matt Pocock), spec, tickets, then the orchestrator in the background). Run it before "
            "answering a request to build or change something. " + RULE)


def main():
    payload = json.load(sys.stdin)
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    root = registry.toplevel(cwd or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context(root, payload.get("source"))}},
                     ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
