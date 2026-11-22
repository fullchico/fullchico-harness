#!/usr/bin/env python3
"""UserPromptSubmit: a cada pedido do dono, o agente é lembrado de por onde o código muda.

A regra estava só no AGENTS.md, e uma sessão decidiu não segui-la quando o pedido chegou em
texto livre. Aqui ela chega junto com o pedido. É também o único lugar que abre a edição
direta: só uma mensagem do dono passa por este hook, então o agente não tem como forjá-la.
Nunca bloqueia.
"""
import os
import re
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

# A liberação é a mensagem que começa pelo comando, e nada mais: citado no meio de uma frase ou
# dentro de um texto colado, não abre. É conferido aqui, por máquina, não pelo modelo.
_DIRECT = re.compile(r"^\s*/harness:direto(?:\s|$)")
OPEN = ("O dono liberou a edição direta nesta sessão (/harness:direto). Faça só o que ele pediu, no menor "
        "diff, com teste, e commit no formato do projeto. Commit `feat` continua pedindo spec no push.")
REMIND = ("Regra do harness: código do aplicativo só muda pelo fluxo. Se este pedido muda o aplicativo "
          "(feature, tela, comportamento), invoque a skill `harness:entregar` com ele em vez de implementar; "
          "escrever código neste worktree é negado. Ajuste direto só se o dono rodar `/harness:direto`.")


def main():
    payload = common.read_payload()
    cwd, prompt = payload.get("cwd"), payload.get("prompt")
    if not isinstance(cwd, str) or not isinstance(prompt, str) or not prompt.strip():
        return
    session = payload.get("session_id")
    if _DIRECT.match(prompt):
        path = common.direct_path(cwd, session)
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w").close()
            print(OPEN)
        return
    if common.direct_open(cwd, session) or prompt.lstrip().startswith("/"):
        return
    print(REMIND)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
