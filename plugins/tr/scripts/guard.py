#!/usr/bin/env python3
"""O aplicador único dos portões do projeto (`PreToolUse`).

- A entrega é conferida por `gate delivery` depois do trabalho concluído.
- Escrita em código (ferramentas de edição, ou o terminal nas formas óbvias) com portão de `start`
  faltando: barra, e diz qual etapa cumprir. A entrega só passa com os carimbos finais.
- Edição do próprio registro (`.claude/harness.json`, `.claude/settings.json`): barra. Só o dono muda.
- Disparo de subagente (`Agent`): o validador de um portão recebe o pedido escrito aqui (o de quem
  escreveu o código é descartado) e o modelo da própria definição; os outros subagentes recebem o
  modelo do papel (o `Complexity:` do ticket; nunca opus, que é da sessão que planeja).
- O validador é só leitura; `gate <name>` roda sozinho na chamada; os scripts do harness antigo
  (`.harness/`) não rodam.
Sem `.claude/harness.json` ou sem `gates`, não faz nada.
"""
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import registry  # noqa: E402
import tasks  # noqa: E402
import render  # noqa: E402
import write_watch  # noqa: E402
from render import panel  # noqa: E402

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
WRAPPERS = ledger._WRAPPERS


def deny(root, what, message):
    ledger.log(root, "tr", "blocked", what[:160])
    return render.block_with(message)


def listing(reg, names, root=None):
    row_lines = []
    for n in names:
        gate = reg["gates"][n]
        row_lines.append(f"  ✗ {n} · {gate.get('description') or '(sem descrição)'}")
        row_lines += [f"    → {p}" for p in registry.steps(n, gate, reg.get('models'), root)]
    return row_lines


# BSD: `sed -i '' 's/a/b/' alvo`; GNU: `sed -i 's/a/b/' alvo` ou `sed -i.bak ...`.
_SED_INPLACE = re.compile(r"\bsed\s+-i\S*\s+(?:\S+\s+)+?(\S+?)\s*(?:$|[;|&\n])")


def bash_targets(command):
    """Caminhos que o comando escreve nas formas óbvias: `>`/`>>`, `sed -i`, `tee`, `cp`/`mv`.

    O corpo de um heredoc é texto do arquivo, não comando: um `.md` que cita `> apps/x.ts` não escreve em `apps/`.
    """
    command = ledger.strip_heredocs(command)
    try:
        parts = ledger._split(command)
    except ValueError:
        return []
    found = _SED_INPLACE.findall(command)
    for words in parts:
        for i, w in enumerate(words):
            m = re.fullmatch(r"\d*>>?(.*)", w)
            if m:
                target = m.group(1) or (words[i + 1] if i + 1 < len(words) else "")
                if target and not target.startswith("&"):
                    found.append(target)
        while words and (words[0] in WRAPPERS or re.fullmatch(r"\w+=.*", words[0])):
            words = words[1:]
        if not words:
            continue
        cmd, args = os.path.basename(words[0]), [a for a in words[1:] if not a.startswith(">")]
        plain = [a for a in args if not a.startswith("-")]
        if cmd == "sed" and any(a == "--in-place" or re.fullmatch(r"-[a-zA-Z]*i.*", a) for a in args):
            found += plain[1:]  # o primeiro é o roteiro do sed
        elif cmd == "tee":
            found += plain
        elif cmd in ("cp", "mv") and plain:
            found.append(plain[-1])
    return found


def allow(ti):
    """`PreToolUse`: deixa rodar com a entrada trocada (o pedido e o modelo do subagente)."""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                             "updatedInput": ti}}, ensure_ascii=False))
    return 0


def planner_writes(root, agent_name, client=None):
    """Quem planeja não executa: o orquestrador nunca escreve código, e a sessão principal não escreve
    enquanto a demanda tem tickets abertos. O executor externo de `models run` chega com FULLCHICO_ROLE."""
    if agent_name in registry.ORCHESTRATORS:
        return "o orquestrador coordena; o código é dos executores que ele dispara"
    # O subagente chega com `agent_type` no Claude e no Codex (conferido no Codex 0.171).
    if agent_name or os.environ.get("FULLCHICO_ROLE") == "execution":
        return None
    if tasks.open_tickets(root):
        return "a demanda tem tickets abertos: a sessão principal planeja, o código é dos executores"
    return None


def dispatch(root, reg, ti, caller=None):
    """O `Agent`: pedido canônico ao validador; modelo por papel aos demais."""
    kind_name = ti.get("subagent_type") or "general-purpose"
    validators = registry.validators(reg)
    new_item = dict(ti)
    if ":" not in kind_name and f"tr:{kind_name}" in validators:
        kind_name = new_item["subagent_type"] = f"tr:{kind_name}"  # o nome sem prefixo também é o validador
    if kind_name not in validators:
        blocked = tasks.dispatch_problem(root, reg, ti.get("prompt"), caller, kind_name)
        if blocked:
            return deny(root, f"ticket fora da fronteira: {kind_name}", panel("execução barrada", [
                ("motivo", blocked),
            ], ["  → confira `gate` para ver a fronteira liberada"]))
        if caller in registry.ORCHESTRATORS and kind_name not in tasks.READ_ONLY_AGENTS:
            # Paralelo é várias chamadas de Agent na mesma mensagem, em primeiro plano: o orquestrador espera
            # todas voltarem. Em segundo plano ele não é avisado do fim e acaba disparando o mesmo ticket de novo.
            # O Agent de um subagente não tem `run_in_background`: o orquestrador dispara em primeiro plano, vários
            # na mesma mensagem, e fica esperando. Quem vigia executor travado é a sessão principal (`tr-harness wait`).
            if ti.get("isolation") != "worktree":
                # Executores em paralelo na mesma pasta disputam package.json, lockfile e migrations.
                return deny(root, f"executor sem worktree: {kind_name}", panel("execução barrada", [
                    ("motivo", "cada executor roda no próprio worktree; o orquestrador integra depois"),
                ], ['  → dispare com isolation: "worktree" (commite o plano antes, porque o worktree nasce do último commit)']))
            limit = reg.get("max_parallel", registry.MAX_PARALLEL)
            if len(tasks._in_flight(root)) >= limit:
                return deny(root, f"limite de executores: {limit}", panel("execução barrada", [
                    ("motivo", f"já há {limit} executores rodando, o limite do projeto (max_parallel)"),
                ], ["  → espere um voltar e dispare a próxima onda; o dono muda com `tr-harness gates --parallel N`"]))
            busy = tasks.start_executor(root, ti.get("prompt"))
            if busy:
                return deny(root, f"executor duplicado: {busy}", panel("execução barrada", [
                    ("ticket", busy), ("motivo", "este ticket já tem um executor em andamento"),
                ], ["  → espere o executor voltar; não dispare outro para o mesmo ticket"]))
            refs = tasks.ticket_refs(root, ti.get("prompt"))
            if refs and "DONE:" not in (ti.get("prompt") or ""):
                new_item["prompt"] = ((ti.get("prompt") or "") + tasks.executor_env(refs[0])
                                      + tasks.protocol(root, refs[0]))
        # ticket com `Complexity:` decide; sem ticket, só opus é trocado (o resto, a definição do agente
        # ou o CLAUDE_CODE_SUBAGENT_MODEL do settings.local resolvem)
        model_name = registry.ticket_model(root, ti.get("prompt"))
        if not model_name and ti.get("model") == "opus":
            model_name = registry.EXECUTOR_MODEL
        if model_name and ti.get("model") != model_name:
            new_item["model"] = model_name
        return allow(new_item) if new_item != ti else 0
    config = reg.get("models") or {}
    per_gate = config.get("gates") or {}
    external_cli = [name for name in validators[kind_name]
                    if reg["gates"][name]["signs"] == "agent" and
                    (per_gate.get(name) or config.get("review") or {}).get("cli") == "codex"]
    if external_cli:
        return deny(root, f"revisor Codex externo: {kind_name}", panel("modelo do portão", [
            ("portões", ", ".join(external_cli)),
            ("motivo", "este portão usa Codex CLI; o Agent do Claude não pode assinar no lugar dele"),
        ], [f"  → rode `tr-harness models validate-gate {name} --detach`" for name in external_cli]))
    top = ledger.head(root) or ""
    if kind_name == registry.CHECKER:
        m = re.search(r"(?m)^\s*gate:\s*([\w.-]+)", ti.get("prompt") or "")
        gate_name = m.group(1) if m else None
        if gate_name not in validators[kind_name]:
            return deny(root, f"verificador sem portão: {gate_name}", panel("validação barrada", [
                ("validador", kind_name), ("motivo", f"`{gate_name}` não é portão de comando ou artefato do registro"),
            ], [f"  → peça com a primeira linha `gate: <name>`; existem: {', '.join(validators[kind_name])}"]))
        ticket_request = re.search(r"(?m)^\s*ticket:\s*([^\s]+)", ti.get("prompt") or "")
        ticket = ticket_request.group(1) if ticket_request else None
        gate = reg["gates"][gate_name]
        if gate["stage"] == "end":
            refused = audit_too_early(root, [gate_name])
            if refused:
                return deny(root, *refused)
        if gate["stage"] != "middle" and registry.satisfied(root, gate_name, reg):
            return deny(root, f"carimbo já vale: {gate_name}", panel("validação desnecessária", [
                ("portão", gate_name), ("motivo", "já há carimbo deste portão para o estado atual do projeto"),
            ], ["  → siga; valide de novo só depois de mudar o projeto"]))
        if gate["stage"] == "middle" and ticket not in tasks.tickets(root):
            return deny(root, f"verificador sem ticket: {gate_name}", panel("validação barrada", [
                ("portão", gate_name), ("motivo", "portão de meio exige ticket válido na segunda linha"),
            ], ["  → peça `gate: <name>\\nticket: <path>`"]))
        if gate["stage"] != "middle":
            ticket = None  # portão de entrada ou de fim vale para o projeto todo; o ticket citado não muda nada
        new_item["prompt"] = f"gate: {gate_name}\n" + (f"ticket: {ticket}\n" if ticket else "") + f"commit: {top}"
    else:
        refused = audit_too_early(root, [n for n in validators[kind_name] if reg["gates"][n]["stage"] == "end"])
        if refused:
            return deny(root, *refused)
        new_item["prompt"] = (f"snapshot: {top}\ncommit: {top}\nInspect the project's current files. " + DELTA)
    # Um modelo Claude específico do portão vence o padrão de revisão; sem escolha, vale o
    # `model` da definição do agente. O CLI externo de Codex usa `models run`, não o Agent.
    config = reg.get("models") or {}
    per_gate = config.get("gates") or {}
    pick = per_gate.get(gate_name) if kind_name == registry.CHECKER else None
    if not pick:
        picks = [per_gate.get(n) for n in validators[kind_name]]
        if len(picks) == 1 or (all(picks) and all(item == picks[0] for item in picks)):
            pick = picks[0]
    pick = pick or config.get("review")
    if isinstance(pick, dict) and pick.get("cli") == "claude" and pick.get("model"):
        new_item["model"] = pick["model"]
    else:
        new_item.pop("model", None)  # vale o `model` da definição do validador
    ledger.log(root, "tr", "requested", f"{kind_name}: {new_item['prompt'].splitlines()[0]}")
    return allow(new_item)


GATE_TIMEOUT = 600000  # o máximo do Bash; um portão que passa disso precisa ficar mais rápido


DELTA = ("Validate the delta between the planned (the accepted spec, its tickets and the artifacts approved at "
         "the start) and the delivered, observed in the delivered state: the running product, the code and the "
         "tests that exercise it. An artifact of the plan is the reference to compare against, never the evidence.")


def audit_too_early(root, gates):
    """A auditoria é a chegada do trem: com ticket ou ajuste aberto, revisor de fim não roda."""
    pending = tasks.open_work(root) if gates else []
    if not pending:
        return None
    return (f"auditoria antes da chegada: {', '.join(gates)}", panel("o trem ainda não chegou", [
        ("portões", ", ".join(gates)), ("em aberto", ", ".join(p.rsplit("/", 1)[-1] for p in pending[:4])),
        ("motivo", "os portões de fim auditam o estado final, uma vez, com todos os tickets e ajustes integrados"),
    ], ["  → termine e integre o que está aberto; depois rode a auditoria, com os validadores em paralelo"]))


OWNER_FLAGS = {"--write", "--set", "--register", "--remove", "--approve", "--parallel", "--accept"}


def owner_write(command):
    """`tr-harness gates --write|--set|--register|--approve …` ou `tr-harness models configure …`, sozinho
    na chamada: o comando que grava o que é do dono. Devolve as palavras depois de `tr-harness`."""
    try:
        parts = ledger._split(ledger.strip_heredocs(command))
    except ValueError:
        return None
    if len(parts) != 1:
        return None
    words = parts[0]
    while words and (words[0] in WRAPPERS or re.fullmatch(r"\w+=.*", words[0])):
        words = words[1:]
    if words[:2] == ["claude", "plugin"] and "--scope" in words and words[words.index("--scope") + 1:][:1] == ["project"] \
            and words[2:3] in (["install"], ["uninstall"], ["enable"], ["disable"]):
        return words  # muda os plugins do projeto (.claude/settings.json): também é decisão do dono
    if not words or os.path.basename(words[0]) != "tr-harness":
        return None
    rest = words[1:]
    if rest[:1] == ["gates"] and OWNER_FLAGS & set(rest) or rest[:2] == ["models", "configure"]:
        return rest
    return None


def owner_combined(command):
    """Um comando do dono no meio de outros (`git commit && tr-harness gates --accept | tail`): o hook não
    consegue pedir a aprovação e o CLI recusa. Devolve o comando do dono, para mandar rodar sozinho."""
    try:
        parts = ledger._split(ledger.strip_heredocs(command))
    except ValueError:
        return None
    for words in parts if len(parts) > 1 else []:
        while words and (words[0] in WRAPPERS or re.fullmatch(r"\w+=.*", words[0])):
            words = words[1:]
        if words and os.path.basename(words[0]) == "tr-harness":
            rest = [w for w in words[1:] if not re.match(r"\d*[<>]", w)]
            if rest[:1] == ["gates"] and OWNER_FLAGS & set(rest) or rest[:2] == ["models", "configure"]:
                return "tr-harness " + shlex.join(rest)
    return None


def ask_owner(root, payload, words):
    """O dono aprova no diálogo do Claude Code o comando exato; sem diálogo possível, vai para o terminal."""
    canonical = registry.owner_canonical(words)
    terminal_line = shlex.join(words) if words[:1] == ["claude"] else registry.owner_command(root, words)
    codex = payload.get("harness_client") == "codex"
    if payload.get("permission_mode") in ("bypassPermissions", "dontAsk", "auto") or codex:
        if not codex and registry.owner_pending(root, canonical):
            return 0  # o dono respondeu "Aprovo" na pergunta da sessão; o CLI consome a aprovação
        steps = [] if codex else [
            "  → pergunte ao dono, sozinho na mensagem, com AskUserQuestion:",
            f"      pergunta: {registry.owner_question(canonical)}",
            f"      opções: {registry.OWNER_YES} / {registry.OWNER_NO}",
            "    com a resposta Aprovo, rode o mesmo comando de novo",
            "  → ou o dono roda no terminal dele:"]
        return deny(root, f"gravação do dono: {canonical}", panel("aprovação do dono", [
            ("comando", canonical[:80]),
            ("motivo", "neste modo não há diálogo de permissão; a decisão é do dono"),
        ], steps + [f"  → {'no seu terminal, fora da sessão: ' if codex else '    '}{terminal_line}"]))
    registry.grant_owner(root, canonical)
    ledger.log(root, "tr", "asked", canonical[:160])
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                             "permissionDecisionReason": "Aprovação do dono: este comando grava os portões, os "
                                             f"modelos ou os plugins do projeto ({canonical[:120]}). Aprove só se for a sua decisão."}},
                     ensure_ascii=False))
    return 0


def foreign_kill(root, command):
    """Matar processo que não é deste projeto: outro projeto da máquina pode estar na mesma porta.

    Devolve o motivo da recusa, ou None. `kill <pid>` só passa se a pasta do processo está dentro do projeto
    (os worktrees dos executores ficam em `.claude/worktrees/`). Matar por nome (`pkill`, `killall`) ou por PID
    calculado na hora (`$(...)`, `| xargs kill`) não deixa conferir de quem é: recusa."""
    import subprocess
    if not re.search(r"\b(kill|pkill|killall)\b", command):
        return None
    if re.search(r"\bxargs\b[^|;&]*\bkill\b", command) or re.search(r"\bkill\b[^|;&]*(\$\(|`)", command):
        return "PID calculado na hora (`$(...)` ou `xargs kill`): não dá para conferir de quem é o processo"
    try:
        parts = ledger._split(ledger.strip_heredocs(command))
    except ValueError:
        return None
    home = os.path.realpath(root)
    for words in parts:
        while words and (words[0] in WRAPPERS or re.fullmatch(r"\w+=.*", words[0])):
            words = words[1:]
        if not words:
            continue
        name = os.path.basename(words[0])
        if name in ("pkill", "killall"):
            return f"`{name}` mata por nome e pode atingir processos de outros projetos; use `kill <pid>` de um processo seu"
        if name != "kill":
            continue
        for pid in (w for w in words[1:] if w.isdigit()):
            out = subprocess.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"], capture_output=True, text=True)
            cwd = next((line[1:] for line in out.stdout.splitlines() if line.startswith("n")), "")
            if cwd and not os.path.realpath(cwd).startswith(home + os.sep) and os.path.realpath(cwd) != home:
                return f"o processo {pid} é de fora deste projeto ({cwd})"
    return None


def combined_gate(command):
    """`gate <name>` com pipe, encadeamento ou redirecionamento: roda, mas não carimba. Barra antes."""
    try:
        parts = ledger._split(ledger.strip_heredocs(command))
    except ValueError:
        return False
    for words in parts:
        while words and (words[0] in WRAPPERS or re.fullmatch(r"\w+=.*", words[0])):
            words = words[1:]
        # Redirecionamento não é argumento: `gate 2>&1 | tail` só lista, e listar não carimba.
        words = [w for w in words if not re.fullmatch(r"\d*[<>]{1,2}&?\S*|&>\S*", w)]
        if words and os.path.basename(words[0]) == "gate" and len(words) > 1:
            valid = len(words) == 2 or (len(words) == 4 and words[2] == "--ticket")
            if len(parts) > 1 or not valid:
                return True
    return False


_GIT_MUTATES = {"add", "commit", "checkout", "switch", "reset", "restore", "apply", "stash", "merge", "rebase",
             "cherry-pick", "revert", "rm", "mv", "am", "pull", "push", "tag", "update-ref", "worktree", "clean"}

_BRANCH_WRITES = {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "-f", "--force",
                  "-u", "--set-upstream-to", "--unset-upstream"}


def git_mutates(command):
    """O comando muda o repositório pelo git (commit, checkout, reset...)? Para o validador, que só lê."""
    try:
        parts = ledger._split(ledger.strip_heredocs(command))
    except ValueError:
        return False
    for words in parts:
        while words and (words[0] in WRAPPERS or re.fullmatch(r"\w+=.*", words[0])):
            words = words[1:]
        if words and os.path.basename(words[0]) == "git":
            rest, i = words[1:], 0
            while i < len(rest) and rest[i].startswith("-"):
                i += 2 if rest[i] in ("-C", "-c", "--git-dir", "--work-tree") else 1
            sub, args = (rest[i], rest[i + 1:]) if i < len(rest) else ("", [])
            if sub == "worktree" and args[:1] == ["list"]:
                continue  # listar worktrees só lê
            if sub == "tag" and (not args or args[0] in ("-l", "--list")):
                continue
            if sub == "branch" and any(a in _BRANCH_WRITES for a in args):
                return True
            if sub in _GIT_MUTATES:
                return True
    return False


def legacy_harness(command):
    try:
        parts = ledger._split(ledger.strip_heredocs(command))
    except ValueError:
        return False
    for words in parts:
        while words and (words[0] in WRAPPERS or re.fullmatch(r"\w+=.*", words[0])):
            words = words[1:]
        if words and re.match(r"(\./)?\.harness/", words[0]):
            return True
    return False


def certificate_tamper(root, tool, ti, targets):
    """O agente mexendo no apêndice de certificados (ou forjando o trailer de assinatura)? Devolve o arquivo."""
    import certs
    if tool == "Bash":
        command = ti.get("command") or ""
        if certs.TRAILER + ":" in command:
            return "commit com " + certs.TRAILER
        for t in targets:  # pelo shell não dá para ver o que muda: documento com certificado só por Edit
            path = os.path.join(root, registry.relative(root, t) or t)
            if path.endswith(".md") and os.path.isfile(path) and certs.block(open(path, encoding="utf-8").read()):
                return registry.relative(root, t) or t
        return None
    if tool not in EDIT_TOOLS or not targets or not str(targets[0]).endswith(".md"):
        return None
    path = os.path.join(root, registry.relative(root, targets[0]) or targets[0])
    try:
        with open(path, encoding="utf-8") as stream:
            before = stream.read()
    except OSError:
        before = ""
    after = before
    if tool == "Write":
        after = ti.get("content") or ""
    else:
        for edit in ti.get("edits") or [ti]:
            old, new = edit.get("old_string") or "", edit.get("new_string") or ""
            after = after.replace(old, new) if edit.get("replace_all") else after.replace(old, new, 1)
    return registry.relative(root, targets[0]) if certs.block(after) != certs.block(before) else None


def main():
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name")
    if payload.get("agent_id"):
        try:  # batimento do subagente para o quadro de status; nunca decide nada
            tasks.beat(registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()),
                       payload["agent_id"], payload.get("agent_type") or "")
        except OSError:
            pass
    ti = payload.get("tool_input") or {}
    root = registry.toplevel(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    # O arquivo de portões é protegido sempre, mesmo sem registro ainda: o agente não cria um
    # registro fraco por conta própria. Só o plugin tr (os scripts do dono) escreve ali.
    if tool in EDIT_TOOLS:
        path = ti.get("file_path") or ti.get("notebook_path")
        targets_pre = [path] if isinstance(path, str) else []
    elif tool == "Bash" and isinstance(ti.get("command"), str):
        targets_pre = bash_targets(ti["command"])
    else:
        targets_pre = []
    for t in targets_pre:
        rel = registry.relative(root, t)
        if rel == ".claude/harness.json":
            return deny(root, f"registro: {t}", panel("registro protegido", [
                ("arquivo", ".claude/harness.json"),
                ("motivo", f"só o dono altera, por `{registry.owner_command(root, 'gates')}` no terminal"),
            ], footer="o plugin tr escreve ali; o agente não"))
        if rel in (".claude/settings.json", ".claude/settings.local.json"):
            return deny(root, f"configuração: {t}", panel("configuração protegida", [
                ("arquivo", rel), ("motivo", "define plugins e hooks do projeto; só o dono altera"),
            ], footer="use o terminal do dono para configurar o harness"))
        if (rel or "").startswith(".git/"):
            return deny(root, f"git interno: {t}", panel("estado do git protegido", [
                ("arquivo", rel), ("motivo", "alterar `.git/` muda o que os portões enxergam"),
            ], footer="use os comandos Git normais; não edite os arquivos internos"))
        if rel in (".codex/hooks.json", ".codex/config.toml", ".agents/plugins/marketplace.json") or (
                rel or "").startswith(".codex/harness/") or rel in (
                ".codex/agents/tr-orchestrator.toml", ".codex/agents/tr-quality-checker.toml", ".codex/agents/tr-bug-hunter.toml", ".codex/agents/tr-scope-checker.toml",
                ".codex/agents/memory-extractor.toml"):
            return deny(root, f"configuração Codex: {t}", panel("harness protegido", [
                ("arquivo", rel), ("motivo", "contém os hooks ou validadores que aplicam os portões"),
            ], footer="o dono atualiza com `fullchico-harness install-codex` no terminal"))

    if tool == "AskUserQuestion" and (ti.get("answers") or ti.get("annotations")):
        # a resposta vem da interface, do dono; o agente que já manda respondida está respondendo por ele
        return deny(root, "pergunta já respondida pelo agente", panel("resposta do dono", [
            ("motivo", "a pergunta não pode chegar com `answers`: quem responde é o dono, na interface"),
        ], ["  → mande só `questions`"]))

    refused = certificate_tamper(root, tool, ti, targets_pre)
    if refused:
        return deny(root, f"certificado: {refused}", panel("certificado protegido", [
            ("arquivo", refused), ("motivo", "o apêndice de certificados é escrito pelos hooks, no commit do responsável"),
        ], ["  → edite o resto do documento com Edit; o certificado sai do portão"]))

    if tool == "Bash" and isinstance(ti.get("command"), str):
        words = owner_write(ti["command"])
        if words:
            return ask_owner(root, payload, words)
        alone = owner_combined(ti["command"])
        if alone:
            return deny(root, f"comando do dono combinado: {alone}", panel("comando do dono sozinho", [
                ("comando", alone[:80]), ("motivo", "junto de outros comandos o hook não consegue pedir a aprovação do dono"),
            ], [f"  → rode `{alone}` sozinho na chamada, sem `&&`, pipe ou redirecionamento"]))

    try:
        reg = registry.load(root)
    except registry.RegistryError as e:
        command = (ti.get("command") or "").strip() if tool == "Bash" else ""
        if tool == "Bash" and re.fullmatch(r"cat[ \t]+[\w./-]+", command):
            return 0  # permite ler o registro quebrado para diagnosticá-lo
        if tool in EDIT_TOOLS or tool in ("Bash", "Agent", "Task"):
            return deny(root, "registro inválido", panel("trilho indisponível", [
                ("motivo", str(e)),
            ], ["  → corrija `.claude/harness.json` no terminal do dono antes de continuar"]))
        return 0
    if not reg:
        # Plugin instalado e portões ainda não decididos: o fluxo começa pela configuração, não pelo código.
        for t in targets_pre:
            if registry.is_code(root, t, reg):
                return deny(root, f"sem portões: {t}", panel("portões não configurados", [
                    ("arquivo", registry.relative(root, t)),
                    ("motivo", "o projeto usa o tr, mas ainda não tem portões; o código vem depois da entrada"),
                ], ["  → rode /tr:configure: a entrevista propõe os portões e o dono grava no terminal"]))
        return 0

    # O agente que assina um portão é parte do portão: afrouxar a instrução dele é afrouxar o portão.
    gate_agents = {g["agent"].split(":")[-1] for g in reg["gates"].values() if g["signs"] == "agent"}
    for t in targets_pre:
        rel = registry.relative(root, t) or ""
        stem = os.path.splitext(os.path.basename(rel))[0]
        if stem in gate_agents and (rel.startswith(".claude/agents/") or rel.startswith(".codex/agents/")):
            return deny(root, f"agente de portão: {t}", panel("agente de portão protegido", [
                ("arquivo", rel), ("motivo", "este agente assina um portão registrado; mudar a instrução dele muda o portão"),
            ], footer="o dono altera no terminal, fora da sessão"))

    if tool in ("Agent", "Task"):
        return dispatch(root, reg, ti, payload.get("agent_type"))
    agent_name = payload.get("agent_type")
    if agent_name and agent_name in registry.validators(reg):
        targets_list = targets_pre if tool in EDIT_TOOLS or tool == "Bash" else []
        if any(registry.relative(root, t) for t in targets_list) or (tool == "Bash" and git_mutates(ti.get("command") or "")):
            return deny(root, f"validador escreveu: {agent_name}", panel("validador só lê", [
                ("validador", agent_name), ("motivo", "quem valida não escreve: o carimbo é sobre o que outro fez"),
            ], ["  → relate o que achou no veredito; a correção é de quem implementa"]))

    if tool == "Bash":
        command = ti.get("command")
        if not isinstance(command, str):
            return 0
        if legacy_harness(command):
            return deny(root, f"harness antigo: {command[:100]}", panel("harness antigo", [
                ("comando", command.split()[0]), ("motivo", "os scripts de `.harness/` são do modelo antigo; os portões são do tr"),
            ], listing(reg, registry.missing(root, "end", reg), root) or ["  → valide a entrega com `gate delivery`"],
                "estado: `gate`"))
        foreign = foreign_kill(root, command)
        if foreign:
            return deny(root, f"kill alheio: {command[:100]}", panel("processo de outro projeto", [
                ("comando", command[:80]), ("motivo", foreign),
            ], ["  → use outra porta (a do seu ticket); só pare processos que você mesmo subiu, por `kill <pid>`"]))
        if combined_gate(command):
            return deny(root, f"gate combinado: {command[:100]}", panel("gate sozinho", [
                ("comando", command[:80]), ("motivo", "com pipe, `&&` ou redirecionamento o portão roda mas não carimba"),
            ], ["  → rode `gate <name>` sozinho na chamada; a saída já vem resumida"]))
        m = re.fullmatch(r"\s*gate[ \t]+([\w.-]+)(?:[ \t]+--ticket[ \t]+\S+)?\s*", command)
        if m and m.group(1) in reg["gates"] and (ti.get("run_in_background") or (ti.get("timeout") or 0) < GATE_TIMEOUT):
            # o hook só assina o que vê: em segundo plano (ou movido para lá depois de 2 min) ele não vê o "passou"
            return deny(root, f"gate sem tempo: {command[:80]}", panel("gate em primeiro plano", [
                ("comando", command.strip()[:80]),
                ("motivo", "o carimbo sai da saída que o hook vê; em segundo plano ela não chega"),
            ], [f"  → rode de novo com timeout {GATE_TIMEOUT} e sem run_in_background"]))
        targets = bash_targets(command)
    elif tool in EDIT_TOOLS:
        path = ti.get("file_path") or ti.get("notebook_path")
        targets = [path] if isinstance(path, str) else []
    else:
        return 0

    for t in targets:
        if registry.is_code(root, t, reg):
            missing_gates = registry.missing(root, "start", reg)
            if missing_gates:
                return deny(root, f"escrita em código: {t}", panel("escrita barrada", [
                    ("arquivo", registry.relative(root, t)), ("motivo", "falta a etapa de início"),
                ], listing(reg, missing_gates, root), "estado: `gate`"))
            reason = planner_writes(root, agent_name, payload.get("harness_client"))
            if reason:
                return deny(root, f"planejador escreveu código: {t}", panel("quem planeja não executa", [
                    ("arquivo", registry.relative(root, t)), ("motivo", reason),
                ], ["  → despache um executor com o caminho do ticket (o `tr:orchestrator` faz isso)"]))
    if tool == "Bash":
        # O que o texto do comando não mostra (python -c, scripts, volumes) é conferido pelo efeito no PostToolUse.
        if agent_name and agent_name in registry.validators(reg):
            restriction = "a validator only reads"
        elif registry.missing(root, "start", reg):
            restriction = "start gates are still missing"
        else:
            restriction = planner_writes(root, agent_name, payload.get("harness_client"))
        if restriction:
            write_watch.snapshot(root, reg, payload.get("tool_use_id"), restriction)
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as error:
        print(f"guard.py falhou: {error}", file=sys.stderr)
        code = 1  # onFailure:block impede a escrita se o verificador travar
    sys.exit(code)
