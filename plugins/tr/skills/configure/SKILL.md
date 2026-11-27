---
name: configure
description: Diagnoses Claude Code and Codex, analyzes the project and interviews the owner with Matt Pocock's grilling skill to propose rails and entry and exit gates (.claude/harness.json).
---

# Configure the project's gates

You will diagnose the environments, analyze the project, interview the owner with `mattpocock-skills:grilling`
and propose the `.claude/harness.json` registry. The agent **does not edit** that file (the tr hook
blocks it): the harness CLI writes it, and only with the **owner's approval**. You ask the questions,
decide the gates, build the sketch and run the CLI; the owner approves each write inside the session.
The owner does not have to type commands.

**How the owner approves, without leaving the session.** Run the owner command yourself. In the normal
permission mode the tr hook turns it into Claude Code's permission dialog. In auto or bypass mode there is no
dialog: the hook denies the call and gives you an exact question. Put that question to the owner with
`AskUserQuestion`, alone in the message, with the options `Aprovo` and `Não aprovo`, and never fill `answers`
yourself (the hook refuses it). When the owner answers `Aprovo`, run the same command again: the hook lets it
through once. Codex has no such question: there the owner runs the printed line in the terminal.

Inside the session, always call the CLI as `tr-harness` (it ships with the installed plugin, at the same
version). Never use `npx @fullchico/harness` without a version: it fetches another release, with another
registry format. When a write cannot be approved in the session (the hook says so, for example in
`bypassPermissions` mode), get the exact terminal line with `tr-harness owner <args>`: it prints the
`npx @fullchico/harness@<version>` pinned in this project.

## 1. Diagnose the environments

Detect the environments installed for this project. If Claude Code is installed, run
`claude doctor` at the project root. If Codex is installed, run `codex doctor --json`.
These are health diagnostics of the CLIs, not validators of the code. Summarize errors, warnings and hints;
do not paste credentials, personal paths or the raw JSON into the gate sketch. If the doctor
is unavailable or fails, record the limitation and continue the project analysis.
Do not apply repairs suggested by the doctors without a decision from the owner.

## 2. Analyze the project

Run `tr-harness gates --analyze` (or the script installed in the project) and read the
existing registry. Also check `package.json`, `pyproject.toml`, `Cargo.toml`, CI scripts,
tests, lint/typecheck configuration, spec documentation and deploy
tools. For each suggestion, note the concrete evidence and check that the command really
exists. Preserve the gates already defined by the owner.

**A flow that does what the tr does is a competing flow, not a gate.** When the project already has its own
process for specs, plans, tickets or review (a spec framework, its slash commands, a commit gate, a planning
folder with its own state), registering it as the `process` gate keeps two flows that disagree. Show the
owner what it does and where it is wired (commands, hooks, scripts, CI), and recommend replacing it with the
tr flow: its open specs become a demand through `/tr:process-plan`, and its wiring is removed as the first
demand. Its useful rules stay as project rules (`AGENTS.md`, a lint, a check). The owner decides.

As soon as the stack and the architecture are decided in the interview, run `/tr:skills-discover`
by default: inventory what the project and this machine already have, propose pinning to the project the
machine-only skills that matter to the stack, and search best-practice skills for each main technology
(framework, ORM, queue, UI, accessibility). Ask the owner before installing. Bring each chosen candidate to the interview, with its origin, what it
runs and whether it produces evidence for an entry gate or final review. Show which
tickets the gate applies to and who reviews it. Installing a skill does not register
a gate.

## 3. Interview with Matt Pocock's flow

Invoke `mattpocock-skills:grilling` with the Skill tool. Invoke it; do not reproduce its format from memory.
Show first what the doctors and the project revealed. Follow its flow: rounds over the frontier of decisions,
each question with your recommended answer, until the frontier is empty and the owner confirms the design. The interview defines:

- which **entry** gates prevent starting code: spec, spec validation, architecture
  review, the domain glossary (`domain` gate, checks `GLOSSARY.md`), approval or another
  verifiable artifact/command/agent;
- how many **executors run at once** (`max_parallel`, 3 by default; each executor runs its own servers, database and browser, so more than 3 can exhaust a 16 GB machine): fewer on a modest machine, more when
  the executors are external Codex runs. To change it, run `tr-harness gates --parallel <n>` (owner approval).
- the machine stays awake while subagents work (`keep_awake`, on by default; the screen may still turn off). Mention it;
  only an owner who wants it off sets `"keep_awake": false`.
- the **environment profile**: `fluxo` (default, no native sandbox, so the project's Docker works;
  hooks steer the flow but stamps are not tamper-proof) or `isolado` (native sandbox with the
  registry write-protected and only `docker` and `fullchico-harness` outside it). For `isolado`,
  hand the owner the line printed by `tr-harness owner install --sandbox`. Do not switch profiles during an
  approved demand.
- which **exit** gates validate the delivery: tests, lint, typecheck, build, e2e, review,
  security, accessibility, deploy or other checks actually used in the project;
- which are always mandatory and which depend on the type of delivery.
- for each final gate, the `attempts` limit of automatic rejections (3 by default;
  configurable) and `approval: auto` (default) or `human`. On the fourth rejection with the default,
  the orchestrator asks for intervention; the reviewer remains independent of the executor.
- which CLI and model do planning, execution and review, and whether any end gate needs a
  reviewer different from the default. Show the models already configured with
  `tr-harness models show`; include the choice in the interview. In Claude Code,
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

Do not limit the configuration to the names `process`, `domain`, `quality`, `bugs` and `scope`: they are only
default proposals. You can create any number of entry and exit gates. A
doctor warning is an environment improvement; it only becomes a gate if there is a verifiable
project check and the owner chooses it.

**New project (no code yet): register the real commands now, not `@define`.** The stack is decided in this
interview, so decide the script names too (`pnpm typecheck`, `pnpm test:e2e`...) and register them as the
gates' commands. They fail until the scaffold ticket creates them, which is expected; `/tr:process-plan` makes
the scaffold ticket create exactly those scripts. `@define` stops the delivery mid-way waiting for the owner to
run `gates --set`, so keep it only for a check nobody can name yet, and say how to define it later.
The `lint` gate uses the recommended rule set of **every framework in the stack**, not only the language's
(TypeScript plus React and React hooks for a React app, the framework's own config such as Next's, and
`jsx-a11y` when accessibility is a decision of the interview). A lint that only knows the language passes
code the framework would reject.

## How to write it, with the owner's approval

0. **Reviewer agents first.** Create every reviewer agent a gate will use (`.claude/agents/<agent>.md` and,
   with Codex, `.codex/agents/<agent>.toml`) **before** registering that gate: once the gate is registered, its
   agent files are protected and only the owner can change them. Reusing an agent the project already has
   counts as creating it: adapt it first so it reviews the whole delivery against the base branch and ends with
   `VERDICT: APPROVED|REJECTED`, `COMMIT: <sha>` and `SUMMARY: …`; an agent that reviews only the staged diff
   or answers in another format fails the gate even on correct code. A reviewer that writes captures or reports
   inside the project needs that folder in `.gitignore`: otherwise its own
   output changes the project's content and drops every stamp already given.
0. **Code paths.** Add a top-level `"code": [...]` to the sketch with the folders that will hold the app's
   code (for a planned monorepo, `apps` and `packages`), even before they exist. Without it, everything
   outside `docs/`, `.claude/`, `.codex/`, `.agents/` and Markdown counts as code, which is too broad.
0. **Where Matt's skills write.** `to-spec` and `to-tickets` publish to the project's "issue tracker". Point
   it at the tr layout, the extension point Matt's `setup-matt-pocock-skills` documents: write
   `docs/agents/issue-tracker.md` saying the spec is `docs/specs/<slug>/spec.md`, each ticket is
   `docs/specs/<slug>/issues/NN-<slug>.md` with the tr passport as plain lines (`Status: open`,
   `Blocked by:`, `Start:`, `Gates:`, `Files:`, `Complexity:`), and the `## Certificates` appendix is written
   only by the tr hooks. Add the `## Agent skills` block that points to it in `CLAUDE.md` (or `AGENTS.md` when
   that is the one the project has). A tracker the project already uses (GitHub, Linear) stays for its own
   issues; the demand's criterion and certificates live in `docs/specs/`, versioned with the code.
1. **New gate** (a name not yet in the registry): build a JSON sketch. Entry example:
   `{"planning": {"stage": "start", "signs": "artifact", "artifact": "docs/specs/*/spec.md"}}`.
   Exit example: `{"e2e": {"stage": "end", "signs": "command", "command": "pnpm test:e2e", "always": false}}`.
   Use a field that matches the signing mode and write the sketch
   **outside the repository** (the session's temporary folder). A new file inside the repository dirties the
   tree, and an end stamp does not sign with a dirty tree.
2. **Existing gate command**: `gates --set <name> "<command>"`.
   **Models**: also hand over the chosen pairs, for example `models configure review claude:sonnet`.
   In a Claude-only project, do not configure `execution`: executors are native subagents whose model
   comes from the ticket's `Complexity:` (haiku or sonnet). Never propose opus for an executor; opus is the
   planning session's model.
3. Run each write yourself, alone in its terminal call (no `&&`, pipe or `cd` in front), one per call:

   ```bash
   tr-harness gates --register /path/to/draft.json
   tr-harness gates --remove <gate>
   tr-harness models configure planning claude:opus review claude:sonnet
   ```

   Before each one, tell the owner in one line what it writes. The tr hook turns each call into a Claude
   Code permission dialog with the exact command: the owner's approval is what lets it write. If the
   owner declines, ask what to change; do not retry the same command or look for another way. If the
   hook denies it instead (no dialog in this mode), ask the owner the exact question it gives, as above.
4. **Close the round against the owner's answers.** Before moving on, list each decision the owner gave
   in this interview (including answers that contradicted your recommendation, such as "make it a gate
   anyway") and check that the registry, the models, the installed skills and the agents reflect it. Anything
   still missing is done now, with approval, before `/tr:process-plan`.
5. After it is written, check `.claude/harness.json` and `.claude/settings.json`, if it changed.
   Only consider the configuration closed when the chosen registry is applied and
   readable. The final confirmation of the interview already authorized the plan; do not ask for another
   approval to start execution after the entry gates pass. The final stamp
   validates the current state of the project.

Never try `Write` or `Edit` on `.claude/harness.json`: the hook blocks it.

A command gate runs exactly the registry's command, via `gate <name>`, with no variable in
front. If the check needs environment (port, URL, browser), it reads it from a file the project already
loads (for example `.env`), not from the command line.

**Every command gate runs once before the configuration closes.** Run `tr-harness gates --check`: it runs each
command gate and says `passes`, `runs and fails` or `DOES NOT RUN`. A gate that does not run (missing script,
missing env file, a service that is down) is not configured yet: fix it now, or tell the owner exactly what it
needs and get an explicit "leave it pending" before closing. `runs and fails` on an existing project is a
finding: show it to the owner, because the first delivery that needs that gate will stop there.

**Preparing an executor's seat.** Each executor works in a fresh worktree, without installed dependencies, and a
Codex executor has no network to install them. When the project needs a step before tests can run (install,
code generation), register it with `tr-harness gates --prepare-seat "<command>"` (owner approval); the tr runs
it when it creates the seat.

When done, run `gate` and show the result to the owner. If any gate fails on the first
check, explain what is missing without rewriting the registry.

When the project has the `memory` plugin (the `memory` command exists), finish by running `/tr:memory-map`
on your own: the project leaves the configuration with its code map, and every session starts from it.

## Checklist

- [ ] I summarized the doctor for each available environment and analyzed the project before asking.
- [ ] With the stack decided, I ran `/tr:skills-discover`: inventory by scope, pinning of machine-only skills, best practices per technology, owner asked before installing.
- [ ] I invoked `mattpocock-skills:grilling` (Skill tool) to decide the entry and exit gates with the owner.
- [ ] Each proposed gate has evidence, timing, signing mode and a concrete verifier.
- [ ] Sketch outside the repository; `--register`/`--set`/`models configure` run by me and approved by the owner in the session (dialog or question), never `Write`/`Edit`.
- [ ] I remembered to review the registry before stamping.
- [ ] I ran `tr-harness gates --check`; no command gate is left as `DOES NOT RUN` without the owner saying so.
- [ ] I registered `--prepare-seat` when tests need installed dependencies.
- [ ] I ran `gate` at the end and showed the state.
- [ ] With the `memory` plugin, I ran `/tr:memory-map` so the project starts with its map.
