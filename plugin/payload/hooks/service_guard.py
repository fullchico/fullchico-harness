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
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

DENY_SKIP = ("Pular os hooks de git (--no-verify, commit -n, core.hooksPath) não é permitido a agentes. "
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
    if skips_hooks(command):
        return DENY_SKIP
    if _CALLED.search(command) and not _EXACT.match(command.strip()):
        return DENY_ALONE
    return None


# --- Leitura do comando ------------------------------------------------------------------------
# O comando é lido como o shell o leria (aspas, redirecionamento, encadeamento), em vez de por
# pedaço de texto: `grep hooksPath` não é pular hook, e `rm "src/a.ts"` é apagar código.
# Não é um interpretador: variável, laço e programa que grava por conta própria passam. A
# barreira de verdade continua sendo o portão do push; isto barra cedo as formas usuais.
_HEREDOC = re.compile(r"(<<-?\s*(['\"]?)(\w+)\2[^\n]*)\n.*?\n[ \t]*\3[ \t]*(?=\n|$)", re.S)
_OPS = {";", "&&", "||", "|", "&", "|&", "(", ")", ";;"}
_OUT = {">", ">>", ">|", "&>", "&>>"}
_IN = {"<", "<<", "<<<", "<<-", ">&", "<&"}
_WRAP = {"command", "sudo", "time", "nohup", "exec", "env", "builtin", "nice", "caffeinate"}
_SHELLS = {"bash", "sh", "zsh", "dash"}


def _segments(command: str, depth: int = 0):
    """Os comandos simples de uma linha: (nome, argumentos, alvos de redirecionamento). None se ilegível."""
    lexer = shlex.shlex(_HEREDOC.sub(r"\1", command).replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    found, words, made = [], [], []

    def close():
        nonlocal words, made
        while words and (re.match(r"^\w+=", words[0]) or os.path.basename(words[0]) in _WRAP):
            words = words[1:]
        if words:
            name, args = os.path.basename(words[0]), words[1:]
            inner = None
            if name in _SHELLS and "-c" in args and args.index("-c") + 1 < len(args):
                inner = args[args.index("-c") + 1]
            elif name == "eval":
                inner = " ".join(args)
            nested = _segments(inner, depth + 1) if inner is not None and depth < 4 else None
            found.extend(nested if nested else [(name, args, made)])
        elif made:
            found.append(("", [], made))
        words, made = [], []

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _OPS:
            close()
        elif token in _OUT or token in _IN:
            if token in _OUT and index + 1 < len(tokens):
                made.append(tokens[index + 1])
            index += 1
        else:
            words.append(token)
        index += 1
    close()
    return found


_COMMIT_VALUE = set("mFCct")  # opções curtas do commit que levam valor: o próximo argumento não é opção


def skips_hooks(command: str) -> bool:
    """O comando pula os hooks de git: `--no-verify`, `commit -n`, ou mexe em `core.hooksPath`."""
    segments = _segments(command)
    if segments is None:  # ilegível: vale o texto, como antes
        lowered = command.lower()
        return "--no-verif" in lowered or "hookspath" in lowered
    for name, args, made in segments:
        lowered = [a.lower() for a in args]
        if any(t.rstrip("/").endswith((".git/config", ".git/hooks")) or "/.git/hooks/" in t for t in list(made) + (
                args if name in ("sed", "perl", "rm", "mv", "cp", "tee", "ln", "truncate", "chmod") else [])):
            return True
        if name != "git":
            continue
        index, sub = 0, None
        while index < len(args):  # opções globais do git, antes do subcomando
            if args[index] == "-c" and index + 1 < len(args):
                if lowered[index + 1].startswith("core.hookspath"):
                    return True
                index += 2
            elif args[index] in ("-C", "--git-dir", "--work-tree") and index + 1 < len(args):
                index += 2
            elif args[index].startswith("-"):
                index += 1
            else:
                sub = args[index]
                break
        rest = args[index + 1:] if sub else []
        if sub == "config":
            reading = any(a in ("--get", "--get-all", "--get-regexp", "-l", "--list") for a in rest)
            if any("core.hookspath" in a.lower() for a in rest) and not reading:
                return True
        if sub in ("commit", "push", "merge", "pull", "am", "rebase", "cherry-pick", "revert"):
            skip = False
            for arg in rest:
                if skip:
                    skip = False
                    continue
                if arg == "--":
                    break
                if arg.lower().startswith("--no-verif"):
                    return True
                if sub == "commit" and re.match(r"^-[a-zA-Z]+$", arg):
                    if "n" in arg[1:]:
                        return True
                    skip = arg[-1] in _COMMIT_VALUE
                elif sub == "commit" and arg in ("--message", "--file", "--author", "--date", "--reuse-message"):
                    skip = True
    return False


_SED_INPLACE = re.compile(r"^(?:--in-place.*|-[nEr]*i.*)$")
_PERL_INPLACE = re.compile(r"^-[pnlae0]*i.*$")
_REMOVES = {"rm", "unlink", "truncate", "shred"}
_CREATES = {"tee", "touch"}


def writes_code(command: str, cwd: str) -> bool:
    segments = _segments(command)
    if not segments:
        return False
    where = cwd
    for name, args, made in segments:
        if name == "cd":
            if args:
                where = os.path.join(where, os.path.expanduser(args[0]))
            continue
        plain = [a for a in args if a and not a.startswith("-")]
        made, touched = list(made), []
        if name == "git":
            rest = list(plain)
            while rest and rest[0] not in ("mv", "rm", "apply", "checkout", "restore", "am", "stash"):
                rest = rest[1:]
            sub, paths = (rest[0], rest[1:]) if rest else (None, [])
            if sub in ("mv", "rm", "checkout", "restore"):
                touched = paths
                made += paths[-1:] if sub == "mv" else []
            elif sub == "apply" and not any(a in ("--check", "--stat", "--numstat", "--summary") for a in args):
                made.append("__patch__.code")  # o remendo grava onde quiser: vale como código neste worktree
        elif name == "sed" and any(_SED_INPLACE.match(a) for a in args):
            touched = plain
        elif name == "perl" and any(_PERL_INPLACE.match(a) for a in args):
            touched = plain
        elif name in _REMOVES or name == "mv":
            touched = plain
            made += plain[-1:] if name == "mv" else []
        elif name in _CREATES:
            made += plain
        elif name in ("cp", "install", "ln", "rsync"):
            made += plain[-1:]
        elif name == "dd":
            made += [a[3:] for a in args if a.startswith("of=")]
        elif name in ("curl", "wget"):
            made += [args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-o", "--output", "-O", "--output-document")]
        # Caminho com variável não se resolve aqui: é quase sempre a pasta temporária.
        made = [t for t in made if "$" not in t and not t.startswith(("&", "/dev/"))]
        touched = [t for t in touched if "$" not in t]
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
CHECKS = ("VALIDATE_PUSH", "VALIDATE_MERGE", "VALIDATE_ARCH", "MODULE_ROOTS", "CONTRACT_PATHS", "TOKENS_CSS")
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
    common.watch("service_guard", cwd)
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
