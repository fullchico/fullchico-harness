---
name: skills-discover
description: Researches skills useful for the project's stack and demand, compares the candidates, installs the chosen one for Claude and Codex and proposes verifiable gates when it makes sense.
---

# Discover skills for the project

Use this flow when configuring the harness or when a demand needs a capability that the
installed skills do not cover. `/tr:grill-me` remains responsible for the entry and exit decisions;
if you came from `/tr:configure`, bring the options to the same interview, without opening another.

1. **Inventory, by scope.** Read the stack, the current spec/ticket, `skills-lock.json` and
   `npx skills list --json`. Split what the session can use into two lists:
   - **in the project** (every clone gets it): `.claude/skills/`, `.agents/skills/`, `skills-lock.json` and
     the plugins enabled in the project's `.claude/settings.json`;
   - **only on this machine**: `~/.claude/skills/` and the plugins enabled in `~/.claude/settings.json`
     (for example `vercel@claude-plugins-official`, which brings `vercel:nextjs`). A skill in your list of
     available skills that is in neither project location is a machine-only one.
   A machine-only skill does not cover the stack for the project: another clone, another person or Codex
   will not have it. For each one that matters to the stack, propose **pinning it to the project**:
   a Claude plugin with `claude plugin install <plugin>@<marketplace> --scope project` (alone in a terminal
   call; the owner approves it in the permission dialog), and, when Codex is present, the equivalent
   skill with `npx --yes skills add <source> --skill <name> -a codex -y` if one exists.
   Then look for a concrete gap. Do not install another skill just because it showed up in the search.
2. Run `npx skills find "<specific task>"`; try a second phrasing if the first
   is vague. For each plausible candidate, read its `SKILL.md` and the scripts/hooks it ships,
   check its origin and compare it with the already installed skills. Choose the one that best covers the real
   task and works in the project's environments; say why it won. If none fits,
   record the gap without inventing a dependency.
3. When the choice is part of the demand, install **the specific skill**, in the project, for
   the present environments: `npx --yes skills add <source> --skill <name> -a claude-code -a codex -y`
   for both. Use only the installed environment if the project has just one. Prefer a source pinned to a
   tag or commit for reproducibility. Check `npx skills list --json` and the installed content.
4. Present each selected candidate as a simple proposal: **skill and origin**, task
   covered, **entry gate or final reviewer**, approval evidence, tickets it
   applies to and the reviewer's model. Take this proposal to `/tr:grill-me`: the owner decides whether the skill
   only helps the executor, becomes a requirement before starting, or reviews the delivery.
   An installed skill does not automatically become a gate. For a verifier with a
   real command, propose `signs: command` and test the command. For AI review, create a
   reviewer agent **unique to the gate** in `.claude/agents/<agent>.md` and
   `.codex/agents/<agent>.toml`, both instructed to use the installed skill, examine the current
   state without editing and emit `VERDICT`, `COMMIT` and `SUMMARY`. The reviewer is another session, separate
   from the executor. Propose `signs: agent`, `agent: <agent>`, `stage: start|end` and, if the
   demand calls for it, `always: false` for gates applicable only to some tickets. A design
   skill can check the brief at entry; an accessibility one can review only interface tickets
   at the end. Configure the
   model with `models configure gate:<name> claude:<model>` or `codex:<model>`.
5. Show the owner the JSON sketch and the `gates --register` commands. The protected registry is
   written by the CLI in their terminal; preserve existing gates. Then check `gate` and
   run a real example review before considering the gate ready.

The handoff to the reviewer includes the ticket, spec and completion summary as context. The reviewer rereads the
code and the evidence on its own; the harness stamps only the snapshot it reviewed.
