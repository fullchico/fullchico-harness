#!/usr/bin/env python3
"""SessionStart: registra o portão dos plugins ligados no projeto que ainda não está no registro.

Lê `enabledPlugins` do projeto e, de cada plugin ligado, o `portao.json` da versão mais alta no cache
de plugins (`~/.claude/plugins/cache/<marketplace>/<plugin>/<versão>/`). Só ACRESCENTA: entrada que já
existe no registro nunca é tocada (afrouxar é do dono, por `fullchico-harness portoes`). Nunca bloqueia.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import portoes  # noqa: E402


def versao(nome):
    return tuple(int(n) for n in re.findall(r"\d+", nome))


def manifesto(marketplace, plugin):
    base = os.path.join(os.path.expanduser("~"), ".claude", "plugins", "cache", marketplace, plugin)
    try:
        versoes = sorted(os.listdir(base), key=versao, reverse=True)
    except OSError:
        return {}
    return portoes.read_json(os.path.join(base, versoes[0], "portao.json")) if versoes else {}


def main():
    root = os.environ.get("CLAUDE_PROJECT_DIR") or ""
    if not root:
        return
    ligados = []
    for arquivo in ("settings.json", "settings.local.json"):
        enabled = portoes.read_json(os.path.join(root, ".claude", arquivo)).get("enabledPlugins") or {}
        ligados += [k for k, v in enabled.items() if v and "@" in k]
    avisos = []
    for chave in dict.fromkeys(ligados):
        plugin, marketplace = chave.split("@", 1)
        for nome in portoes.mesclar(root, manifesto(marketplace, plugin)):
            ledger.log(root, "trilho", "registrou", f"portão {nome} pelo plugin {plugin}")
            avisos.append(f"portão `{nome}` registrado automaticamente pelo plugin `{plugin}`")
    if avisos:
        print(json.dumps({"systemMessage": "; ".join(avisos) + " (veja .claude/trilho.json)."}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
