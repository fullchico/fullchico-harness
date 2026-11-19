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
