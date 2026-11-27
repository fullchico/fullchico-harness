#!/usr/bin/env python3
"""SessionStart: os programas que o tr exige estão nesta máquina?

O `install` cobra o tmux e o rtk, mas só na máquina e na hora em que roda. Quem clona o projeto, ou perde um
dos dois depois, abriria a sessão sem saber: o hook do rtk não faz nada sem ele (a economia some em silêncio) e
a falta do tmux só apareceria na partida do trem. Aqui o aviso vem no começo da sessão, com o que instalar."""
import json
import shutil
import sys

NEEDED = (
    ("tmux", "o orquestrador e os peixes abrem cada um num terminal dele", "brew install tmux (ou o pacote `tmux` do sistema)"),
    ("rtk", "comprime a saída dos comandos e economiza tokens", "brew install rtk (outras formas: https://github.com/rtk-ai/rtk)"),
)


def missing():
    return [(name, why, how) for name, why, how in NEEDED if not shutil.which(name)]


def main():
    try:
        json.load(sys.stdin)
    except ValueError:
        pass
    absent = missing()
    if not absent:
        return 0
    lines = ["⚠ trilho · falta nesta máquina um programa que o tr exige:"]
    lines += [f"  · `{name}`: {why}. Instale: {how}" for name, why, how in absent]
    text = "\n".join(lines)
    print(json.dumps({"systemMessage": text, "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": text + "\nTell the owner at the first opportunity; do not work around the missing program."}},
        ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
