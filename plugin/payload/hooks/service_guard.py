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
import subprocess
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

DENY_SKIP = ("Pular os hooks de git (--no-verify, core.hooksPath) não é permitido a agentes. "
             "Se o push foi negado, corrija o motivo; a exceção é do dono.")
SKIP = ("--no-verif", "hookspath")


def classify(command: str, cwd=None):
    lowered = command.lower()
    if any(mark in lowered for mark in SKIP):
        return DENY_SKIP
    return None


ENV_FORMS = {prefix + name: name for name in ("up", "down", "destroy") for prefix in (".harness/", "./.harness/")}
PAYLOAD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def env_reason(action: str, cwd: str) -> str:
    """Texto que o dono lê ao decidir se o ambiente sobe, para ou é removido."""
    root = common.repo_root(cwd) or cwd
    values = {}
    try:
        printed = subprocess.run([os.path.join(PAYLOAD, "worktree-env"), "--print"], cwd=root,
                                 capture_output=True, text=True, timeout=20)
        values = dict(line.split("=", 1) for line in printed.stdout.splitlines() if "=" in line)
    except (OSError, subprocess.SubprocessError):
        pass
    project = values.get("COMPOSE_PROJECT_NAME", "desta feature")
    if action == "down":
        return f"Parar o app e os contêineres do ambiente {project}. Os dados são mantidos."
    if action == "destroy":
        return (f"Remover o ambiente {project}: contêineres, volumes e imagens locais. "
                "Isso apaga os dados do banco desse ambiente.")
    head = f"Subir o ambiente {project}. O comando roda fora do sandbox e só sobe a infra."
    compose_file = common.read_conf(os.path.join(root, "harness.conf")).get("COMPOSE_FILE", "")
    try:
        config = subprocess.run(["docker", "compose", "-p", project, "-f", os.path.join(root, compose_file),
                                 "config", "--format", "json"], cwd=root, capture_output=True, text=True,
                                timeout=20, env=dict(os.environ, **values))
        if config.returncode != 0 or not compose_file:
            raise ValueError("docker compose config falhou")
        sys.path.insert(0, PAYLOAD)
        import compose_check
        parsed = json.loads(config.stdout)
        lines = [head, compose_check.summary(parsed, root)]
        problems = compose_check.violations(parsed, root)
        if problems:
            lines.append("ATENÇÃO, o script vai recusar este compose: " + "; ".join(problems))
        return "\n".join(lines)
    except Exception:
        return head + " Não consegui resumir o compose; o script confere e mostra o resumo ao rodar."


CONF_FORMS = (".harness/conf-apply", "./.harness/conf-apply")
CONF_LIMIT = 4000
CONF_HEAD = ("Gravar o harness.conf deste projeto com o conteúdo abaixo, proposto pelo agente. "
             "Atenção: os comandos dele (instalação, migration, checagens) rodam fora do sandbox.")


def conf_question(cwd: str) -> str:
    """Confere a proposta, guarda a cópia que o dono vai ver e devolve o texto da pergunta.

    O script grava essa cópia, e não o arquivo do agente: o que é aplicado é o que foi mostrado.
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
    return f"{CONF_HEAD}\n\n{text}"


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
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": conf_question(cwd),
        }}, ensure_ascii=False))
        return
    action = ENV_FORMS.get(command.strip())
    if action and isinstance(cwd, str):
        # A pergunta em si vem da regra nativa permissions.ask, que vale em todo modo.
        # Aqui só se acrescenta o que o dono precisa ler para decidir.
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": env_reason(action, cwd),
        }}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # falha do guard nunca libera
        common.deny(f"service-guard: erro interno ({exc}); comando negado.")
