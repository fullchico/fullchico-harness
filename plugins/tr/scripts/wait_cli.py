#!/usr/bin/env python3
"""`tr-harness wait [--seconds N] [--stale N]`: a sessão principal vigia o trem.

O orquestrador é um subagente: dispara os executores e fica parado até voltarem, então não percebe um travado.
Sai com 0 quando o trem parou (nenhum executor em voo, nenhum orquestrador ativo), 4 quando um executor travou
(sem usar ferramenta há `--stale` segundos; o socorro é da sessão principal) e 3 no fim do prazo, ainda rodando
(chame de novo). O prazo padrão cabe numa chamada de terminal."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import registry  # noqa: E402
import tasks  # noqa: E402


def main(argv):
    seconds, stale = 540, tasks.STALE_WAIT
    try:
        for flag, value in zip(argv[::2], argv[1::2]):
            if flag == "--seconds":
                seconds = int(value)
            elif flag == "--stale":
                stale = int(value)
            else:
                raise ValueError(flag)
    except ValueError:
        print("uso: tr-harness wait [--seconds N] [--stale N]", file=sys.stderr)
        return 2
    code, state = tasks.wait(registry.toplevel(os.getcwd()), seconds, stale)
    print(json.dumps(state, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
