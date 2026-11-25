#!/usr/bin/env python3
"""SessionStart: registra o portão dos plugins ligados no projeto que ainda não está no registro.

Lê `enabledPlugins` do projeto e, de cada plugin ligado, o `gate.json` da versão mais alta no cache
de plugins (`~/.claude/plugins/cache/<marketplace>/<plugin>/<versão>/`). Só ACRESCENTA: entrada que já
existe no registro nunca é tocada (afrouxar é do dono, por `fullchico-harness gates`). Nunca bloqueia.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import gates_cli  # noqa: E402


def version_str(gate_name):
    return tuple(int(n) for n in re.findall(r"\d+", gate_name))


def manifest_data(marketplace, plugin):
    base = os.path.join(os.path.expanduser("~"), ".claude", "plugins", "cache", marketplace, plugin)
    try:
        versions = sorted(os.listdir(base), key=version_str, reverse=True)
    except OSError:
        return {}
    return gates_cli.read_json(os.path.join(base, versions[0], "gate.json")) if versions else {}


def main():
    root = os.environ.get("CLAUDE_PROJECT_DIR") or ""
    if not root:
        return
    enabled_list = []
    for file_name in ("settings.json", "settings.local.json"):
        enabled = gates_cli.read_json(os.path.join(root, ".claude", file_name)).get("enabledPlugins") or {}
        enabled_list += [k for k, v in enabled.items() if v and "@" in k]
    warnings = []
    for key_name in dict.fromkeys(enabled_list):
        plugin, marketplace = key_name.split("@", 1)
        for gate_name in gates_cli.merge(root, manifest_data(marketplace, plugin)):
            ledger.log(root, "tr", "registered", f"portão {gate_name} pelo plugin {plugin}")
            warnings.append(f"portão `{gate_name}` registrado automaticamente pelo plugin `{plugin}`")
    if warnings:
        print(json.dumps({"systemMessage": "; ".join(warnings) + " (veja .claude/harness.json)."}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
