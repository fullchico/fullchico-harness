---
name: memory-learn
description: Closes the loop after a delivery is merged. Updates the map, measures usage per role, runs the delivery retrospective and consolidates the session notes.
disable-model-invocation: true
---

# Learn from the delivery

Run after the pull request has been merged. There are four things, in this order. Wait for the
subagents of each step to finish before moving to the next.

## 1. Update

Bring the default branch up to date. Then use the `/tr:memory-map` skill: it redoes only what the
delivery changed in the map, and reports glossary terms and architecture decisions to review.

## 2. Retrospective

The subject is the environment the agent worked in, not the agent. Read the digest of the delivery's
sessions (`memory-sessions sessions`, then `memory-sessions digest <id> .harness-run/dream/<id>.md`)
and look for:

- **Where time was lost finding something.** Would a pointer in the map or in `AGENTS.md` have prevented it?
- **What error an automatic check would catch.** What can be checked by machine becomes a
  check proposal (lint, test, validation), not a text one.
- **What rule was missing,** and made a reviewer reject something the implementer had no way to know.
- **What instruction changed nothing,** and only takes up space.
- **What command was denied** by the sandbox or by a guard, and whether the denial was right.
- **Where the spec or the tickets failed,** and an implementer had to stop because of a gap.

Write each proposal to a file in `.harness-run/`, with what happened, the evidence and the
suggested change, and store it with `memory-sessions propose <subject> <file>`. The command writes
to the repository, outside the worktree: the proposal is still there after the feature worktree is
removed. `memory-sessions proposals` lists the stored ones. Say whether the change belongs to the project (`AGENTS.md`,
a check in the project itself) or to a plugin.

What belongs to a plugin is not changed here. The owner takes the proposal to the plugin repository,
decides, publishes a version, and all projects receive it through the update.

## 3. Measure

Measure after the map and the retrospective, with their subagents already finished: measuring earlier
leaves out the cost of the cycle itself.

```bash
memory-sessions usage
```

The table shows, for the sessions not yet processed, the tokens of each role: the main
session and each subagent type, per model. The first column is the start of the session id,
which the other `learn` commands accept. Include in the report:

- the total, and each role's share;
- what stands out: a cheap role spending like an expensive one, a lot of uncached input tokens,
  an implementer that consumed several times more than the others.

Do not draw a conclusion from a single number. One delivery is one sample.

## 4. Consolidate

Use the `/tr:memory-dream` skill. It turns what the sessions taught about the project into notes
anchored in the code, and marks the sessions as processed.

## Report

Tell the owner: what changed in the map, the usage table with what stands out, the saved
proposals and where they are, and the new notes.
