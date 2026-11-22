#!/usr/bin/env python3
"""SubagentStart e SubagentStop (todo subagente): registra quem começou e quem terminou.

É por aqui que o painel (`.harness/board`) sabe que agentes estão rodando agora: cada evento vira
uma linha em `<estado>/activity.jsonl`. Do orquestrador que termina fica também a linha
`ENTREGA: ...` com que ele encerrou. Depois de gravar, o painel é refeito.

Não decide nada: não imprime, não bloqueia, e sai 0 sempre. No `SubagentStop`, sair 2 impediria
o subagente de parar.
"""
import datetime
import json
import os
import signal
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import common  # noqa: E402

EVENTS = {"SubagentStart": "start", "SubagentStop": "stop"}
BOARD_LIMIT = 1.0  # segundos: o painel é um extra, não pode atrasar o agente


def text_or_none(value, limit=200):
    return value[:limit] if isinstance(value, str) and value else None


def outcome(message):
    """A linha `ENTREGA: ...` com que o orquestrador encerrou, se houver."""
    lines = [l.strip() for l in message.splitlines()] if isinstance(message, str) else []
    return next((l[:300] for l in reversed(lines) if l.startswith("ENTREGA:")), None)


def _give_up(*_):
    raise TimeoutError


def main() -> None:
    payload = common.read_payload()
    event, cwd = EVENTS.get(payload.get("hook_event_name")), payload.get("cwd")
    state = common.state_dir(cwd) if event and isinstance(cwd, str) else None
    if not state:
        return
    forced = os.environ.get("HARNESS_NOW", "")  # o relógio dos testes, como no resume.py
    at = datetime.datetime.fromtimestamp(int(forced), datetime.timezone.utc) if forced.isdigit() \
        else datetime.datetime.now(datetime.timezone.utc)
    record = {"at": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "event": event, "agent_type": text_or_none(payload.get("agent_type")),
              "agent_id": text_or_none(payload.get("agent_id")), "session_id": text_or_none(payload.get("session_id"))}
    if event == "stop" and record["agent_type"] == "harness:orquestrador":
        record["outcome"] = outcome(payload.get("last_assistant_message"))
    os.makedirs(state, exist_ok=True)
    # ponytail: só acrescenta, como o log.jsonl; o painel lê só o fim do arquivo.
    with open(os.path.join(state, "activity.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    signal.signal(signal.SIGALRM, _give_up)
    signal.setitimer(signal.ITIMER_REAL, BOARD_LIMIT)
    import board
    board.write(common.feature_root(common.repo_root(cwd)))


if __name__ == "__main__":
    try:
        main()
    except BaseException:  # nunca muda o fluxo do agente; nem o painel que demorou
        pass
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    sys.exit(0)
