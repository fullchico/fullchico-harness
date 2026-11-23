#!/usr/bin/env python3
"""`fullchico-harness custo [pasta do projeto] [--desde <commit|AAAA-MM-DD[THH:MM]>] [--json]`.

Quanto custou a entrega da branch atual: tokens e dólares por modelo, sessão principal contra
subagentes, tempo de parede, tempo ativo e as paradas, e o que os portões fizeram (bloqueios,
carimbos). Serve para comparar versões da lib e entregas entre si.

Só lê: as transcrições do Claude Code (`~/.claude/projects`) e o livro de carimbos. Não grava nada.
Não é portão: medir não barra nada.

Janela: começa em `--desde` (commit, data ou data e hora) ou, sem ele, no primeiro commit da branch
depois da base. Entram as sessões do projeto (e dos worktrees de agente dele) que têm atividade dentro
da janela, contadas desde o começo delas, mas nunca antes da base da branch: o trabalho de antes do
primeiro commit (ler, especificar) também é da entrega. Limite: uma sessão que trabalhou e terminou
antes do primeiro commit da branch fica de fora; para ela, passe `--desde` com a hora de início.

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
PRECOS = [
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
PARADA = 5 * 60  # intervalo sem nenhum evento, em segundos, que conta como parada e não como trabalho


def preco(model):
    for prefix, p in PRECOS:
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


def janela_inicio(root, desde):
    """Início da janela e a base da branch (o início nunca vem antes da base)."""
    mb = registry.merge_base(root)
    base_t = commit_time(root, mb) if mb else None
    if desde:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?", desde):
            t = datetime.datetime.fromisoformat(desde)
            return (t if t.tzinfo else t.astimezone()), base_t
        t = commit_time(root, desde)
        if not t:
            raise SystemExit(f"custo: `{desde}` não é data (AAAA-MM-DD[THH:MM]) nem commit deste repositório.")
        return t, base_t
    primeiros = (registry._git(root, "rev-list", "--reverse", f"{mb}..HEAD") or "").split() if mb else []
    if primeiros:
        return commit_time(root, primeiros[0]), base_t
    return None, base_t


def pastas(root):
    """Pastas de transcrição do projeto e dos worktrees de agente dele (`.claude/worktrees/*`)."""
    home = os.path.expanduser("~/.claude/projects")
    slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(root))
    found = [os.path.join(home, slug)]
    found += glob.glob(os.path.join(home, slug + "--claude-worktrees-*"))
    return [f for f in found if os.path.isdir(f)]


def eventos(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def medir(root, desde=None, agora=None):
    agora = agora or datetime.datetime.now(datetime.timezone.utc)
    inicio, base_t = janela_inicio(root, desde)
    if not inicio:
        return {"erro": "a branch não tem commit depois da base; use --desde <commit|AAAA-MM-DD>"}
    # Sem --desde, a sessão que tocou a janela conta desde o começo dela, limitado pela base da branch.
    piso = inicio if desde else (base_t or inicio)
    modelos, papeis, vistos, momentos = {}, {"principal": 0.0, "subagentes": 0.0}, set(), []
    sessoes = 0
    for pasta in pastas(root):
        for arquivo in glob.glob(os.path.join(pasta, "**", "*.jsonl"), recursive=True):
            linhas = [(parse_ts(e.get("timestamp")), e) for e in eventos(arquivo)]
            linhas = [(t, e) for t, e in linhas if t]
            if not any(inicio <= t <= agora for t, _ in linhas):
                continue  # a sessão não tocou a janela
            sessoes += "/subagents/" not in arquivo
            papel = "subagentes" if "/subagents/" in arquivo else "principal"
            for t, e in linhas:
                if not piso <= t <= agora:
                    continue
                momentos.append(t)
                msg = e.get("message") if isinstance(e.get("message"), dict) else {}
                uso, mid, model = msg.get("usage"), msg.get("id"), msg.get("model") or ""
                if e.get("type") != "assistant" or not uso or not mid or mid in vistos or model.startswith("<"):
                    continue
                vistos.add(mid)
                m = modelos.setdefault(model, {"entrada": 0, "cache_escrita": 0, "cache_leitura": 0, "saida": 0,
                                               "usd": 0.0, "mensagens": 0})
                tok = (uso.get("input_tokens", 0), uso.get("cache_creation_input_tokens", 0),
                       uso.get("cache_read_input_tokens", 0), uso.get("output_tokens", 0))
                for chave, n in zip(("entrada", "cache_escrita", "cache_leitura", "saida"), tok):
                    m[chave] += n or 0
                m["mensagens"] += 1
                p = preco(model)
                usd = sum((n or 0) * v for n, v in zip(tok, p)) / 1e6 if p else 0.0
                m["usd"] += usd
                papeis[papel] += usd
    momentos.sort()
    paradas, ativo = [], 0
    for a, b in zip(momentos, momentos[1:]):
        gap = (b - a).total_seconds()
        if gap > PARADA:
            paradas.append({"inicio": a.isoformat(timespec="seconds"), "minutos": round(gap / 60)})
        else:
            ativo += gap
    paradas.sort(key=lambda p: -p["minutos"])
    livro = portoes_no_livro(root, momentos[0] if momentos else inicio, agora)
    mb = registry.merge_base(root)
    return {
        "branch": registry.branch(root),
        "commits": len((registry._git(root, "rev-list", f"{mb}..HEAD") or "").split()) if mb else 0,
        "inicio": (momentos[0] if momentos else inicio).isoformat(timespec="seconds"),
        "fim": (momentos[-1] if momentos else agora).isoformat(timespec="seconds"),
        "parede_min": round(((momentos[-1] - momentos[0]).total_seconds() if momentos else 0) / 60),
        "ativo_min": round(ativo / 60),
        "paradas": paradas,
        "sessoes": sessoes,
        "modelos": modelos,
        "usd": round(sum(m["usd"] for m in modelos.values()), 2),
        "usd_por_papel": {k: round(v, 2) for k, v in papeis.items()},
        "sem_preco": sorted(m for m in modelos if not preco(m)),
        "portoes": livro,
    }


def portoes_no_livro(root, inicio, fim):
    """O que o livro de carimbos registrou na janela: bloqueios, carimbos, recusas."""
    d = ledger.state_dir(root)
    contagem = {}
    if not d:
        return contagem
    try:
        with open(os.path.join(d, "log.jsonl"), encoding="utf-8") as f:
            linhas = [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        return contagem
    for linha in linhas:
        t = parse_ts(linha.get("at"))
        if t and inicio <= t <= fim:
            contagem[linha.get("what", "?")] = contagem.get(linha.get("what", "?"), 0) + 1
    return contagem


def mil(n):
    return f"{n:,}".replace(",", ".")


def texto(r):
    if "erro" in r:
        return f"custo: {r['erro']}"
    loc = lambda iso: datetime.datetime.fromisoformat(iso).astimezone().strftime("%d/%m %H:%M")  # noqa: E731
    out = [f"Custo da entrega — branch {r['branch']} ({r['commits']} commits, {r['sessoes']} sessões)",
           f"Janela: {loc(r['inicio'])} → {loc(r['fim'])}  |  parede {r['parede_min']} min, "
           f"ativo {r['ativo_min']} min, parado {r['parede_min'] - r['ativo_min']} min", ""]
    out.append(f"{'modelo':<22}{'entrada':>12}{'cache esc.':>13}{'cache leit.':>14}{'saída':>11}{'US$':>9}")
    for nome, m in sorted(r["modelos"].items(), key=lambda kv: -kv[1]["usd"]):
        out.append(f"{nome[:21]:<22}{mil(m['entrada']):>12}{mil(m['cache_escrita']):>13}"
                   f"{mil(m['cache_leitura']):>14}{mil(m['saida']):>11}{m['usd']:>9.2f}")
    out.append(f"{'total':<72}{r['usd']:>9.2f}")
    out.append(f"Sessão principal US$ {r['usd_por_papel']['principal']:.2f}  |  "
               f"subagentes US$ {r['usd_por_papel']['subagentes']:.2f}")
    if r["sem_preco"]:
        out.append(f"Sem preço na tabela (fora do total): {', '.join(r['sem_preco'])}")
    if r["paradas"]:
        out.append("\nParadas (mais de 5 min sem nenhum evento):")
        out += [f"  {loc(p['inicio'])}  {p['minutos']} min" for p in r["paradas"][:8]]
    if r["portoes"]:
        out.append("\nPortões no livro: " + ", ".join(f"{k} {v}" for k, v in sorted(r["portoes"].items())))
    out.append("\nUS$ é estimativa pelo preço de API (tabela em custo.py); serve para comparar entregas.")
    return "\n".join(out)


def main(argv):
    pasta, desde, como_json, i = ".", None, False, 0
    while i < len(argv):
        if argv[i] == "--desde" and i + 1 < len(argv):
            desde, i = argv[i + 1], i + 1
        elif argv[i] == "--json":
            como_json = True
        elif argv[i].startswith("-"):
            print("uso: fullchico-harness custo [pasta do projeto] [--desde <commit|AAAA-MM-DD[THH:MM]>] [--json]", file=sys.stderr)
            return 2
        else:
            pasta = argv[i]
        i += 1
    root = registry.toplevel(os.path.abspath(pasta))
    if not ledger.head(root):
        print(f"custo: {root} não é um repositório git com commits.", file=sys.stderr)
        return 2
    r = medir(root, desde)
    print(json.dumps(r, ensure_ascii=False, indent=2) if como_json else texto(r))
    return 1 if "erro" in r else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
