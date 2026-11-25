#!/usr/bin/env python3
"""`tr-harness status`: o quadro da demanda, gravado pelos hooks (não pela impressão de um agente).

Tickets: concluído, bloqueado, em execução, pronto (na fronteira) ou na fila. Subagentes ativos com a última
atividade; quem passou de `tasks.STALE_AFTER` sem usar ferramenta aparece como possivelmente parado.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry  # noqa: E402
import tasks  # noqa: E402


def ago(ts, now):
    minutes = int((now - ts) // 60)
    return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h"


def main():
    root = registry.toplevel(os.getcwd())
    reg = registry.load(root)
    if not reg:
        print("Este projeto não tem portões configurados: rode /tr:configure.")
        return 0
    now, data, running = time.time(), tasks.board(root), tasks._in_flight(root)
    _, ready = tasks.audit(root, reg)
    all_tickets = tasks.tickets(root)
    if not all_tickets:
        print("Nenhum ticket na demanda atual.")
    else:
        finished = sum(1 for f in all_tickets.values() if f.get("status", "").lower() == "done")
        print(f"Progresso: {finished}/{len(all_tickets)} concluídos · executores simultâneos até "
              f"{reg.get('max_parallel', registry.MAX_PARALLEL)}\n")
    for path, fields in sorted(all_tickets.items()):
        event = (data.get("tickets") or {}).get(path, {})
        if fields.get("status", "").lower() == "done":
            state = "concluído"
        elif event.get("state") == "blocked":
            state = f"bloqueado há {ago(event['at'], now)}: {event.get('note', '')}"
        elif path in running:
            state = f"em execução há {ago(running[path], now)}"
        elif event.get("state") == "done":
            state = "em revisão (executor terminou; integrar, validar e marcar done)"
        elif path in ready:
            state = "pronto (na fronteira)"
        else:
            state = "na fila"
        print(f"{os.path.basename(path):34} {state}")
    orphans = tasks.orphan_containers(root)
    if orphans:
        print("\nContêineres esquecidos (de worktrees que já não existem):")
        print("  " + ", ".join(orphans))
        print(f"  para remover: docker rm -f {' '.join(orphans)}")
    until = tasks.awake_until(root)
    if until > time.time():
        print(f"\nMáquina acordada até {time.strftime('%H:%M', time.localtime(until))} (cafeína do tr; renova enquanto há trabalho)")
    agents = data.get("agents") or {}
    if agents:
        print("\nSubagentes ativos:")
        for agent_id, info in sorted(agents.items(), key=lambda kv: kv[1].get("last", 0)):
            idle = now - info.get("last", now)
            if info.get("type") in registry.ORCHESTRATORS and running:
                # Quem orquestra fica sem usar ferramenta enquanto espera os executores em primeiro plano:
                # isso é espera, não travamento. O alarme vale para quem trabalha, o executor.
                flag = f"  (aguardando {len(running)} executor{'es' if len(running) > 1 else ''})"
            else:
                flag = "  ⚠ possivelmente parado" if idle > tasks.STALE_AFTER else ""
            print(f"  {info.get('type') or '?':22} {agent_id[:10]}  última atividade há {ago(info.get('last', now), now)}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
