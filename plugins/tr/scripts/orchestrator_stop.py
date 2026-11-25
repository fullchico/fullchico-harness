#!/usr/bin/env python3
"""Mantém o orquestrador trabalhando até o passaporte fechar ou haver bloqueio real."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry  # noqa: E402
import attempts  # noqa: E402
import tasks  # noqa: E402

ORQUESTRADORES = {"tr:orquestrador", "tr-orquestrador", "orquestrador"}


def decision(payload):
    if payload.get("agent_type") not in ORQUESTRADORES:
        return None
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if not os.path.isfile(os.path.join(root, ".claude", "demanda-atual")):
        return None  # fora de uma demanda aberta, não cria obrigação nova
    try:
        reg = registry.load(root)
        if reg:
            missing = registry.missing(root, "inicio", reg) + registry.missing(root, "fim", reg)
            problems, _ = tasks.audit(root, reg)
        else:
            missing, problems = ["registro de portões"], []
    except registry.RegistryError as error:
        missing, problems = [], [f"registro inválido: {error}"]
    if not missing and not problems:
        return None
    escalated = [name for name in missing if attempts.status(root, name).get("intervencao")]
    human = [name for name in missing if reg and reg["portoes"].get(name, {}).get("aprovacao") == "humana"]
    message = payload.get("last_assistant_message") or ""
    handoff = isinstance(message, str) and all(
        any(line.startswith(prefix) and line[len(prefix):].strip() for line in message.splitlines())
        for prefix in ("BLOQUEIO:", "TENTATIVAS:", "DECISÃO NECESSÁRIA:")
    )
    if (escalated or human) and not handoff:
        names = ", ".join(sorted(set(escalated + human)))
        return {"decision": "block", "reason":
                f"Portão final `{names}` requer intervenção humana. Faça handoff à sessão principal "
                "com BLOQUEIO:, TENTATIVAS: e DECISÃO NECESSÁRIA:; indique a validação técnica e o comando "
                "`fullchico-harness portoes --aprovar <nome>` quando ela já tiver passado."}
    if handoff:
        return None  # handoff explícito à sessão principal para uma decisão fora do plano
    details = [f"portão {name}" for name in missing] + problems
    return {"decision": "block", "reason":
            "Trilho ainda aberto: " + "; ".join(details[:5]) + ". Continue a execução, corrija e revalide "
            "sem pedir aprovação intermediária. Só encerre sem entrega validada se houver bloqueio "
            "real fora do plano; nesse caso relate BLOQUEIO:, TENTATIVAS: e DECISÃO NECESSÁRIA:."}


def main():
    payload = json.load(sys.stdin)
    result = decision(payload)
    if result:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
