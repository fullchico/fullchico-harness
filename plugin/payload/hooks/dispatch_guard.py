#!/usr/bin/env python3
"""PreToolUse (Agent): o pedido a um revisor do harness só aponta, não narra.

O documento é a única interface entre quem escreveu e quem revisa. Para os
revisores do harness, cada linha do pedido é `chave: valor`, com chaves fixas.
Os demais agentes não são afetados. Erro do hook vira negação.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

REQUIRED = {
    "harness:seguranca": ("diff", "commit"),
    "harness:revisor": ("diff", "commit"),
    "harness:revisor-spec": ("spec",),
}
_LINE = re.compile(r"^(spec|ticket|diff|commit|leitura): (\S.*)$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
# Revisões do git: nomes, caminhos de ref, ~N, ^, @{N}. Nada de espaço, opção ou shell.
_REV = r"[\w./~^@{}-]+"
_DIFF = re.compile(rf"^(?!-){_REV}\.\.\.?(?!-){_REV}$")
FORMAT = ("Pedido a revisor do harness tem formato fixo, uma chave por linha: "
          "`spec: <caminho>`, `ticket: <caminho>`, `diff: <base>...<topo>`, "
          "`commit: <hash de 40 dígitos>`, `leitura: <caminho>, <caminho>`. "
          "Sem narrativa nem opinião: o revisor lê os documentos por conta própria.")


def _inside(root: str, value: str) -> bool:
    if os.path.isabs(value) or ".." in value.split("/"):
        return False
    full = os.path.realpath(os.path.join(root, value))
    return full.startswith(os.path.realpath(root) + os.sep) and os.path.exists(full)


def check(agent: str, prompt, root):
    required = REQUIRED.get(agent)
    if required is None:
        return None
    if not isinstance(prompt, str) or not root:
        return FORMAT
    seen = {}
    for raw in prompt.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _LINE.match(line)
        if not m or m.group(1) in seen:
            return FORMAT
        seen[m.group(1)] = m.group(2).strip()
    missing = [key for key in required if key not in seen]
    if missing:
        return f"{FORMAT} Falta: {', '.join(missing)}."
    for key in ("spec", "ticket"):
        if key in seen and not _inside(root, seen[key]):
            return f"{FORMAT} `{key}` precisa ser um caminho relativo existente no repositório."
    if "leitura" in seen:
        for item in seen["leitura"].split(","):
            if not _inside(root, item.strip()):
                return f"{FORMAT} `leitura` aponta para um caminho que não existe: {item.strip()}"
    if "commit" in seen and not _SHA.match(seen["commit"]):
        return f"{FORMAT} `commit` precisa ser o hash completo."
    if "diff" in seen and not _DIFF.match(seen["diff"]):
        return f"{FORMAT} `diff` precisa ser um intervalo, como main...HEAD."
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        common.deny("dispatch-guard: entrada do hook inválida; chamada negada.")
    if not isinstance(payload, dict):
        common.deny("dispatch-guard: entrada do hook inválida; chamada negada.")
    if payload.get("tool_name") not in ("Agent", "Task"):
        return
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd")
    root = common.repo_root(cwd) if isinstance(cwd, str) else None
    reason = check(tool_input.get("subagent_type"), tool_input.get("prompt"), root)
    if reason:
        common.deny(reason)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        common.deny(f"dispatch-guard: erro interno ({exc}); chamada negada.")
