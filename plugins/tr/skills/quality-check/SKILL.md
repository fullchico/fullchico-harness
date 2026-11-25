---
name: quality-check
description: Validates command or artifact gates at the start, middle and end, each in an independent subagent. Use after preparing the plan, on each ticket or before delivering.
---

# Verify command and artifact gates

Whoever produced the evidence does not stamp: each command or artifact gate is run by a `tr:quality-checker`,
a clean-context subagent, and the hook signs the stamp from its execution.

1. **Ready state.** The plan or code to validate must be complete. There is no need to open a PR.
2. **What is missing.** Run `gate` alone and pick up the start or end gates marked `[falta]`; for the middle, check the `Middle:` field of each ticket.
3. **One verifier per gate, one at a time.** Dispatch the `tr:quality-checker` agent with the
   first line `gate: <name>`. For a middle gate, include `ticket: <path>` on the second line.
   The hook rewrites the request (name and state reference) and picks the model; anything
   else you write is discarded. Wait for it to finish before the next one: project commands compete for
   port, build and report in the same folder.
4. **Failed:** the implementer fixes and the reviewer revalidates. A code change requires a new stamp.
5. At the end, `gate` shows the state. Agent gates (e.g. `bugs`) have their own invoker
   (`/tr:bugs-hunt`).

Running `gate <name>` in the main session shows the result, but does not stamp.
