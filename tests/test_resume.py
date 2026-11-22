"""Retomada de uma entrega: o estado real de cada ticket, o trilho contra redespacho do que já
tem trabalho pronto, o tempo limite por despacho e o orquestrador que não encerra com filho rodando.

Vistos em entregas reais: a API caiu com o commit do ticket já feito num worktree de agente, e
quem redisparou o orquestrador não tinha como saber; e um implementador ficou 44 minutos parado
com o orquestrador esperando em silêncio.
"""
import json
import os
import subprocess
import time
import unittest

from tests.helpers import ROOT, bug_review_passes, commit_all, git, make_repo, run_hook, sync
import common

SPEC = "docs/specs/x"
T1 = f"{SPEC}/issues/01-a.md"
T2 = f"{SPEC}/issues/02-b.md"
# O relógio dos testes: os despachos acontecem "uma hora atrás", antes dos commits de verdade.
T0 = int(time.time()) - 3600
MIN = 60


def at(when):
    os.environ["HARNESS_NOW"] = str(when)


def stamp(repo, sha, verdict="APPROVED", agent="harness:revisor-bugs"):
    return run_hook("gate_stamp.py", {"hook_event_name": "SubagentStop", "agent_type": agent, "cwd": str(repo),
                                      "last_assistant_message": f"VEREDITO: {verdict}\nCOMMIT: {sha}\nRESUMO: x"})


class Base(unittest.TestCase):
    def setUp(self):
        self.addCleanup(os.environ.pop, "HARNESS_NOW", None)
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        for number, name, status, blocked in ((1, "a", "claimed", ""), (2, "b", "claimed", ""),
                                              (3, "c", "open", ""), (4, "d", "open", "3")):
            path = self.repo / SPEC / "issues" / f"{number:02d}-{name}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {name}\n\nStatus: {status}\nBlocked by: {blocked}\nOwns: src/{name}\n")
        (self.repo / SPEC / "spec.md").write_text("spec\n")
        commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "feat/x")

    def agent(self, name, ticket=T1, done=True, date=None):
        """Um implementador num worktree de agente: escreve no que o ticket possui e fecha o ticket."""
        tree = self.repo / f".claude/worktrees/agent-{name}"
        git(self.repo, "worktree", "add", "-q", "-b", f"worktree-agent-{name}", str(tree), "HEAD")
        owned = [l for l in (tree / ticket).read_text().splitlines() if l.startswith("Owns:")][0].split(": ")[1]
        (tree / owned).mkdir(parents=True, exist_ok=True)
        (tree / owned / f"{name}.py").write_text("x\n")
        if done:
            (tree / ticket).write_text((tree / ticket).read_text().replace("Status: claimed", "Status: done"))
        env = dict(os.environ)
        if date:
            env.update(GIT_COMMITTER_DATE=f"@{date} +0000", GIT_AUTHOR_DATE=f"@{date} +0000")
        subprocess.run(["git", "add", "-A"], cwd=tree, check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"feat: {name}"], cwd=tree, check=True, env=env)
        return git(tree, "rev-parse", "HEAD")

    def resume(self, *args):
        return subprocess.run([str(self.repo / ".harness/resume"), *args], cwd=self.repo, capture_output=True, text=True)

    def state(self, ticket=T1):
        r = self.resume(SPEC, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return next(t for t in json.loads(r.stdout)["tickets"] if t["ticket"] == ticket)

    def dispatch(self, agent, prompt):
        tool_input = {"subagent_type": agent, "prompt": prompt}
        if agent == "harness:implementador":
            tool_input["isolation"] = "worktree"
        return run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(self.repo),
                                              "agent_type": "harness:orquestrador", "tool_input": tool_input})

    def implement(self, ticket=T1, extra=""):
        return self.dispatch("harness:implementador", f"spec: {SPEC}/spec.md\nticket: {ticket}{extra}")

    def review(self, tip, ticket=T1, agent="harness:revisor-bugs"):
        return self.dispatch(agent, f"spec: {SPEC}/spec.md\nticket: {ticket}\ndiff: feat/x...{tip}\ncommit: {tip}")

    def ticket_cmd(self, *args):
        r = subprocess.run([str(self.repo / ".harness/ticket"), *args], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestResume(Base):
    def test_done_commit_left_in_an_agent_worktree_asks_for_review(self):
        tip = self.agent("a")
        found = self.state()
        self.assertEqual((found["action"], found["branch"], found["commit"]), ("revisar", "worktree-agent-a", tip))
        self.assertEqual(found["bugs"]["state"], "none")
        text = self.resume(SPEC).stdout
        for needed in ("01-a", "revisar", "worktree-agent-a", tip):
            self.assertIn(needed, text, needed)

    def test_approved_commit_is_ready_to_integrate(self):
        self.agent("a")
        bug_review_passes(self.repo, "worktree-agent-a")
        found = self.state()
        self.assertEqual((found["action"], found["bugs"]["state"]), ("integrar", "approved"))
        self.assertIn(f".harness/integrate {T1} worktree-agent-a", found["next"])

    def test_review_asked_and_not_answered_waits_then_is_stalled(self):
        tip = self.agent("a")
        at(T0)
        self.assertEqual(self.review(tip)[0], 0)
        at(T0 + 5 * MIN)
        found = self.state()
        self.assertEqual((found["action"], found["bugs"]["state"], found["bugs"]["age_min"]), ("esperar", "waiting", 5))
        at(T0 + 31 * MIN)
        self.assertEqual(self.state()["action"], "parado")

    def test_rejected_commit_is_a_fix_round(self):
        tip = self.agent("a")
        self.review(tip)
        stamp(self.repo, tip, "REJECTED")
        found = self.state()
        self.assertEqual((found["action"], found["bugs"]["state"]), ("corrigir", "rejected"))

    def test_claimed_ticket_with_no_commit_anywhere_is_dispatched(self):
        self.agent("b", ticket=T2)  # o trabalho de outro ticket não conta para este
        found = self.state()
        self.assertEqual((found["action"], found["branch"], found["commit"]), ("despachar", None, None))

    def test_dispatch_older_than_the_limit_without_a_commit_is_stalled(self):
        at(T0)
        self.assertEqual(self.implement()[0], 0)
        at(T0 + 10 * MIN)
        found = self.state()
        self.assertEqual((found["action"], found["waiting_min"]), ("esperar", 10))
        at(T0 + 31 * MIN)
        found = self.state()
        self.assertEqual(found["action"], "parado")
        self.assertIn("31 min", found["next"])
        with open(self.repo / "harness.conf", "a") as f:
            f.write("\nDISPATCH_TIMEOUT_MIN=60\n")
        self.assertEqual(self.state()["action"], "esperar", "o limite é do harness.conf")

    def test_commits_without_done_show_an_implementer_at_work(self):
        self.agent("a", done=False)  # commit de agora, ticket ainda em andamento
        found = self.state()
        self.assertEqual((found["action"], found["working"]), ("esperar", "worktree-agent-a"))
        at(int(time.time()) + 31 * MIN)
        self.assertEqual(self.state()["action"], "parado")

    def test_two_branches_with_the_same_ticket_done_the_newest_wins(self):
        old = self.agent("old", date=T0)
        new = self.agent("new", date=T0 + 600)
        found = self.state()
        self.assertEqual((found["branch"], found["commit"]), ("worktree-agent-new", new))
        self.assertEqual(found["superseded"], [{"branch": "worktree-agent-old", "commit": old}])
        self.assertIn("superada", self.resume(SPEC).stdout)

    def test_reopened_ticket_leaves_the_old_attempt_behind(self):
        old = self.agent("a")
        self.ticket_cmd("reopen", SPEC, "01", "o trabalho não presta")
        self.ticket_cmd("claim", SPEC, "01")
        found = self.state()
        self.assertEqual((found["action"], found["commit"]), ("despachar", None))
        self.assertEqual(found["superseded"], [{"branch": "worktree-agent-a", "commit": old}])

    def test_editing_the_ticket_without_changing_status_keeps_the_work(self):
        # O orquestrador corrige o `Owns:` antes de integrar: o commit pronto continua valendo.
        tip = self.agent("a")
        path = self.repo / T1
        path.write_text(path.read_text().replace("Owns: src/a", "Owns: src/a, src/extra"))
        commit_all(self.repo, "docs: widen ownership")
        self.assertEqual(self.state()["commit"], tip)

    def test_contract_ticket_also_needs_the_environment_review(self):
        with open(self.repo / "harness.conf", "a") as f:
            f.write('\nCONTRACT_PATHS="src/a"\n')
        tip = self.agent("a")
        bug_review_passes(self.repo, "worktree-agent-a")
        found = self.state()
        self.assertEqual((found["action"], found["contract"], found["ambiente"]["state"]), ("revisar", True, "none"))
        self.assertIn("harness:revisor-ambiente", found["next"])
        self.assertNotIn("ambiente", self.state(T2))
        stamp(self.repo, tip, agent="harness:revisor-ambiente")
        self.assertEqual(self.state()["action"], "integrar")

    def test_json_and_text_tell_the_same_and_open_tickets_are_only_counted(self):
        self.agent("a")
        data = json.loads(self.resume("--json", SPEC).stdout)
        self.assertEqual((data["spec"], data["feature"], data["timeout_min"]), (SPEC, "feat/x", 30))
        self.assertEqual((data["done"], data["open"]), (0, 2))
        self.assertEqual(data["frontier"], [f"{SPEC}/issues/03-c.md"])
        self.assertEqual([t["ticket"] for t in data["tickets"]], [T1, T2], "só os que estão em andamento")
        for item in data["tickets"]:
            for key in ("ticket", "status", "action", "next", "branch", "commit", "superseded"):
                self.assertIn(key, item)
        text = self.resume(SPEC).stdout
        for item in data["tickets"]:
            self.assertIn(item["action"], text)
            self.assertIn(item["next"], text)
        self.assertIn("03-c", text)
        self.assertNotIn("04-d", text, "aberto e bloqueado não aparece: só a contagem")

    def test_reads_only_and_usage_errors_exit_2(self):
        before = git(self.repo, "status", "--short"), git(self.repo, "rev-parse", "HEAD")
        self.assertEqual(self.resume(f"{SPEC}/spec.md").returncode, 0, "o caminho da spec também serve")
        self.assertEqual((git(self.repo, "status", "--short"), git(self.repo, "rev-parse", "HEAD")), before)
        self.assertEqual(self.resume().returncode, 2)
        self.assertEqual(self.resume("docs/specs/nao-existe").returncode, 2)
        self.assertEqual(self.resume(SPEC, "--outra").returncode, 2)


class TestNoRedispatch(Base):
    def test_ticket_with_finished_work_is_not_dispatched_again(self):
        self.assertEqual(self.implement()[0], 0, "sem trabalho pronto, o despacho passa")
        tip = self.agent("a")
        rc, _, err = self.implement()
        self.assertEqual(rc, 2)
        for needed in ("worktree-agent-a", tip, ".harness/resume", ".harness/ticket reopen"):
            self.assertIn(needed, err, needed)

    def test_reopening_the_ticket_frees_the_dispatch(self):
        self.agent("a")
        self.ticket_cmd("reopen", SPEC, "01", "o trabalho não presta")
        self.ticket_cmd("claim", SPEC, "01")
        self.assertEqual(self.implement()[0], 0)

    def test_fix_round_is_not_blocked(self):
        self.agent("a")
        (self.repo / SPEC / "achados").mkdir()
        (self.repo / SPEC / "achados/01-rodada-1.md").write_text("achado\n")
        commit_all(self.repo, "docs: add finding")
        self.assertEqual(self.implement()[0], 2)
        self.assertEqual(self.implement(extra=f"\nachado: {SPEC}/achados/01-rodada-1.md")[0], 0)


class TestDispatchRecord(Base):
    def records(self):
        folder = os.path.join(common.state_dir(str(self.repo)), "dispatches")
        found = []
        for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            self.assertTrue(name.endswith(".json"), f"sobrou temporário: {name}")
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                found.append(json.load(f))
        return found

    def test_accepted_dispatch_is_recorded_with_the_time(self):
        at(T0)
        self.assertEqual(self.implement()[0], 0)
        self.assertEqual(self.implement(ticket=f"{SPEC}/issues/03-c.md")[0], 2, "ticket que não foi pego")
        (only,) = self.records()
        self.assertEqual((only["at"], only["agent"], only["ticket"], only["spec"]),
                         (T0, "harness:implementador", T1, SPEC))
        tip = self.agent("a")
        at(T0 + 60)
        self.assertEqual(self.review(tip)[0], 0)
        by_agent = {r["agent"]: r for r in self.records()}
        self.assertEqual(len(by_agent), 2, "um arquivo por ticket e agente")
        reviewer = by_agent["harness:revisor-bugs"]
        self.assertEqual((reviewer["at"], reviewer["commit"], reviewer["branch"]), (T0 + 60, tip, "worktree-agent-a"))
        at(T0 + 120)
        self.review(tip)
        self.assertEqual(len(self.records()), 2, "o novo despacho substitui o registro")


class TestOrchestratorStop(Base):
    def stop(self, active=False):
        return run_hook("orchestrator_stop.py", {"hook_event_name": "SubagentStop", "agent_type": "harness:orquestrador",
                                                 "cwd": str(self.repo), "stop_hook_active": active,
                                                 "last_assistant_message": "terminei"})

    def log(self):
        path = os.path.join(common.state_dir(str(self.repo)), "log.jsonl")
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_holds_the_first_stop_and_releases_the_second(self):
        at(T0)
        self.implement()
        at(T0 + 3 * MIN)
        rc, _, err = self.stop()
        self.assertEqual(rc, 2)
        for needed in ("01-a", "3 min", "PARADA"):
            self.assertIn(needed, err, needed)
        self.assertEqual(self.stop(active=True)[0], 0, "nunca prende em laço")
        self.assertIn("orchestrator_stop", self.log())

    def test_does_not_hold_without_a_pending_dispatch(self):
        self.assertEqual(self.stop()[0], 0)
        at(T0)
        self.implement()
        at(T0 + 31 * MIN)
        self.assertEqual(self.stop()[0], 0, "além do limite o despacho está parado: o roteiro manda agir, não esperar")

    def test_does_not_hold_once_the_work_arrived_or_was_integrated(self):
        at(T0)
        self.implement()
        tip = self.agent("a")
        at(T0 + MIN)
        self.assertEqual(self.stop()[0], 0, "o commit chegou: falta revisar, não esperar")
        self.assertEqual(self.review(tip)[0], 0)
        self.assertEqual(self.stop()[0], 2, "o revisor ainda não respondeu")
        bug_review_passes(self.repo, "worktree-agent-a")
        self.assertEqual(self.stop()[0], 0)
        r = subprocess.run([str(self.repo / ".harness/integrate"), T1, "worktree-agent-a"], cwd=self.repo,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.stop()[0], 0, "ticket integrado não segura ninguém")

    def test_internal_error_never_holds(self):
        self.assertEqual(run_hook("orchestrator_stop.py", None, raw="isto não é json")[0], 0)
        self.assertEqual(run_hook("orchestrator_stop.py", {"cwd": "/nao/existe"})[0], 0)


class TestWiring(unittest.TestCase):
    def test_settings_wire_the_stop_hook_in_its_own_group(self):
        groups = json.loads((ROOT / "plugin/templates/settings.json").read_text())["hooks"]["SubagentStop"]
        matchers = [g.get("matcher") for g in groups]
        self.assertIn("^harness:(seguranca|revisor|qualidade|revisor-bugs|revisor-ambiente)$", matchers)
        (own,) = [g for g in groups if g.get("matcher") == "^harness:orquestrador$"]
        self.assertEqual([h["command"] for h in own["hooks"]],
                         ['[ -f "$CLAUDE_PROJECT_DIR/.harness/hooks/orchestrator_stop.py" ] || exit 0; '
                          'python3 -I "$CLAUDE_PROJECT_DIR/.harness/hooks/orchestrator_stop.py"'])

    def test_playbooks_start_by_the_resume(self):
        for path in ("plugin/agents/orquestrador.md", "plugin/payload/entrega/despacho.md",
                     "plugin/skills/entregar/SKILL.md", "README.md"):
            self.assertIn(".harness/resume", (ROOT / path).read_text(), path)
        dispatch = (ROOT / "plugin/payload/entrega/despacho.md").read_text()
        for needed in ("parado", "DISPATCH_TIMEOUT_MIN", "assim que"):
            self.assertIn(needed, dispatch, needed)
        self.assertIn("# DISPATCH_TIMEOUT_MIN=30", (ROOT / "plugin/templates/harness.conf").read_text())

    def test_synced_project_gets_the_command_and_the_hook(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        self.assertTrue(os.access(repo / ".harness/resume", os.X_OK))
        self.assertTrue((repo / ".harness/hooks/orchestrator_stop.py").exists())


if __name__ == "__main__":
    unittest.main()
