#!/usr/bin/env python3
"""SubagentStop (harness:orquestrador): o orquestrador não encerra com filho em andamento.

O despacho de subagente pode sair em segundo plano. Se o orquestrador encerra a resposta final
com um implementador ou revisor ainda rodando, o relato do filho vai parar na sessão do dono e
a entrega fica sem quem a conduza. Aqui a primeira parada é segurada (saída 2: o stderr volta
para ele como instrução). A segunda passa sempre (`stop_hook_active`): nunca prende em laço.
Erro interno não segura ninguém: sai 0.
"""
import os
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import common  # noqa: E402


def main():
    payload = common.read_payload()
    cwd = payload.get("cwd")
    root = common.repo_root(cwd) if isinstance(cwd, str) else None
    if not root or payload.get("agent_type") != "harness:orquestrador":
        return 0
    import resume
    waiting = resume.running(root)
    if not waiting:
        return 0
    who = "; ".join(f"ticket {t['name']}, despachado há {t['waiting_min']} min" for t in waiting)
    if payload.get("stop_hook_active"):
        common.log(cwd, "orchestrator_stop", "deixou parar", f"já tinha sido segurado uma vez; em andamento: {who}")
        return 0
    common.log(cwd, "orchestrator_stop", "segurou", who)
    sys.stderr.write(f"há agente em andamento ({who}): espere o aviso de término dele; se você está parando "
                     "por bloqueio, diga PARADA e o motivo.\n")
    return 2


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        code = 0
    sys.exit(code)
