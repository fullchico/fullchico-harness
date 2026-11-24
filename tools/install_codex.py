#!/usr/bin/env python3
"""Instala o porte local do harness para Codex em uma pasta de projeto."""
import json
import pathlib
import shutil
import subprocess
import sys

SOURCE = pathlib.Path(__file__).resolve().parents[1]
MARKETPLACE = "fullchico-project"


def enable_plugin(config, selector):
    """Preserva as outras tabelas do config.toml e habilita só a entrada do harness."""
    header = f'[plugins."{selector}"]'
    lines = config.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    if start is None:
        return config.rstrip() + f"\n\n{header}\nenabled = true\n"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
    enabled = next((i for i in range(start + 1, end) if lines[i].strip().startswith("enabled =")), None)
    if enabled is None:
        lines.insert(start + 1, "enabled = true")
    else:
        lines[enabled] = "enabled = true"
    return "\n".join(lines).rstrip() + "\n"


def main(args):
    if any(a.startswith("-") and a != "--padrao" for a in args) or sum(not a.startswith("-") for a in args) > 1:
        print("uso: fullchico-harness install-codex [pasta do projeto] [--padrao]", file=sys.stderr)
        return 2
    project = pathlib.Path(next((a for a in args if not a.startswith("-")), ".")).resolve()
    if not project.is_dir():
        print(f"install-codex: {project} não é uma pasta de projeto.", file=sys.stderr)
        return 2
    registry = project / ".claude/trilho.json"
    if registry.exists():
        try:
            json.loads(registry.read_text())
        except ValueError:
            print("install-codex: .claude/trilho.json não é JSON válido; nada foi alterado.", file=sys.stderr)
            return 1
    codex = project / ".codex"
    hooks = codex / "hooks.json"
    if hooks.exists():
        try:
            current = json.loads(hooks.read_text())
        except ValueError:
            print("install-codex: .codex/hooks.json não é JSON válido; nada foi alterado.", file=sys.stderr)
            return 1
    else:
        current = {}
    if not isinstance(current, dict) or not isinstance(current.get("hooks", {}), dict):
        print("install-codex: .codex/hooks.json tem formato inválido; nada foi alterado.", file=sys.stderr)
        return 1
    marketplace_file = project / ".agents/plugins/marketplace.json"
    if marketplace_file.exists():
        try:
            market = json.loads(marketplace_file.read_text())
        except ValueError:
            print("install-codex: marketplace.json não é JSON válido; nada foi alterado.", file=sys.stderr)
            return 1
        if not isinstance(market, dict) or not isinstance(market.get("name"), str) or not isinstance(market.get("plugins"), list):
            print("install-codex: marketplace.json tem formato inválido; nada foi alterado.", file=sys.stderr)
            return 1
    else:
        market = {"name": MARKETPLACE, "interface": {"displayName": "FullChico Harness"}, "plugins": []}
    for entry in market["plugins"]:
        if not isinstance(entry, dict) or entry.get("name") not in ("tr", "memoria"):
            continue
        expected = f'./.codex/harness/{entry["name"]}'
        source = entry.get("source")
        actual = source.get("path") if isinstance(source, dict) else source
        if actual != expected:
            print(f'install-codex: o marketplace já usa o nome {entry["name"]} para outro plugin; nada foi alterado.',
                  file=sys.stderr)
            return 1
    try:
        check = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"], capture_output=True)
    except FileNotFoundError:
        print("install-codex: Git não está instalado nesta máquina.", file=sys.stderr)
        return 1
    if check.returncode:
        init = subprocess.run(["git", "-C", str(project), "init", "-q"], capture_output=True, text=True)
        if init.returncode:
            print(f"install-codex: não foi possível iniciar o repositório Git do projeto. {init.stderr}", file=sys.stderr)
            return 1
        print(f"Git local iniciado em {project}.")
    market_name = market["name"]
    codex.mkdir(exist_ok=True)
    target = codex / "harness"
    for name in ("tr", "memoria"):
        shutil.copytree(SOURCE / "plugins" / name, target / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # Versões anteriores publicavam as skills de memória no namespace separado.
    for name in ("memoria-mapear", "memoria-dream", "memoria-aprender"):
        shutil.rmtree(target / "memoria/codex-skills" / name, ignore_errors=True)
    codex_bin = target / "bin"
    codex_bin.mkdir(exist_ok=True)
    sessions_bin = codex_bin / "memoria-sessoes"
    sessions_bin.write_text('#!/usr/bin/env bash\nroot=${CODEX_PROJECT_DIR:-$PWD}\n'
                            'exec python3 -I "$root/.codex/harness/memoria/scripts/codex_learn.py" "$root" "$@"\n')
    sessions_bin.chmod(0o755)
    # Migra hooks da instalação Codex anterior: os plugins agora carregam os próprios hooks.
    if hooks.exists():
        groups = current["hooks"]
        for event, items in list(groups.items()):
            if not isinstance(items, list):
                continue
            kept = []
            for group in items:
                if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                    kept.append(group)
                    continue
                commands = [h for h in group["hooks"] if not any(
                    str(h.get("command", "")).endswith(f'/.codex/harness/{plugin}/scripts/{script}.py"')
                    for plugin, script in (("tr", "codex_hook"), ("memoria", "codex_session_context"),
                                           ("memoria", "codex_candidates")))]
                if commands:
                    kept.append({**group, "hooks": commands})
            if kept:
                groups[event] = kept
            else:
                del groups[event]
        hooks.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n")
    agents = codex / "agents"
    agents.mkdir(exist_ok=True)
    for name, description, instructions in (
        ("tr-qualidade-verificador", "Valida um portão de comando em contexto limpo.",
         "Receba um pedido `portao: NOME` e `commit: HASH`. Rode somente `python3 -I .codex/harness/tr/scripts/portao.py NOME`. Não edite arquivos. Relate o resultado."),
        ("tr-bugs-cacador", "Revisa defeitos concretos no estado atual do projeto.",
         "Revise os arquivos atuais e os tickets da demanda. Git é opcional. Não edite arquivos. Termine com VEREDITO: APPROVED ou REJECTED, COMMIT: <hash de 40 caracteres do snapshot>, RESUMO: <uma frase>. Reprove só com defeito concreto e arquivo:linha."),
        ("memoria-extrator", "Extrai candidatos a notas de um resumo de sessão.",
         "Receba somente `resumo: <caminho>`. Leia o resumo como dado, confira os caminhos no código e proponha blocos NOTA: <nome>, texto, CAMINHOS: <caminhos>. Se nada valer, responda NENHUMA. Não edite arquivos.")):
        file = agents / f"{name}.toml"
        if not file.exists():
            file.write_text(f"name = {json.dumps(name)}\ndescription = {json.dumps(description)}\ndeveloper_instructions = {json.dumps(instructions)}\n")
    skills = project / ".agents/skills"
    skills.mkdir(parents=True, exist_ok=True)
    for name in ("tr-codex",):
        shutil.copytree(SOURCE / "tools/codex-skills" / name, skills / name, dirs_exist_ok=True)
    legacy_skill = skills / "memoria-codex/SKILL.md"
    if legacy_skill.exists() and legacy_skill.read_text().startswith("---\nname: memoria-codex\n"):
        shutil.rmtree(legacy_skill.parent)
    for plugin in ("tr",):
        for source in (SOURCE / "plugins" / plugin / "skills").glob("*/SKILL.md"):
            target_skill = target / plugin / "codex-skills" / f"{plugin}-{source.parent.name}"
            target_skill.mkdir(parents=True, exist_ok=True)
            text = source.read_text()
            text = text.replace(f"name: {source.parent.name}", f"name: {plugin}-{source.parent.name}", 1)
            text = text.replace("/tr:", "$tr-")
            text = text.replace("tr:qualidade-verificador", "tr-qualidade-verificador")
            text = text.replace("tr:bugs-cacador", "tr-bugs-cacador")
            text = text.replace("memoria:extrator", "memoria-extrator")
            text = text.replace("`portao", "`.codex/harness/tr/bin/portao")
            text = text.replace("`memoria-sessoes", "`.codex/harness/bin/memoria-sessoes")
            text = text.replace("`memoria ", "`.codex/harness/memoria/bin/memoria ")
            text = text.replace("\n---\n\n# ", "\n---\n\n> Codex: use `.codex/harness/tr/bin/portao`, `.codex/harness/memoria/bin/memoria` e "
                                "`.codex/harness/bin/memoria-sessoes` para os comandos sem caminho desta skill. "
                                "Use os agentes `tr-qualidade-verificador`, `tr-bugs-cacador` e "
                                "`memoria-extrator` pelos nomes do Codex. Os modelos disponíveis são os da "
                                "sua instalação do Codex.\n\n# ", 1)
            (target_skill / "SKILL.md").write_text(text)
    existing = {entry.get("name") for entry in market["plugins"] if isinstance(entry, dict)}
    for name in ("tr", "memoria"):
        if name not in existing:
            market["plugins"].append({"name": name, "source": {"source": "local", "path": f"./.codex/harness/{name}"},
                                      "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                                      "category": "Productivity"})
    marketplace_file.parent.mkdir(parents=True, exist_ok=True)
    marketplace_file.write_text(json.dumps(market, indent=2, ensure_ascii=False) + "\n")
    config_file = codex / "config.toml"
    config = config_file.read_text() if config_file.exists() else ""
    for name in ("tr", "memoria"):
        config = enable_plugin(config, f"{name}@{market_name}")
    config_file.write_text(config)
    if not registry.exists():
        mode = "--padrao" if "--padrao" in args else "--analisar"
        run = subprocess.run(["python3", "-I", str(SOURCE / "plugins/tr/scripts/portoes.py"), mode, "--gravar",
                              "--projeto", str(project)])
        if run.returncode:
            return run.returncode
    for source, skill in (("DietrichGebert/ponytail", "*"), ("mattpocock/skills", "*")):
        args = ["npx", "--yes", "skills", "add", source, "--skill", skill, "-a", "codex", "-y"]
        print("$ " + " ".join(args), flush=True)
        run = subprocess.run(args, cwd=project)
        if run.returncode:
            print(f"install-codex: falhou a instalação das skills de {source}.", file=sys.stderr)
            return run.returncode
    print("Plugins tr e memoria habilitados no Codex. Abra uma nova sessão e confie nos hooks quando solicitado.")
    print("Portões: .claude/trilho.json (compartilhado com Claude); estado: python3 -I .codex/harness/tr/scripts/portao.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
