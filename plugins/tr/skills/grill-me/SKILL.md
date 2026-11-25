---
name: grill-me
description: Interviews the owner to decide the harness configuration, the rails and the gates based on the environment diagnostics and the project's evidence.
---

# Interview to configure the project

This skill includes Matt Pocock's `grilling` flow (version 1.3.1, MIT license;
see `../../THIRD_PARTY_NOTICES.md`) adapted for configuring FullChico Harness.
Use it inside `/tr:configure`, after reading the diagnostics and the project.

Map the decisions as a tree: each choice opens the decisions that depend on it.
Ask in rounds. In each round, present only the questions whose premises are already
resolved. Number the questions, give a concrete recommendation for each one and
wait for the owner's answers before moving on. Recompute the next round based on the
answers. Phrase each question so that "yes" accepts your recommendation.

Discovering facts is your job: check files, commands and diagnostics before
asking. Ask the owner only about decisions, for example the level of rigor at submission,
which checks are mandatory and which are optional per type of delivery.
For the end gates chosen as approval criteria, confirm `approval: auto`
(default) or `human`, and the `attempts` limit of automatic rejections (default 3;
configurable per gate). The fourth rejection with the default limit asks for human intervention.
Leave criteria, evidence and expected fixes as clear as the interview allows.
Identify in the interview the services and commands needed to run and validate:
for example, which Compose to bring up, which services on localhost to test, which browser or
Playwright to use, which network destinations to access and whether there will be writes outside the project.
Record in the plan the purpose of those actions and what remains out of scope. The plan does not
turn off the sandbox or grant access automatically: when the platform asks for permission,
the executor requests release for the concrete action. If a need arises later,
ask for release only for it, without reopening all of the planning.

For each proposed gate, show the evidence, the moment (`start` or `end`), the signing
mode (`command`, `artifact` or `agent`) and the exact command, path or agent.
If there is no evidence for a command, do not invent one: leave the decision open.

Finish when there is no pending decision. Summarize the agreement, the recommendation for each choice
and what the plan authorizes delivering. Ask the owner for a final confirmation of that understanding.
That confirmation authorizes execution of the recommended plan through to the end gates; do not ask for
another approval of the same plan before implementing. If there is a protected record to write,
include the terminal command as the last step of the configuration and check that it was applied.
Only then announce the interview closed and hand off to the orchestrator.
