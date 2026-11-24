#!/usr/bin/env python3
"""O aplicador único dos portões do projeto (`PreToolUse`).

- A entrega é conferida por `portao entrega` depois do trabalho concluído.
- Escrita em código (ferramentas de edição, ou o terminal nas formas óbvias) com portão de `inicio`
  faltando: barra, e diz qual etapa cumprir. A entrega só passa com os carimbos finais.
- Edição do próprio registro (`.claude/trilho.json`, `.claude/settings.json`): barra. Só o dono muda.
- Disparo de subagente (`Agent`): o validador de um portão recebe o pedido escrito aqui (o de quem
  escreveu o código é descartado) e o modelo da própria definição; os outros subagentes recebem o
  modelo do papel (o `Complexidade:` do ticket; nunca opus, que é da sessão que planeja).
- O validador é só leitura; `portao <nome>` roda sozinho na chamada; os scripts do harness antigo
  (`.harness/`) não rodam.
Sem `.claude/trilho.json` ou sem `portoes`, não faz nada.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import registry  # noqa: E402
import tasks  # noqa: E402
import saida  # noqa: E402
from saida import quadro  # noqa: E402

EDICAO = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
WRAPPERS = ledger._WRAPPERS


def deny(root, what, message):
    ledger.log(root, "trilho", "barrou", what[:160])
    return saida.barrar(message)


def lista(reg, names):
    linhas = []
    for n in names:
        gate = reg["portoes"][n]
        linhas.append(f"  ✗ {n} · {gate.get('descricao') or '(sem descrição)'}")
        linhas += [f"    → {p}" for p in registry.passos(n, gate, reg.get('modelos'))]
    return linhas


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


def permitir(ti):
    """`PreToolUse`: deixa rodar com a entrada trocada (o pedido e o modelo do subagente)."""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                             "updatedInput": ti}}, ensure_ascii=False))
    return 0


def disparo(root, reg, ti):
    """O `Agent`: pedido canônico ao validador; modelo por papel aos demais."""
    tipo = ti.get("subagent_type") or "general-purpose"
    validadores = registry.validadores(reg)
    novo = dict(ti)
    if ":" not in tipo and f"tr:{tipo}" in validadores:
        tipo = novo["subagent_type"] = f"tr:{tipo}"  # o nome sem prefixo também é o validador
    if tipo not in validadores:
        blocked = tasks.dispatch_problem(root, reg, ti.get("prompt"))
        if blocked:
            return deny(root, f"ticket fora da fronteira: {tipo}", quadro("execução barrada", [
                ("motivo", blocked),
            ], ["  → confira `portao` para ver a fronteira liberada"]))
        # ticket com `Complexidade:` decide; sem ticket, só opus é trocado (o resto, a definição do agente
        # ou o CLAUDE_CODE_SUBAGENT_MODEL do settings.local resolvem)
        modelo = registry.modelo_do_ticket(root, ti.get("prompt"))
        if not modelo and ti.get("model") == "opus":
            modelo = registry.MODELO_EXECUTOR
        if not modelo or ti.get("model") == modelo:
            return 0
        novo["model"] = modelo
        return permitir(novo)
    config = reg.get("modelos") or {}
    por_portao = config.get("portoes") or {}
    cli_externos = [name for name in validadores[tipo]
                    if reg["portoes"][name]["assina"] == "agente" and
                    (por_portao.get(name) or config.get("revisao") or {}).get("cli") == "codex"]
    if cli_externos:
        return deny(root, f"revisor Codex externo: {tipo}", quadro("modelo do portão", [
            ("portões", ", ".join(cli_externos)),
            ("motivo", "este portão usa Codex CLI; o Agent do Claude não pode assinar no lugar dele"),
        ], [f"  → rode `fullchico-harness modelos validar-portao {name}`" for name in cli_externos]))
    top = ledger.head(root) or ""
    if tipo == registry.VERIFICADOR:
        m = re.search(r"(?m)^\s*portao:\s*([\w.-]+)", ti.get("prompt") or "")
        nome = m.group(1) if m else None
        if nome not in validadores[tipo]:
            return deny(root, f"verificador sem portão: {nome}", quadro("validação barrada", [
                ("validador", tipo), ("motivo", f"`{nome}` não é portão de comando ou artefato do registro"),
            ], [f"  → peça com a primeira linha `portao: <nome>`; existem: {', '.join(validadores[tipo])}"]))
        pedido_ticket = re.search(r"(?m)^\s*ticket:\s*([^\s]+)", ti.get("prompt") or "")
        ticket = pedido_ticket.group(1) if pedido_ticket else None
        gate = reg["portoes"][nome]
        if gate["momento"] == "meio" and ticket not in tasks.tickets(root):
            return deny(root, f"verificador sem ticket: {nome}", quadro("validação barrada", [
                ("portão", nome), ("motivo", "portão de meio exige ticket válido na segunda linha"),
            ], ["  → peça `portao: <nome>\\nticket: <caminho>`"]))
        if gate["momento"] != "meio" and ticket:
            return deny(root, f"ticket inesperado: {nome}", quadro("validação barrada", [
                ("portão", nome), ("motivo", "só portão de meio recebe ticket"),
            ]))
        novo["prompt"] = f"portao: {nome}\n" + (f"ticket: {ticket}\n" if ticket else "") + f"commit: {top}"
    else:
        novo["prompt"] = f"snapshot: {top}\ncommit: {top}\nInspecione os arquivos atuais do projeto."
    # Um modelo Claude específico do portão vence o padrão de revisão; sem escolha, vale o
    # `model` da definição do agente. O CLI externo de Codex usa `modelos executar`, não o Agent.
    config = reg.get("modelos") or {}
    por_portao = config.get("portoes") or {}
    escolha = por_portao.get(nome) if tipo == registry.VERIFICADOR else None
    if not escolha:
        escolhas = [por_portao.get(n) for n in validadores[tipo]]
        if len(escolhas) == 1 or (all(escolhas) and all(item == escolhas[0] for item in escolhas)):
            escolha = escolhas[0]
    escolha = escolha or config.get("revisao")
    if isinstance(escolha, dict) and escolha.get("cli") == "claude" and escolha.get("modelo"):
        novo["model"] = escolha["modelo"]
    else:
        novo.pop("model", None)  # vale o `model` da definição do validador
    ledger.log(root, "trilho", "pedido", f"{tipo}: {novo['prompt'].splitlines()[0]}")
    return permitir(novo)


def portao_combinado(command):
    """`portao <nome>` com pipe, encadeamento ou redirecionamento: roda, mas não carimba. Barra antes."""
    try:
        parts = ledger._split(ledger.strip_heredocs(command))
    except ValueError:
        return False
    for words in parts:
        while words and (words[0] in WRAPPERS or re.fullmatch(r"\w+=.*", words[0])):
            words = words[1:]
        if words and os.path.basename(words[0]) == "portao" and len(words) > 1:
            valid = len(words) == 2 or (len(words) == 4 and words[2] == "--ticket")
            if len(parts) > 1 or not valid:
                return True
    return False


_GIT_MUDA = {"add", "commit", "checkout", "switch", "reset", "restore", "apply", "stash", "merge", "rebase",
             "cherry-pick", "revert", "rm", "mv", "am", "pull", "push", "tag", "update-ref", "worktree", "clean"}


def git_muda(command):
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
            if i < len(rest) and rest[i] in _GIT_MUDA:
                return True
    return False


def harness_antigo(command):
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
    if tool in EDICAO:
        path = ti.get("file_path") or ti.get("notebook_path")
        targets_pre = [path] if isinstance(path, str) else []
    elif tool == "Bash" and isinstance(ti.get("command"), str):
        targets_pre = bash_targets(ti["command"])
    else:
        targets_pre = []
    for t in targets_pre:
        rel = registry.relative(root, t)
        if rel == ".claude/trilho.json":
            return deny(root, f"registro: {t}", quadro("registro protegido", [
                ("arquivo", ".claude/trilho.json"),
                ("motivo", "só o dono altera, por `fullchico-harness portoes` no terminal"),
            ], rodape="o plugin tr escreve ali; o agente não"))
        if rel in (".claude/settings.json", ".claude/settings.local.json"):
            return deny(root, f"configuração: {t}", quadro("configuração protegida", [
                ("arquivo", rel), ("motivo", "define plugins e hooks do projeto; só o dono altera"),
            ], rodape="use o terminal do dono para configurar o harness"))
        if (rel or "").startswith(".git/"):
            return deny(root, f"git interno: {t}", quadro("estado do git protegido", [
                ("arquivo", rel), ("motivo", "alterar `.git/` muda o que os portões enxergam"),
            ], rodape="use os comandos Git normais; não edite os arquivos internos"))
        if rel in (".codex/hooks.json", ".codex/config.toml", ".agents/plugins/marketplace.json") or (
                rel or "").startswith(".codex/harness/") or rel in (
                ".codex/agents/tr-orquestrador.toml", ".codex/agents/tr-qualidade-verificador.toml", ".codex/agents/tr-bugs-cacador.toml",
                ".codex/agents/memoria-extrator.toml"):
            return deny(root, f"configuração Codex: {t}", quadro("harness protegido", [
                ("arquivo", rel), ("motivo", "contém os hooks ou validadores que aplicam os portões"),
            ], rodape="o dono atualiza com `fullchico-harness install-codex` no terminal"))

    try:
        reg = registry.load(root)
    except registry.RegistryError as e:
        return 0
    if not reg:
        return 0

    if tool in ("Agent", "Task"):
        return disparo(root, reg, ti)
    agente = payload.get("agent_type")
    if agente and agente in registry.validadores(reg):
        alvos = targets_pre if tool in EDICAO or tool == "Bash" else []
        if any(registry.relative(root, t) for t in alvos) or (tool == "Bash" and git_muda(ti.get("command") or "")):
            return deny(root, f"validador escreveu: {agente}", quadro("validador só lê", [
                ("validador", agente), ("motivo", "quem valida não escreve: o carimbo é sobre o que outro fez"),
            ], ["  → relate o que achou no veredito; a correção é de quem implementa"]))

    if tool == "Bash":
        command = ti.get("command")
        if not isinstance(command, str):
            return 0
        if harness_antigo(command):
            return deny(root, f"harness antigo: {command[:100]}", quadro("harness antigo", [
                ("comando", command.split()[0]), ("motivo", "os scripts de `.harness/` são do modelo antigo; os portões são do tr"),
            ], lista(reg, registry.missing(root, "fim", reg)) or ["  → valide a entrega com `portao entrega`"],
                "estado: `portao`"))
        if portao_combinado(command):
            return deny(root, f"portao combinado: {command[:100]}", quadro("portao sozinho", [
                ("comando", command[:80]), ("motivo", "com pipe, `&&` ou redirecionamento o portão roda mas não carimba"),
            ], ["  → rode `portao <nome>` sozinho na chamada; a saída já vem resumida"]))
        targets = bash_targets(command)
    elif tool in EDICAO:
        path = ti.get("file_path") or ti.get("notebook_path")
        targets = [path] if isinstance(path, str) else []
    else:
        return 0

    for t in targets:
        if registry.is_code(root, t, reg):
            faltam = registry.missing(root, "inicio", reg)
            if faltam:
                return deny(root, f"escrita em código: {t}", quadro("escrita barrada", [
                    ("arquivo", registry.relative(root, t)), ("motivo", "falta a etapa de início"),
                ], lista(reg, faltam), "estado: `portao`"))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # sem leitura confiável, não barra por engano
        code = 0
    sys.exit(code)
