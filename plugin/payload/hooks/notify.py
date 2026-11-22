#!/usr/bin/env python3
"""Registra que um pedido de permissão foi mostrado ao dono.

Eventos: `PermissionRequest` (o Claude Code vai pedir permissão para uma ferramenta) e
`Notification` do tipo `permission_prompt` (o pedido está na tela há alguns segundos).
Um pedido parado na tela não deixa rastro em lugar nenhum: o agente fica mudo e parece morto.
Aqui ele vira uma linha em `<estado>/permissions.jsonl`, uma em `<estado>/log.jsonl` e uma em
`.harness-run/aguardando-dono.txt`, que o orquestrador lê de dentro do sandbox.

Não decide nada: não imprime, não bloqueia, e qualquer erro interno sai 0.
"""
import datetime
import json
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

LIMIT = 200
# ponytail: heurística de nomes comuns, não um detector de segredo; o corte em LIMIT é a outra metade.
_SECRET = re.compile(r"(?i)(bearer\s+|[\w-]*(?:token|secret|senha|password|passwd|api[_-]?key|credential)[\w-]*\s*[=:]\s*)[^\s'\"]+")


def short(text) -> str:
    text = " ".join(str(text).split())
    text = _SECRET.sub(lambda m: m.group(1) + "***", text)
    return text if len(text) <= LIMIT else text[:LIMIT] + "…"


def summary(tool_input) -> str:
    """O bastante para o dono reconhecer o pedido, nunca o conteúdo: comando, caminho ou endereço."""
    if not isinstance(tool_input, dict):
        return ""
    for key in ("command", "file_path", "path", "url", "subagent_type", "description"):
        if isinstance(tool_input.get(key), str) and tool_input[key].strip():
            return short(tool_input[key])
    return short("campos: " + ", ".join(sorted(tool_input)))


def text_or_none(value):
    return short(value) if isinstance(value, str) and value else None


def main() -> None:
    payload = common.read_payload()
    event = payload.get("hook_event_name")
    if event == "PermissionRequest":
        what, tool, resumo = "permissão pedida", text_or_none(payload.get("tool_name")), summary(payload.get("tool_input"))
    elif event == "Notification" and payload.get("notification_type") == "permission_prompt":
        what, tool, resumo = "permissão esperando", None, short(payload.get("message") or "")
    else:
        return
    cwd = payload.get("cwd")
    state = common.state_dir(cwd) if isinstance(cwd, str) else None
    if not state:
        return
    at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    agent = text_or_none(payload.get("agent_type"))
    record = {"at": at, "what": what, "session": text_or_none(payload.get("session_id")), "agent_type": agent,
              "agent_id": text_or_none(payload.get("agent_id")), "tool": tool, "summary": resumo}
    label = f"{tool}: {resumo}" if tool else resumo
    os.makedirs(state, exist_ok=True)
    # ponytail: só acrescenta, como o log.jsonl; se crescer demais, rodar por tamanho nos dois.
    with open(os.path.join(state, "permissions.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    common.log(cwd, "notify", what, label + (f" (agente {agent})" if agent else ""))

    # O agente de um ticket roda no worktree dele; quem espera por ele está no da feature.
    run = os.path.join(common.feature_root(common.repo_root(cwd)), ".harness-run")
    os.makedirs(run, exist_ok=True)
    ignore = os.path.join(run, ".gitignore")
    if not os.path.exists(ignore):
        with open(ignore, "w", encoding="utf-8") as f:
            f.write("*\n")
    with open(os.path.join(run, "aguardando-dono.txt"), "a", encoding="utf-8") as f:
        f.write(f"{at} {what}: {label}" + (f" (agente {agent})" if agent else "") + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # nunca muda o fluxo do pedido
        try:
            common.log(os.getcwd(), "notify", "erro", f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
    sys.exit(0)
