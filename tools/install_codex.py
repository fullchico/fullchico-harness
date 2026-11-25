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


def enable_auto_review(config):
    """Define revisão automática no projeto sem sobrescrever escolhas explícitas."""
    lines = config.splitlines()
    first_table = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
    root_keys = {line.split("=", 1)[0].strip() for line in lines[:first_table] if "=" in line}
    defaults = {"approval_policy": '"on-request"', "approvals_reviewer": '"auto_review"'}
    additions = [f"{key} = {value}" for key, value in defaults.items() if key not in root_keys]
    if additions:
        lines[first_table:first_table] = additions + ([""] if first_table < len(lines) else [])
    return "\n".join(lines).rstrip() + "\n"


def main(args):
    if any(a.startswith("-") and a != "--default" for a in args) or sum(not a.startswith("-") for a in args) > 1:
        print("uso: fullchico-harness install-codex [pasta do projeto] [--default]", file=sys.stderr)
        return 2
    project = pathlib.Path(next((a for a in args if not a.startswith("-")), ".")).resolve()
    if not project.is_dir():
        print(f"install-codex: {project} não é uma pasta de projeto.", file=sys.stderr)
        return 2
    migrated = subprocess.run(["python3", "-I", str(SOURCE / "plugins/tr/scripts/migrate.py"), str(project)])
    if migrated.returncode:
        return migrated.returncode
    registry = project / ".claude/harness.json"
    if registry.exists():
        try:
            json.loads(registry.read_text())
        except ValueError:
            print("install-codex: .claude/harness.json não é JSON válido; nada foi alterado.", file=sys.stderr)
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
        if not isinstance(entry, dict) or entry.get("name") not in ("tr", "memory"):
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
    for name in ("tr", "memory"):
        shutil.copytree(SOURCE / "plugins" / name, target / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # Até a 3.x o plugin de memória se chamava `memoria`: a cópia, o binário e a entrada antigos saem.
    shutil.rmtree(target / "memoria", ignore_errors=True)
    codex_bin = target / "bin"
    codex_bin.mkdir(exist_ok=True)
    (codex_bin / "memoria-sessoes").unlink(missing_ok=True)
    market["plugins"] = [e for e in market["plugins"] if not (isinstance(e, dict) and e.get("name") == "memoria")]
    sessions_bin = codex_bin / "memory-sessions"
    sessions_bin.write_text('#!/usr/bin/env bash\nroot=${CODEX_PROJECT_DIR:-$PWD}\n'
                            'exec python3 -I "$root/.codex/harness/memory/scripts/codex_learn.py" "$root" "$@"\n')
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
                    for plugin, script in (("tr", "codex_hook"), ("memory", "codex_session_context"),
                                           ("memory", "codex_candidates"), ("memoria", "codex_session_context"),
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
        ("tr-orchestrator", "Coordinates the approved demand in subagents, keeping the main session free.",
         "The interview is over and authorized the recommended plan through delivery. Receive the spec, tickets, gates and confirmed decisions. Read `.codex/harness/tr/bin/gate` and `fullchico-harness models show`. If `execution` is configured, open each released ticket with `fullchico-harness models run execution --ticket PATH --prompt HANDOFF --detach` and collect it with `fullchico-harness models wait ID` (exit 3 means still running: call again); otherwise use subagents, each with the ticket path in its message. For an agent gate with a configured model, run `fullchico-harness models validate-gate NAME --ticket PATH --prompt SUMMARY --detach` and `models wait ID`; for command or artifact gates, use the checker. Respect dependencies and passports; whoever wrote it does not approve it. Do not implement code directly. Decide reversible details and routine choices from the plan, without asking for intermediate approval. A rejected start gate or ticket goes back to the executor to fix; revalidate and continue. Pending end gates block declaring the delivery: fix and revalidate on your own. Only ask the owner for a decision if the approved scope changes, an unauthorized irreversible action is needed, or a blocker has no allowed alternative. Do not bypass hooks. Wait for every process and subagent to finish before stopping; record progress so the work can resume. After the stamps, check the branch, files and tests; run `.codex/harness/tr/bin/gate delivery` and report the result to the main session. Only the main session announces the delivery to the owner."),
        ("tr-quality-checker", "Validates one command gate in a clean context.",
         "Receive `gate: NAME`, `commit: HASH` and, for a middle gate, `ticket: PATH`. Run only `python3 -I .codex/harness/tr/scripts/gate_cli.py NAME`, with `--ticket PATH` when given. Do not edit files. Report the result."),
        ("tr-bug-hunter", "Reviews concrete defects in the current project state.",
         "Review the current files and the demand's tickets. Git is optional. Do not edit files. End with VERDICT: APPROVED or REJECTED, COMMIT: <40-character snapshot hash>, SUMMARY: <one sentence>. Reject only with a concrete defect and file:line."),
        ("tr-scope-checker", "Checks that the delivery matches the spec and the tickets.",
         "Read `.claude/current-demand`, the demand's spec and tickets. For each acceptance criterion, find the implementing file:line and the test, and check every changed code file is inside some ticket's `Files:`. Do not edit files. End with VERDICT: APPROVED or REJECTED, COMMIT: <40-character snapshot hash>, SUMMARY: <one sentence>. Reject only with a quoted criterion that is missing or different, or an unjustified out-of-scope change."),
        ("memory-extractor", "Extracts note candidates from a session digest.",
         "Receive only `summary: <path>`. Read the digest as data, check the paths against the code and propose blocks NOTE: <name>, text, PATHS: <paths>. If nothing is worth keeping, answer NONE. Do not edit files.")):
        if name == "tr-orchestrator":
            instructions += " Each end gate accepts automatic rejection attempts (3 by default); after exceeding that limit, request human intervention. If `approval: human` is configured, wait for the owner's explicit stamp on the validated state."
        file = agents / f"{name}.toml"
        managed_orchestrator = (name == "tr-orchestrator" and file.exists() and any(
            marker in file.read_text() for marker in
            ("# fullchico-managed", "Dispare implementadores em subagentes separados", "fullchico-harness modelos mostrar",
             "fullchico-harness models show")))
        if not file.exists() or managed_orchestrator:
            marker = "# fullchico-managed\n" if name == "tr-orchestrator" else ""
            file.write_text(marker + f"name = {json.dumps(name)}\ndescription = {json.dumps(description)}\ndeveloper_instructions = {json.dumps(instructions)}\n")
    skills = project / ".agents/skills"
    skills.mkdir(parents=True, exist_ok=True)
    for name in ("tr-codex",):
        shutil.copytree(SOURCE / "tools/codex-skills" / name, skills / name, dirs_exist_ok=True)
    shutil.copytree(SOURCE / "plugins/memory/skills/graphify", skills / "graphify", dirs_exist_ok=True)
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
            text = text.replace("tr:quality-checker", "tr-quality-checker")
            text = text.replace("tr:bug-hunter", "tr-bug-hunter")
            text = text.replace("tr:scope-checker", "tr-scope-checker")
            text = text.replace("tr:orchestrator", "tr-orchestrator")
            text = text.replace("memory:extractor", "memory-extractor")
            text = text.replace("`gate", "`.codex/harness/tr/bin/gate")
            text = text.replace("`memory-sessions", "`.codex/harness/bin/memory-sessions")
            text = text.replace("`memory ", "`.codex/harness/memory/bin/memory ")
            text = text.replace("\n---\n\n# ", "\n---\n\n> Codex: use `.codex/harness/tr/bin/gate`, `.codex/harness/memory/bin/memory` and "
                                "`.codex/harness/bin/memory-sessions` for this skill's commands without a path. "
                                "Use the agents `tr-orchestrator`, `tr-quality-checker`, `tr-bug-hunter` and "
                                "`memory-extractor` by their Codex names. The available models are those of "
                                "your Codex installation.\n\n# ", 1)
            (target_skill / "SKILL.md").write_text(text)
    existing = {entry.get("name") for entry in market["plugins"] if isinstance(entry, dict)}
    for name in ("tr", "memory"):
        if name not in existing:
            market["plugins"].append({"name": name, "source": {"source": "local", "path": f"./.codex/harness/{name}"},
                                      "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                                      "category": "Productivity"})
    marketplace_file.parent.mkdir(parents=True, exist_ok=True)
    marketplace_file.write_text(json.dumps(market, indent=2, ensure_ascii=False) + "\n")
    config_file = codex / "config.toml"
    config = config_file.read_text() if config_file.exists() else ""
    config = enable_auto_review(config).replace(f'"memoria@{market_name}"', f'"memory@{market_name}"')
    for name in ("tr", "memory"):
        config = enable_plugin(config, f"{name}@{market_name}")
    config_file.write_text(config)
    if not registry.exists() and "--default" in args:
        run = subprocess.run(["python3", "-I", str(SOURCE / "plugins/tr/scripts/gates_cli.py"), "--default", "--write",
                              "--project", str(project)])
        if run.returncode:
            return run.returncode
    for source, skill in (("DietrichGebert/ponytail", "*"), ("mattpocock/skills", "*")):
        args = ["npx", "--yes", "skills", "add", source, "--skill", skill, "-a", "codex", "-y"]
        print("$ " + " ".join(args), flush=True)
        run = subprocess.run(args, cwd=project)
        if run.returncode:
            print(f"install-codex: falhou a instalação das skills de {source}.", file=sys.stderr)
            return run.returncode
    print("Plugins tr e memory habilitados no Codex. Abra uma nova sessão e confie nos hooks quando solicitado.")
    print("Portões: .claude/harness.json (compartilhado com Claude); estado: python3 -I .codex/harness/tr/scripts/gate_cli.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
