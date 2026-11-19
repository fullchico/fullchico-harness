#!/usr/bin/env python3
"""PreToolUse (Bash): pular os hooks de git não é permitido a agentes.

A barreira de escrita é o sandbox do Bash, imposto pelo sistema operacional: é
ele que impede gravar em .harness/, harness.conf e no estado dos portões, por
qualquer comando, script ou heredoc. Este guard cuida só do que não é escrita:
os argumentos que fazem o git ignorar os hooks.

A checagem é sobre o texto inteiro do comando, então `bash -c` e `eval` não
escondem nada. As regras de serviço e de porta entram aqui no plano de ambiente.
Qualquer erro do próprio hook vira negação, nunca liberação.
"""
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

DENY_SKIP = ("Pular os hooks de git (--no-verify, core.hooksPath) não é permitido a agentes. "
             "Se o push foi negado, corrija o motivo; a exceção é do dono.")
SKIP = ("--no-verif", "hookspath")


# Os scripts que saem do sandbox. Só a forma exata é excluída dele: encadeados ou embrulhados,
# rodariam dentro do sandbox e falhariam sem dizer o motivo (Docker e remoto inalcançáveis).
_OUTSIDE = "up|down|destroy|conf-apply|push|fetch|pr"
_CALLED = re.compile(rf"(?:^|[;&|(\n]|\b(?:bash|sh|zsh|exec|env|source)\s)\s*(?:[\w./-]*/)?\.harness/(?:{_OUTSIDE})(?=\s|$|[;&|)<>])")
_EXACT = re.compile(r"^(?:\./)?\.harness/(?:(?:up|down|destroy|conf-apply|fetch|push)|push --force|pr(?: [^\n;&|`$<>]*)?)$")
DENY_ALONE = ("Os scripts do harness que saem do sandbox rodam sozinho, um por chamada, na forma exata "
              "(`.harness/up`, `.harness/conf-apply`, `.harness/push`, `.harness/fetch`, `.harness/pr ...`): "
              "sem `&&`, `;`, `|`, redirecionamento nem `bash` na frente. Rode os outros comandos numa chamada separada.")


def classify(command: str, cwd=None):
    lowered = command.lower()
    if any(mark in lowered for mark in SKIP):
        return DENY_SKIP
    if _CALLED.search(command) and not _EXACT.match(command.strip()):
        return DENY_ALONE
    return None


DESTROY_FORMS = (".harness/destroy", "./.harness/destroy")
PAYLOAD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def destroy_reason(cwd: str) -> str:
    """Texto que o dono lê ao decidir se o ambiente é removido. É a única pergunta do ambiente:
    subir e parar não apagam nada, e o compose é conferido pelo próprio script."""
    root = common.repo_root(cwd) or cwd
    project = "desta feature"
    try:
        printed = subprocess.run([os.path.join(PAYLOAD, "worktree-env"), "--print"], cwd=root,
                                 capture_output=True, text=True, timeout=20)
        values = dict(line.split("=", 1) for line in printed.stdout.splitlines() if "=" in line)
        project = values.get("COMPOSE_PROJECT_NAME", project)
    except (OSError, subprocess.SubprocessError):
        pass
    return (f"Remover o ambiente {project}: contêineres, volumes e imagens locais. "
            "Isso apaga os dados do banco desse ambiente.")


CONF_FORMS = (".harness/conf-apply", "./.harness/conf-apply")
CONF_LIMIT = 4000


def conf_check(cwd: str) -> None:
    """Confere a proposta de harness.conf e guarda a cópia conferida onde o agente não grava.

    O script aplica essa cópia, e não o arquivo do agente: o que é gravado é o que foi conferido.
    Não há pergunta ao dono: o arquivo é versionado, e chega aos revisores no diff da entrega.
    """
    root = common.repo_root(cwd)
    if not root:
        common.deny("conf-apply: fora de um repositório git.")
    proposal = os.path.join(root, ".harness-run", "harness.conf")
    if os.path.islink(proposal) or not os.path.isfile(proposal):
        common.deny("conf-apply: escreva antes a proposta em .harness-run/harness.conf.")
    with open(proposal, encoding="utf-8") as f:
        text = f.read(CONF_LIMIT + 1)
    if len(text) > CONF_LIMIT:
        common.deny(f"conf-apply: a proposta passa de {CONF_LIMIT} caracteres.")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not common._CONF_LINE.match(stripped):
            common.deny(f"conf-apply: linha fora do formato CHAVE=valor: {stripped[:80]}")
    if not common.read_conf(proposal).get("PROJECT"):
        common.deny("conf-apply: a proposta precisa trazer PROJECT.")
    target = common.conf_approval_path(root)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = f"{target}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, target)


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
    if command.strip() in CONF_FORMS and isinstance(cwd, str):
        conf_check(cwd)
    elif command.strip() in DESTROY_FORMS and isinstance(cwd, str):
        # A pergunta em si vem da regra nativa permissions.ask, que vale em todo modo.
        # Aqui só se acrescenta o que o dono precisa ler para decidir.
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": destroy_reason(cwd),
        }}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # falha do guard nunca libera
        common.deny(f"service-guard: erro interno ({exc}); comando negado.")
