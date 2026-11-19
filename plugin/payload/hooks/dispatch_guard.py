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
    "harness:implementador": ("spec", "ticket"),
    "harness:orquestrador": ("spec",),
}
# O que cada um pode receber. O implementador recebe a spec e o ticket, e numa rodada
# de correção o arquivo com o achado; quem revisa recebe o que vai ler, e mais nada.
ALLOWED = {
    "harness:seguranca": ("diff", "commit", "spec", "leitura"),
    "harness:revisor": ("diff", "commit", "spec", "leitura"),
    "harness:revisor-spec": ("spec", "leitura"),
    "harness:implementador": ("spec", "ticket", "leitura", "achado"),
    # Quem executa a entrega recebe a spec aprovada e nada da conversa de quem a desenhou.
    "harness:orquestrador": ("spec", "leitura"),
}
_LINE = re.compile(r"^(spec|ticket|diff|commit|leitura|achado): (\S.*)$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
# Revisões do git: nomes, caminhos de ref, ~N, ^, @{N}. Nada de espaço, opção ou shell.
_REV = r"[\w./~^@{}-]+"
_DIFF = re.compile(rf"^(?!-){_REV}\.\.\.?(?!-){_REV}$")
FORMAT = ("Pedido a revisor do harness tem formato fixo, uma chave por linha: "
          "`spec: <caminho>`, `ticket: <caminho>`, `diff: <base>...<topo>`, "
          "`commit: <hash de 40 dígitos>`, `leitura: <caminho>, <caminho>`, `achado: <caminho>`. "
          "Sem narrativa nem opinião: o revisor lê os documentos por conta própria.")


def _inside(root: str, value: str) -> bool:
    if os.path.isabs(value) or ".." in value.split("/"):
        return False
    full = os.path.realpath(os.path.join(root, value))
    return full.startswith(os.path.realpath(root) + os.sep) and os.path.exists(full)


def _committed(root: str, value: str) -> bool:
    """O arquivo existe no commit atual, com o mesmo conteúdo que está no disco?"""
    if common._git(root, "cat-file", "-t", "HEAD:" + value) != "blob":
        return False
    import subprocess
    return subprocess.run(["git", "diff", "--quiet", "HEAD", "--", value], cwd=root).returncode == 0


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
    extra = [key for key in seen if key not in ALLOWED[agent]]
    if extra:
        return f"{FORMAT} Este agente não recebe: {', '.join(extra)}."
    missing = [key for key in required if key not in seen]
    if missing:
        return f"{FORMAT} Falta: {', '.join(missing)}."
    for key in ("spec", "ticket", "achado"):
        if key in seen and not _inside(root, seen[key]):
            return f"{FORMAT} `{key}` precisa ser um caminho relativo existente no repositório."
    if agent == "harness:implementador":
        # Ele trabalha num worktree próprio, que só tem o que está em commit.
        for key in ("spec", "ticket", "achado"):
            if key in seen and not _committed(root, seen[key]):
                return (f"`{key}` aponta para um arquivo que ainda não está em commit ({seen[key]}). "
                        "O implementador trabalha num worktree próprio e só enxerga o que foi commitado.")
    if "ticket" in seen:
        issues = os.path.realpath(os.path.join(root, os.path.dirname(seen["spec"]), "issues"))
        if not os.path.realpath(os.path.join(root, seen["ticket"])).startswith(issues + os.sep):
            return f"{FORMAT} `ticket` precisa ser um ticket da mesma spec (na pasta issues/ ao lado dela)."
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


ONLY_ORCHESTRATOR = ("Quem despacha implementador é o `harness:orquestrador`. A sessão do dono desenha "
                     "(entrevista e spec) e entrega a execução a ele, só com o caminho da spec: o modelo "
                     "caro não fatia, não despacha e não integra.")


def chain(agent, caller):
    """Quem pode despachar quem. É o que mantém o modelo caro no desenho e o barato na execução."""
    if agent == "harness:implementador" and caller != "harness:orquestrador":
        return ONLY_ORCHESTRATOR
    if agent == "harness:orquestrador" and caller:
        return "O `harness:orquestrador` é despachado pela sessão do dono, não por um subagente."
    return None


def ready_for_execution(prompt, root):
    """O orquestrador não tem a quem perguntar: o que ele precisa tem de estar na spec, em commit."""
    fields = dict(m.groups() for m in map(_LINE.match, (l.strip() for l in prompt.splitlines())) if m)
    spec = fields["spec"]
    if not _committed(root, spec):
        return (f"A spec ({spec}) precisa estar em commit, igual ao que está no disco: o orquestrador "
                "trabalha só com o que foi commitado.")
    if not common.read_conf(os.path.join(root, "harness.conf")).get("PROJECT"):
        with open(os.path.join(root, spec), encoding="utf-8", errors="replace") as f:
            if "harness.conf" not in f.read():
                return ("Este projeto ainda não tem `harness.conf` preenchido, e a spec não diz o conteúdo dele. "
                        "Acrescente à spec uma seção `harness.conf` com as chaves (PROJECT, SERVICES, COMPOSE_FILE, "
                        "INSTALL_CMD, AFTER_UP, DEV_CMD, VALIDATE_PUSH, VALIDATE_MERGE, ENV_*) e faça o commit.")
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
    reason = chain(agent, payload.get("agent_type")) or check(agent, tool_input.get("prompt"), root)
    if not reason and agent == "harness:orquestrador":
        reason = ready_for_execution(tool_input.get("prompt"), root)
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
