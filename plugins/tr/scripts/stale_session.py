#!/usr/bin/env python3
"""PostToolUse: a sessão roda uma versão do tr mais velha que a instalada? Avisa o dono uma vez por sessão.

A sessão carrega o plugin quando abre; atualizar no terminal não chega nela. Sem o aviso, ela segue batendo
em defeitos já corrigidos."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import certs  # noqa: E402
import ledger  # noqa: E402
import registry  # noqa: E402
import render  # noqa: E402


def _v(text):
    return tuple(int(n) for n in text.split(".")) if re.fullmatch(r"\d+(\.\d+)*", text or "") else None


def main():
    payload = json.load(sys.stdin)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    running = _v(certs.version())
    installed = [v for v in (_v(d) for d in os.listdir(os.path.dirname(here))) if v]
    if not running or not installed or max(installed) <= running:
        return 0
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    marker = os.path.join(ledger.state_dir(root), "stale-" + re.sub(r"[^\w-]", "", payload.get("session_id") or "x"))
    if os.path.exists(marker):
        return 0
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    open(marker, "w").close()
    newest = ".".join(map(str, max(installed)))
    return render.warn(f"⚠ trilho · esta sessão roda o tr {certs.version()}, mas o {newest} já está instalado: "
                       "abra uma sessão nova para usar a versão atual")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
