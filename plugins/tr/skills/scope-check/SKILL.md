---
name: scope-check
description: Checks that the finished work matches the spec and the tickets — every criterion met, nothing outside each ticket's Files — in an independent subagent that stamps the current state. Use before delivery.
---

# Check the scope

The `scope` gate is signed by the verdict of the `tr:scope-checker` agent. You sign nothing and do not
write its request: the tr hook writes the snapshot, so the checker starts without the context of
whoever wrote the code. It reads the spec and tickets of `.claude/current-demand` on its own.

1. **State ready.** The tickets are done and the code to validate is finished.
2. **Dispatch the `tr:scope-checker` agent.** If `gate:scope` or the `review` role uses a model
   from another CLI, run `tr-harness models validate-gate scope`. With the native agent, any
   short request works; the hook swaps it for the canonical one.
3. **The verdict** comes in three lines (`VERDICT`, `COMMIT`, `SUMMARY`).
   - `APPROVED`: the hook stamps the current state.
   - `REJECTED`: the gaps go back to the executor of the ticket; another examination validates the new state.

The checker validates fidelity to the plan; defects belong to `/tr:bugs-hunt` and command gates to `/tr:quality-check`.
