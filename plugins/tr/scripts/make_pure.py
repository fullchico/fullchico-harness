#!/usr/bin/env python3
"""Marca um projeto como puro e traz do global só a ferramenta pessoal, para o escopo local.

O modo puro carrega o escopo do projeto (versionado) e o local (`.claude/settings.local.json`, da
máquina de quem usa). Do `~/.claude/settings.json` vêm só os hooks que são ferramenta pessoal, como
o do Orca e o do rtk, e a statusline; plugins, skills e o resto do global ficam de fora. Só lê o
global: nada é alterado lá. O arquivo local não vai para o repositório.

Uso: make_pure.py <raiz do projeto>
"""
import json
import os
import subprocess
import sys

PERSONAL = (".orca/agent-hooks", "orca_agent_hook", "rtk hook")


def personal(command: str) -> bool:
    return isinstance(command, str) and any(mark in command.lower() for mark in PERSONAL)


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def main(root: str) -> int:
    root = os.path.abspath(root)
    folder = os.path.join(root, ".claude")
    os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, "puro"), "a").close()
    user = load(os.path.expanduser("~/.claude/settings.json"))
    local_path = os.path.join(folder, "settings.local.json")
    local = load(local_path)
    hooks = local.get("hooks") if isinstance(local.get("hooks"), dict) else {}
    copied = []
    for event, groups in (user.get("hooks") or {}).items():
        # O mesmo comando (o do Orca) vale em vários eventos: a repetição se confere por evento.
        known = {h.get("command") for g in hooks.get(event, []) for h in g.get("hooks", [])}
        for group in groups or []:
            keep = [h for h in group.get("hooks", []) if personal(h.get("command")) and h.get("command") not in known]
            if keep:
                hooks.setdefault(event, []).append({**{k: v for k, v in group.items() if k != "hooks"}, "hooks": keep})
                known |= {h["command"] for h in keep}
                copied += [f"{event}: {h['command'][:60]}" for h in keep]
    if hooks:
        local["hooks"] = hooks
    if "statusLine" in user and "statusLine" not in local:
        local["statusLine"] = user["statusLine"]
        copied.append("statusLine")
    with open(local_path, "w", encoding="utf-8") as f:
        json.dump(local, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if subprocess.run(["git", "check-ignore", "-q", ".claude/settings.local.json"], cwd=root).returncode != 0:
        with open(os.path.join(root, ".gitignore"), "a", encoding="utf-8") as f:
            f.write("\n.claude/settings.local.json\n")
    print(f"Projeto marcado como puro: {root}")
    print(f"Trazido do global para .claude/settings.local.json ({len(copied)}):" if copied else
          "Nada novo a trazer do global.")
    for line in copied:
        print(f"  {line}")
    print("Abra a sessão com `cc` (no lugar de `claude`): só o projeto e o escopo local entram nela.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
