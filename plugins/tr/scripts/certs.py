"""Certificados dos portões: no apêndice do documento da demanda e assinados por commit.

Um certificado diz que um estado (a chave: conteúdo do código e critério aceito) passou por um portão. Ele
mora no próprio documento que foi combinado (o apêndice da spec da demanda; o do ticket para o que é do
ticket), viaja com o repositório e vale em qualquer máquina ou agente. A assinatura é o commit que traz a
linha: só o responsável pelo portão o faz, com o trailer `Certified-by: <responsável>`. Linha sem commit, ou
de commit sem o trailer do responsável, não vale.

O apêndice não é critério: os hashes do critério e dos artefatos ignoram o bloco, porque assinar não muda o
texto assinado. Fora do Git não há assinatura, e vale o apêndice.
"""
import hashlib
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone

START = "<!-- tr:certificates: written by the tr hooks; do not edit -->"
END = "<!-- /tr:certificates -->"
_BLOCK = re.compile(r"\n*^## Certificates\n+" + re.escape(START) + r".*?^" + re.escape(END) + r"[^\n]*\n?",
                    re.M | re.S)
_LINE = re.compile(r"^- `([\w.-]+)` · (APPROVED|REJECTED) · ([0-9a-f]{40}) · `([^`]+)` · tr ([\w.-]+) · (\S+) · (.*)$",
                   re.M)
_PROGRESS = re.compile(r"(?mi)^\s*(?:Status|Delivery):.*$")  # andamento, não critério
OWNER = "owner"
ACCEPT = "accept"  # o aceite do dono sobre o critério, no fim da entrevista
FALLBACK = ".claude/certificates.md"  # sem demanda ativa: o registro do projeto
TRAILER = "Certified-by"


def strip(text):
    """O texto sem o apêndice de certificados."""
    return _BLOCK.sub("\n", text).rstrip("\n") + "\n" if _BLOCK.search(text) else text


def block(text):
    """O bloco de certificados do texto, ou vazio."""
    m = _BLOCK.search(text or "")
    return m.group(0).strip() if m else ""


def _read(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return stream.read()
    except OSError:
        return None


def demand(root):
    path = os.path.join(root, ".claude", "current-demand")
    text = _read(path)
    slug = (text or "").strip()
    return slug if re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug) else None


def _specs(root):
    """As pastas de demanda em jogo: a ativa, ou todas quando nenhuma está marcada (como os tickets)."""
    import glob
    slug = demand(root)
    if slug:
        return [os.path.join(root, "docs", "specs", slug)]
    return sorted(d for d in glob.glob(os.path.join(root, "docs", "specs", "*")) if os.path.isdir(d))


def document(root, ticket=None):
    """Onde o certificado mora: o ticket, a spec da demanda ou, sem uma spec só, o registro do projeto."""
    if ticket:
        return ticket
    specs = [d for d in _specs(root) if os.path.isfile(os.path.join(d, "spec.md"))]
    if len(specs) == 1:
        return os.path.relpath(os.path.join(specs[0], "spec.md"), root).replace(os.sep, "/")
    return FALLBACK


def criterion(root):
    """Hash do critério da demanda: spec e tickets, sem apêndice nem andamento. Vazio sem demanda."""
    files = []
    for base in _specs(root):
        for folder, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if d != "progress"]  # andamento (ajustes, handoffs, balanço) não é critério
            files += [os.path.join(folder, n) for n in names if n.endswith(".md")]
    digest = hashlib.sha1()
    for path in sorted(files):
        digest.update(os.path.relpath(path, root).replace(os.sep, "/").encode() + b"\0")
        digest.update(_PROGRESS.sub("", strip(_read(path) or "")).encode())
    return digest.hexdigest() if files else ""


def criterion_at(root, sha):
    """O hash do critério como estava no commit `sha` (mesma regra de `criterion`)."""
    slug = demand(root)
    if not slug:
        return ""
    listed = _git(root, "ls-tree", "-r", "--name-only", sha, "--", f"docs/specs/{slug}") or ""
    files = sorted(p for p in listed.splitlines() if p.endswith(".md") and "/progress/" not in p)
    digest = hashlib.sha1()
    for rel in files:
        digest.update(rel.encode() + b"\0")
        digest.update(_PROGRESS.sub("", strip(_git(root, "show", f"{sha}:{rel}") or "")).encode())
    return digest.hexdigest() if files else ""


def commit_of(root, doc, entry):
    """O commit que assinou a linha, ou None."""
    blame = _git(root, "blame", "--porcelain", "-L", f"{entry['line']},{entry['line']}", "--", doc)
    sha = (blame or "").split(" ", 1)[0]
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) and set(sha) != {"0"} else None


def entries(root, doc):
    text = _read(os.path.join(root, doc)) or ""
    block = _BLOCK.search(text)
    if not block:
        return []
    out = []
    for m in _LINE.finditer(block.group(0)):
        line = text[:block.start() + m.start()].count("\n") + 1  # a linha no arquivo, para o blame
        out.append({"name": m.group(1), "verdict": m.group(2), "key": m.group(3), "by": m.group(4),
                    "version": m.group(5), "at": m.group(6), "summary": m.group(7), "line": line})
    return out


def _git(root, *args, check=False):
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if check and r.returncode != 0:
        return None
    return r.stdout if r.returncode == 0 else None


def _write_git(root, *args):
    """Comando que grava no índice: outro processo (um `git status` do editor, outro hook) pode estar com o
    `index.lock`; tenta de novo por alguns segundos. Devolve None se deu certo, ou o erro do git."""
    import time
    error = "git não respondeu"
    for attempt in range(8):
        try:
            r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            return str(exc)
        if r.returncode == 0:
            return None
        error = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["sem mensagem"]
        error = error[0]
        if "index.lock" not in (r.stderr or ""):
            return error
        time.sleep(0.5 * (attempt + 1))
    return error


def _in_git(root):
    return (_git(root, "rev-parse", "--is-inside-work-tree") or "").strip() == "true"


def signed(root, doc, entry):
    """A linha entrou por um commit do responsável (trailer `Certified-by`)? Fora do Git, vale a linha."""
    if not _in_git(root):
        return True
    blame = _git(root, "blame", "--porcelain", "-L", f"{entry['line']},{entry['line']}", "--", doc)
    sha = (blame or "").split(" ", 1)[0]
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or set(sha) == {"0"}:
        return False
    body = _git(root, "show", "-s", "--format=%B", sha) or ""
    return re.search(rf"(?m)^{TRAILER}: {re.escape(entry['by'])}\s*$", body) is not None


def current(root, name, key, ticket=None, by=None):
    """O certificado vigente daquele portão para a chave (o último registro vale), ou None."""
    doc = document(root, ticket)
    found = [e for e in entries(root, doc) if e["name"] == name and e["key"] == key]
    if not found:
        return None
    last = found[-1]
    if by and last["by"] != by:
        return None
    return last if signed(root, doc, last) else None


def has(root, name, key, ticket=None, by=None):
    entry = current(root, name, key, ticket, by)
    return bool(entry) and entry["verdict"] == "APPROVED"


def accepted(root):
    """O dono aceitou o critério atual da demanda? Sem demanda, não há o que aceitar."""
    key = criterion(root)
    return not key or has(root, ACCEPT, key, by=OWNER)


def rejections(root, name, ticket=None):
    """Reprovações registradas daquele portão na demanda (o histórico vai junto do documento)."""
    return [e for e in entries(root, document(root, ticket)) if e["name"] == name and e["verdict"] == "REJECTED"]


def version():
    import json
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude-plugin", "plugin.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)["version"]
    except (OSError, ValueError, KeyError):
        return "unknown"


def _clean(summary, root):
    """O texto do certificado entra no Git: nada da máquina de quem rodou vai junto. Caminhos do projeto viram
    relativos, a pasta pessoal vira `~` e a pasta temporária vira `<tmp>` (o nome do usuário mora nesses caminhos)."""
    import tempfile
    text = " ".join((summary or "").split())
    swaps = [(os.path.realpath(root), "."), (root, "."), (os.path.expanduser("~"), "~"),
             (os.path.realpath(tempfile.gettempdir()), "<tmp>"), (tempfile.gettempdir(), "<tmp>")]
    for found, shown in sorted(swaps, key=lambda pair: -len(pair[0])):
        if found and found not in ("/", "."):
            text = text.replace(found.rstrip("/"), shown)
    text = re.sub(r"/(?:Users|home)/[^/\s]+", "~", text)            # a pasta pessoal de outra máquina
    text = re.sub(r"(?:/private)?/var/folders/\S+?/T(?=/|\b)", "<tmp>", text)  # a temporária do macOS, por usuário
    return text[:300]


def certify(root, name, key, verdict, by, summary, ticket=None):
    """`record` sem repetir o mesmo veredito (o relatório e o fecho do subagente trazem o mesmo bloco)."""
    doc = document(root, ticket)
    found = [e for e in entries(root, doc) if e["name"] == name]
    last = found[-1] if found else {}
    if (last.get("key"), last.get("verdict"), last.get("by"), last.get("summary")) == \
            (key, verdict, by, _clean(summary, root)) and signed(root, doc, last):
        return None  # já está assinado; uma linha que ficou sem commit é escrita de novo
    return record(root, name, key, verdict, by, version(), summary, ticket)


def _lock(root):
    try:
        import fcntl
    except ImportError:
        return None
    key = hashlib.sha1(os.path.realpath(root).encode()).hexdigest()[:12]
    try:
        stream = open(os.path.join(tempfile.gettempdir(), f"tr-certs-{key}.lock"), "w")
        fcntl.flock(stream, fcntl.LOCK_EX)
        return stream
    except OSError:
        return None


def record(root, name, key, verdict, by, version, summary, ticket=None):
    lock = _lock(root)  # revisores em paralelo: um commit por vez
    try:
        return _record(root, name, key, verdict, by, version, summary, ticket)
    finally:
        if lock:
            lock.close()


def _record(root, name, key, verdict, by, version, summary, ticket=None):
    """Escreve a linha no apêndice e assina com o commit do responsável. Devolve None ou o motivo da recusa.

    Recusa se o documento tem alteração sem commit fora do apêndice: o commit do responsável assinaria um
    texto que ninguém combinou."""
    doc = document(root, ticket)
    path = os.path.join(root, doc)
    git = _in_git(root)
    text = _read(path)
    if git and text is not None:
        committed = _git(root, "show", f"HEAD:{doc}", check=True)
        if committed is None and doc != FALLBACK:
            return f"{doc} ainda não tem commit; faça o commit do documento antes do certificado"
        if committed is not None and strip(committed) != strip(text):
            return f"{doc} tem alteração sem commit; faça o commit do documento antes do certificado"
        if committed is not None:
            text = committed  # linha de certificado sem commit (assinatura que falhou) não pega carona
    summary = _clean(summary, root)
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"- `{name}` · {verdict} · {key} · `{by}` · tr {version} · {at} · {summary}"
    base = text if text is not None else ""
    block = _BLOCK.search(base)
    if block:
        inner = block.group(0).rstrip("\n")
        inner = inner[:inner.rindex(END)].rstrip("\n") + "\n" + line + "\n" + END + "\n"
        new = base[:block.start()] + "\n\n" + inner.lstrip("\n") + base[block.end():]
    else:
        new = base.rstrip("\n") + ("\n\n" if base.strip() else "") + f"## Certificates\n\n{START}\n{line}\n{END}\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(new)
    if not git:
        return None
    failed = _write_git(root, "add", "-f", "--", doc)
    if failed:
        return f"não consegui preparar {doc} para o commit: {failed}"
    # ponytail: --no-verify, o commit só traz o apêndice; hooks do projeto (lint, mensagem) não têm o que
    # validar ali e poderiam recusar a assinatura
    message = f"chore(tr): certify {name} ({verdict.lower()})"
    failed = _write_git(root, "commit", "--no-verify", "-q", "-m", message, "-m", f"{TRAILER}: {by}", "--", doc)
    if failed:
        return f"o commit do certificado de {name} falhou: {failed}"
    return None
