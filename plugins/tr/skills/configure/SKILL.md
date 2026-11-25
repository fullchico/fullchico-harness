---
name: configure
description: Diagnoses Claude Code and Codex, analyzes the project and interviews the owner with grill-me to propose rails and entry and exit gates (.claude/harness.json).
---

# Configure the project's gates

You will diagnose the environments, analyze the project, interview the owner with `/tr:grill-me`
and propose the `.claude/harness.json` registry. The agent **does not write** that
file: the tr hook blocks it, and with a sandbox the file is also write-protected. Whoever writes it is
the `fullchico-harness gates` CLI, run by the owner in their terminal. You ask the question, decide the
gates, build the sketch and hand the owner the ready-made commands.

## 1. Diagnose the environments

Detect the environments installed for this project. If Claude Code is installed, run
`claude doctor` at the project root. If Codex is installed, run `codex doctor --json`.
These are health diagnostics of the CLIs, not validators of the code. Summarize errors, warnings and hints;
do not paste credentials, personal paths or the raw JSON into the gate sketch. If the doctor
is unavailable or fails, record the limitation and continue the project analysis.
Do not apply repairs suggested by the doctors without a decision from the owner.

## 2. Analyze the project

Run `fullchico-harness gates --analyze` (or the script installed in the project) and read the
existing registry. Also check `package.json`, `pyproject.toml`, `Cargo.toml`, CI scripts,
tests, lint/typecheck configuration, spec documentation and deploy
tools. For each suggestion, note the concrete evidence and check that the command really
exists. Preserve the gates already defined by the owner.

Use `/tr:skills-discover` to search for a skill only when the stack or the demand
shows a concrete gap. Bring the chosen candidate to the interview, with its origin, what it
runs and whether it produces evidence for an entry gate or final review. Show which
tickets the gate applies to and who reviews it. Installing a skill does not register
a gate.

## 3. Interview with Matt Pocock's flow

Call `/tr:grill-me`, included in this plugin from Matt Pocock's `grilling` flow.
Show first what the doctors and the project revealed. Explore the decisions in rounds,
with a recommendation per question, until the owner confirms the design. The interview defines:

- which **entry** gates prevent starting code: spec, spec validation, architecture
  review, approval or another verifiable artifact/command/agent;
- the **environment profile**: `fluxo` (default, no native sandbox, so the project's Docker works;
  hooks steer the flow but stamps are not tamper-proof) or `isolado` (native sandbox with the
  registry write-protected and only `docker` and `fullchico-harness` outside it). For `isolado`,
  hand the owner `npx @fullchico/harness install --sandbox`. Do not switch profiles during an
  approved demand.
- which **exit** gates validate the delivery: tests, lint, typecheck, build, e2e, review,
  security, accessibility, deploy or other checks actually used in the project;
- which are always mandatory and which depend on the type of delivery.
- for each final gate, the `attempts` limit of automatic rejections (3 by default;
  configurable) and `approval: auto` (default) or `human`. On the fourth rejection with the default,
  the orchestrator asks for intervention; the reviewer remains independent of the executor.
- which CLI and model do planning, execution and review, and whether any end gate needs a
  reviewer different from the default. Show the models already configured with
  `npx @fullchico/harness models show`; include the choice in the interview. In Claude Code,
  `models.review` sets the default for agent gates; on command or artifact gates,
  a Claude model can tune the native verifier. `gate:<name> cli:model` overrides
  a specific reviewer. Agent gates can use Claude or Codex in a separate CLI session:
  `models validate-gate <name>` checks the verdict and the snapshot before stamping.
  For Codex, confirm that the agent instructions are installed in `.codex/agents/` or
  `.claude/agents/`; without them the command refuses the review.

Task-specific entry gates use `always: false` in the registry and are named on the
`Start:` line of the ticket. Task-specific exit gates use the `Gates:` line. Example:
a frontend task asks for `Start: design` and `Gates: accessibility`; a backend one
uses `Start: none` and `Gates: api`. Gates without `always: false` remain global.

Do not limit the configuration to the names `process`, `quality`, `bugs` and `scope`: they are only
default proposals. You can create any number of entry and exit gates. A
doctor warning is an environment improvement; it only becomes a gate if there is a verifiable
project check and the owner chooses it. With no known command, leave `@define` and
explain how to define it later.

## How to hand over to the owner

1. **New gate** (a name not yet in the registry): build a JSON sketch. Entry example:
   `{"planning": {"stage": "start", "signs": "artifact", "artifact": "docs/specs/*/spec.md"}}`.
   Exit example: `{"e2e": {"stage": "end", "signs": "command", "command": "pnpm test:e2e", "always": false}}`.
   Use a field that matches the signing mode and write the sketch
   **outside the repository** (the session's temporary folder). A new file inside the repository dirties the
   tree, and an end stamp does not sign with a dirty tree.
2. **Existing gate command**: `fullchico-harness gates --set <name> "<command>"`.
   **Models**: also hand over the chosen pairs for the owner to write in the terminal, for example
   `npx @fullchico/harness models configure review claude:sonnet gate:design-review codex:sol`.
3. Write the exact commands for the owner, one per line, to run in the terminal, outside the session:

   ```bash
   npx @fullchico/harness gates --set quality "pnpm lint && pnpm test"
   npx @fullchico/harness gates --register /path/to/draft.json
   ```

   If you want to try it yourself, run the CLI once. If it answers "Sem permissão para gravar" (no permission to write), do not
   insist or look for another way: that is the protection working. Hand over the commands and wait.
4. After the owner has written it, check `.claude/harness.json` and `.claude/settings.json`, if it changed.
   Only consider the configuration closed when the chosen registry is applied and
   readable. The final confirmation of `/tr:grill-me` already authorized the plan; do not ask for another
   approval to start execution after the entry gates pass. The final stamp
   validates the current state of the project.

Never try `Write` or `Edit` on `.claude/harness.json`: the hook blocks it.

A command gate runs exactly the registry's command, via `gate <name>`, with no variable in
front. If the check needs environment (port, URL, browser), it reads it from a file the project already
loads (for example `.env`), not from the command line.

When done, run `gate` and show the result to the owner. If any gate fails on the first
check, explain what is missing without rewriting the registry.

## Checklist

- [ ] I summarized the doctor for each available environment and analyzed the project before asking.
- [ ] I compared installed skills with concrete gaps; I used `/tr:skills-discover` when appropriate.
- [ ] I used `/tr:grill-me` to decide the entry and exit gates with the owner.
- [ ] Each proposed gate has evidence, timing, signing mode and a concrete verifier.
- [ ] Sketch outside the repository; `--set`/`--register` commands handed to the owner, never `Write`/`Edit`.
- [ ] I remembered to review the registry before stamping.
- [ ] I ran `gate` at the end and showed the state.
