#!/usr/bin/env python3
"""`fullchico-harness portoes [--analisar] [--gravar] [--padrao] [--projeto <pasta>]`.

Lê o projeto e PROPÕE o registro de portões, com o porquê de cada um; com `--gravar`, grava em
`.claude/trilho.json` (preservando as outras chaves) e protege o arquivo no sandbox.
"""
import glob
import json
import os
import sys

PADRAO = {
    "portoes": {
        "processo": {"momento": "inicio", "assina": "artefato", "artefato": "docs/specs/*/spec.md",
                     "descricao": "spec da mudança, saída da entrevista"},
        "qualidade": {"momento": "fim", "assina": "comando", "comando": "npm test"},
        "bugs": {"momento": "fim", "assina": "agente", "agente": "bugs:cacador"},
    }
}


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def plugin_on(settings, prefix):
    enabled = settings.get("enabledPlugins") or {}
    return any(k.startswith(prefix) and v for k, v in enabled.items())


def analisar(project):
    """Devolve (registro, [(portão, porquê)])."""
    p = lambda *a: os.path.join(project, *a)  # noqa: E731
    settings = read_json(p(".claude", "settings.json"))
    portoes, why = {}, []

    grill = bool(glob.glob(p(".claude", "skills", "*grill*"))) or plugin_on(settings, "mattpocock-skills")
    entrevista = " (entrevista com grill-me)" if grill else ""
    if os.path.isdir(p("openspec")):
        portoes["processo"] = {"momento": "inicio", "assina": "comando", "comando": "openspec validate --all",
                               "descricao": "spec da mudança validada pelo OpenSpec" + entrevista}
        why.append(("processo", "a pasta `openspec/` existe: a etapa é a spec valer, conferida por `openspec validate --all`"))
    elif os.path.isdir(p("docs", "specs")):
        portoes["processo"] = {"momento": "inicio", "assina": "artefato", "artefato": "docs/specs/*/spec.md",
                               "descricao": "spec da mudança, saída da entrevista" + (" (grill-me)" if grill else "")}
        why.append(("processo", "a pasta `docs/specs/` existe: a etapa é haver uma spec nova ou alterada na branch"))
    if grill and "processo" in portoes:
        why.append(("processo", "há skill de entrevista (grill-me) no projeto: a descrição a cita"))

    scripts = read_json(p("package.json")).get("scripts") or {}
    found = [s for s in ("lint", "typecheck", "test") if s in scripts]
    if found:
        pm = "pnpm" if os.path.isfile(p("pnpm-lock.yaml")) else "yarn" if os.path.isfile(p("yarn.lock")) else "npm"
        run = {"pnpm": "pnpm {}", "yarn": "yarn {}", "npm": "npm run {}"}[pm]
        cmds = [("npm test" if pm == "npm" and s == "test" else run.format(s)) for s in found]
        portoes["qualidade"] = {"momento": "fim", "assina": "comando", "comando": " && ".join(cmds)}
        why.append(("qualidade", f"`package.json` tem os scripts {', '.join(found)}; gerenciador {pm} pelo lockfile"))

    if plugin_on(settings, "bugs@"):
        portoes["bugs"] = {"momento": "fim", "assina": "agente", "agente": "bugs:cacador"}
        why.append(("bugs", "o plugin `bugs` está ligado em .claude/settings.json: o caçador assina"))

    reg = {}
    codigo = [d for d in ("apps", "packages", "src") if os.path.isdir(p(d))]
    if codigo:
        reg["codigo"] = codigo
        why.append(("codigo", f"as pastas {', '.join(codigo)} existem: só elas contam como código do app"))
    reg["portoes"] = portoes
    return reg, why


def gravar(project, reg):
    path = os.path.join(project, ".claude", "trilho.json")
    data = read_json(path)
    data.update(reg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"gravado: {path}")
    sp = os.path.join(project, ".claude", "settings.json")
    settings = read_json(sp)
    if isinstance(settings.get("sandbox"), dict):
        fs = settings["sandbox"].setdefault("filesystem", {})
        deny = fs.setdefault("denyWrite", [])
        if ".claude/trilho.json" not in deny:
            deny.append(".claude/trilho.json")
            with open(sp, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
                f.write("\n")
            print(f"acrescentado ao sandbox.filesystem.denyWrite: .claude/trilho.json ({sp})")


def main(argv):
    project, flags, i = ".", set(), 0
    while i < len(argv):
        if argv[i] == "--projeto":
            i += 1
            project = argv[i] if i < len(argv) else "."
        elif argv[i] in ("--analisar", "--gravar", "--padrao"):
            flags.add(argv[i])
        else:
            print("uso: fullchico-harness portoes [--analisar] [--gravar] [--padrao] [--projeto <pasta>]", file=sys.stderr)
            return 2
        i += 1
    project = os.path.abspath(project)
    if "--padrao" in flags:
        reg, why = PADRAO, [("padrão", "o registro padrão da lib")]
    else:
        reg, why = analisar(project)
    print(json.dumps(reg, ensure_ascii=False, indent=2))
    print()
    for name, reason in why:
        print(f"- {name}: {reason}")
    if not reg["portoes"]:
        print("\nNada reconhecido para propor; escreva `.claude/trilho.json` à mão ou use --padrao.")
    elif "--gravar" in flags:
        print()
        gravar(project, reg)
    else:
        print("\nProposta apenas; para gravar, rode de novo com --gravar.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
