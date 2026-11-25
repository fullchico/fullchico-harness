---
name: tr-codex
description: Use to plan a change, check gates, consult the memory and validate the delivery in Codex.
---

# Gates in Codex

The registry is `.claude/harness.json`, shared with Claude Code. Query the state with
`python3 -I .codex/harness/tr/scripts/gate_cli.py`.

Before editing code, follow the start gate. For the `process` default, write the spec at the path
the registry asks for and run `python3 -I .codex/harness/tr/scripts/gate_cli.py process`
alone. The hook signs the stamp after the command passes.

When the implementation is ready, check the end gates. For each command gate, use a
`tr-quality-checker` subagent with `gate: <name>` as the first line of the message. The hook replaces
the message with the name and snapshot and signs after the command runs successfully. For `bugs`, use a
`tr-bug-hunter` subagent, and for `scope` a `tr-scope-checker` subagent; the hook replaces the message
with the snapshot and reads the final verdict.
If the agent gate has a configured model, use `fullchico-harness models validate-gate
<name> [--ticket <path>] [--prompt <summary>]`. The harness opens the chosen CLI, requires the
verdict on the current snapshot and stamps. A gate's own model overrides `review`.
Wait for each validator to finish before the next. The agent that implemented does not sign the
end gates itself. Run `python3 -I .codex/harness/tr/scripts/gate_cli.py delivery` before answering.
Only declare `DELIVERY: done` when it passes. The installer initializes Git; PR and push are optional.

Codex needs to load the hooks from `.codex/hooks.json` and the project must be trusted. Without active
hooks, running the command does not stamp and the gates have no blocking force.

For memory, use the skills `$tr-memory-map`, `$tr-memory-dream` and `$tr-memory-learn`.
The engine lives in `.codex/harness/memory/`: query the index with
`.codex/harness/memory/bin/memory index` and a piece of code with
`.codex/harness/memory/bin/memory slice <path>`. Check the notes against the code.
