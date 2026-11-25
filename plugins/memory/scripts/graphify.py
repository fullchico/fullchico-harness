"""Índice local em grafo para a memória compartilhada do harness.

O índice é derivado de map.json, notes.json e anchors.json e mora junto da
memória no git-common-dir. Não é fonte canônica: pode ser apagado e refeito.
"""
import os
import re
import shutil
import subprocess

TOKEN = re.compile(r"[\w./@-]+", re.UNICODE)
STOP = {"para", "com", "uma", "que", "dos", "das", "por", "the", "and", "from"}
RESULT_LIMIT = 8
TEXT_LIMIT = 500


def _tokens(text):
    return {word.casefold().strip("./-") for word in TOKEN.findall(text or "")
            if len(word.strip("./-")) > 1 and word.casefold() not in STOP}


def _git_paths(root):
    from common import _git
    return [p for p in (_git(root, "ls-files", "-z") or "").split("\0") if p]


def build(root):
    """Monta grafo efêmero: arquivo → unidade/nota/decisão → termos e commit."""
    import memory
    from common import head_sha

    paths = _git_paths(root)
    path_set = set(paths)
    nodes, edges = {}, set()

    def node(key, kind, label, text="", refs=None, commit="", source=None):
        nodes[key] = {"kind": kind, "label": label, "text": (text or "")[:TEXT_LIMIT],
                      "refs": list(dict.fromkeys(refs or [])), "commit": commit or "", "source": source}

    def link(a, b, rel):
        edges.add((a, b, rel))

    for path in paths:
        key = "file:" + path
        node(key, "file", path, refs=[path])

    mapping = memory._load(root, "map.json").get("units", {})
    if isinstance(mapping, dict):
        for unit, entry in mapping.items():
            if not isinstance(entry, dict):
                continue
            text = memory.summary(root, unit) or ""
            key = "unit:" + unit
            refs = [p for p in paths if ("/" not in p if unit == "." else
                                         p == unit or p.startswith(unit.rstrip("/") + "/"))]
            node(key, "unit", unit, text, refs, entry.get("commit"))
            for path in refs:
                link(key, "file:" + path, "contains")
            for term in _tokens(unit + " " + text):
                term_key = "term:" + term
                if term_key not in nodes:
                    node(term_key, "term", term)
                link(key, term_key, "mentions")

    for slug, entry in memory._notes(root).items():
        text = memory.note_show(root, slug) or ""
        refs = [p for p in entry.get("paths", []) if p in path_set]
        key = "note:" + slug
        node(key, "note", slug, text, refs, entry.get("commit"), entry.get("source"))
        for path in refs:
            link(key, "file:" + path, "references")
        for term in _tokens(slug + " " + text):
            term_key = "term:" + term
            if term_key not in nodes:
                node(term_key, "term", term)
            link(key, term_key, "mentions")

    anchors = memory._load(root, "anchors.json")
    for kind in ("glossary", "adr"):
        entries = anchors.get(kind, {})
        if not isinstance(entries, dict):
            continue
        for label, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            key = f"{kind}:{label}"
            refs = [p for p in entry.get("paths", []) if p in path_set]
            node(key, kind, label, refs=refs, commit=entry.get("commit"))
            for path in refs:
                link(key, "file:" + path, "references")

    return {"version": 1, "built_from": head_sha(root), "nodes": nodes,
            "edges": [list(edge) for edge in sorted(edges)]}


def refresh(root):
    import memory
    graph = build(root)
    if graph != memory._load(root, "graphify.json"):
        memory._save(root, "graphify.json", graph)
    return graph


def update_engine(root):
    """Atualiza Graphify local quando instalado; a memória continua funcionando sem ele."""
    executable = shutil.which("graphify")
    if not executable:
        return {"available": False, "updated": False}
    import common
    output = os.path.join(common.memory_dir(root), "graphify-out")
    os.makedirs(output, exist_ok=True)
    env = dict(os.environ, GRAPHIFY_OUT=output, GRAPHIFY_BACKEND="none")
    try:
        result = subprocess.run([executable, "update", root], cwd=root, env=env,
                                capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": True, "updated": False, "error": str(exc)}
    return {"available": True, "updated": result.returncode == 0,
            "error": result.stderr.strip()[-500:] if result.returncode else ""}


def query_engine(root, query):
    """Consulta o grafo de código Graphify; retorna vazio quando ainda não foi gerado."""
    executable = shutil.which("graphify")
    if not executable:
        return ""
    import common
    output = os.path.join(common.memory_dir(root), "graphify-out")
    graph = os.path.join(output, "graph.json")
    if not os.path.isfile(graph):
        return ""
    env = dict(os.environ, GRAPHIFY_OUT=output, GRAPHIFY_BACKEND="none")
    try:
        result = subprocess.run([executable, "query", query, "--graph", graph, "--depth", "2",
                                 "--budget", "800"], cwd=root, env=env, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()[:3000] if result.returncode == 0 else ""


def search(root, query, limit=RESULT_LIMIT):
    """Busca lexical por texto/caminho e retorna nós com referências diretas."""
    graph = refresh(root)
    terms = _tokens(query)
    if not terms:
        return []
    nodes = graph["nodes"]
    adjacency = {}
    for left, right, relation in graph["edges"]:
        adjacency.setdefault(left, []).append((right, relation))
        adjacency.setdefault(right, []).append((left, relation))
    scored = []
    for key, item in nodes.items():
        if item["kind"] == "file":
            continue
        corpus = _tokens(" ".join([key, item["label"], item["text"], *item["refs"]]))
        score = len(terms & corpus)
        if score:
            score += min(2, sum(1 for neighbor, _ in adjacency.get(key, [])
                                if nodes.get(neighbor, {}).get("kind") == "file")) * 0.15
            scored.append((score, key, item))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [{"id": key, **item} for _, key, item in scored[:max(1, min(int(limit), RESULT_LIMIT))]]
