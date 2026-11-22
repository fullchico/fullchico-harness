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


# Pedido de implementação, reconhecido pelo texto: verbo de pedir ou de construir, em mensagem que
# não começa como pergunta. Errar para mais custa uma entrevista curta; errar para menos deixava
# o modelo decidir sozinho se seguia o fluxo, e ele decidiu que não.
_BUILD = re.compile(
    r"\b(?:quero|queria|preciso|gostaria|cri(?:a|e|ar|em)|implement(?:a|e|ar|em)|adicion(?:a|e|ar)|"
    r"acrescent(?:a|e|ar)|mont(?:a|e|ar)|fa(?:z|ça|zer)|constru(?:a|ir)|desenvolv(?:a|er)|mud(?:a|e|ar)|"
    r"alter(?:a|e|ar)|troc(?:a|ar|que)|inclu(?:a|i|ir)|remov(?:a|e|er)|coloc(?:a|ar)|coloque|"
    r"corrij(?:a|am)|corrig(?:e|ir)|ajust(?:a|e|ar)|refator(?:a|e|ar)|"
    r"add|build|create|implement|make|change|remove|fix)\b", re.I)
_QUESTION = re.compile(r"^\s*(?:como|qual|quais|o que|oq|por que|porque|pq|onde|quando|quem|quanto|what|how|why|which)\b", re.I)
ENTER = ("O harness classificou este pedido como de implementação. Sua PRIMEIRA ação é invocar a skill "
         "`harness:entregar` com o pedido do dono: a entrevista refina, a spec registra e os implementadores "
         "escrevem. Não explore o código nem escreva nada antes disso; escrever código neste worktree é negado. "
         "Ajuste direto só se o dono rodar `/harness:direto`. Se a mensagem for só uma pergunta, responda a pergunta.")


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
    # A ordem vem uma vez por sessão: depois dela vêm as respostas da entrevista ("quero azul"), e
    # mandar entrar no fluxo de novo a cada uma faria o agente recomeçar.
    entered = common.direct_path(cwd, session)
    entered = entered.replace(os.sep + "direct" + os.sep, os.sep + "entered" + os.sep) if entered else None
    if _BUILD.search(prompt) and not _QUESTION.match(prompt) and entered and not os.path.exists(entered):
        os.makedirs(os.path.dirname(entered), exist_ok=True)
        open(entered, "w").close()
        print(ENTER)
    else:
        print(REMIND)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
