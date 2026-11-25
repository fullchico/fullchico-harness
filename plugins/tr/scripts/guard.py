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


def listing(reg, names):
    row_lines = []
    for n in names:
        gate = reg["gates"][n]
        row_lines.append(f"  ✗ {n} · {gate.get('description') or '(sem descrição)'}")
        row_lines += [f"    → {p}" for p in registry.steps(n, gate, reg.get('models'))]
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
        # ticket com `Complexity:` decide; sem ticket, só opus é trocado (o resto, a definição do agente
        # ou o CLAUDE_CODE_SUBAGENT_MODEL do settings.local resolvem)
        model_name = registry.ticket_model(root, ti.get("prompt"))
        if not model_name and ti.get("model") == "opus":
            model_name = registry.EXECUTOR_MODEL
        if not model_name or ti.get("model") == model_name:
            return 0
        new_item["model"] = model_name
        return allow(new_item)
    config = reg.get("models") or {}
    per_gate = config.get("gates") or {}
    external_cli = [name for name in validators[kind_name]
                    if reg["gates"][name]["signs"] == "agent" and
                    (per_gate.get(name) or config.get("review") or {}).get("cli") == "codex"]
    if external_cli:
        return deny(root, f"revisor Codex externo: {kind_name}", panel("modelo do portão", [
            ("portões", ", ".join(external_cli)),
            ("motivo", "este portão usa Codex CLI; o Agent do Claude não pode assinar no lugar dele"),
        ], [f"  → rode `fullchico-harness models validate-gate {name}`" for name in external_cli]))
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
        if gate["stage"] == "middle" and ticket not in tasks.tickets(root):
            return deny(root, f"verificador sem ticket: {gate_name}", panel("validação barrada", [
                ("portão", gate_name), ("motivo", "portão de meio exige ticket válido na segunda linha"),
            ], ["  → peça `gate: <name>\\nticket: <path>`"]))
        if gate["stage"] != "middle" and ticket:
            return deny(root, f"ticket inesperado: {gate_name}", panel("validação barrada", [
                ("portão", gate_name), ("motivo", "só portão de meio recebe ticket"),
            ]))
        new_item["prompt"] = f"gate: {gate_name}\n" + (f"ticket: {ticket}\n" if ticket else "") + f"commit: {top}"
    else:
        new_item["prompt"] = f"snapshot: {top}\ncommit: {top}\nInspect the project's current files."
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


def combined_gate(command):
    """`gate <name>` com pipe, encadeamento ou redirecionamento: roda, mas não carimba. Barra antes."""
    try:
        parts = ledger._split(ledger.strip_heredocs(command))
    except ValueError:
        return False
    for words in parts:
        while words and (words[0] in WRAPPERS or re.fullmatch(r"\w+=.*", words[0])):
            words = words[1:]
        if words and os.path.basename(words[0]) == "gate" and len(words) > 1:
            valid = len(words) == 2 or (len(words) == 4 and words[2] == "--ticket")
            if len(parts) > 1 or not valid:
                return True
    return False


_GIT_MUTATES = {"add", "commit", "checkout", "switch", "reset", "restore", "apply", "stash", "merge", "rebase",
             "cherry-pick", "revert", "rm", "mv", "am", "pull", "push", "tag", "update-ref", "worktree", "clean"}


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
            if i < len(rest) and rest[i] in _GIT_MUTATES:
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


def main():
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name")
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
                ("motivo", "só o dono altera, por `fullchico-harness gates` no terminal"),
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
        return 0

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
            ], listing(reg, registry.missing(root, "end", reg)) or ["  → valide a entrega com `gate delivery`"],
                "estado: `gate`"))
        if combined_gate(command):
            return deny(root, f"gate combinado: {command[:100]}", panel("gate sozinho", [
                ("comando", command[:80]), ("motivo", "com pipe, `&&` ou redirecionamento o portão roda mas não carimba"),
            ], ["  → rode `gate <name>` sozinho na chamada; a saída já vem resumida"]))
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
                ], listing(reg, missing_gates), "estado: `gate`"))
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
