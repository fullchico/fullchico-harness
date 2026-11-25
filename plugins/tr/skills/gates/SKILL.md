---
name: gates
description: How to work in a project with gates (.claude/harness.json). Use when starting a change, when validating the delivery, or to find out what is missing.
---

# Working with gates

A gate is a mandatory step of the project's flow. The **start** ones come before writing code;
the **end** ones are checked when the model finishes the implementation. The stamp (the proof) is
written by a hook, outside the project files: you carry out the step, you sign nothing, and you do
not change the registry (`.claude/harness.json`), which belongs to the owner.

## Step by step

1. **See what is missing.** Run `gate` alone. It lists each gate with `ok` or `falta` (missing) and
   says what to do for each one.
2. **Start with the start gates.** Before writing in app code, carry out the step (for example, the
   change's spec, the output of the interview). Writing without it is blocked, and the message says
   which step is missing. Docs, `.claude/` and `.md` files are never blocked.
3. **Start gate:** `gate <name>`, alone in a call (no `&&`, no pipe; the hook blocks the combined
   form). It ends with `gate <name>: passou` or `FALHOU (<reason>)`; if it passed, the hook signs.
   For an artifact gate, the file must exist. If the artifact changed: the stamp is new.
4. **End gates:** whoever wrote the code does not stamp. When the implementation is ready,
   run the reviewer of each gate required by the registry and the passport: `/tr:quality-check`
   for command or artifact; the registered agent or `models validate-gate <name>` for agent
   review. The hook or the review executor checks the current state before stamping; changed
   code requires a new validation. The `Gates:` line of the spec chooses the optional ones.
5. **Deliver** after `tr-harness deliver` passes (`[fora]` (out) is a gate this demand does not require).

Each end gate accepts `attempts` (3 by default) and `approval` (`auto` by default or
`human`). After exceeding the demand's rejection limit, or if `approval: human` was
configured, the owner approves the already validated state: run `tr-harness gates --approve <name>`
alone in a terminal call, and the owner approves it in Claude Code's permission dialog. A change in the
state invalidates that stamp.

A new demand starts with `/tr:process-plan`.

Blocked and not understanding why? Run `gate` and follow the "fazer" (to do) of the missing gate.
