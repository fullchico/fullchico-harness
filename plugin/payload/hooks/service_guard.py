#!/usr/bin/env python3
"""PreToolUse (Bash): o que um agente não pode tocar pela linha de comando.

Neste arquivo: o estado dos portões de push, os arquivos do harness no projeto e
os atalhos que pulam os hooks de git. As regras de serviço e de porta entram
aqui no plano de ambiente.

A checagem é sobre o texto inteiro do comando, sem tentar entender o shell:
`bash -c`, `eval`, variável ou `cd` antes não escondem nada. O preço é negar
também quem só cita esses nomes; para ler esses arquivos existe a ferramenta de
leitura. Qualquer erro do próprio hook vira negação, nunca liberação.
"""
import json
import os
import re
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

DENY_STATE = ("O estado dos portões de push e a configuração do git não são alterados por agente. "
              "A aprovação nasce do veredito do revisor; o carimbo manual (.harness/approve) é do "
              "dono, no terminal.")
DENY_SKIP = ("Pular os hooks de git (--no-verify, core.hooksPath, HUSKY=) não é permitido a "
             "agentes. Se o push foi negado, corrija o motivo; a exceção é do dono.")
DENY_HARNESS = ("Os arquivos do harness (.harness/, harness.conf, harness.d/, "
                ".claude/settings*.json) não são tocados por agente pela linha de comando. "
                "Para ler, use a ferramenta de leitura. Para rodar, só os comandos do harness: "
                ".harness/validate, up, dev, down, destroy, memory. Mudança de padrão é no "
                "repositório do harness; harness.conf é do dono.")

SKIP = ("--no-verif", "hookspath", "husky=")
STATE = ("harness/approvals", ".git/harness", ".git/config", ".git/hooks")
# Executáveis do harness que o agente pode chamar; o resto de .harness/ é negado.
ALLOWED = re.compile(r"(?<![\w./-])(?:\./)?\.harness/(?:validate|up|dev|down|destroy|memory)(?![\w./-])")
# harness.conf e harness.d na raiz do projeto (não um arquivo de mesmo nome em outra pasta).
ROOT_CONF = re.compile(r"(?<![\w/-])(?:\./)?harness\.(?:conf|d)(?![\w-])")
SETTINGS = re.compile(r"\.claude/settings[\w.]*\.json")


def classify(command: str, cwd=None):
    lowered = command.lower()
    if any(mark in lowered for mark in SKIP):
        return DENY_SKIP
    if any(mark in lowered for mark in STATE):
        return DENY_STATE
    for path in (common.git_dirs(cwd) if cwd else []):
        if path in command:
            return DENY_STATE
    if ".harness" in ALLOWED.sub("", command):
        return DENY_HARNESS
    if ROOT_CONF.search(command) or SETTINGS.search(command):
        return DENY_HARNESS
    root = common.repo_root(cwd) if cwd else None
    if root and any(os.path.join(root, name) in command for name in ("harness.conf", "harness.d")):
        return DENY_HARNESS
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        common.deny("service-guard: entrada do hook inválida; comando negado.")
    if not isinstance(payload, dict):
        common.deny("service-guard: entrada do hook inválida; comando negado.")
    if payload.get("tool_name") != "Bash":
        return
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        common.deny("service-guard: comando ausente na entrada do hook; negado.")
    cwd = payload.get("cwd")
    reason = classify(command, cwd if isinstance(cwd, str) else None)
    if reason:
        common.deny(reason)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # falha do guard nunca libera
        common.deny(f"service-guard: erro interno ({exc}); comando negado.")
