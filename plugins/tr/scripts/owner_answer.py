#!/usr/bin/env python3
"""PostToolUse do AskUserQuestion: o dono respondeu na interface. "Aprovo" na pergunta canônica de um comando do
dono (`registry.owner_question`) libera aquele comando uma vez, por pouco tempo, como o diálogo de permissão.

A resposta vem da plataforma, não do agente: o guard recusa a pergunta que já chega com `answers`."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import registry  # noqa: E402
import render  # noqa: E402


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "AskUserQuestion":
        return 0
    asked = {q.get("question") for q in (payload.get("tool_input") or {}).get("questions") or [] if isinstance(q, dict)}
    response = payload.get("tool_response")
    answers = (response.get("answers") if isinstance(response, dict) else None) or {}
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    granted = []
    for question, answer in answers.items() if isinstance(answers, dict) else []:
        canonical = registry.owner_from_question(question)
        if canonical and question in asked and str(answer).strip() == registry.OWNER_YES:
            registry.grant_owner(root, canonical)
            ledger.log(root, "tr", "owner_answered", canonical[:160])
            granted.append(canonical)
    if granted:
        return render.warn("✓ trilho · o dono aprovou: " + "; ".join(granted))
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:  # um hook de aprovação nunca derruba a sessão
        pass
    sys.exit(0)
