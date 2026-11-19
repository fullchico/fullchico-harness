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

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

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
    if "commit" in seen and "diff" in seen:
        return bound(seen["diff"], seen["commit"], root)
    return None


def bound(diff: str, commit: str, root: str):
    """O revisor vê a branch inteira, e é o commit do topo que ele aprova.

    Sem isso, um diff vazio ou parcial renderia uma aprovação que o push lê
    como sendo de tudo o que a branch acrescenta.
    """
    if commit != common.head_sha(root):
        return "`commit` precisa ser o commit atual (HEAD): é ele que a aprovação assina."
    left, right = re.split(r"\.\.\.?", diff, maxsplit=1)
    resolve = lambda rev: common._git(root, "rev-parse", "-q", "--verify", rev + "^{commit}")
    base = common.branch_base(root, commit)
    if not base or base == commit:
        return ("Não há o que revisar: a branch não tem commits além da branch padrão, ou a "
                "branch padrão não foi encontrada (defina DEFAULT_BRANCH no harness.conf).")
    if resolve(right) != commit:
        return "`diff` precisa terminar no commit atual (HEAD)."
    if common._git(root, "merge-base", resolve(left) or "", commit) != base:
        return ("`diff` precisa cobrir a branch inteira, a partir da branch padrão "
                f"(por exemplo {base[:12]}...HEAD).")
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
    agent = tool_input.get("subagent_type")
    reason = check(agent, tool_input.get("prompt"), root)
    if reason:
        common.deny(reason)
    record_request(agent, tool_input.get("prompt"), root)


GATE = {"harness:seguranca": "seguranca", "harness:revisor": "revisao"}


def record_request(agent, prompt, root):
    """Guarda a base do intervalo que o revisor vai ler.

    O push compara essa base com a que o remoto de verdade informa. Assim, mexer
    nas referências locais para mostrar ao revisor só parte da branch não rende
    uma aprovação da branch inteira.
    """
    gate = GATE.get(agent)
    if not gate or not isinstance(prompt, str):
        return
    fields = dict(m.groups() for m in map(_LINE.match, (l.strip() for l in prompt.splitlines())) if m)
    left = re.split(r"\.\.\.?", fields["diff"], maxsplit=1)[0]
    commit = fields["commit"]
    left_sha = common._git(root, "rev-parse", "-q", "--verify", left + "^{commit}")
    base = common._git(root, "merge-base", left_sha, commit)
    path = common.request_path(common.state_dir(root), gate, commit)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"gate": gate, "commit": commit, "base": base, "diff": fields["diff"]}, f)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        common.deny(f"dispatch-guard: erro interno ({exc}); chamada negada.")
