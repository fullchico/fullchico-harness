#!/usr/bin/env python3
"""Mantém o orquestrador trabalhando até o passaporte fechar ou haver bloqueio real."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import registry  # noqa: E402
import attempts  # noqa: E402
import tasks  # noqa: E402

ORCHESTRATORS = registry.ORCHESTRATORS
NO_PROGRESS_LIMIT = 3  # retomadas seguidas com as mesmas pendências antes de soltar o orquestrador


def stalled(root, payload, details):
    """Conta as retomadas sem progresso. Solta depois do limite: segurar mais só gasta, e a entrega
    continua barrada pelo Stop da sessão principal."""
    path = os.path.join(ledger.state_dir(root) or "", "orchestrator-stop.json")
    fingerprint = "\n".join(sorted(details))
    try:
        with open(path, encoding="utf-8") as f:
            last = json.load(f)
    except (OSError, ValueError):
        last = {}
    same = payload.get("stop_hook_active") and last.get("fingerprint") == fingerprint
    count = last.get("count", 0) + 1 if same else 1
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"fingerprint": fingerprint, "count": count}, f)
    except OSError:
        return False
    if count > NO_PROGRESS_LIMIT:
        ledger.log(root, "tr", "released", f"orquestrador sem progresso após {NO_PROGRESS_LIMIT} retomadas")
        return True
    return False


def decision(payload):
    if payload.get("agent_type") not in ORCHESTRATORS:
        return None
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if not os.path.isfile(os.path.join(root, ".claude", "current-demand")):
        return None  # fora de uma demanda aberta, não cria obrigação nova
    try:
        reg = registry.load(root)
        if reg:
            missing = registry.missing(root, "start", reg) + registry.missing(root, "end", reg)
            problems, _ = tasks.audit(root, reg)
        else:
            missing, problems = ["registro de portões"], []
    except registry.RegistryError as error:
        missing, problems = [], [f"registro inválido: {error}"]
    if not missing and not problems:
        return None
    escalated = [name for name in missing if attempts.status(root, name).get("intervention")]
    human = [name for name in missing if reg and reg["gates"].get(name, {}).get("approval") == "human"]
    message = payload.get("last_assistant_message") or ""
    handoff = isinstance(message, str) and all(
        any(line.startswith(prefix) and line[len(prefix):].strip() for line in message.splitlines())
        for prefix in ("BLOCKER:", "ATTEMPTS:", "DECISION NEEDED:")
    )
    if (escalated or human) and not handoff:
        names = ", ".join(sorted(set(escalated + human)))
        return {"decision": "block", "reason":
                f"End gate `{names}` requires human intervention. Hand off to the main session "
                "with BLOCKER:, ATTEMPTS: and DECISION NEEDED:; point to the technical validation and to the command "
                f"`{registry.owner_command(root, 'gates --approve <name>')}` once it has passed."}
    if handoff:
        return None  # handoff explícito à sessão principal para uma decisão fora do plano
    details = [f"gate {name}" for name in missing] + problems
    if stalled(root, payload, details):
        return None
    return {"decision": "block", "reason":
            "Rail still open: " + "; ".join(details[:5]) + ". Keep executing, fix and revalidate "
            "without asking for intermediate approval. Only stop without a validated delivery if there is a real "
            "blocker outside the plan; in that case report BLOCKER:, ATTEMPTS: and DECISION NEEDED:."}


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
