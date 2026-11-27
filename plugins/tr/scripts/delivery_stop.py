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
    wanted = os.environ.get("TR_REPORT")
    if wanted and not payload.get("stop_hook_active") and not os.path.isfile(wanted):
        # o executor aberto em terminal devolve o trabalho pelo relato; parar sem ele deixa quem o abriu no escuro
        print(json.dumps({"decision": "block", "reason": (
            f"You have not reported. Finish your work; then, as the last thing, write `{wanted}` the way your "
            "request says (an executor: a first line DONE or BLOCKED and what you did; a reviewer: your answer "
            "ending with VERDICT, COMMIT and SUMMARY).")},
            ensure_ascii=False))
        return 0
    if os.environ.get("TR_ROLE") == "orchestrator" and not payload.get("stop_hook_active"):
        # quem conduz a demanda avisa o maestro pelo relato; parar sem ele deixa o dono sem saber
        here = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        waiting = bool(tasks._raw_in_flight(here))  # com executor em voo, parar é esperar o aviso dele: não é sumir
        if not waiting and not os.path.isfile(os.path.join(here, ".harness-run", "report.md")):
            print(json.dumps({"decision": "block", "reason": (
                "You are the orchestrator of this demand and have not reported. Keep working until "
                "`tr-harness deliver` passes; when it passes, or when you truly cannot continue, run "
                "`tr-harness report done \"...\"` or `tr-harness report blocked \"...\"` alone in the call.")},
                ensure_ascii=False))
            return 0
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
