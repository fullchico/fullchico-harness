#!/usr/bin/env python3
"""Certifica os portões. Quem certifica é o hook, no contexto do responsável, nunca o agente à mão.

O certificado vai para o apêndice do documento da demanda e é assinado por commit (`certs.py`).

- `PostToolUse` de `Bash`: o comando foi exatamente `gate <name>` e a saída termina em
  `gate <name>: passou` -> portão `command` ou `artifact`. Portão de fim só assina dentro do
  `tr:quality-checker` (quem escreveu não assina); o de início (o plano) assina onde rodar. Árvore suja num portão de fim: não assina e recusa (JSON `decision: block`).
- `SubagentStop` e `PreToolUse` de `SubagentHandback`: o veredito APPROVED do agente de um portão `agent`.
  REJECTED apaga o carimbo.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import attempts  # noqa: E402
import certs  # noqa: E402
import registry  # noqa: E402
import render  # noqa: E402


def version():
    return certs.version()


def once(pattern, text):
    found = re.findall(pattern, text, re.M)
    return found[0] if len(found) == 1 else None


def output_of(response):
    if isinstance(response, dict):
        return response.get("stdout") or ""
    return response if isinstance(response, str) else ""


def from_command(payload, root, reg):
    command = ((payload.get("tool_input") or {}).get("command") or "").strip()
    m = re.fullmatch(r"gate[ \t]+([\w.-]+)(?:[ \t]+--ticket[ \t]+([^\s]+))?", command)
    if not m:
        return 0
    name, ticket = m.group(1), m.group(2)
    gate = reg["gates"].get(name)
    if not gate or gate["signs"] == "agent":
        return 0
    failed_event = payload.get("hook_event_name") == "PostToolUseFailure"
    # comando que sai com erro chega por outro evento, com a saída em `error` (e "Exit code N" em volta)
    text = payload.get("error") if failed_event else output_of(payload.get("tool_response"))
    lines = [l for l in (text if isinstance(text, str) else "").splitlines() if l.strip()]
    expected = f"gate {name}{' ticket ' + ticket if ticket else ''}: passou"
    failure = next((l.strip() for l in reversed(lines) if l.strip().startswith(f"gate {name}: FALHOU")), None)
    if failed_event and not failure:
        return 0
    if failure and (failed_event or lines[-1].strip() == failure) and payload.get("agent_type") == registry.CHECKER:
        key = registry.stamp_key(root, gate, ticket)
        if key:
            certs.certify(root, name, key, "REJECTED", registry.CHECKER, failure, ticket)
        state = attempts.status(root, name, gate)
        if gate["stage"] == "end" and state["intervention"]:
            return render.warn(f"Intervenção humana necessária no portão {name}: {state['rejections']} reprovações; limite {gate.get('attempts', 3)}.")
        return 0
    if failed_event or not lines or lines[-1].strip() != expected:
        return 0
    if payload.get("agent_type") != registry.CHECKER:
        # quem escreveu o código vê o resultado, mas não assina: o carimbo vem de um subagente limpo
        ledger.log(root, "tr", "not_signed", f"{name}: rodado fora do {registry.CHECKER}")
        return render.warn(f"trilho · {name} passou aqui, mas o carimbo vem de {registry.INVOKERS[registry.CHECKER]}")
    if registry.dirty(root):
        ledger.log(root, "tr", "not_signed", f"{name}: árvore suja")
        return render.refuse(render.panel("carimbo recusado", [
            ("portão", name), ("motivo", "passou, mas a árvore tem alteração sem commit"),
        ], [f"  → faça o commit e rode `gate {name}` de novo"],
            "o fiscal só assina com a árvore limpa"))
    if gate["stage"] == "end" and __import__("tasks").open_work(root):
        ledger.log(root, "tr", "not_signed", f"{name}: auditoria antes da chegada do trem")
        return render.warn(f"trilho · {name} passou, mas a auditoria só certifica com todos os tickets e ajustes integrados")
    if gate["stage"] == "middle" and (not ticket or ticket not in __import__("tasks").tickets(root)):
        return 0
    if gate["stage"] != "middle" and ticket:
        return 0
    key = registry.stamp_key(root, gate, ticket)
    if not key:
        return 0
    by = registry.responsible(gate) or payload.get("agent_type") or "tr:main-session"
    refused = certs.certify(root, name, key, "APPROVED", by, f"gate {name} passou ({gate['signs']})", ticket)
    if refused:
        ledger.log(root, "tr", "not_signed", f"{name}: {refused}")
        return render.refuse(render.panel("certificado recusado", [("portão", name), ("motivo", refused)], [],
                                          "o certificado vai no documento da demanda, assinado por commit"))
    ledger.log(root, "tr", "signed", f"{name}: {key[:10]}")
    return render.warn(f"✓ trilho · {name} carimbado ({key[:10]})")


def from_agent(payload, root, reg):
    agent = payload.get("agent_type")
    gates = {n: g for n, g in reg["gates"].items() if g["signs"] == "agent" and g["agent"] == agent}
    if not gates:
        return 0
    if payload.get("hook_event_name") == "PreToolUse":
        if payload.get("tool_name") != "SubagentHandback":
            return 0
        text = (payload.get("tool_input") or {}).get("message")
    else:
        text = payload.get("last_assistant_message")
    if not isinstance(text, str):
        return 0
    verdict = once(r"^[ \t]*VERDICT: (APPROVED|REJECTED)[ \t]*$", text)
    commit = once(r"^[ \t]*COMMIT: ([0-9a-f]{40})[ \t]*$", text)
    summary = once(r"^[ \t]*SUMMARY: (\S.*?)[ \t]*$", text)
    top = ledger.head(root)
    warnings = []
    for name, gate in gates.items():
        key = registry.stamp_key(root, gate)
        if not (verdict and commit and summary):
            # no SubagentStop vem só o fecho: se o relatório já assinou na entrega, não é falha
            if not (payload.get("hook_event_name") == "SubagentStop" and key and certs.has(root, name, key)):
                ledger.log(root, "tr", "not_signed", f"{name}: bloco de três linhas ausente ou ambíguo")
        elif commit != top:
            ledger.log(root, "tr", "not_signed", f"{name}: o commit {commit[:10]} não é o topo ({(top or '?')[:10]})")
        elif not key:
            ledger.log(root, "tr", "not_signed", f"{name}: sem chave do carimbo")
        elif verdict == "APPROVED":
            refused = certs.certify(root, name, key, "APPROVED", agent, summary)
            if refused:
                ledger.log(root, "tr", "not_signed", f"{name}: {refused}")
                warnings.append(f"✗ trilho · {name} aprovado por {agent}, mas o certificado foi recusado: {refused}")
            else:
                ledger.log(root, "tr", "signed", f"{name}: {key[:10]}: {summary}")
                warnings.append(f"✓ trilho · {name} certificado por {agent} ({key[:10]})")
        else:
            certs.certify(root, name, key, "REJECTED", agent, summary)
            state = attempts.status(root, name, gate)
            ledger.log(root, "tr", "rejected", f"{name}: {key[:10]}: {summary}")
            warnings.append(f"✗ trilho · {name} reprovado por {agent} ({key[:10]}): {summary}")
            if gate["stage"] == "end" and state["intervention"]:
                warnings.append(f"Intervenção humana necessária: {state['rejections']} reprovações; limite {gate.get('attempts', 3)}.")
    return render.warn("\n".join(warnings)) if warnings else 0


def main():
    payload = json.load(sys.stdin)
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    reg = registry.load(root)
    if not reg:
        return 0
    if payload.get("hook_event_name") in ("PostToolUse", "PostToolUseFailure"):
        return from_command(payload, root, reg) if payload.get("tool_name") == "Bash" else 0
    return from_agent(payload, root, reg)


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # um hook de carimbo nunca derruba a sessão
        code = 0
    sys.exit(code)
