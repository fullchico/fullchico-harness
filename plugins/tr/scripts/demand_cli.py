#!/usr/bin/env python3
"""`tr-harness demand open <slug> [--base <ref>]` | `demand list` | `demand path <slug>`.

A estação e os trens: o maestro (a sessão com quem o dono conversa) fica na pasta em que foi aberto, a estação.
Cada demanda viaja num worktree filho, com a sua branch e o seu orquestrador; ao chegar, o resultado volta para
o pai. Assim nenhum trem viaja na estação, e os commits de uma demanda nunca derrubam os certificados de outra.

`open` cria o worktree filho com o Git, ao lado desta pasta, nascido da branch dela (`--base` para outra base), e diz o
caminho: o maestro entra nele (EnterWorktree) para a entrevista, o plano, o aceite e a partida, e sai de volta
para a estação. `list` mostra os trens deste repositório; `path` devolve a pasta de um."""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import certs  # noqa: E402
import registry  # noqa: E402
import tasks  # noqa: E402

SLUG = r"[a-z0-9][a-z0-9-]*"


def _flag(argv, name):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def trains(root):
    """[(pasta, branch, demanda)] dos worktrees deste repositório, menos os dos executores."""
    out = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=root, capture_output=True, text=True).stdout
    found, path = [], None
    for line in out.splitlines() + [""]:
        if line.startswith("worktree "):
            path, branch = line[9:], ""
        elif line.startswith("branch "):
            branch = line[7:].replace("refs/heads/", "")
        elif not line and path:
            if "/.claude/worktrees/" not in path:
                found.append((path, branch, certs.demand(path)))
            path = None
    return found


def path_of(root, slug):
    """A pasta da demanda: a que a marca em `.claude/current-demand`, ou a da branch `<prefixo>/<slug>` recém-aberta."""
    rows = trains(root)
    for path, _branch, demand in rows:
        if demand == slug and os.path.realpath(path) != os.path.realpath(root):
            return path
    for path, branch, demand in rows:
        if demand == slug or branch == slug or branch.endswith("/" + slug):
            return path
    return None


def main(argv):
    root = registry.toplevel(os.getcwd())
    if argv[:1] == ["list"]:
        for path, branch, demand in trains(root):
            here = " (esta pasta)" if os.path.realpath(path) == os.path.realpath(root) else ""
            driving = "com orquestrador registrado" if demand and os.path.isfile(
                tasks.coordination(path, "orchestrator.json")) else "sem orquestrador"
            print(f"{demand or '(sem demanda)'} · {branch or '(sem branch)'} · {path}{here} · {driving}")
        return 0
    if argv[:1] == ["path"] and len(argv) == 2:
        found = path_of(root, argv[1])
        if not found:
            print(f"nenhum worktree deste repositório é da demanda `{argv[1]}` (`tr-harness demand list`)", file=sys.stderr)
            return 1
        print(found)
        return 0
    if len(argv) < 2 or argv[0] != "open" or not re.fullmatch(SLUG, argv[1]):
        print("uso: tr-harness demand open <slug-em-minúsculas> [--base <ref>] | demand list | demand path <slug>",
              file=sys.stderr)
        return 2
    slug = argv[1]
    if path_of(root, slug):
        print(f"a demanda `{slug}` já tem pasta: {path_of(root, slug)}", file=sys.stderr)
        return 1
    current = subprocess.run(["git", "branch", "--show-current"], cwd=root, capture_output=True, text=True).stdout.strip()
    base = _flag(argv, "--base") or current  # a filha nasce da branch do pai e volta para ela por merge
    if not base:
        print("sem branch atual: informe `--base <ref>`", file=sys.stderr)
        return 2
    prefix = current.rsplit("/", 1)[0] + "/" if "/" in current else ""
    path = os.path.join(os.path.dirname(os.path.realpath(root)), slug)
    if os.path.exists(path):
        print(f"a pasta {path} já existe: escolha outro slug", file=sys.stderr)
        return 1
    run = subprocess.run(["git", "worktree", "add", "-b", prefix + slug, path, base], cwd=root, capture_output=True, text=True)
    if run.returncode:
        print(f"o Git não criou o worktree da demanda: {(run.stderr or run.stdout).strip()[-300:]}", file=sys.stderr)
        return 1
    if os.path.isdir(os.path.join(path, ".claude")):
        # a filha herda o ponteiro da branch de onde nasceu: sem isto ela dividiria o estado do trem da mãe
        with open(os.path.join(path, ".claude", "current-demand"), "w", encoding="utf-8") as stream:
            stream.write(slug + "\n")
    print(f"demanda `{slug}` aberta em {path}, na branch {prefix + slug} (sobre {base}), filha desta pasta; ao chegar, volta para {base} por merge.\n"
          f"Entre nela com EnterWorktree (path: {path}) para a entrevista, o plano, o aceite e a partida; depois "
          "volte para a estação com ExitWorktree (action: keep). Da estação, acompanhe com "
          f"`tr-harness --demand {slug} status` e `tr-harness --demand {slug} orchestrate --status|--read|--stop`.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
