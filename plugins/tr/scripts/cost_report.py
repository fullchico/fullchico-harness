#!/usr/bin/env python3
"""`fullchico-harness cost [folder do projeto] [--since <commit|AAAA-MM-DD[THH:MM]>] [--json]`.

Quanto custou a entrega da branch atual: tokens e dólares por modelo, sessão principal contra
subagentes, tempo de parede, tempo ativo e as paradas, e o que os portões fizeram (bloqueios,
carimbos). Serve para comparar versões do plugin e entregas entre si.

Só lê: as transcrições do Claude Code (`~/.claude/projects`) e o livro de carimbos. Não grava nada.
Não é portão: medir não barra nada.

Janela: começa em `--since` (commit, data ou data e hora) ou, sem ele, no primeiro commit da branch
depois da base. Entram as sessões do projeto (e dos worktrees de agente dele) que têm atividade dentro
da janela, contadas desde o começo delas, mas nunca antes da base da branch: o trabalho de antes do
primeiro commit (ler, especificar) também é da entrega. Limite: uma sessão que trabalhou e terminou
antes do primeiro commit da branch fica de fora; para ela, passe `--since` com a hora de início.

Preço: estimativa pela tabela PRECOS (US$ por milhão de tokens, preço de API). Assinatura do Claude
não cobra por token; o número serve para comparar, não é fatura.
"""
import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
import registry  # noqa: E402

# US$ por milhão de tokens: (entrada, escrita de cache, leitura de cache, saída). Entrada e saída da
# tabela oficial de preços; leitura de cache quando a tabela a dá, senão 0,1 × entrada; escrita de
# cache estimada em 1,25 × entrada (cache de 5 minutos). Casamento por prefixo do id do modelo.
PRICES = [
    ("claude-fable-5-2", (8.00, 10.00, 0.20, 40.00)),
    ("claude-mythos-5-2", (8.00, 10.00, 0.20, 40.00)),
    ("claude-fable-5", (10.00, 12.50, 1.00, 50.00)),
    ("claude-mythos-5", (10.00, 12.50, 1.00, 50.00)),
    ("claude-opus-5-5", (4.00, 5.00, 0.20, 20.00)),
    ("claude-opus-5", (5.00, 6.25, 0.50, 25.00)),
    ("claude-opus-4", (5.00, 6.25, 0.50, 25.00)),
    ("claude-sonnet-5-5", (2.00, 2.50, 0.10, 10.00)),
    ("claude-sonnet-5", (2.00, 2.50, 0.20, 10.00)),
    ("claude-sonnet-4", (3.00, 3.75, 0.30, 15.00)),
    ("claude-haiku-5-5", (0.10, 0.125, 0.01, 0.50)),
    ("claude-haiku-4", (1.00, 1.25, 0.10, 5.00)),
]
PAUSE = 5 * 60  # intervalo sem nenhum evento, em segundos, que conta como parada e não como trabalho


def price(model):
    for prefix, p in PRICES:
        if model.startswith(prefix):
            return p
    return None


def parse_ts(text):
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def commit_time(root, ref):
    out = registry._git(root, "show", "-s", "--format=%cI", ref)
    return parse_ts(out) if out else None


def window_start(root, since):
    """Início da janela e a base da branch (o início nunca vem antes da base)."""
    mb = registry.merge_base(root)
    base_t = commit_time(root, mb) if mb else None
    if since:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?", since):
            t = datetime.datetime.fromisoformat(since)
            return (t if t.tzinfo else t.astimezone()), base_t
        t = commit_time(root, since)
        if not t:
            raise SystemExit(f"custo: `{since}` não é data (AAAA-MM-DD[THH:MM]) nem commit deste repositório.")
        return t, base_t
    first_items = (registry._git(root, "rev-list", "--reverse", f"{mb}..HEAD") or "").split() if mb else []
    if first_items:
        return commit_time(root, first_items[0]), base_t
    return None, base_t


def folders(root):
    """Pastas de transcrição do projeto e dos worktrees de agente dele (`.claude/worktrees/*`)."""
    home = os.path.expanduser("~/.claude/projects")
    slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(root))
    found = [os.path.join(home, slug)]
    found += glob.glob(os.path.join(home, slug + "--claude-worktrees-*"))
    return [f for f in found if os.path.isdir(f)]


def events_list(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def measure(root, since=None, now_ts=None):
    now_ts = now_ts or datetime.datetime.now(datetime.timezone.utc)
    start, base_t = window_start(root, since)
    if not start:
        return {"error": "a branch não tem commit depois da base; use --since <commit|AAAA-MM-DD>"}
    # Sem --since, a sessão que tocou a janela conta desde o começo dela, limitado pela base da branch.
    floor = start if since else (base_t or start)
    models, roles, seen_items, stages = {}, {"main": 0.0, "subagents": 0.0}, set(), []
    sessions_list = 0
    for folder in folders(root):
        for file_name in glob.glob(os.path.join(folder, "**", "*.jsonl"), recursive=True):
            row_lines = [(parse_ts(e.get("timestamp")), e) for e in events_list(file_name)]
            row_lines = [(t, e) for t, e in row_lines if t]
            if not any(start <= t <= now_ts for t, _ in row_lines):
                continue  # a sessão não tocou a janela
            sessions_list += "/subagents/" not in file_name
            role = "subagents" if "/subagents/" in file_name else "main"
            for t, e in row_lines:
                if not floor <= t <= now_ts:
                    continue
                stages.append(t)
                msg = e.get("message") if isinstance(e.get("message"), dict) else {}
                usage_line, mid, model = msg.get("usage"), msg.get("id"), msg.get("model") or ""
                if e.get("type") != "assistant" or not usage_line or not mid or mid in seen_items or model.startswith("<"):
                    continue
                seen_items.add(mid)
                m = models.setdefault(model, {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0,
                                               "usd": 0.0, "messages": 0})
                tok = (usage_line.get("input_tokens", 0), usage_line.get("cache_creation_input_tokens", 0),
                       usage_line.get("cache_read_input_tokens", 0), usage_line.get("output_tokens", 0))
                for key_name, n in zip(("input", "cache_write", "cache_read", "output"), tok):
                    m[key_name] += n or 0
                m["messages"] += 1
                p = price(model)
                usd = sum((n or 0) * v for n, v in zip(tok, p)) / 1e6 if p else 0.0
                m["usd"] += usd
                roles[role] += usd
    stages.sort()
    pauses, active_flag = [], 0
    for a, b in zip(stages, stages[1:]):
        gap = (b - a).total_seconds()
        if gap > PAUSE:
            pauses.append({"start": a.isoformat(timespec="seconds"), "minutes": round(gap / 60)})
        else:
            active_flag += gap
    pauses.sort(key=lambda p: -p["minutes"])
    ledger_book = ledger_gates(root, stages[0] if stages else start, now_ts)
    mb = registry.merge_base(root)
    return {
        "branch": registry.branch(root),
        "commits": len((registry._git(root, "rev-list", f"{mb}..HEAD") or "").split()) if mb else 0,
        "start": (stages[0] if stages else start).isoformat(timespec="seconds"),
        "end": (stages[-1] if stages else now_ts).isoformat(timespec="seconds"),
        "wall_min": round(((stages[-1] - stages[0]).total_seconds() if stages else 0) / 60),
        "active_min": round(active_flag / 60),
        "pauses": pauses,
        "sessions": sessions_list,
        "models": models,
        "usd": round(sum(m["usd"] for m in models.values()), 2),
        "usd_by_role": {k: round(v, 2) for k, v in roles.items()},
        "unpriced": sorted(m for m in models if not price(m)),
        "gates": ledger_book,
    }


def ledger_gates(root, start, end_ts):
    """O que o livro de carimbos registrou na janela: bloqueios, carimbos, recusas."""
    d = ledger.state_dir(root)
    tally = {}
    if not d:
        return tally
    try:
        with open(os.path.join(d, "log.jsonl"), encoding="utf-8") as f:
            row_lines = [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        return tally
    for row_text in row_lines:
        t = parse_ts(row_text.get("at"))
        if t and start <= t <= end_ts:
            tally[row_text.get("what", "?")] = tally.get(row_text.get("what", "?"), 0) + 1
    return tally


def per_thousand(n):
    return f"{n:,}".replace(",", ".")


def text_value(r):
    if "error" in r:
        return f"custo: {r['error']}"
    loc = lambda iso: datetime.datetime.fromisoformat(iso).astimezone().strftime("%d/%m %H:%M")  # noqa: E731
    out = [f"Custo da entrega — branch {r['branch']} ({r['commits']} commits, {r['sessions']} sessões)",
           f"Janela: {loc(r['start'])} → {loc(r['end'])}  |  parede {r['wall_min']} min, "
           f"ativo {r['active_min']} min, parado {r['wall_min'] - r['active_min']} min", ""]
    out.append(f"{'modelo':<22}{'entrada':>12}{'cache esc.':>13}{'cache leit.':>14}{'saída':>11}{'US$':>9}")
    for model_name, m in sorted(r["models"].items(), key=lambda kv: -kv[1]["usd"]):
        out.append(f"{model_name[:21]:<22}{per_thousand(m['input']):>12}{per_thousand(m['cache_write']):>13}"
                   f"{per_thousand(m['cache_read']):>14}{per_thousand(m['output']):>11}{m['usd']:>9.2f}")
    out.append(f"{'total':<72}{r['usd']:>9.2f}")
    out.append(f"Sessão principal US$ {r['usd_by_role']['main']:.2f}  |  "
               f"subagentes US$ {r['usd_by_role']['subagents']:.2f}")
    if r["unpriced"]:
        out.append(f"Sem preço na tabela (fora do total): {', '.join(r['unpriced'])}")
    if r["pauses"]:
        out.append("\nParadas (mais de 5 min sem nenhum evento):")
        out += [f"  {loc(p['start'])}  {p['minutes']} min" for p in r["pauses"][:8]]
    if r["gates"]:
        out.append("\nPortões no livro: " + ", ".join(f"{k} {v}" for k, v in sorted(r["gates"].items())))
    out.append("\nUS$ é estimativa pelo preço de API (tabela em cost_report.py); serve para comparar entregas.")
    return "\n".join(out)


def main(argv):
    folder, since, as_json, i = ".", None, False, 0
    while i < len(argv):
        if argv[i] == "--since" and i + 1 < len(argv):
            since, i = argv[i + 1], i + 1
        elif argv[i] == "--json":
            as_json = True
        elif argv[i].startswith("-"):
            print("uso: fullchico-harness cost [pasta do projeto] [--since <commit|AAAA-MM-DD[THH:MM]>] [--json]", file=sys.stderr)
            return 2
        else:
            folder = argv[i]
        i += 1
    root = registry.toplevel(os.path.abspath(folder))
    if not ledger.head(root):
        print(f"custo: {root} não é um repositório git com commits.", file=sys.stderr)
        return 2
    r = measure(root, since)
    print(json.dumps(r, ensure_ascii=False, indent=2) if as_json else text_value(r))
    return 1 if "error" in r else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
