"""O que os hooks do trilho mostram no terminal: o quadro do bloqueio e o aviso de carimbo.

Pelo JSON do hook, não por exit 2: com exit 2 o Claude Code mostra o caminho do script antes da mensagem
(`hook error: [python3 -I ".../guard.py"]: ...`), e o bloqueio parece uma exceção.
"""
import json


def panel(title, fields_list, body_lines=(), footer=None):
    """Título, campos alinhados, o corpo (portões que faltam, passos) e o rodapé."""
    width = max(len(k) for k, _ in fields_list)
    row_lines = [f"⛔ trilho · {title}", ""] + [f"  {k.ljust(width)}   {v}" for k, v in fields_list]
    if body_lines:
        row_lines += [""] + list(body_lines)
    if footer:
        row_lines += ["", f"  {footer}"]
    return "\n".join(row_lines)


def block_with(reason_text):
    """`PreToolUse`: a ferramenta não roda; o motivo vai para o Claude e aparece no terminal."""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason_text}}, ensure_ascii=False))
    return 0


def refuse(reason_text):
    """`PostToolUse`: a ferramenta já rodou; o motivo volta ao Claude como erro a corrigir."""
    print(json.dumps({"decision": "block", "reason": reason_text}, ensure_ascii=False))
    return 0


def warn(message_text):
    """Uma linha para o dono, sem bloquear nada (ex.: o carimbo assinado)."""
    print(json.dumps({"systemMessage": message_text}, ensure_ascii=False))
    return 0
