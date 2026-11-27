"""A camada de terminal: tudo que o tr pede a um terminal passa por aqui (hoje, o tmux).

O conceito fica nos comandos do tr: abrir outro agente numa pasta com a instrução, ler a tela dele, encerrá-lo.
O aviso para o nível de cima não vem do terminal: é o relato que o agente grava (`tr-harness report`), e quem
espera olha o arquivo. Se a ferramenta de terminal mudar, troca-se só este arquivo."""
import os
import re
import shlex
import shutil
import subprocess

# telas que só uma pessoa responde: o agente fica parado até lá, então quem vigia leva a tela ao dono
HUMAN = ("Yes, I trust this folder", "Trust and continue", "Hooks need review", "Do you want to proceed",
         "Trust this folder", "Enter to confirm",
         # o CLI recusou o modelo ou a conta: ninguém vai trabalhar ali, e só o dono resolve
         "is not supported when using Codex", "model_not_found", "Invalid model")


class Unavailable(Exception):
    pass


def executable():
    return shutil.which("tmux")


def _run(*args, timeout=30):
    binary = executable()
    if not binary:
        raise Unavailable("o tmux não está no PATH desta máquina (é obrigatório: `brew install tmux` ou o pacote "
                          "`tmux` do sistema)")
    try:
        return subprocess.run([binary, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Unavailable(str(exc))


def name(role, subject, model=None):
    """O nome do terminal diz quem é: `<papel>-<assunto>-<modelo>` (`exec-02-tutores-haiku`, `rev-bugs-sonnet`,
    `orq-clinica-api-opus`). Com `tmux ls` vira o painel da demanda. Se já existe um igual vivo, ganha um número."""
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", "-".join(str(p) for p in (role, subject, model) if p)).strip("-")[:70]
    candidate, n = base, 1
    while alive(candidate):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def plugin_dir():
    """Em desenvolvimento o plugin é carregado de uma pasta (`--plugin-dir`); o agente aberto herda a mesma."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache = os.path.join(os.path.expanduser("~"), ".claude", "plugins", "cache")
    return None if os.path.realpath(here).startswith(os.path.realpath(cache)) or "/.codex/" in here else here


def _git_dir(root):
    run = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root,
                         capture_output=True, text=True)
    return run.stdout.strip() if run.returncode == 0 else None


def _servers_in(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return set(re.findall(r"(?m)^\[mcp_servers\.([A-Za-z0-9_-]+)", stream.read()))
    except OSError:
        return set()


def _codex_servers(root=None):
    """Os conectores MCP do Codex da máquina que o peixe não leva: os do dono, menos os que o projeto registrou
    (`.codex/config.toml` do projeto). Conector é do projeto ou não entra."""
    mine = _servers_in(os.path.join(os.path.expanduser("~"), ".codex", "config.toml"))
    project = _servers_in(os.path.join(root, ".codex", "config.toml")) if root else set()
    return sorted(mine - project)


def command(cli, model, prompt_file, env=None, root=None):
    """A linha que abre o agente com a instrução. O modo de permissão vem de `TR_AGENT_PERMISSION` (padrão `auto`)."""
    env = dict(env or {})
    if os.environ.get("TR_AGENT_PERMISSION"):
        env.setdefault("TR_AGENT_PERMISSION", os.environ["TR_AGENT_PERMISSION"])  # a escolha desce a todos os níveis
    sets = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env.items())
    prompt = f'"$(cat {shlex.quote(prompt_file)})"'
    if cli == "claude":
        mode = os.environ.get("TR_AGENT_PERMISSION") or "auto"
        flags = "--dangerously-skip-permissions" if mode == "bypassPermissions" else f"--permission-mode {shlex.quote(mode)}"
        extra = f" --plugin-dir {shlex.quote(plugin_dir())}" if plugin_dir() else ""
        # a sessão nova é independente, não uma tentativa de aninhar a atual
        # O peixe é limpo: carrega só as configurações do projeto, que é onde o instalador põe o plugin, as skills
        # do Matt, o rtk e o ponytail. O ambiente do usuário (outros plugins, hooks, conectores MCP) não entra.
        # Conector MCP segue a mesma regra: só os que o projeto registrou (`.mcp.json` na raiz), nenhum do usuário.
        registered = os.path.join(root, ".mcp.json") if root else None
        mcp = " --strict-mcp-config" + (f" --mcp-config {shlex.quote(registered)}" if registered and os.path.isfile(registered) else "")
        return (f"env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT {sets} claude"
                + (f" --model {shlex.quote(model)}" if model else "")
                + f" {flags}{extra} --setting-sources project,local{mcp} -- {prompt}")  # `--`: a opção
        # `--mcp-config` aceita vários arquivos; sem o separador ela engole o pedido como se fosse mais um
    # num worktree o commit grava na pasta `.git` do repositório, fora da pasta de trabalho: ela entra como gravável
    git_dir = _git_dir(root) if root else None
    extra = f" --add-dir {shlex.quote(git_dir)}" if git_dir and not git_dir.startswith(os.path.realpath(root)) else ""
    clean = "".join(f" -c mcp_servers.{name}.enabled=false" for name in _codex_servers(root))
    return (f"env {sets} codex" + (f" --model {shlex.quote(model)}" if model else "")
            + f" --sandbox workspace-write --ask-for-approval never{extra}{clean} {prompt}")


def transcript(cli, cwd, since):
    """O registro que o próprio agente grava da sessão (cada chamada de ferramenta, com comando e resultado):
    mais completo que a tela. Devolve o caminho do mais recente desta pasta desde `since`, ou None."""
    import glob
    home = os.path.expanduser("~")
    if cli == "claude":
        folder = os.path.join(home, ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        found = [f for f in glob.glob(os.path.join(folder, "*.jsonl")) if os.path.getmtime(f) >= since]
    else:
        found = []
        for f in glob.glob(os.path.join(home, ".codex", "sessions", "*", "*", "*", "*.jsonl")):
            if os.path.getmtime(f) < since:
                continue
            try:
                with open(f, encoding="utf-8", errors="replace") as stream:
                    if os.path.realpath(cwd) in stream.read(4000):
                        found.append(f)
            except OSError:
                pass
    return max(found, key=os.path.getmtime) if found else None


def open_agent(root, session, cli, model, prompt_file, env=None, record=None):
    """Abre o agente num terminal próprio, na pasta `root`. Devolve o nome da sessão. Com `record`, tudo que
    passa pela tela é gravado nesse arquivo desde a abertura (sem limite de linhas, e sobrevive a uma queda)."""
    if alive(session):
        raise Unavailable(f"já existe um terminal `{session}`: leia com `tmux attach -t {session}` ou encerre antes")
    run = _run("new-session", "-d", "-s", session, "-x", "200", "-y", "50", "-c", root,
               command(cli, model, prompt_file, env, root))
    if run.returncode:
        raise Unavailable((run.stderr or run.stdout).strip()[-300:] or "o tmux não abriu o terminal")
    if record:
        try:
            os.makedirs(os.path.dirname(record), exist_ok=True)
            _run("pipe-pane", "-o", "-t", session, f"cat >> {shlex.quote(record)}")
        except (OSError, Unavailable):
            pass
    return session


def alive(session):
    try:
        return _run("has-session", "-t", session).returncode == 0
    except Unavailable:
        return False


def read(session, lines=60):
    run = _run("capture-pane", "-p", "-S", f"-{lines}", "-t", session)
    if run.returncode:
        raise Unavailable(f"o terminal `{session}` não existe mais")
    return "\n".join(line.rstrip() for line in run.stdout.splitlines() if line.strip())


def _descendants(pid):
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()
    found = []
    for child in out:
        found += _descendants(child) + [child]
    return found


def history(session):
    """Tudo que passou pela tela do terminal, do começo."""
    run = _run("capture-pane", "-p", "-S", "-", "-t", session)
    return "\n".join(line.rstrip() for line in run.stdout.splitlines()) if run.returncode == 0 else ""


def stop(session, log=None):
    """Desmonta o terminal e o agente dentro dele; com `log`, guarda antes o que passou pela tela. Fechar só o terminal não basta: um agente pode ignorar o
    sinal de terminal fechado e seguir trabalhando (e commitando) sem ninguém vendo."""
    if log:
        try:
            text = history(session)
            if text.strip():
                os.makedirs(os.path.dirname(log), exist_ok=True)
                with open(log, "w", encoding="utf-8") as stream:
                    stream.write(text + "\n")
        except (OSError, Unavailable):
            pass
    panes = _run("list-panes", "-t", session, "-F", "#{pane_pid}")
    pids = []
    for pid in panes.stdout.split() if panes.returncode == 0 else []:
        pids += _descendants(pid) + [pid]
    closed = _run("kill-session", "-t", session).returncode == 0
    import signal
    import time
    for sig in (signal.SIGTERM, signal.SIGKILL):
        alive = []
        for pid in pids:
            try:
                os.kill(int(pid), sig)
                alive.append(pid)
            except (OSError, ValueError):
                pass
        if not alive:
            break
        time.sleep(1)
    return closed


def tell(session, text):
    """Escreve uma mensagem no terminal do agente e a envia: é como quem o coordena responde a ele."""
    if _run("send-keys", "-t", session, "-l", " ".join(text.split())).returncode:
        raise Unavailable(f"o terminal `{session}` não existe mais")
    import time
    time.sleep(0.5)  # o colado e o Enter em chamadas separadas: juntos, alguns CLIs tratam o Enter como texto
    _run("send-keys", "-t", session, "Enter")


def settle(session, screen):
    """Perguntas de abertura que o próprio isolamento responde, sempre pela opção que dá menos acesso.
    O peixe carrega só o projeto: se o Claude pergunta se pode importar um arquivo de fora da pasta (uma
    instrução do usuário, por exemplo), a resposta é não, que já vem marcada. Devolve True se respondeu."""
    tail = "\n".join(screen.splitlines()[-25:])
    if "Allow external CLAUDE.md file imports?" in tail and "❯ No, disable external imports" in tail:
        _run("send-keys", "-t", session, "Enter")
        return True
    return False


def waiting_on_human(screen):
    """A tela mostra uma pergunta que só uma pessoa responde? Devolve o trecho, ou None."""
    tail = "\n".join(screen.splitlines()[-25:])
    return tail if any(mark in tail for mark in HUMAN) else None
