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
_OUTSIDE = "up|down|destroy|conf-apply|push|fetch|pr|skills-search|skills-show|skills-add|ports-free|logs"
_CALLED = re.compile(rf"(?:^|[;&|(\n]|\b(?:bash|sh|zsh|exec|env|source)\s)\s*(?:[\w./-]*/)?\.harness/(?:{_OUTSIDE})(?=\s|$|[;&|)<>])")
_EXACT = re.compile(r"^(?:\./)?\.harness/(?:(?:up|down|destroy|conf-apply|fetch|push|ports-free)|push --force|logs(?: \w[\w-]*)?|(?:pr|skills-search|skills-show|skills-add)(?: [^\n;&|`$<>]*)?)$")
DENY_ALONE = ("Os scripts do harness que saem do sandbox rodam sozinho, um por chamada, na forma exata "
              "(`.harness/up`, `.harness/conf-apply`, `.harness/push`, `.harness/fetch`, `.harness/ports-free`, `.harness/logs`, `.harness/pr ...`): "
              "sem `&&`, `;`, `|`, redirecionamento nem `bash` na frente. Rode os outros comandos numa chamada separada.")


# Revisor roda no worktree da feature, que o orquestrador e os outros revisores também usam.
# Trocar o commit dele no meio deixa a feature fora da branch: um commit nessa hora se perde.
REVIEWERS = ("harness:revisor-bugs", "harness:revisor-ambiente", "harness:revisor", "harness:seguranca",
             "harness:qualidade", "harness:revisor-spec")
_MOVES = re.compile(r"\bgit\b(?:\s+-C\s+\S+|\s+-c\s+\S+)*\s+(?:checkout|switch|reset|restore|stash|clean)\b")
DENY_MOVE = ("Revisor não muda o commit nem os arquivos deste worktree: ele é da feature inteira. "
             "Para ler o código de outro commit use `git show <commit>:<arquivo>` e `git diff`. Para rodar os "
             "testes da branch de um implementador, entre no worktree dele: `git worktree list` mostra o caminho.")


# Ambiente, remoto e pull request são de quem conduz a entrega. Implementador e revisor não
# sobem nem derrubam nada, e não enviam.
_CONDUCTOR = re.compile(r"(?:^|[\s;&|(/])\.harness/(?:up|down|destroy|dev|push|pr)(?=\s|$|[;&|)])")
DENY_CONDUCTOR = ("Subir, parar ou remover o ambiente, rodar o aplicativo, enviar e abrir pull request são do "
                  "orquestrador e do dono. Você trabalha com o ambiente que já está de pé; se falta algo, relate.")
# Quem junta é o .harness/integrate: ele confere a posse, a revisão e a checagem, e desfaz se falhar.
_JOINS = re.compile(r"\bgit\b(?:\s+-C\s+\S+|\s+-c\s+\S+)*\s+(?:merge|rebase|cherry-pick)\b(?!\s+--abort)")
DENY_JOIN = ("O orquestrador não junta branch à mão (`git merge`, `rebase`, `cherry-pick`) nem resolve conflito: "
             "use `.harness/integrate <ticket> <branch>`. Conflito mostra que o fatiamento está errado.")


def classify(command: str, cwd=None):
    lowered = command.lower()
    if any(mark in lowered for mark in SKIP):
        return DENY_SKIP
    if _CALLED.search(command) and not _EXACT.match(command.strip()):
        return DENY_ALONE
    return None


# Escrita de código por fora da ferramenta de edição: redirecionamento e os comandos que alteram
# arquivo no lugar. Não é análise completa de shell: pega as formas usuais, e o push continua
# exigindo a spec de toda `feat`.
_HEREDOC = re.compile(r"<<-?\s*['\"]?\w+['\"]?[^\n]*")
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
_REDIRECT = re.compile(r"(?<![0-9&>])>>?\s*([^\s;&|()<>]+)")
_SPLIT = re.compile(r"\s*(?:&&|\|\||[;|\n])\s*")
_CD = re.compile(r"^\s*cd\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))\s*(?:&&|;)")
_INPLACE = re.compile(r"^-(?:-in-place|[a-zA-Z]*i[a-zA-Z]*)$")


def writes_code(command: str, cwd: str) -> bool:
    heredoc = _HEREDOC.search(command)
    head = _QUOTED.sub(" Q ", command[:heredoc.end()] if heredoc else command)
    where = cwd
    first = _CD.match(command)  # os agentes costumam abrir com `cd <pasta> &&`, às vezes entre aspas
    if first:
        where = os.path.join(cwd, os.path.expanduser(next(g for g in first.groups() if g)))
    for segment in _SPLIT.split(head):
        made = [t for t in _REDIRECT.findall(segment) if not t.startswith(("&", "/dev/"))]
        tokens = _REDIRECT.sub(" ", segment).split()
        if not tokens:
            continue
        if tokens[0] == "cd":
            continue
        name, args = os.path.basename(tokens[0]), [t for t in tokens[1:] if not t.startswith("-")]
        touched = []
        if name == "git" and len(tokens) > 2 and tokens[1] in ("mv", "rm", "apply"):
            touched, made = args[1:], made + (args[-1:] if tokens[1] == "mv" else [])
        elif name in ("sed", "perl") and any(_INPLACE.match(t) for t in tokens[1:]):
            touched = args
        elif name in ("rm", "mv"):
            touched, made = args, made + (args[-1:] if name == "mv" else [])
        elif name in ("tee", "cp"):
            made += args if name == "tee" else args[-1:]
        # Caminho com variável não se resolve aqui: é quase sempre a pasta temporária.
        made, touched = [t for t in made if "$" not in t], [t for t in touched if "$" not in t]
        if any(common.is_code(where, t) for t in made):
            return True
        if any(os.path.exists(os.path.join(where, os.path.expanduser(t))) and common.is_code(where, t) for t in touched):
            return True
    return False


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
CHECKS = ("VALIDATE_PUSH", "VALIDATE_MERGE", "VALIDATE_ARCH", "MODULE_ROOTS", "CONTRACT_PATHS")
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
    proposed = common.read_conf(proposal)
    # Checagem já gravada não some nem fica vazia: senão o agente que não passa nela a desliga.
    current = common.read_conf(os.path.join(root, "harness.conf"))
    for key in CHECKS:
        if current.get(key) and not proposed.get(key):
            common.deny(f"conf-apply: a proposta remove ou esvazia {key}, que já está no harness.conf. "
                        "Uma checagem gravada pode mudar de comando, não sumir. Se ela falha, o que se corrige "
                        "é o código ou o ticket; desligar é decisão do dono, à mão.")
    profile = proposed.get("PROFILE") or common.read_conf(os.path.join(root, "harness.conf")).get("PROFILE") or "fullstack-typescript"
    if profile == "fullstack-typescript" and not proposed.get("MODULE_ROOTS"):
        common.deny("conf-apply: a proposta precisa trazer MODULE_ROOTS, a pasta dos módulos do back "
                    '(por exemplo MODULE_ROOTS="apps/api/src/modules"). É por ela que o harness confere que um '
                    "módulo não entra por dentro de outro.")
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
    agent = payload.get("agent_type")
    if agent in REVIEWERS and _MOVES.search(command):
        common.deny(DENY_MOVE)
    if isinstance(agent, str) and agent != "harness:orquestrador" and _CONDUCTOR.search(command):
        common.deny(DENY_CONDUCTOR)
    if agent == "harness:orquestrador" and _JOINS.search(command):
        common.deny(DENY_JOIN)
    reason = classify(command, cwd if isinstance(cwd, str) else None)
    if reason:
        common.deny(reason)
    if isinstance(cwd, str) and writes_code(command, cwd) and not common.direct_open(cwd, payload.get("session_id")):
        common.deny(common.DENY_CODE)
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
