"""Contagem de reprovações dos portões finais por demanda, fora do repositório."""
import hashlib
import json
import os
import tempfile

import ledger


def _path(root, name):
    active = os.path.join(root, ".claude", "demanda-atual")
    try:
        with open(active, encoding="utf-8") as stream:
            demand = stream.read().strip()
    except OSError:
        demand = "sem-demanda"
    scope = hashlib.sha256((os.path.realpath(root) + "\0" + demand + "\0" + name).encode()).hexdigest()[:24]
    return os.path.join(ledger.state_dir(root), "attempts", scope + ".json")


def status(root, name):
    try:
        with open(_path(root, name), encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def reject(root, name, gate, evidence=None):
    if gate.get("momento") != "fim":
        return None
    data = status(root, name)
    if evidence and data.get("ultimo") == evidence:
        return data
    data["reprovacoes"] = data.get("reprovacoes", 0) + 1
    data["ultimo"] = evidence
    limit = gate.get("tentativas", 3)
    data["intervencao"] = bool(data.get("intervencao") or data["reprovacoes"] > limit)
    path = _path(root, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(data, stream)
    os.replace(tmp, path)
    return data
