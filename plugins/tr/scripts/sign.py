#!/usr/bin/env python3
"""Assina os carimbos dos portões. Quem assina é o hook, nunca o agente.

- `PostToolUse` de `Bash`: o comando foi exatamente `portao <nome>` e a saída termina em
  `portao <nome>: passou` -> portão `comando` ou `artefato`. Portão de fim só assina dentro do
  `tr:qualidade-verificador` (quem escreveu não assina); o de início (o plano) assina onde rodar. Árvore suja num portão de fim: não assina e recusa (JSON `decision: block`).
- `SubagentStop` e `PreToolUse` de `SubagentHandback`: o veredito APPROVED do agente de um portão `agente`.
  REJECTED apaga o carimbo.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import attempts  # noqa: E402
import registry  # noqa: E402
import saida  # noqa: E402


def version():
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude-plugin", "plugin.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)["version"]
    except (OSError, ValueError, KeyError):
        return "desconhecida"


def once(pattern, text):
    found = re.findall(pattern, text, re.M)
    return found[0] if len(found) == 1 else None


def output_of(response):
    if isinstance(response, dict):
        return response.get("stdout") or ""
    return response if isinstance(response, str) else ""


def from_command(payload, root, reg):
    command = ((payload.get("tool_input") or {}).get("command") or "").strip()
    m = re.fullmatch(r"portao[ \t]+([\w.-]+)(?:[ \t]+--ticket[ \t]+([^\s]+))?", command)
    if not m:
        return 0
    name, ticket = m.group(1), m.group(2)
    gate = reg["portoes"].get(name)
    if not gate or gate["assina"] == "agente":
        return 0
    lines = [l for l in output_of(payload.get("tool_response")).splitlines() if l.strip()]
    expected = f"portao {name}{' ticket ' + ticket if ticket else ''}: passou"
    if lines and lines[-1].strip().startswith(f"portao {name}: FALHOU") and payload.get("agent_type") == registry.VERIFICADOR:
        key = registry.stamp_key(root, gate, ticket)
        if key:
            ledger.forget(root, registry.scoped_stamp(name, ticket) if ticket else name, key)
        state = attempts.reject(root, name, gate)
        if state and state["intervencao"]:
            return saida.avisar(f"Intervenção humana necessária no portão {name}: {state['reprovacoes']} reprovações; limite {gate.get('tentativas', 3)}.")
        return 0
    if not lines or lines[-1].strip() != expected:
        return 0
    if payload.get("agent_type") != registry.VERIFICADOR:
        # quem escreveu o código vê o resultado, mas não assina: o carimbo vem de um subagente limpo
        ledger.log(root, "trilho", "não assinou", f"{name}: rodado fora do {registry.VERIFICADOR}")
        return saida.avisar(f"trilho · {name} passou aqui, mas o carimbo vem de {registry.INVOKERS[registry.VERIFICADOR]}")
    if registry.dirty(root):
        ledger.log(root, "trilho", "não assinou", f"{name}: árvore suja")
        return saida.recusar(saida.quadro("carimbo recusado", [
            ("portão", name), ("motivo", "passou, mas a árvore tem alteração sem commit"),
        ], [f"  → faça o commit e rode `portao {name}` de novo"],
            "o fiscal só assina com a árvore limpa"))
    if gate["momento"] == "meio" and (not ticket or ticket not in __import__("tasks").tickets(root)):
        return 0
    if gate["momento"] != "meio" and ticket:
        return 0
    key = registry.stamp_key(root, gate, ticket)
    if not key:
        return 0
    stamp = registry.scoped_stamp(name, ticket) if ticket else name
    ledger.sign(root, stamp, key, "trilho", version(), f"portao {name}", f"{name} passou ({gate['assina']})")
    ledger.log(root, "trilho", "assinou", f"{stamp}: {key[:10]}")
    return saida.avisar(f"✓ trilho · {name} carimbado ({key[:10]})")


def from_agent(payload, root, reg):
    agent = payload.get("agent_type")
    gates = {n: g for n, g in reg["portoes"].items() if g["assina"] == "agente" and g["agente"] == agent}
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
    verdict = once(r"^[ \t]*VEREDITO: (APPROVED|REJECTED)[ \t]*$", text)
    commit = once(r"^[ \t]*COMMIT: ([0-9a-f]{40})[ \t]*$", text)
    summary = once(r"^[ \t]*RESUMO: (\S.*?)[ \t]*$", text)
    top = ledger.head(root)
    avisos = []
    for name, gate in gates.items():
        key = registry.stamp_key(root, gate)
        if not (verdict and commit and summary):
            # no SubagentStop vem só o fecho: se o relatório já assinou na entrega, não é falha
            if not (payload.get("hook_event_name") == "SubagentStop" and key and ledger.has(root, name, key)):
                ledger.log(root, "trilho", "não assinou", f"{name}: bloco de três linhas ausente ou ambíguo")
        elif commit != top:
            ledger.log(root, "trilho", "não assinou", f"{name}: o commit {commit[:10]} não é o topo ({(top or '?')[:10]})")
        elif not key:
            ledger.log(root, "trilho", "não assinou", f"{name}: sem chave do carimbo")
        elif verdict == "APPROVED":
            ledger.sign(root, name, key, "trilho", version(), agent, summary)
            ledger.log(root, "trilho", "assinou", f"{name}: {key[:10]}: {summary}")
            avisos.append(f"✓ trilho · {name} carimbado por {agent} ({key[:10]})")
        else:
            ledger.forget(root, name, key)
            state = attempts.reject(root, name, gate, f"{commit}:{summary}")
            ledger.log(root, "trilho", "reprovou", f"{name}: {key[:10]}: {summary}")
            avisos.append(f"✗ trilho · {name} reprovado por {agent} ({key[:10]}): {summary}")
            if state and state["intervencao"]:
                avisos.append(f"Intervenção humana necessária: {state['reprovacoes']} reprovações; limite {gate.get('tentativas', 3)}.")
    return saida.avisar("\n".join(avisos)) if avisos else 0


def main():
    payload = json.load(sys.stdin)
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    reg = registry.load(root)
    if not reg:
        return 0
    if payload.get("hook_event_name") == "PostToolUse":
        return from_command(payload, root, reg) if payload.get("tool_name") == "Bash" else 0
    return from_agent(payload, root, reg)


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # um hook de carimbo nunca derruba a sessão
        code = 0
    sys.exit(code)
