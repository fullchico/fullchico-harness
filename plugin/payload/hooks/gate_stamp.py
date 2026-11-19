#!/usr/bin/env python3
"""SubagentStop: grava a aprovação de um portão a partir do veredito do revisor.

Nenhum agente carimba. Este hook lê a resposta final do subagente e só grava
quando o subagente é um revisor do harness, o veredito é APPROVED e o commit
revisado é o topo atual. Nunca bloqueia: na dúvida, não carimba e sai 0.
"""
import datetime
import json
import os
import re
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

AGENT_GATE = {"harness:seguranca": "seguranca", "harness:revisor": "revisao"}
HANDBACK_TOOL = "SubagentHandback"
_VERDICT = re.compile(r"^VEREDITO: (APPROVED|REJECTED)$")
_COMMIT = re.compile(r"^COMMIT: ([0-9a-f]{40})$")
_RESUMO = re.compile(r"^RESUMO: (\S.*)$")


def gate_for(agent_type):
    return AGENT_GATE.get(agent_type) if isinstance(agent_type, str) else None


def parse_verdict(message):
    """Só aceita uma linha inteira de cada chave; qualquer ambiguidade vira None."""
    if not isinstance(message, str):
        return None
    found = {"verdict": [], "commit": [], "resumo": []}
    for raw in message.splitlines():
        line = raw.strip()
        for key, pattern in (("verdict", _VERDICT), ("commit", _COMMIT), ("resumo", _RESUMO)):
            m = pattern.match(line)
            if m:
                found[key].append(m.group(1).strip())
    if any(len(values) != 1 for values in found.values()):
        return None
    return {key: values[0] for key, values in found.items()}


def _is_message(entry) -> bool:
    """Entrada de usuário que é texto, e não resultado de ferramenta."""
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "text" for b in content)
    return False


def final_message(payload):
    """Resposta final do subagente.

    A documentação descreve `last_assistant_message`, mas a plataforma observada não
    o envia. O texto então vem da transcrição do subagente: a última entrada do
    assistente, em blocos de texto ou na chamada de devolução `SubagentHandback`.
    Só essa última entrada conta, para um veredito citado no meio do trabalho não
    valer como resposta.
    """
    message = payload.get("last_assistant_message")
    path = payload.get("agent_transcript_path")
    if not isinstance(path, str) or not os.path.exists(os.path.expanduser(path)):
        return message if isinstance(message, str) and message.strip() else None
    last = None
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or not entry.get("isSidechain"):
                    continue
                if entry.get("type") == "assistant":
                    last = entry
                elif entry.get("type") == "user" and last is not None and _is_message(entry):
                    # Alguém falou com o revisor depois que ele começou: o veredito
                    # deixa de ser só sobre os documentos, então não vale como aprovação.
                    return None
    except OSError:
        return None
    content = ((last or {}).get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif block.get("type") == "tool_use" and block.get("name") == HANDBACK_TOOL:
            text = (block.get("input") or {}).get("message")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts) if parts else None


def main():
    payload = common.read_payload()
    gate = gate_for(payload.get("agent_type"))
    verdict = parse_verdict(final_message(payload))
    cwd = payload.get("cwd")
    if not gate or not verdict or not isinstance(cwd, str):
        return
    state = common.state_dir(cwd)
    if not state or verdict["commit"] != common.head_sha(cwd):
        return
    path = common.approval_path(state, gate, verdict["commit"])
    if verdict["verdict"] == "REJECTED":
        if os.path.exists(path):
            os.remove(path)
        return
    base = None
    try:
        with open(common.request_path(state, gate, verdict["commit"]), encoding="utf-8") as f:
            base = json.load(f).get("base")
    except (OSError, ValueError):
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {
        "gate": gate,
        "sha": verdict["commit"],
        "base": base,
        "status": "PASS",
        "resumo": verdict["resumo"],
        "by": "hook",
        "agent_type": payload.get("agent_type"),
        "transcript": payload.get("agent_transcript_path"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
