---
name: bugs-hunt
description: Hunts for bugs in the finished work, in an independent subagent that stamps the current state. Use before delivery.
---

# Hunt bugs

The `bugs` gate is signed by the verdict of the `tr:bug-hunter` agent. You sign nothing and do not
write its request: the tr hook writes the snapshot, so the hunter starts without the context of
whoever wrote the code. Without Git, it inspects the current files.

1. **State ready.** The implementer finished the code to validate; there is no need to open a PR.
2. **Dispatch the `tr:bug-hunter` agent.** If `gate:bugs` or the `review` role uses a
   model from another CLI, run `fullchico-harness models validate-gate bugs`. The harness opens the
   independent reviewer, checks the snapshot and stamps. With the native agent, any short request
   works; the hook swaps it for the canonical one.
3. **The verdict** comes in three lines (`VERDICT`, `COMMIT`, `SUMMARY`).
   - `APPROVED`: the hook stamps the current state.
   - `REJECTED`: the implementer fixes, and another examination validates the new state.

The hunter validates only defects in the diff; command gates belong to `/tr:quality-check`.
