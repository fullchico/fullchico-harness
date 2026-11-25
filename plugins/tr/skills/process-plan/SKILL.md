---
name: process-plan
description: Opens and drives a demand through to validated delivery — interviews the owner, writes the spec and tickets, orchestrates execution and runs it through the gates.
---

# Plan and drive the demand

You are the main session that interviews, plans and keeps the owner informed (planning model).
After the interview's final confirmation, with the registry configured and the entry gates
stamped, dispatch `tr:orchestrator` as a background subagent
(`run_in_background: true` on Claude's Agent). In Codex, use `spawn_agent`
with `tr-orchestrator` and stay available for messages from the owner. Do not drive each ticket
in the main session. The orchestrator dispatches executors and reviewers as its own subagents; the
tr hook picks their model from the ticket's `Complexity:` (`simple` → haiku, `complex` →
sonnet). The ones who validate are the gate validators, in a clean context. The middle belongs to the orchestrator; the start and the end
are blocked by a hook until the steps happen.

The confirmation that closes the interview is the approval of the planning; do not open a second
approval round for the spec or the tickets when they reflect the confirmed decisions.
Hand the orchestrator the spec path, the tickets, the result of the entry gates,
the approved decisions and the recommendation chosen for each point. It drives the demand to
delivery without asking for confirmation on routine implementation choices. Use the plan's recommendation,
the project conventions and the verifiers' results. A formatting change with no change to
content, such as blank lines in `PRODUCT.md`, is an engineering decision: keep it if it is
harmless, or fix it safely, and record the choice. Go back to the owner only if the request
needs to change scope, a decision is missing that the plan does not let you infer, or there is an
irreversible action not yet authorized.

Before the handoff, check that the spec records the destination, acceptance criteria, applicable gates,
dependencies, services and expected commands (Docker, localhost, browser and network when
applicable), recommended choices and what is out of scope. A missing reversible technical detail
does not reopen the interview: the orchestrator chooses, implements and validates. If a CLI
or project restriction denies an action, try an allowed path to the same goal; only stop
on a real blocker with no authorized alternative.

In the handoff, say explicitly: "interview complete; recommended plan authorized; run
until `gate delivery` passes; resolve rejections and reversible technical decisions without new
approval". Include the expected services and say that a platform restriction must be
handled with an elevation request for the specific command. This instruction also applies when the
orchestrator switches CLI because of a model limit.
The limit on human intervention is set in the plan: only a change of scope or destination, an unauthorized irreversible
external action, or a technical/policy blocker with no allowed alternative after
investigation. Gate rejections produce a fix and revalidation inside the loop.

## 1. Interview

Invoke `mattpocock-skills:grilling` and `mattpocock-skills:domain-modeling` with the Skill tool (the same
as Matt's grill-with-docs). Invoke them; do not reproduce their format from memory.

The product interview follows Matt: one question at a time on each decision that changes the domain
(roles, booking rules, cancellation, subscription, auth...), each with your recommended answer. An owner
reply like "go with the recommendation" answers only the current question; it does not close the
interview. The interview ends when no decision that changes what will be built is left.

`domain-modeling` is mandatory, not optional, and runs during the interview, not after it. If it is not
installed, write the files yourself in the same format. It must produce or update:

- `GLOSSARY.md` with the demand's domain terms.
- One ADR in `docs/adr/NNNN-<slug>.md` for each hard-to-reverse decision (stack, auth,
  payments/subscriptions, data model, queues...).

The spec's decisions section links to the ADRs instead of holding the decisions. The `domain`
start gate checks that `GLOSSARY.md` exists, so planning does not pass without it.

## 2. Spec with passport

`docs/specs/<slug>/spec.md` (or the project's start gate path: see `gate`): problem,
solution, stories, decisions, what is out of scope, and how to test. One line states the end gates this
demand requires, in addition to the mandatory ones in the registry:

Write the slug to `.claude/current-demand` so that passports from old demands do not enter the
current delivery. When starting another demand, update that file.

```
Gates: e2e, accessibility
```

Choose based on what the demand touches (screen → accessibility and e2e; public page → seo). The mandatory ones
always apply; this line only adds the optional ones. Without the line, all end gates are required.

## 3. Tickets

`docs/specs/<slug>/issues/NN-<slug>.md`, vertical slices (each delivers something verifiable on its own),
each with its own passport:

```
Status: open
Complexity: simple | complex
Blocked by: NN, NN | none
Start: design | none
Gates: e2e, accessibility | api | none
Files: apps/web/**, packages/ui/**
```

`simple`: mechanical and local (text, style, a field, one more test). `complex`: business rule,
contract, data, concurrency, or more than one layer. When in doubt, `complex`.
`Gates:` lists the end gates specific to this ticket. A backend task does not get
`accessibility` just because another task in the demand changes a screen. All names must exist
in the registry, and `always: true` gates remain required for the whole integration.
`Start:` lists the start gates specific to the ticket, for example a screen proposal
checked against the design system. Start gates with `always: false` only release the tickets
that cite them. The reviewer stamps the plan before the executor for that ticket is dispatched.
`Files:` lists the paths or globs the ticket may change. If any of those files change
after the stamp, the passport becomes pending and the reviewer must revalidate the current state.
The project's entry gates release the start of the demand; artifacts such as design standards
or a screen proposal may be required there before any code.

## 4. Start gate

Prepare the spec and the tickets. Consult `gate` and validate each start gate required by the registry.
For command or artifact gates, dispatch `/tr:quality-check`. For agent gates,
use the configured reviewer; if the model is from another CLI, run
`tr-harness models validate-gate <name>`. Only the gates registered by the project are required.

## 5. Execution by the orchestrator subagent

The orchestrator reads the spec, the tickets and `tr-harness models show`. Tickets with no blockers and with `Start:` stamped are the frontier. If `execution` is configured, for each released ticket it uses
`tr-harness models run execution --ticket <path> --prompt <handoff> --detach` to open the chosen CLI and model, and collects it with `tr-harness models wait <id>`. The handoff contains the spec, the approved decision, the ticket and its gates. The execution manifest stays outside the repository and allows resuming after a failure. If `execution` is not configured, it dispatches an implementer subagent with the
ticket path in the request (the hook reads its `Complexity:`), the `tdd` skill, and an isolated context when there is
more than one in parallel. For **each gate in the passport**,
dispatch the matching reviewer in a clean context. For an agent gate with a configured model,
use `tr-harness models validate-gate <name> --ticket <path> --prompt <summary>`;
the harness checks the verdict and the snapshot and issues the stamp. For commands and artifacts, use the
gate's verifier. Whoever implemented does not validate.
If rejected, hand the findings back to the implementer; it fixes and the reviewer re-examines.
Approval stamps the current state of the project.

Only after the stamps, record `Status: done` on the ticket and open the next frontier.
If the project uses Git, `Delivery:` may record the validated commit.
The orchestrator gathers, decides and informs the main session about progress, real blockers and the result.

## 6. End gates

Before declaring delivery, the orchestrator checks the branch as engineering work: `git status`, ignored
and untracked files, the diff of what will be included, test results and stamps. Fix
a local file included by mistake and changes unrelated to the demand. Each gate's reviewer
examines the state that will be delivered; whoever executed does not approve their own work. Do not require a PR,
push or remote if the project did not configure them as a gate.

When the executor declares the implementation ready, the orchestrator runs `gate`: it checks the passports and shows the
frontier still open. It dispatches the verifiers of `/tr:quality-check` (one per global
command or artifact gate) and, for each required agent gate, the registered reviewer or
`tr-harness models validate-gate <name>` depending on the configured model.
If it failed or was rejected: an implementer fixes and the reviewer revalidates what changed, without asking
the owner for intermediate approval. Finally, run `tr-harness deliver` or `gate delivery`.
The orchestrator reports the result to the main session; it only declares the delivery complete when that command passes. At the start of the final response write
`DELIVERY: done`; the Stop hook checks the stamps again. Intermediate replies and questions
do not use this mark. Git is initialized by the installer; push and PR are separate actions.
