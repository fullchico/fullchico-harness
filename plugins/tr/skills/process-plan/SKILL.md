---
name: process-plan
description: Opens and drives a demand through to validated delivery — interviews the owner, writes the spec and tickets, orchestrates execution and runs it through the gates.
---

# Plan and drive the demand

You are the main session that interviews, plans and keeps the owner informed (planning model).
After the interview's final confirmation, with the registry configured and the entry gates
certified and the owner acceptance recorded, dispatch `tr:orchestrator` as a background subagent
(`run_in_background: true` on Claude's Agent). In Codex, use `spawn_agent`
with `tr-orchestrator` and stay available for messages from the owner. Do not drive each ticket
in the main session. The orchestrator dispatches executors and reviewers as its own subagents; the
tr hook picks their model from the ticket's `Complexity:` (`simple` → haiku, `complex` →
sonnet). The ones who validate are the gate validators, in a clean context. The middle belongs to the orchestrator; the start and the end
are blocked by a hook until the steps happen.

The confirmation that closes the interview is the approval of the planning. Once the spec and the tickets
are written and committed, it becomes the owner's **acceptance** (`tr-harness gates --accept`, see section 4):
the certificate that the written criterion is the one agreed. Do not open another approval round beyond it.
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

## 0. Memory up to date

When the project has the `memory` plugin (the `memory` command exists), run `memory check` before the
interview. If units are aged or without a summary, run `/tr:memory-map` first: it redoes only what changed,
on `haiku`. The interview then starts on a current map. Without the plugin, skip this step.

## 1. Interview

Invoke `mattpocock-skills:grilling` and `mattpocock-skills:domain-modeling` with the Skill tool (the same
as Matt's grill-with-docs). Invoke them; do not reproduce their format from memory.

The product interview follows `grilling` as it is: rounds over the **frontier** of the design tree
(every decision whose prerequisites are settled: roles, booking rules, cancellation, subscription, auth...),
numbered, each with your recommended answer. An owner reply like "go with the recommendation" settles
**that round** only: recompute the frontier and ask the next round. The interview ends only when the
frontier is empty and the owner confirms the shared understanding; do not write the spec before that.

`domain-modeling` is mandatory, not optional, and runs during the interview, not after it. If it is not
installed, write the files yourself in the same format. It must produce or update:

- `GLOSSARY.md` with the demand's domain terms.
- One ADR in `docs/adr/NNNN-<slug>.md` for each hard-to-reverse decision (stack, auth,
  payments/subscriptions, data model, queues...).

The spec's decisions section links to the ADRs instead of holding the decisions. The `domain`
start gate checks that `GLOSSARY.md` exists, so planning does not pass without it.

**Status is read, not remembered.** Whenever the owner asks how the delivery is going, or the
orchestrator returns, run `tr-harness status` and answer from it: done, blocked (with the reason), running
(and any subagent flagged as possibly stopped), ready and queued tickets. Never state progress from memory.

## 2. Spec with passport

Write the spec by following Matt's `to-spec` as it is: run `tr-harness skill to-spec` and follow the file it
prints (the skill does not let the model invoke it, so read it; do not reproduce it from memory). Its "issue
tracker" is this project's `docs/specs/` layout, described in `docs/agents/issue-tracker.md`:
`docs/specs/<slug>/spec.md`, or the project's start gate path (see `gate`).

Write the slug to `.claude/current-demand` so that passports from old demands do not enter the
current delivery. When starting another demand, update that file.

On top of `to-spec`'s sections, the spec carries:

- one line with the end gates this demand requires, in addition to the mandatory ones in the registry:

  ```
  Gates: e2e, accessibility
  ```

  Choose based on what the demand touches (screen → accessibility and e2e; public page → seo). The mandatory
  ones always apply; this line only adds the optional ones. Without the line, all end gates are required.
- **Owner prerequisites**: everything a gate or a ticket will need that only the owner can do (the
  environment up and pointing at the right services, a credential, an external account, data). Agents do not
  start services or create credentials, so what is not asked here stops the delivery at the end. Derive the
  list, do not guess it: for each gate this demand requires, read its verifier (the registered command, or the
  instructions of its reviewer agent) and write down what that verifier needs to run. "None" is only a valid
  answer after that reading. List each one with the check that proves it is ready.

## 3. Tickets

Break the spec by following Matt's `to-tickets` (`tr-harness skill to-tickets`), one file per ticket at
`docs/specs/<slug>/issues/NN-<slug>.md`. Each ticket also carries the tr passport, as plain lines (no bold)
near the top:

```
Status: open
Complexity: simple | complex
Blocked by: NN, NN | none
Start: design | none
Gates: e2e, accessibility | api | none
Files: apps/web/**, packages/ui/**
```

`Status:` and `Delivery:` are progress; every other line of the spec and the tickets is the criterion the
owner accepts, so whoever executes does not edit it.

**Environment per executor.** Executors run in parallel worktrees, and other projects may be running on the
same machine. The first (scaffold) ticket creates the exact scripts the registered command gates run (read them in
`.claude/harness.json`), so no gate needs the owner in the middle of the delivery. It also makes every server and test read its ports and database from
environment variables (`PORT`, `API_PORT`, `DATABASE_URL`), with no hard-coded `3000`, and Playwright must not
reuse a server it did not start. The tr hook gives each executor its own port range and database name.

**Open the frontier.** A ticket is blocked only by tickets whose code it actually uses, not by the order you
thought of them. Split each feature so independent work can run together (for example the API and the
screen of a feature once the contract exists; screens that only share the base layout; read-only views
after the write path). A plan where every ticket blocks the next one runs one executor at a time: avoid it
unless each step truly consumes the previous one. In the plan you show the owner, list the waves: which
tickets run together in each one.

**One owner per area.** Two tickets of the same wave must not build the same capability (each would create
its own version of the module and the integration conflicts). What two tickets of a wave both use (a
calculation, a shared module, a client) goes into an earlier ticket or the scaffold, and both depend on it.
`gate` refuses the plan when two tickets that can run together claim the same area in `Files:` (a folder or
glob; one exact file both edit, such as a module registry, is allowed). Keep `Files:` narrow: `apps/api/**`
claims the whole API.

`simple`: mechanical and local (text, style, a field, one more test). `complex`: business rule,
contract, data, concurrency, or more than one layer. When in doubt, `complex`.
`Gates:` lists the end gates specific to this ticket. A backend task does not get
`accessibility` just because another task in the demand changes a screen. All names must exist
in the registry, and `always: true` gates remain required for the whole integration.
`Start:` lists the start gates specific to the ticket, for example a screen proposal
checked against the design system. Start gates with `always: false` only release the tickets
that cite them. The reviewer certifies the plan before the executor for that ticket is dispatched.
`Files:` lists the paths or globs the ticket may change. If any of those files change
after the certificate, the passport becomes pending and the reviewer must revalidate the current state.

## 4. Owner acceptance and start gates

Commit the spec and the tickets. Then ask for the owner's acceptance in one message: the summary of the
criterion, the waves, and the owner prerequisites with the check for each. The acceptance is
`tr-harness gates --accept`, run by you in the session.

**How the owner approves, without leaving the session.** Run the owner command yourself. In the normal
permission mode the tr hook turns it into Claude Code's permission dialog. In auto or bypass mode there is no
dialog: the hook denies the call and gives you an exact question. Put that question to the owner with
`AskUserQuestion`, alone in the message, with the options `Aprovo` and `Não aprovo`, and never fill `answers`
yourself (the hook refuses it). When the owner answers `Aprovo`, run the same command again: the hook lets it
through once. Codex has no such question: there the owner runs the printed line in the terminal.

The acceptance writes into the spec's
certificate appendix, signed by a commit of the owner. No executor starts, and no delivery passes, while the
current criterion has no acceptance: if the spec or a ticket changes later (anything but `Status:` and
`Delivery:`), the acceptance drops and the change goes back to the owner. Whoever is judged never loosens a
criterion alone: when a gate rejects, fix the work; when the criterion itself is wrong, bring the change to the
owner as a question with your recommendation.

**Questions to the owner live only at the edges.** After the acceptance the delivery runs on its own until the
pull request is open. `AskUserQuestion` (or any question that stops the flow) is used only for the owner
commands above and for the four urgent cases: the criterion must change, a final gate exceeded its rejection
limit (`gates --approve`), an irreversible external action not yet authorized, or a blocker with no allowed
alternative after investigation. Everything else is decided by the orchestrator.

Every command the owner must run in a terminal goes in its own code block, alone, ready to paste: no prose,
`and`, or `!` inside the block.

Then validate each start gate required by the registry (see `gate`). For command or artifact gates,
dispatch `/tr:quality-check`. For agent gates, use the configured reviewer; if the model is from another CLI,
run `tr-harness models validate-gate <name>`. Only the gates registered by the project are required.

## 5. The train: trip, arrival and adjustment trains

The delivery is a train with a start and an end. Boarding is section 4 (owner acceptance, owner prerequisites
ready, start gates). After it, the orchestrator runs on its own until the arrival is certified; the owner is
asked only in the urgent cases of section 4.

**Trip.** The execution follows Matt's `implement-spec` model (an integration branch, one worktree per ticket,
each ticket built with `tdd`), with the tr rails on top. Tickets with no blockers and with `Start:` certified
are the frontier. With `execution` configured, the orchestrator uses `tr-harness models run execution
--ticket <path> --prompt <handoff> --detach` and `tr-harness models wait <id>`; otherwise it dispatches an
implementer subagent with the ticket path in the request (the hook reads its `Complexity:` and adds the
executor protocol: align to the demand branch, ports and database, handoff, `DONE`/`BLOCKED`). The
orchestrator dispatches the executors of a wave together and waits for them, so it cannot notice a stuck one:
**you, the main session, watch the train**. After dispatching the orchestrator in the background, run
`tr-harness wait` (alone, with the Bash `timeout` at 600000) and repeat while it exits 3. Exit 0: the train
stopped; read the orchestrator's report. Exit 4: an executor stopped using tools for minutes. Rescue it: stop
the orchestrator (`TaskStop`), write `progress/handoff-<ticket>.md` for each stuck ticket from its worktree
(commits made, what is left), commit the handoffs and dispatch the orchestrator again, telling it to continue
from them. A stuck or blocked executor never loses work: the next one starts from the handoff.
No end gate runs during the trip (the hook refuses it while tickets or adjustments are open).

**Arrival.** With every ticket integrated, the orchestrator checks the branch as engineering work (`git status`,
untracked files, the diff, changes unrelated to the demand) and runs the audit: every required end gate at the
same time, each reviewer in a clean context. A reviewer validates the delta between the planned (spec, tickets,
artifacts approved at the start) and the delivered, observed in the delivered state; an artifact of the plan is
the reference, never the evidence. Whoever executed does not approve their own work. The reviewer gets the
accepted criterion and the code, never instructions from whoever asks. Approval writes the certificate into the
spec's appendix, committed by the hook in the reviewer's name (`Certified-by:`); nobody edits the appendix by
hand. `tr-harness balance --write` records the arrival balance in `progress/balance.md`.

**Adjustment trains.** Each rejected point becomes an adjustment in `progress/adjust-NN-<slug>.md` (progress,
not criterion: the owner's acceptance stays), dispatched like a ticket, in parallel. On their arrival, only the
gates that rejected are validated again, plus the command gates if the code changed; a model reviewer's approval
stays while the adjustments touched only what they declared in `Files:`. Each end gate has its `attempts` limit;
past it, the owner decides with the balance in hand. When every end gate is certified, the orchestrator runs
`tr-harness deliver` or `gate delivery` and reports to the main session; it only declares the delivery complete
when that command passes. After the audit nothing enters the branch except the certificates. Do not require a
PR, push or remote if the project did not configure them as a gate. At the start of the final response write
`DELIVERY: done`; the Stop hook checks the certificates again.

**Learn from the delivery.** When the main session receives `DELIVERY: done` and the project has the
`memory` plugin, it runs `/tr:memory-dream` right away, on its own, without asking the owner: what this
demand's sessions taught becomes notes while it is fresh. It does not block the delivery and is not a
gate; it is the loop that closes it. Report the new notes with the delivery result. Intermediate replies and questions
do not use this mark. Git is initialized by the installer; push and PR are separate actions.
