#!/usr/bin/env python3
"""Os comandos de memória de sessões sobre transcrições locais do Codex."""
import json
import os
import pathlib
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(__file__))
import learn


def entries(path):
    if path.endswith(".zst"):
        if not shutil.which("zstd"):
            raise ValueError("transcrição .zst exige o programa zstd")
        run = subprocess.run(["zstd", "-dc", path], capture_output=True, text=True)
        if run.returncode:
            raise ValueError(f"não consegui ler {path}: {run.stderr.strip()}")
        lines = run.stdout.splitlines()
    else:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    for line in lines:
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            yield value


def sessions(root, home=None):
    base = pathlib.Path(home or os.path.expanduser("~")) / ".codex/sessions"
    if not base.is_dir():
        return []
    known = {os.path.realpath(p) for p in learn._worktrees(root)}
    state = learn._state(root)
    found = []
    for path in base.rglob("rollout-*.jsonl*"):
        if not (path.name.endswith(".jsonl") or path.name.endswith(".jsonl.zst")):
            continue
        try:
            first = next(entries(str(path)), None)
            meta = first.get("payload", {}) if first and first.get("type") == "session_meta" else {}
            if os.path.realpath(meta.get("cwd", "")) not in known:
                continue
            sid = meta.get("id") or meta.get("session_id")
            if not isinstance(sid, str):
                continue
            size = path.stat().st_size
            grew = sid in state["sizes"] and size > state["sizes"][sid] + learn.GREW
            found.append({"id": sid, "path": str(path), "mtime": path.stat().st_mtime,
                          "processed": sid in state["processed"] and not grew})
        except (OSError, ValueError):
            continue
    return sorted(found, key=lambda s: s["mtime"])


def usage(path):
    total = None
    messages = 0
    model = "codex"
    for item in entries(path):
        payload = item.get("payload") or {}
        if item.get("type") == "turn_context" and isinstance(payload.get("model"), str):
            model = payload["model"]
        if item.get("type") == "response_item" and payload.get("type") == "message" and payload.get("role") == "assistant":
            messages += 1
        if item.get("type") == "event_msg" and payload.get("type") == "token_count":
            value = (payload.get("info") or {}).get("total_token_usage")
            if isinstance(value, dict):
                total = value
    total = total or {}
    bucket = {"input": total.get("input_tokens", 0), "output": total.get("output_tokens", 0),
              "cache_read": total.get("cached_input_tokens", 0),
              "cache_write": total.get("cache_write_input_tokens", 0), "messages": messages}
    return {"papéis": {"principal": {model: bucket}}, "total": bucket}


def digest(path):
    lines = [learn.HEADER, ""]
    for item in entries(path):
        payload = item.get("payload") or {}
        if item.get("type") != "response_item" or payload.get("type") != "message":
            continue
        role = payload.get("role")
        if role not in ("user", "assistant"):
            continue
        for block in payload.get("content") or []:
            text = block.get("text") if isinstance(block, dict) else None
            if isinstance(text, str) and text.strip():
                lines.append(("DONO: " if role == "user" else "AGENTE: ") + learn._cut(text))
    text = "\n".join(lines)
    return text[:learn.DIGEST_LIMIT].rsplit("\n", 1)[0] if len(text) > learn.DIGEST_LIMIT else text


def main(argv):
    learn.sessions = sessions
    learn.usage = usage
    learn.digest = digest
    return learn.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
