#!/usr/bin/env python3
"""Configuração de modelos por papel no projeto."""
import json
import os
import shutil
import sys
import tempfile

ESPELHOS = {"claude": {"opus": ("codex", "sol"), "sonnet": ("codex", "luna"),
                       "haiku": ("codex", "terra"), "fable": ("codex", "astra")},
            "codex": {"sol": ("claude", "opus"), "luna": ("claude", "sonnet"),
                      "terra": ("claude", "haiku"), "astra": ("claude", "fable")}}
PAPEIS = ("planejamento", "execucao", "revisao", "apoio")
PATH = os.path.join(".claude", "trilho.json")


def ler(root):
    try:
        with open(os.path.join(root, PATH), encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(".claude/trilho.json deve conter um objeto JSON")
        return data
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise ValueError(f".claude/trilho.json não pôde ser lido: {error}") from error


def validar_papel(value):
    try:
        cli, modelo = value.split(":", 1)
    except (AttributeError, ValueError):
        raise ValueError("use cli:modelo, por exemplo claude:sonnet")
    if cli not in ("claude", "codex") or not modelo.strip():
        raise ValueError("CLI deve ser claude ou codex e o modelo não pode ser vazio")
    return {"cli": cli, "modelo": modelo.strip()}


def configurar(root, args):
    if args and len(args) % 2:
        raise ValueError("informe pares papel cli:modelo")
    chosen = {}
    for i in range(0, len(args), 2):
        role, value = args[i], args[i + 1]
        if role not in PAPEIS:
            raise ValueError(f"papel inválido: {role}; use {', '.join(PAPEIS)}")
        chosen[role] = validar_papel(value)
    if not args:
        if not sys.stdin.isatty():
            raise ValueError("modo não interativo exige pares papel cli:modelo")
        print("Configure cada papel como cli:modelo (Enter mantém o atual).")
        current = (ler(root).get("modelos") or {})
        for role in PAPEIS:
            old = current.get(role, {})
            default = f"{old.get('cli', '')}:{old.get('modelo', '')}" if old else ""
            value = input(f"{role} [{default}]: ").strip()
            if value:
                chosen[role] = validar_papel(value)
    data = ler(root)
    config = data.get("modelos") if isinstance(data.get("modelos"), dict) else {}
    for role, entry in chosen.items():
        config[role] = entry
    data["modelos"] = config
    folder = os.path.join(root, ".claude")
    os.makedirs(folder, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder, delete=False) as f:
        try:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            temp = f.name
        except BaseException:
            os.unlink(f.name)
            raise
    os.replace(temp, os.path.join(root, PATH))
    print(f"configuração gravada em {os.path.join(root, PATH)}")


def mostrar(root):
    config = ler(root).get("modelos") or {}
    if not isinstance(config, dict):
        raise ValueError("`modelos` deve ser um objeto em .claude/trilho.json")
    for role in PAPEIS:
        value = config.get(role)
        if role == "apoio" and not value:
            print("apoio: não configurado (usa o espelho inicial do papel que atingiu limite)")
            continue
        if not value:
            print(f"{role}: não configurado")
            continue
        cli, model = value.get("cli"), value.get("modelo")
        mirror = ESPELHOS.get(cli, {}).get(model.lower())
        mirror_text = f"; espelho {mirror[0]}:{mirror[1]}" if mirror else "; sem espelho inicial conhecido"
        available = "disponível" if shutil.which(cli) else "CLI indisponível no PATH"
        print(f"{role}: {cli}:{model}{mirror_text}; {available}")


def main(argv):
    if not argv or argv[0] not in ("configurar", "mostrar"):
        print("uso: fullchico-harness modelos configurar [papel cli:modelo ...] | mostrar", file=sys.stderr)
        return 2
    root, args = os.path.abspath("."), argv[1:]
    for i, arg in enumerate(args):
        if arg == "--projeto" and i + 1 < len(args):
            root = os.path.abspath(args[i + 1])
            del args[i:i + 2]
            break
    if not os.path.isdir(root):
        print(f"projeto não encontrado: {root}", file=sys.stderr)
        return 2
    try:
        configurar(root, args) if argv[0] == "configurar" else mostrar(root)
        return 0
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
