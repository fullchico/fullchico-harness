#!/usr/bin/env python3
"""Painel da entrega: uma página que o dono abre uma vez no navegador e acompanha.

Junta o que os trilhos já sabem (tickets, `resume`, despachos, portões, pendências, registro dos
hooks, commits) e o que o `activity.py` registra (que agente começou e terminou). Só lê o
repositório e o estado; a única escrita é `.harness-run/painel.html`.

Uso: board.py <raiz> [--json | --text | --watch [segundos]]
Sai 0 sempre que consegue escrever a página, mesmo sem entrega nenhuma; 2 para uso errado.

O que o painel não sabe: o que cada agente está fazendo neste instante (só que começou e não
terminou), e se um pedido de permissão já foi respondido (o harness vê o pedido aparecer, não
a resposta). A página diz isso onde importa.
"""
import calendar
import html
import json
import os
import re
import socket
import sys
import time

sys.dont_write_bytecode = True  # não deixa __pycache__ dentro de .harness/ do projeto
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "hooks"))
import common  # noqa: E402
import resume  # noqa: E402
import tickets_check  # noqa: E402

GATES = (("seguranca", "Segurança"), ("revisao", "Revisão de código"), ("bugs", "Caça a bugs"), ("qualidade", "Qualidade"))
VISUAL = ("visual", "Conferência das telas")
ROLES = {"harness:orquestrador": "orquestrador (conduz a entrega)", "harness:implementador": "implementador",
         "harness:revisor-bugs": "revisor de bugs", "harness:revisor-ambiente": "revisor de ambiente",
         "harness:revisor": "revisor de código", "harness:seguranca": "revisor de segurança",
         "harness:qualidade": "revisor de qualidade", "harness:revisor-spec": "revisor da especificação",
         "harness:extrator": "extrator de aprendizados"}
ACTIONS = {"integrar": "aprovado na revisão; falta juntar à entrega", "revisar": "trabalho pronto; falta pedir a revisão",
           "esperar": "em trabalho", "corrigir": "a revisão achou problema; volta para correção",
           "despachar": "reservado; ainda sem ninguém trabalhando", "parado": "parado: sem sinal além do limite"}
STATES = {"none": ("○", "Nenhuma entrega em andamento"), "working": ("▶", "Trabalhando"),
          "waiting_owner": ("✋", "Esperando você"), "stalled": ("⏸", "Parada"), "done": ("✔", "Concluída"),
          "not_started": ("○", "Ainda não começou")}
ACTIVE_WINDOW = 3 * 3600   # `start` sem `stop` mais velho que isto é agente que morreu sem avisar
PERMISSION_FRESH = 10 * 60  # pedido de permissão mais novo que isto conta como esperando, haja o que houver depois
TAIL = 200_000             # bytes lidos do fim de cada registro: o painel só olha o que é recente
TIMELINE = 25
_PR = re.compile(r"https://[^\s\"')]+/pull/\d+")
_ISO = "%Y-%m-%dT%H:%M:%SZ"


def _epoch(text):
    try:
        return calendar.timegm(time.strptime(text, _ISO))
    except (TypeError, ValueError):
        return None


def _tail(path) -> list:
    """As linhas recentes de um registro do estado, cada uma com a hora em segundos em `_at`."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - TAIL))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines[1:] if size > TAIL else lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        at = _epoch(row.get("at")) if isinstance(row, dict) else None
        if at is not None:
            rows.append(dict(row, _at=at))
    return rows


def _span(seconds) -> str:
    minutes = max(0, int(seconds)) // 60
    if minutes < 60:
        return f"{minutes} min" if minutes else "menos de 1 min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min" if hours < 24 else f"{hours // 24} d {hours % 24} h"


def _clock(at, when) -> str:
    local = time.localtime(at)
    same_day = time.strftime("%Y%m%d", local) == time.strftime("%Y%m%d", time.localtime(when))
    return time.strftime("%H:%M" if same_day else "%d/%m %H:%M", local)


def _heading(path, fallback) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("# ") and line[2:].strip():
                    return line[2:].strip()
    except (OSError, ValueError):
        pass
    return fallback


def _text(value, limit=160) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit] + "…"


def _role(agent_type) -> str:
    name = agent_type if isinstance(agent_type, str) and agent_type else "agente"
    return ROLES.get(name) or name.split(":")[-1]


def _specs(root):
    """As specs com tickets, e as que não puderam ser lidas (para a página dizer, em vez de quebrar)."""
    base, found, problems = os.path.join(root, "docs", "specs"), [], []
    for slug in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        try:
            tickets = tickets_check.load(os.path.join(base, slug, "issues"))
        except (ValueError, OSError) as exc:
            problems.append(f"Não consegui ler os tickets de {slug}: {_text(str(exc).replace(root + os.sep, ''), 240)}")
            continue
        if tickets:
            found.append((f"docs/specs/{slug}", tickets))
    return found, problems


def _pick(root, specs):
    """A entrega em andamento: a spec com ticket por fechar; entre várias, a mexida por último."""
    pool = [s for s in specs if any(t["status"] != "done" for t in s[1].values())] or specs
    if len(pool) > 1:
        pool = sorted(pool, key=lambda s: int(common._git(root, "log", "-1", "--format=%ct", "--", s[0]) or 0))
    return pool[-1] if pool else None


def _dispatches(state, root) -> list:
    folder, here, found = os.path.join(state, "dispatches"), os.path.realpath(root), []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        record = resume._load(os.path.join(folder, name)) if name.endswith(".json") else None
        if record and record.get("root") == here and isinstance(record.get("at"), int) and isinstance(record.get("ticket"), str):
            found.append(record)
    return found


def _agents(rows, dispatches, when) -> list:
    """Quem começou e não terminou. O ticket vem do despacho aceito logo antes do começo."""
    started = {}
    for row in rows:
        if row.get("event") == "start":
            started[row.get("agent_id")] = row
        elif row.get("event") == "stop":
            started.pop(row.get("agent_id"), None)
    found, used = [], set()
    for row in sorted(started.values(), key=lambda r: r["_at"]):
        if when - row["_at"] > ACTIVE_WINDOW:
            continue
        # ponytail: casa pelo tipo do agente e pela hora (despacho até 2 min antes do começo); dois
        # despachos do mesmo tipo no mesmo instante podem sair trocados. O certo é o despacho
        # guardar o `agent_id`, o que só dá para fazer no dispatch_guard.py.
        near = [d for d in dispatches if d.get("agent") == row.get("agent_type") and id(d) not in used
                and -5 <= row["_at"] - d["at"] <= 120]
        sent = min(near, key=lambda d: d["at"], default=None)
        used.add(id(sent))
        found.append({"agent_id": row.get("agent_id"), "agent_type": row.get("agent_type"), "role": _role(row.get("agent_type")),
                      "since": row["_at"], "minutes": (when - row["_at"]) // 60,
                      "ticket": os.path.basename(sent["ticket"])[:-3] if sent else None})
    return found


def _who(item) -> str:
    if item.get("commit"):
        asked = [g for g in ("bugs", "ambiente") if item.get(g, {}).get("state") == "waiting"]
        return " e ".join(_role(resume.REVIEWER[g]) for g in asked) or "orquestrador"
    return "implementador" if item["action"] in ("esperar", "parado") else "orquestrador"


def _cards(root, spec, tickets, report, dispatches, when) -> list:
    doing = {t["number"]: t for t in (report or {}).get("tickets", [])}
    try:
        findings = os.listdir(os.path.join(root, spec, "achados"))
    except OSError:
        findings = []
    cards = []
    for number, ticket in sorted(tickets.items()):
        owns = ticket["owns"]
        card = {"number": number, "name": os.path.basename(ticket["path"])[:-3],
                "title": _heading(ticket["path"], os.path.basename(ticket["path"])[:-3]),
                "owns": ", ".join(owns[:2]) + (f" e mais {len(owns) - 2}" if len(owns) > 2 else ""),
                "status": ticket["status"], "column": {"open": "todo", "claimed": "doing", "done": "done"}[ticket["status"]]}
        if ticket["status"] == "claimed":
            item = doing.get(number, {"action": "despachar", "next": ""})
            sent = [d["at"] for d in dispatches if d["ticket"].endswith(f"/{card['name']}.md")]
            minutes = item.get("waiting_min")
            if minutes is None and sent:
                minutes = (when - max(sent)) // 60
            who = _who(item)
            label = "em revisão" if item["action"] == "esperar" and who != "implementador" else ACTIONS.get(item["action"], item["action"])
            card.update(who=who, minutes=minutes, action=item["action"], label=label, next=item.get("next", ""),
                        stalled=item["action"] == "parado",
                        rounds=sum(1 for n in findings if re.match(rf"^{number:02d}-rodada-.*\.md$", n)))
        cards.append(card)
    return cards


def _timeline(root, log, activity, when) -> list:
    events = []
    for line in (common._git(root, "log", "-30", "--format=%ct%x09%s") or "").splitlines():
        at, _, subject = line.partition("\t")
        merge = subject.startswith("Merge ticket")
        events.append({"at": int(at), "kind": "merge" if merge else "commit",
                       "text": ("Ticket integrado: " + os.path.basename(subject.split()[-1])[:-3] if merge and subject.endswith(".md")
                                else ("Ticket integrado: " if merge else "Commit: ") + _text(subject))})
    wording = {"negou": "Trilho barrou uma ação", "carimbou": "Revisão aprovada", "não carimbou": "Revisão sem aprovação",
               "permissão pedida": "Pedido de permissão para você", "permissão esperando": "Pedido de permissão esperando você",
               "segurou": "Orquestrador segurado até os agentes dele terminarem", "violou": "Código alterado fora do fluxo",
               "erro": "Erro num trilho"}
    for row in log:
        what = str(row.get("what", ""))
        events.append({"at": row["_at"], "kind": {"negou": "denied", "carimbou": "stamp"}.get(what, "rail"),
                       "text": f"{wording.get(what, what)} ({row.get('hook', '?')}): {_text(row.get('detail'))}"})
    for row in activity:
        if row.get("event") in ("start", "stop"):
            verb = "Começou" if row["event"] == "start" else "Terminou"
            events.append({"at": row["_at"], "kind": row["event"],
                           "text": f"{verb}: {_role(row.get('agent_type'))}"
                                   + (f" ({_text(row['outcome'])})" if row.get("outcome") else "")})
    events.sort(key=lambda e: e["at"], reverse=True)
    return [dict(e, clock=_clock(e["at"], when)) for e in events[:TIMELINE]]


def _port_open(port) -> bool:
    try:
        socket.create_connection(("localhost", int(port)), timeout=0.3).close()
        return True
    except (OSError, ValueError):
        return False


def _result(root, conf, log) -> dict:
    port = common.read_conf(os.path.join(root, ".env")).get("WEB_PORT", "")
    screens = conf.get("SCREENS_DIR", "").strip("/")
    urls = [m.group(0) for row in log for m in [_PR.search(str(row.get("detail", "")))] if m]
    return {"app": f"http://localhost:{port}" if port.isdigit() else None,
            "app_up": _port_open(port) if port.isdigit() else False,
            "screens": f"{screens}/index.html" if screens and os.path.isfile(os.path.join(root, screens, "index.html")) else None,
            "design": "DESIGN.md" if os.path.isfile(os.path.join(root, "DESIGN.md")) else None,
            "pr": urls[-1] if urls else None}


def _waiting(permissions, activity, quiet_since, when):
    """O pedido de permissão que pode estar na tela: o mais novo, se nada aconteceu depois dele
    (ou se é de agora), e se o agente que pediu ainda não terminou."""
    if not permissions:
        return None
    last = permissions[-1]
    age = when - last["_at"]
    ended = any(r.get("event") == "stop" and r.get("agent_id") == last.get("agent_id") and r["_at"] >= last["_at"]
                for r in activity) if last.get("agent_id") else False
    if ended or age > ACTIVE_WINDOW or not (age <= PERMISSION_FRESH or last["_at"] >= quiet_since):
        return None
    return last


def collect(root) -> dict:
    """O retrato da entrega, para a página, o `--json` e o `--text`. Nunca levanta por falta de dado."""
    # Cada chamada ao git custa uns 10 ms e o `resume` repete várias. Num retrato só, a mesma
    # pergunta tem a mesma resposta: guarda-se a resposta enquanto ele é montado.
    asked, git = {}, common._git

    def remembered(cwd, *args):
        if (cwd, args) not in asked:
            asked[(cwd, args)] = git(cwd, *args)
        return asked[(cwd, args)]

    common._git = remembered
    try:
        return _collect(root)
    finally:
        common._git = git


def _collect(root) -> dict:
    when = resume.now()
    data = {"at": when, "root": root, "spec": None, "name": None, "feature": None, "started": None, "state": "none",
            "headline": STATES["none"][1], "detail": "Quando uma entrega começar, ela aparece aqui.",
            "total": 0, "done": 0, "tickets": [], "agents": [], "head": None, "gates": [],
            "pendings": {"count": 0, "texts": []}, "timeline": [], "result": {}, "warnings": [], "timeout_min": None}
    state = common.state_dir(root) if root and os.path.isdir(root) else None
    if not state:
        data["detail"] = "Esta pasta não é um repositório git: não há o que acompanhar."
        return data
    conf = common.read_conf(os.path.join(root, "harness.conf"))
    log, activity = _tail(os.path.join(state, "log.jsonl")), _tail(os.path.join(state, "activity.jsonl"))
    permissions, dispatches = _tail(os.path.join(state, "permissions.jsonl")), _dispatches(state, root)
    data["feature"] = common._git(root, "branch", "--show-current")
    data["agents"] = _agents(activity, dispatches, when)
    data["timeline"] = _timeline(root, log, activity, when)
    data["result"] = _result(root, conf, log)
    opened = [p for p in common.pendings(root) if isinstance(p, dict) and p.get("status") == "open"]
    data["pendings"] = {"count": len(opened), "texts": [_text(p.get("text"), 240) for p in opened[:5]]}
    head = data["head"] = common.head_sha(root)
    for gate, label in GATES + ((VISUAL,) if conf.get("SCREENS_DIR") else ()):
        record = resume._load(common.approval_path(state, gate, head)) if head else None
        data["gates"].append({"gate": gate, "label": label, "approved": bool(record) and record.get("status") == "PASS"})

    specs, data["warnings"] = _specs(root)
    chosen = _pick(root, specs)
    if not chosen:
        return data
    spec, tickets = chosen
    try:
        report = resume.report(root, spec)
    except Exception as exc:  # o painel não cai porque o `resume` não leu um ticket
        report = None
        data["warnings"].append(f"Não consegui ler o andamento dos tickets: {_text(exc, 240)}")
    limit = data["timeout_min"] = resume.timeout_min(root)
    first = (common._git(root, "log", "--format=%ct", "--", spec) or "").split()
    data.update(spec=spec, name=_heading(os.path.join(root, spec, "spec.md"), os.path.basename(spec)),
                started=int(first[-1]) if first else None, total=len(tickets),
                done=sum(1 for t in tickets.values() if t["status"] == "done"),
                tickets=_cards(root, spec, tickets, report, dispatches, when))

    # O último sinal de vida: commit na feature ou num worktree de agente, linha de um trilho, agente, despacho.
    # (As duas consultas abaixo já foram feitas para a linha do tempo e para o `resume`: saem da memória.)
    signs = [b["time"] for b in resume.agent_branches(root)]
    signs += [int(line.split("\t")[0]) for line in (common._git(root, "log", "-30", "--format=%ct%x09%s") or "").splitlines()[:1]]
    signs += [d["at"] for d in dispatches] + [r["_at"] for r in activity[-1:]]
    signs += [r["_at"] for r in log if r.get("hook") != "notify"][-1:]  # o pedido de permissão não é sinal de trabalho
    quiet_since = max(signs, default=0)
    idle = max(0, when - quiet_since)
    asked = _waiting(permissions, activity, quiet_since, when)
    ended = [r for r in activity if r.get("agent_type") == "harness:orquestrador"]
    stopped = ended[-1].get("outcome", "") if ended and ended[-1].get("event") == "stop" else ""
    left = data["total"] - data["done"]
    if asked:
        label = f"{asked['tool']}: {asked.get('summary', '')}" if asked.get("tool") else str(asked.get("summary", ""))
        who = f" pelo {_role(asked['agent_type'])}" if asked.get("agent_type") else ""
        state_name, detail = "waiting_owner", (
            f"Pedido de permissão visto há {_span(when - asked['_at'])}{who}: {_text(label)}. Responda na tela do "
            "Claude Code. O painel vê o pedido aparecer, mas não sabe se já foi respondido.")
    elif stopped.startswith("ENTREGA: PARADA"):
        state_name, detail = "waiting_owner", (
            "A entrega parou e precisa de uma decisão sua: " + (_text(stopped[len("ENTREGA: PARADA"):], 300) or "veja a sessão."))
    elif not left and not data["agents"]:
        state_name, detail = "done", f"Os {data['total']} tickets foram concluídos."
    elif not left:
        state_name, detail = "working", "Todos os tickets concluídos; a entrega está sendo fechada (revisões finais e envio)."
    elif idle > limit * 60 and not data["done"] and not data["agents"] and all(t["status"] == "open" for t in tickets.values()):
        state_name, detail = "not_started", "Os tickets estão escritos, mas ninguém começou a trabalhar neles."
    elif idle > limit * 60:
        state_name, detail = "stalled", (
            f"Nenhum sinal de atividade há {_span(idle)} (o limite é {limit} min) e ainda faltam {left} tickets. Olhe a "
            "sessão do Claude Code: pode ser pedido de permissão na tela, queda de rede ou a sessão encerrada.")
    else:
        busy = sum(1 for t in data["tickets"] if t["column"] == "doing")
        state_name, detail = "working", f"{busy} em andamento, {len(data['agents'])} agentes ativos. Último sinal há {_span(idle)}."
    data.update(state=state_name, detail=detail, idle_min=idle // 60,
                headline=STATES[state_name][1] + (f" há {_span(idle)}" if state_name == "stalled" else ""))
    return data


def summary(data) -> str:
    """Uma linha: é o que o `--watch` imprime a cada mudança."""
    if not data["spec"]:
        return data["headline"]
    doing = [f"{t['number']:02d}" for t in data["tickets"] if t["column"] == "doing"]
    return (f"{data['headline']} · {data['name']} · {data['done']} de {data['total']} tickets concluídos"
            + (f" · em andamento: {', '.join(doing)}" if doing else "") + f" · {len(data['agents'])} agentes ativos")


def _card_line(card) -> str:
    parts = [card["who"]] + ([f"há {_span(card['minutes'] * 60)}"] if card.get("minutes") is not None else [])
    if card.get("rounds"):
        parts.append(f"{card['rounds']} rodada{'s' if card['rounds'] > 1 else ''} de correção")
    return ", ".join(parts)


def render_text(data) -> str:
    when = data["at"]
    lines = [f"{STATES[data['state']][0]} {data['headline']}", f"  {data['detail']}"]
    if data["spec"]:
        age = f", começou há {_span(when - data['started'])}" if data["started"] else ""
        lines += ["", f"Entrega: {data['name']} ({data['spec']}{age})",
                  f"Progresso: {data['done']} de {data['total']} tickets concluídos", "", "Em andamento:"]
        doing = [t for t in data["tickets"] if t["column"] == "doing"]
        for card in doing:
            lines.append(f"  {'⏸ ' if card['stalled'] else ''}{card['number']:02d} {card['title']}: {_card_line(card)}; {card['label']}")
        lines += [] if doing else ["  nenhum"]
        for column, title in (("todo", "A fazer"), ("done", "Concluídos")):
            lines.append(f"{title}: " + (", ".join(f"{t['number']:02d} {t['title']}" for t in data["tickets"]
                                                   if t["column"] == column) or "nenhum"))
    lines += ["", "Agentes ativos agora: " + ("; ".join(
        f"{a['role']}" + (f" no ticket {a['ticket']}" if a["ticket"] else "") + f" há {_span(a['minutes'] * 60)}"
        for a in data["agents"]) or "nenhum")]
    if data["gates"]:
        lines.append(f"Portões do commit {(data['head'] or '')[:7]}: " + " · ".join(
            f"{g['label']} {'✓ aprovado' if g['approved'] else '– faltando'}" for g in data["gates"]))
    lines.append(f"Pendências abertas: {data['pendings']['count']}")
    lines += [f"  - {text}" for text in data["pendings"]["texts"]]
    if data["timeline"]:
        lines += ["", "Últimos eventos:"] + [f"  {e['clock']} {e['text']}" for e in data["timeline"][:8]]
    result = data["result"]
    if result.get("app"):
        lines += ["", f"Aplicativo: {result['app']} ({'respondendo' if result['app_up'] else 'não está respondendo agora'})"]
    lines += [f"{label}: {result[key]}" for key, label in (("screens", "Telas"), ("design", "Design"), ("pr", "Pull request"))
              if result.get(key)]
    lines += [f"! {w}" for w in data["warnings"]]
    return "\n".join(lines) + "\n"


CSS = """
:root{--bg:#f4f4f5;--card:#fff;--ink:#18181b;--soft:#52525b;--line:#d4d4d8;--ok:#14532d;--okbg:#dcfce7;--warn:#713f12;--warnbg:#fef3c7;--bad:#7f1d1d;--badbg:#fee2e2;--info:#1e3a8a;--infobg:#dbeafe}
@media(prefers-color-scheme:dark){:root{--bg:#18181b;--card:#27272a;--ink:#fafafa;--soft:#d4d4d8;--line:#52525b;--ok:#bbf7d0;--okbg:#14532d;--warn:#fde68a;--warnbg:#713f12;--bad:#fecaca;--badbg:#7f1d1d;--info:#bfdbfe;--infobg:#1e3a8a}}
*{box-sizing:border-box}
body{margin:0;font:16px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--ink)}
main{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:0}h2{font-size:17px;margin:0 0 10px}h3{font-size:15px;margin:0 0 8px;color:var(--soft)}
p{margin:4px 0}ul{margin:0;padding-left:20px}li{margin:3px 0}a{color:inherit}
section,.strip{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:0 0 14px}
.strip{border-width:2px}.strip .state{font-size:26px;font-weight:700}
.working{background:var(--infobg);color:var(--info);border-color:var(--info)}
.waiting_owner,.stalled{background:var(--badbg);color:var(--bad);border-color:var(--bad)}
.done{background:var(--okbg);color:var(--ok);border-color:var(--ok)}
.soft{color:var(--soft);font-size:14px}.strip .soft{color:inherit}
progress{width:100%;height:18px;accent-color:#16a34a}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr));gap:12px}.cols>div{min-width:0}
.card{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:0 0 8px;overflow-wrap:anywhere}
.card.halt{border:2px solid var(--bad);background:var(--badbg);color:var(--bad)}
.card b{display:block}
.tag{display:inline-block;padding:1px 9px;border-radius:10px;font-size:14px}
.yes{background:var(--okbg);color:var(--ok)}.no{background:var(--warnbg);color:var(--warn)}
.gates{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(230px,100%),1fr));gap:8px}.gates .tag{white-space:nowrap;align-self:center}
.gates div{display:flex;justify-content:space-between;gap:8px;border:1px solid var(--line);border-radius:8px;padding:6px 10px}
.time li{list-style:none;margin-left:-20px;display:flex;gap:10px;overflow-wrap:anywhere}
.time span{flex:0 0 auto;color:var(--soft);font-variant-numeric:tabular-nums}
.time .merge{font-weight:700}
details{font-size:14px;color:var(--soft)}
"""

# Se ninguém regenera o arquivo, a página recarrega o mesmo retrato: sem este aviso ela pareceria ao vivo.
STALE = """<script>(function(){var e=document.getElementById('idade'),s=Math.round(Date.now()/1000-e.dataset.at);
if(s>90){e.textContent+=' Atenção: este retrato tem '+Math.round(s/60)+' min. Ele é refeito quando um agente começa ou termina; para refazer a cada 5 segundos, rode .harness/board --watch no seu terminal.';e.className='tag no';}})();</script>"""


def render_html(data) -> str:
    e, when = html.escape, data["at"]
    icon = STATES[data["state"]][0]
    out = [f'<div class="strip {data["state"]}" role="status"><h1>{e(data["name"] or "Painel da entrega")}</h1>'
           f'<p class="state"><span aria-hidden="true">{icon}</span> {e(data["headline"])}</p><p>{e(data["detail"])}</p>']
    if data["spec"]:
        age = f'Começou há {_span(when - data["started"])}. ' if data["started"] else ""
        out.append(f'<p class="soft">{age}Especificação em {e(data["spec"])}'
                   + (f', branch {e(data["feature"])}' if data["feature"] else "") + ".</p>")
    out.append("</div>")
    out += [f'<section><p class="tag no">! {e(w)}</p></section>' for w in data["warnings"]]
    if data["spec"]:
        out.append(f'<section><h2>Progresso: {data["done"]} de {data["total"]} tickets concluídos</h2>'
                   f'<progress max="{data["total"]}" value="{data["done"]}">{data["done"]} de {data["total"]}</progress></section>')
        out.append('<section><h2>Tickets</h2><div class="cols">')
        for column, title in (("todo", "A fazer"), ("doing", "Em andamento"), ("done", "Concluído")):
            cards = [t for t in data["tickets"] if t["column"] == column]
            out.append(f"<div><h3>{title} ({len(cards)})</h3>")
            for card in cards:
                body = f'<b>{card["number"]:02d} · {e(card["title"])}</b><span class="soft">Cuida de: {e(card["owns"])}</span>'
                if column == "doing":
                    halted = '<p><strong><span aria-hidden="true">⏸</span> Parado</strong></p>' if card["stalled"] else ""
                    body += (f'{halted}<p>Com: {e(_card_line(card))}</p><p>{e(card["label"])}</p>'
                             + (f'<details><summary>Próxima ação</summary>{e(card["next"])}</details>' if card["next"] else ""))
                out.append(f'<div class="card{" halt" if card.get("stalled") else ""}">{body}</div>')
            out.append("" if cards else '<p class="soft">Nenhum.</p>')
            out.append("</div>")
        out.append("</div></section>")
    out.append("<section><h2>Agentes ativos agora</h2>")
    if data["agents"]:
        out.append("<ul>" + "".join(
            f'<li>{e(a["role"])}' + (f', no ticket {e(a["ticket"])}' if a["ticket"] else "") + f', há {_span(a["minutes"] * 60)}</li>'
            for a in data["agents"]) + "</ul>")
    else:
        out.append('<p class="soft">Nenhum agente rodando.</p>')
    out.append('<p class="soft">O painel sabe quem começou e ainda não terminou, não o que cada um está fazendo neste instante.</p></section>')
    if data["gates"]:
        out.append(f'<section><h2>Portões do commit atual <span class="soft">({e((data["head"] or "")[:7])})</span></h2><div class="gates">'
                   + "".join(f'<div><span>{e(g["label"])}</span> <span class="tag {"yes" if g["approved"] else "no"}">'
                             f'{"✓ aprovado" if g["approved"] else "– faltando"}</span></div>' for g in data["gates"])
                   + '</div><p class="soft">Cada commit novo começa sem aprovação: os portões são conferidos no fechamento.</p></section>')
    pend = data["pendings"]
    out.append(f'<section><h2>Pendências abertas: {pend["count"]}</h2>'
               + ("<ul>" + "".join(f"<li>{e(t)}</li>" for t in pend["texts"]) + "</ul>" if pend["texts"] else
                  '<p class="soft">Nenhuma.</p>')
               + (f'<p class="soft">E mais {pend["count"] - len(pend["texts"])}; a lista inteira sai de .harness/pendings.</p>'
                  if pend["count"] > len(pend["texts"]) else "") + "</section>")
    out.append('<section><h2>Linha do tempo</h2>')
    out.append('<ul class="time">' + "".join(f'<li class="{e(ev["kind"])}"><span>{e(ev["clock"])}</span>{e(ev["text"])}</li>'
                                              for ev in data["timeline"]) + "</ul>"
               if data["timeline"] else '<p class="soft">Nada registrado ainda.</p>')
    out.append("</section>")
    result = data["result"]
    links = []
    if result.get("app"):
        links.append(f'<li>Aplicativo: <a href="{e(result["app"])}">{e(result["app"])}</a> '
                     + ('<span class="tag yes">✓ respondendo</span>' if result["app_up"] else
                        '<span class="tag no">! não está respondendo agora (o ambiente pode estar desligado)</span>') + "</li>")
    for key, label in (("screens", "Galeria de telas"), ("design", "Design escolhido")):
        if result.get(key):
            links.append(f'<li>{label}: <a href="../{e(result[key])}">{e(result[key])}</a></li>')
    if result.get("pr"):
        links.append(f'<li>Pull request: <a href="{e(result["pr"])}">{e(result["pr"])}</a></li>')
    out.append("<section><h2>Ver o resultado</h2>" + ("<ul>" + "".join(links) + "</ul>" if links else
               '<p class="soft">Ainda não há endereço do aplicativo: o ambiente não foi preparado neste worktree.</p>') + "</section>")
    out.append(f'<p class="soft"><span id="idade" data-at="{when}">Retrato das {time.strftime("%H:%M:%S", time.localtime(when))}.</span> '
               "A página recarrega sozinha a cada 5 segundos.</p>" + STALE)
    return ('<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="5">'
            f'<title>{icon} {e(data["headline"])} · {e(data["name"] or "painel")}</title><style>{CSS}</style></head><body><main>'
            + "\n".join(out) + "</main></body></html>\n")


def write(root, data=None) -> str:
    """Grava `.harness-run/painel.html` (troca atômica: o navegador nunca lê a página pela metade)."""
    run = os.path.join(root, ".harness-run")
    os.makedirs(run, exist_ok=True)
    ignore = os.path.join(run, ".gitignore")
    if not os.path.exists(ignore):
        with open(ignore, "w", encoding="utf-8") as f:
            f.write("*\n")
    path = os.path.join(run, "painel.html")
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(render_html(data or collect(root)))
    os.replace(tmp, path)
    return path


def main(argv) -> int:
    usage = "uso: board [--json | --text | --watch [segundos]]\n"
    if not argv:
        sys.stderr.write(usage)
        return 2
    here, args = os.path.realpath(argv[0]), argv[1:]
    found = common.repo_root(here)
    root = common.feature_root(found) if found else here  # de um worktree de agente, o painel é o da feature
    try:
        if args and args[0] == "--watch" and len(args) <= 2 and (len(args) == 1 or args[1].isdigit() and int(args[1]) > 0):
            last = None
            try:
                while True:
                    data = collect(root)
                    path, line = write(root, data), summary(data)
                    if last is None:
                        print(f"Painel em {path} (abra no navegador). Ctrl+C para parar.", file=sys.stderr)
                    if line != last:
                        print(f"{time.strftime('%H:%M:%S')} {line}", flush=True)
                    last = line
                    time.sleep(int(args[1]) if len(args) == 2 else 5)
            except KeyboardInterrupt:
                return 0
        if len(args) > 1 or args and args[0] not in ("--json", "--text"):
            sys.stderr.write(usage)
            return 2
        data = collect(root)
        path = write(root, data)
    except OSError as exc:
        sys.stderr.write(f"board: não consegui gravar o painel: {exc}\n")
        return 1
    if args == ["--json"]:
        sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    elif args == ["--text"]:
        sys.stdout.write(render_text(data))
    else:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
