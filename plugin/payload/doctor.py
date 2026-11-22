#!/usr/bin/env python3
"""Diz se os trilhos do harness estão de pé neste projeto.

Uso: doctor.py [--hours N] [--json] [--prune]

Só lê, a não ser com --prune, que apaga do estado as aprovações e os pedidos de commit que não
existe mais. Sai 0 se está saudável, 1 se algo está quebrado (✗). Atenção (!) e informação (-)
não reprovam: são para o dono olhar.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "hooks"))
sys.path.insert(0, HERE)
import common  # noqa: E402

OK, BAD, WARN, INFO = "✓", "✗", "!", "-"
GATES = ("seguranca", "revisao", "bugs", "qualidade")
CONF_KEYS = ("VALIDATE_PUSH", "VALIDATE_MERGE", "VALIDATE_ARCH", "MODULE_ROOTS", "CONTRACT_PATHS", "TOKENS_CSS")
PERMISSION_WINDOW = 60  # minutos
_HOOK = re.compile(r"\.harness/hooks/([\w-]+\.py)")
_SHA = re.compile(r"^[0-9a-f]{40}$")
UTC = datetime.timezone.utc


class Report:
    def __init__(self):
        self.sections = []

    def section(self, title):
        self.sections.append({"title": title, "items": []})

    def add(self, status, text):
        self.sections[-1]["items"].append({"status": status, "text": text})

    @property
    def problems(self):
        return sum(1 for s in self.sections for i in s["items"] if i["status"] == BAD)


def parse_at(text):
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def read_jsonl(path, since):
    """Linhas de um registro do estado, de `since` para cá, cada uma com a hora já lida em `_at`."""
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        at = parse_at(row.get("at")) if isinstance(row, dict) else None
        if at and at >= since:
            rows.append(dict(row, _at=at))
    return rows


def ago(at, now) -> str:
    minutes = max(0, int((now - at).total_seconds() // 60))
    return f"há {minutes} min" if minutes < 120 else f"há {minutes // 60} h"


def clock(at) -> str:
    return at.astimezone().strftime("%d/%m %H:%M")


def check_tools(report):
    report.section("Ferramentas")
    where = shutil.which("python3")
    report.add(OK if where else BAD, f"python3 {sys.version.split()[0]}" + (f" ({where})" if where else
               ": não está no PATH; os hooks são chamados como `python3` e não rodam"))
    try:
        version = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        version = ""
    report.add(OK if version else BAD, version or "git: não encontrado")


def check_hooks(report, root):
    report.section("Hooks")
    try:
        with open(os.path.join(root, ".claude", "settings.json"), encoding="utf-8") as f:
            events = json.load(f).get("hooks", {})
    except (OSError, ValueError, AttributeError) as exc:
        report.add(BAD, f".claude/settings.json ilegível: {exc}")
        events = {}
    linked = {}
    for event, groups in (events.items() if isinstance(events, dict) else []):
        for group in (groups if isinstance(groups, list) else []):
            for hook in (group.get("hooks", []) if isinstance(group, dict) else []):
                m = _HOOK.search(str(hook.get("command", ""))) if isinstance(hook, dict) else None
                if not m:
                    continue
                name, matcher = m.group(1), group.get("matcher")
                where = event + (f" [{matcher}]" if matcher else "")
                linked.setdefault(name, []).append(where)
                # Guarda que quebra sem isto deixa a ação passar. O gate_stamp só carimba: não entra.
                if event == "PreToolUse" and name.endswith("_guard.py") and hook.get("onFailure") != "block":
                    report.add(BAD, f'{name} em {where} sem "onFailure": "block": se o hook falhar, a ação passa')
    folder = os.path.join(root, ".harness", "hooks")
    for name in sorted(linked):
        path = os.path.join(folder, name)
        try:
            with open(path, encoding="utf-8") as f:
                source = f.read()
        except OSError:
            report.add(BAD, f"{name}: ligado em {', '.join(linked[name])}, mas não existe em .harness/hooks/")
            continue
        try:
            compile(source, path, "exec")
        except (SyntaxError, ValueError) as exc:
            report.add(BAD, f"{name}: não compila (linha {getattr(exc, 'lineno', '?')}: {getattr(exc, 'msg', exc)})")
            continue
        report.add(OK, f"{name}: presente e compila ({', '.join(linked[name])})")
    try:
        present = sorted(n for n in os.listdir(folder) if n.endswith(".py") and n != "common.py")
    except OSError:
        present = []
        report.add(BAD, ".harness/hooks/ não existe")
    for name in present:
        if name not in linked:
            report.add(BAD, f"{name}: existe em .harness/hooks/ mas não está ligado no .claude/settings.json")
    if not linked:
        report.add(BAD, "nenhum hook do harness ligado no .claude/settings.json")


def check_managed(report, root):
    report.section("Arquivos gerenciados")
    try:
        import manifest_check  # aqui e não no topo: ele importa um hook, que pode ser justamente o quebrado
        with open(os.path.join(root, ".harness", "MANIFEST"), encoding="utf-8") as f:
            version = json.load(f).get("version")
        changed = manifest_check.drift(root)
    except Exception as exc:
        report.add(BAD, f"não deu para conferir contra o .harness/MANIFEST: {type(exc).__name__}: {exc}")
        return
    report.add(INFO, f"versão do harness no projeto: {version}")
    if not changed:
        # O settings.json é um deles: íntegro, ele liga exatamente os eventos que esta versão espera.
        report.add(OK, "íntegros: batem com o .harness/MANIFEST (inclui o .claude/settings.json)")
    for rel in changed[:15]:
        report.add(BAD, f"{rel}: alterado, sumiu ou está a mais")
    if len(changed) > 15:
        report.add(BAD, f"e mais {len(changed) - 15}; a lista inteira sai de `python3 -I .harness/manifest_check.py`")


def check_conf(report, root):
    report.section("Checagens do harness.conf")
    path = os.path.join(root, "harness.conf")
    if not os.path.exists(path):
        report.add(WARN, "harness.conf não existe: nenhuma checagem do projeto roda")
        return
    conf = common.read_conf(path)
    defined = [k for k in CONF_KEYS if conf.get(k)]
    missing = [k for k in CONF_KEYS if not conf.get(k)]
    report.add(INFO, "definidas: " + (", ".join(defined) or "nenhuma"))
    if missing:
        report.add(INFO, "sem valor: " + ", ".join(missing))


def check_log(report, state, root, hours, now):
    report.section(f"Registro dos hooks, últimas {hours:g} h")
    rows = read_jsonl(os.path.join(state, "log.jsonl"), now - datetime.timedelta(hours=hours))
    denied = [r for r in rows if r.get("what") == "negou"]
    by_hook = {}
    for row in denied:
        by_hook[row.get("hook")] = by_hook.get(row.get("hook"), 0) + 1
    if denied:
        report.add(INFO, f"negações: {len(denied)} ("
                   + ", ".join(f"{hook}: {count}" for hook, count in sorted(by_hook.items(), key=lambda i: (-i[1], str(i[0])))) + ")")
        for row in denied[-5:][::-1]:
            report.add(INFO, f"  {clock(row['_at'])} {row.get('hook')}: {str(row.get('detail', ''))[:110]}")
    else:
        report.add(INFO, "negações: nenhuma")
    for what in ("não carimbou", "erro"):
        for row in (r for r in rows if r.get("what") == what):
            report.add(WARN, f"{what}: {clock(row['_at'])} {row.get('hook')}: {str(row.get('detail', ''))[:200]}")
    if not rows:
        last = common._git(root, "log", "-1", "--all", "--format=%ct")
        commit = datetime.datetime.fromtimestamp(int(last), UTC) if last and last.isdigit() else None
        if commit and commit >= now - datetime.timedelta(hours=hours):
            report.add(WARN, f"trilho mudo: nenhum hook registrou nada no período, e houve commit {ago(commit, now)}. "
                             "Pode ser trabalho sem nenhuma negação; se houve sessão do Claude Code aqui, confira com "
                             "`/hooks` se eles estão rodando")


def check_gates(report, state, root):
    report.section("Portões no commit atual")
    head = common.head_sha(root)
    if not head:
        report.add(INFO, "repositório sem commit")
        return
    report.add(INFO, f"HEAD {head[:10]}")
    for gate in GATES:
        try:
            with open(common.approval_path(state, gate, head), encoding="utf-8") as f:
                record = json.load(f)
            by = record.get("by") or record.get("agent_type") or "?"
            report.add(OK, f"{gate}: aprovado ({record.get('status', '?')}, por {by})")
        except (OSError, ValueError, AttributeError):
            report.add(INFO, f"{gate}: sem aprovação para este commit")


def check_open(report, state, root, now):
    report.section("Em aberto")
    opened = [p for p in common.pendings(root) if isinstance(p, dict) and p.get("status") == "open"]
    report.add(INFO, f"pendências abertas nesta feature: {len(opened)}" + (" (`.harness/pendings` lista)" if opened else ""))
    try:
        direct = sorted(os.listdir(os.path.join(state, "direct")))
    except OSError:
        direct = []
    report.add(WARN if direct else INFO, f"sessões com edição direta liberada: {len(direct)}"
               + (" (" + ", ".join(direct[:5]) + ")" if direct else ""))
    asked = read_jsonl(os.path.join(state, "permissions.jsonl"), now - datetime.timedelta(minutes=PERMISSION_WINDOW))
    if not asked:
        report.add(INFO, f"pedidos de permissão nos últimos {PERMISSION_WINDOW} min: nenhum")
        return
    report.add(WARN, f"pedidos de permissão nos últimos {PERMISSION_WINDOW} min: {len(asked)}. O harness vê o pedido "
                     "aparecer, mas não há como saber se já foi respondido: olhe a tela do Claude Code")
    for row in asked[::-1]:
        label = f"{row['tool']}: {row.get('summary', '')}" if row.get("tool") else str(row.get("summary", ""))
        who = f" (agente {row['agent_type']})" if row.get("agent_type") else ""
        report.add(WARN, f"  visto {ago(row['_at'], now)}, {row.get('what', 'permissão pedida')}{who}: {label[:160]}")


def stale(state, root) -> list:
    """Aprovações e pedidos de commit que o repositório não tem mais. Na dúvida, lista vazia."""
    found = []
    for kind in ("approvals", "requests"):
        for folder, _, names in os.walk(os.path.join(state, kind)):
            found += [os.path.join(folder, n) for n in sorted(names) if n.endswith(".json") and _SHA.match(n[:-5])]
    if not found or not common.head_sha(root):
        return []
    ask = "".join(os.path.basename(p)[:-5] + "^{commit}\n" for p in found)
    try:
        r = subprocess.run(["git", "cat-file", "--batch-check"], cwd=root, input=ask, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    answers = r.stdout.splitlines()
    if r.returncode != 0 or len(answers) != len(found):
        return []
    return [path for path, answer in zip(found, answers) if answer.endswith(" missing")]


def check_stale(report, state, root, prune):
    report.section("Estado antigo")
    old = stale(state, root)
    if not old:
        report.add(INFO, "nenhuma aprovação ou pedido de commit que não existe mais")
        return
    if not prune:
        report.add(INFO, f"{len(old)} registro(s) de commit que não existe mais (aprovações e pedidos). "
                         "`.harness/doctor --prune` os remove; rode no seu terminal, o sandbox do agente não grava ali")
        return
    removed = 0
    for path in old:
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    left = len(old) - removed
    report.add(WARN if left else OK, f"removidos {removed} registro(s) de commit que não existe mais"
               + (f"; {left} não puderam ser apagados (dentro do sandbox do agente a gravação é negada: rode no seu terminal)"
                  if left else ""))


def main() -> int:
    parser = argparse.ArgumentParser(prog="doctor", description="Diz se os trilhos do harness estão de pé.")
    parser.add_argument("--hours", type=float, default=24, help="período do registro dos hooks (padrão: 24)")
    parser.add_argument("--json", action="store_true", help="os mesmos dados em JSON")
    parser.add_argument("--prune", action="store_true", help="apaga aprovações e pedidos de commit que não existe mais")
    args = parser.parse_args()

    now = datetime.datetime.now(UTC)
    root = common.repo_root(os.getcwd()) or os.path.dirname(HERE)
    state = common.state_dir(root)
    report = Report()
    check_tools(report)
    check_hooks(report, root)
    check_managed(report, root)
    check_conf(report, root)
    if state:
        check_log(report, state, root, args.hours, now)
        check_gates(report, state, root)
        check_open(report, state, root, now)
        check_stale(report, state, root, args.prune)
    else:
        report.section("Estado")
        report.add(BAD, "esta pasta não é um repositório git: sem ele não há portões nem registro")

    problems = report.problems
    if args.json:
        print(json.dumps({"ok": not problems, "root": root, "problems": problems, "sections": report.sections},
                         ensure_ascii=False, indent=2))
        return 1 if problems else 0
    print(f"Harness doctor: {root}")
    print(f"{OK} certo   {BAD} quebrado   {WARN} atenção   {INFO} informação")
    for section in report.sections:
        print(f"\n{section['title']}")
        for item in section["items"]:
            print(f"  {item['status']} {item['text']}")
    print("\nResultado: " + (f"{problems} problema(s) ({BAD}). Os trilhos NÃO estão inteiros." if problems
                             else "trilhos de pé."))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
