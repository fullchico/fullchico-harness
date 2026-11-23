"""O que os hooks do trilho mostram no terminal: o quadro do bloqueio e o aviso de carimbo.

Pelo JSON do hook, não por exit 2: com exit 2 o Claude Code mostra o caminho do script antes da mensagem
(`hook error: [python3 -I ".../gate.py"]: ...`), e o bloqueio parece uma exceção.
"""
import json


def quadro(titulo, campos, corpo=(), rodape=None):
    """Título, campos alinhados, o corpo (portões que faltam, passos) e o rodapé."""
    largura = max(len(k) for k, _ in campos)
    linhas = [f"⛔ trilho · {titulo}", ""] + [f"  {k.ljust(largura)}   {v}" for k, v in campos]
    if corpo:
        linhas += [""] + list(corpo)
    if rodape:
        linhas += ["", f"  {rodape}"]
    return "\n".join(linhas)


def barrar(motivo):
    """`PreToolUse`: a ferramenta não roda; o motivo vai para o Claude e aparece no terminal."""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": motivo}}, ensure_ascii=False))
    return 0


def recusar(motivo):
    """`PostToolUse`: a ferramenta já rodou; o motivo volta ao Claude como erro a corrigir."""
    print(json.dumps({"decision": "block", "reason": motivo}, ensure_ascii=False))
    return 0


def avisar(mensagem):
    """Uma linha para o dono, sem bloquear nada (ex.: o carimbo assinado)."""
    print(json.dumps({"systemMessage": mensagem}, ensure_ascii=False))
    return 0
