#!/usr/bin/env python3
"""Migra um projeto do formato em português (até a 3.x) para o formato em inglês.

`.claude/trilho.json` vira `.claude/harness.json` com chaves e valores em inglês; os cabeçalhos dos
tickets e das specs (`Bloqueado por:`, `Portões:`...) mudam de nome; `.claude/demanda-atual` vira
`.claude/current-demand`; o settings do projeto passa a apontar para os nomes novos. Os nomes dos
portões são do dono e não mudam. Rodar de novo não muda nada.

Uso: migrate.py <raiz do projeto>
"""
import glob
import json
import os
import re
import sys

TOP = {"portoes": "gates", "codigo": "code", "modelos": "models", "qualidade": "quality"}
GATE = {"momento": "stage", "assina": "signs", "comando": "command", "artefato": "artifact", "agente": "agent",
        "valida": "check", "descricao": "description", "sempre": "always", "tentativas": "attempts",
        "aprovacao": "approval"}
VALUES = {"stage": {"inicio": "start", "meio": "middle", "fim": "end"},
          "signs": {"comando": "command", "artefato": "artifact", "agente": "agent"},
          "approval": {"humana": "human"},
          "command": {"@definir": "@define", "@descobrir": "@discover"},
          "agent": {"bugs:cacador": "tr:bug-hunter", "tr:bugs-cacador": "tr:bug-hunter",
                    "tr:qualidade-verificador": "tr:quality-checker"}}
ROLES = {"planejamento": "planning", "execucao": "execution", "revisao": "review", "apoio": "support",
         "portoes": "gates"}
LABELS = {"Bloqueado por": "Blocked by", "Entrada": "Start", "Meio": "Middle", "Portões": "Gates",
          "Portoes": "Gates", "Arquivos": "Files", "Entrega": "Delivery", "Complexidade": "Complexity"}
LABEL_LINE = re.compile(r"(?m)^([\s>*_-]*)(" + "|".join(LABELS) + r")([*_]*:)(.*)$")
LABEL_VALUES = {"nenhum": "none", "simples": "simple", "complexa": "complex"}
SETTINGS_TEXT = [(".claude/trilho.json", ".claude/harness.json"), ("memoria@fullchico", "memory@fullchico"),
                 ("memoria-sessoes", "memory-sessions")]
SETTINGS_WORDS = [(re.compile(r"(?<![\w-])portao(?![\w-])"), "gate"), (re.compile(r"(?<![\w-])memoria(?![\w-])"), "memory")]


def gate(old):
    if not isinstance(old, dict):
        return old
    new = {GATE.get(k, k): v for k, v in old.items()}
    for key, table in VALUES.items():
        if isinstance(new.get(key), str):
            new[key] = table.get(new[key], new[key])
    return new


def model_choice(value):
    return {("model" if k == "modelo" else k): v for k, v in value.items()} if isinstance(value, dict) else value


def registry(old):
    new = {TOP.get(k, k): v for k, v in old.items()}
    if isinstance(new.get("gates"), dict):
        new["gates"] = {name: gate(g) for name, g in new["gates"].items()}
    if isinstance(new.get("quality"), dict):
        new["quality"] = gate(new["quality"])
    if isinstance(new.get("models"), dict):
        models = {ROLES.get(k, k): v for k, v in new["models"].items()}
        for role, value in models.items():
            models[role] = ({n: model_choice(c) for n, c in value.items()} if role == "gates" and isinstance(value, dict)
                            else model_choice(value))
        new["models"] = models
    return new


def label_line(m):
    value = m.group(4)
    word = value.strip(" `*_")
    if word.lower() in LABEL_VALUES:
        value = value.replace(word, LABEL_VALUES[word.lower()])
    return f"{m.group(1)}{LABELS[m.group(2)]}{m.group(3)}{value}"


def settings_value(value):
    if isinstance(value, str):
        for old, new in SETTINGS_TEXT:
            value = value.replace(old, new)
        for rx, new in SETTINGS_WORDS:
            value = rx.sub(new, value)
        return value
    if isinstance(value, list):
        return [settings_value(v) for v in value]
    if isinstance(value, dict):
        return {settings_value(k): settings_value(v) for k, v in value.items()}
    return value


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def migrate(root):
    """Devolve a lista do que mudou. ValueError se um arquivo antigo não for JSON válido."""
    done = []
    claude = os.path.join(root, ".claude")
    old, new = os.path.join(claude, "trilho.json"), os.path.join(claude, "harness.json")
    if os.path.isfile(old):
        if os.path.exists(new):
            done.append("aviso: .claude/trilho.json e .claude/harness.json existem; o novo vale, o antigo ficou para você apagar")
        else:
            try:
                with open(old, encoding="utf-8") as f:
                    data = json.load(f)
            except ValueError as e:
                raise ValueError(f".claude/trilho.json não é JSON válido ({e}); nada foi migrado.")
            write_json(new, registry(data) if isinstance(data, dict) else data)
            os.remove(old)
            done.append(".claude/trilho.json → .claude/harness.json (chaves em inglês)")
    demand_old, demand_new = os.path.join(claude, "demanda-atual"), os.path.join(claude, "current-demand")
    if os.path.isfile(demand_old) and not os.path.exists(demand_new):
        os.rename(demand_old, demand_new)
        done.append(".claude/demanda-atual → .claude/current-demand")
    for path in sorted(glob.glob(os.path.join(root, "docs/specs/*/issues/*.md")) +
                       glob.glob(os.path.join(root, "docs/specs/*/spec.md"))):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        changed = LABEL_LINE.sub(label_line, text)
        if changed != text:
            with open(path, "w", encoding="utf-8") as f:
                f.write(changed)
            done.append(f"{os.path.relpath(path, root)}: cabeçalhos em inglês")
    for name in ("settings.json", "settings.local.json"):
        path = os.path.join(claude, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except ValueError:
            continue  # o install já recusa settings inválido antes de chegar aqui
        changed = settings_value(data)
        if changed != data:
            write_json(path, changed)
            done.append(f".claude/{name}: nomes novos (harness.json, memory, gate)")
    return done


def main(argv):
    if len(argv) != 1:
        print("uso: migrate.py <raiz do projeto>", file=sys.stderr)
        return 2
    try:
        done = migrate(os.path.abspath(argv[0]))
    except ValueError as e:
        print(f"migrate: {e}", file=sys.stderr)
        return 1
    for line in done:
        print(f"migrado: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
