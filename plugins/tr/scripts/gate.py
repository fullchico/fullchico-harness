#!/usr/bin/env python3
"""O aplicador único dos portões do projeto (`PreToolUse`).

- Envio (`git push`, `gh pr create`) com portão de `fim` faltando: barra.
- Escrita em código (ferramentas de edição, ou o terminal nas formas óbvias) com portão de `inicio`
  faltando: barra, e diz qual etapa cumprir. No terminal é um aviso cedo; a barreira de verdade é a do envio.
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
import saida  # noqa: E402
from saida import quadro  # noqa: E402

PROTEGIDOS = (".claude/trilho.json", ".claude/settings.json")
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
        linhas += [f"    → {p}" for p in registry.passos(n, gate)]
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
    if tipo not in validadores:
        pedido = registry.modelo_do_ticket(root, ti.get("prompt"))
        modelo = pedido or (ti.get("model") if ti.get("model") in ("haiku", "sonnet") else registry.MODELO_EXECUTOR)
        if ti.get("model") == modelo:
            return 0
        novo["model"] = modelo
        return permitir(novo)
    top = ledger.head(root) or ""
    if registry.dirty(root):
        return deny(root, f"validador com árvore suja: {tipo}", quadro("validação barrada", [
            ("validador", tipo), ("motivo", "a árvore tem alteração sem commit"),
        ], ["  → faça o commit: o carimbo de fim é do commit do topo"]))
    if tipo == registry.VERIFICADOR:
        m = re.search(r"(?m)^\s*portao:\s*([\w.-]+)", ti.get("prompt") or "")
        nome = m.group(1) if m else None
        if nome not in validadores[tipo]:
            return deny(root, f"verificador sem portão: {nome}", quadro("validação barrada", [
                ("validador", tipo), ("motivo", f"`{nome}` não é portão de comando de fim do registro"),
            ], [f"  → peça com a primeira linha `portao: <nome>`; existem: {', '.join(validadores[tipo])}"]))
        novo["prompt"] = f"portao: {nome}\ncommit: {top}"
    else:
        mb = registry.merge_base(root)
        if not mb:
            return deny(root, f"validador sem base: {tipo}", quadro("validação barrada", [
                ("validador", tipo), ("motivo", "sem base para o diff (nem origin/HEAD, origin/main, main ou master)"),
            ], ["  → defina o remoto ou a branch padrão"]))
        novo["prompt"] = f"diff: {mb}...{top}\ncommit: {top}"
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
        if words and os.path.basename(words[0]) == "portao" and len(words) > 1 and (len(parts) > 1 or len(words) > 2):
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
        if registry.relative(root, t) == ".claude/trilho.json":
            return deny(root, f"registro: {t}", quadro("registro protegido", [
                ("arquivo", ".claude/trilho.json"),
                ("motivo", "só o dono altera, por `fullchico-harness portoes` no terminal"),
            ], rodape="o plugin tr escreve ali; o agente não"))

    try:
        reg = registry.load(root)
    except registry.RegistryError as e:
        if tool == "Bash" and isinstance(ti.get("command"), str) and ledger.is_send(ti["command"]):
            return deny(root, "registro inválido", quadro("envio barrado", [
                ("registro", ".claude/trilho.json"), ("motivo", f"registro de portões inválido: {e}")]))
        return 0
    if not reg:
        return 0

    if tool in ("Agent", "Task"):
        return disparo(root, reg, ti)
    agente = payload.get("agent_type")
    if agente and agente in registry.validadores(reg):
        alvos = targets_pre if tool in EDICAO or tool == "Bash" else []
        if any(registry.relative(root, t) for t in alvos):
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
            ], lista(reg, registry.missing(root, "fim", reg)) or ["  → nada falta: o envio é `git push`"],
                "estado: `portao`"))
        if portao_combinado(command):
            return deny(root, f"portao combinado: {command[:100]}", quadro("portao sozinho", [
                ("comando", command[:80]), ("motivo", "com pipe, `&&` ou redirecionamento o portão roda mas não carimba"),
            ], ["  → rode `portao <nome>` sozinho na chamada; a saída já vem resumida"]))
        if ledger.is_send(command):
            faltam = registry.missing(root, "fim", reg)
            if not faltam:
                return 0
            return deny(root, f"envio: {command[:100]}", quadro("envio barrado", [
                ("commit", (ledger.head(root) or "?")[:10]), ("motivo", "faltam portões de fim"),
            ], lista(reg, faltam), "o carimbo é do commit: commit novo pede os portões de novo · estado: `portao`"))
        targets = bash_targets(command)
    elif tool in EDICAO:
        path = ti.get("file_path") or ti.get("notebook_path")
        targets = [path] if isinstance(path, str) else []
    else:
        return 0

    for t in targets:
        if (registry.relative(root, t) or "").startswith(".git/"):
            # `.git/info/exclude` esconde arquivo sem commit da checagem de árvore limpa: o carimbo mentiria
            return deny(root, f"git interno: {t}", quadro("estado do git protegido", [
                ("arquivo", registry.relative(root, t)), ("motivo", "escrever em `.git/` muda o que a árvore limpa enxerga"),
            ], ["  → arquivo gerado vai no `.gitignore` (em commit); o resto, commit ou apague"]))
        if registry.relative(root, t) == ".claude/settings.json":
            return deny(root, f"registro: {t}", quadro("registro protegido", [
                ("arquivo", ".claude/settings.json"),
                ("motivo", "só o dono altera: ele liga os plugins que barram você"),
            ], rodape="o dono muda no terminal (`fullchico-harness install`, `fullchico-harness portoes`) ou à mão"))
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
