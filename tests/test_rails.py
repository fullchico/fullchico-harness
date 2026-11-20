"""Trilhos: o que antes era instrução em texto e agora é negado ou feito por mecanismo."""
import json
import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, clone_repo, commit_all, commit_file, git, make_repo, owner_approve, run_hook, sync

HOOKS = ROOT / "plugin/payload/hooks"


def bash(repo, command):
    return run_hook("service_guard.py", {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": command}})


class TestHarnessScriptsRunAlone(unittest.TestCase):
    """Só a forma exata sai do sandbox. Encadeado, o script rodava dentro dele e falhava sem explicar."""

    def setUp(self):
        self.repo = make_repo()

    def test_chained_or_wrapped_forms_are_denied_with_the_reason(self):
        for command in ("git status --short && .harness/push", ".harness/up && .harness/prepare",
                        "git add harness.conf && git commit -q -m x && .harness/up", "bash .harness/up",
                        "cd apps && ../.harness/conf-apply; true", ".harness/fetch | tail -3",
                        "mkdir -p x\n.harness/conf-apply", ".harness/destroy 2>&1", "sh ./.harness/push --force"):
            rc, _, err = bash(self.repo, command)
            self.assertEqual(rc, 2, command)
            self.assertIn("sozinho", err, command)

    def test_exact_forms_and_plain_reads_pass(self):
        for command in (".harness/push", "./.harness/push --force", ".harness/fetch", "  .harness/up  ",
                        '.harness/pr create "feat: a" .harness-run/pr-body.md', ".harness/pr view",
                        "cat .harness/push", "grep -n up .harness/up", "ls .harness",
                        ".harness/validate --profile push && echo ok", ".harness/prepare 2>&1 | tail -3"):
            self.assertEqual(bash(self.repo, command)[0], 0, command)


class TestOnlyTheOrchestratorDispatchesImplementers(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        for path in ("docs/specs/x/spec.md", "docs/specs/x/issues/01-a.md"):
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_text("x")
        (self.repo / "harness.conf").write_text("PROJECT=p\nSERVICES=web\n")
        commit_all(self.repo, "docs: add spec")

    def dispatch(self, agent, prompt, caller=None):
        payload = {"tool_name": "Agent", "cwd": str(self.repo), "tool_input": {"subagent_type": agent, "prompt": prompt}}
        if caller:
            payload["agent_type"] = caller
            payload["tool_input"]["run_in_background"] = False
        return run_hook("dispatch_guard.py", payload)

    def test_main_session_cannot_dispatch_an_implementer(self):
        prompt = "spec: docs/specs/x/spec.md\nticket: docs/specs/x/issues/01-a.md"
        rc, _, err = self.dispatch("harness:implementador", prompt)
        self.assertEqual(rc, 2)
        self.assertIn("harness:orquestrador", err)
        self.assertEqual(self.dispatch("harness:implementador", prompt, caller="harness:implementador")[0], 2)
        self.assertEqual(self.dispatch("harness:implementador", prompt, caller="harness:orquestrador")[0], 0)

    def test_orchestrator_is_not_dispatched_by_a_subagent(self):
        self.assertEqual(self.dispatch("harness:orquestrador", "spec: docs/specs/x/spec.md")[0], 0)
        self.assertEqual(self.dispatch("harness:orquestrador", "spec: docs/specs/x/spec.md",
                                       caller="harness:orquestrador")[0], 2)

    def test_new_project_needs_the_conf_in_the_spec(self):
        (self.repo / "harness.conf").write_text("# PROJECT=meuapp\n")
        commit_all(self.repo, "chore: empty conf")
        rc, _, err = self.dispatch("harness:orquestrador", "spec: docs/specs/x/spec.md")
        self.assertEqual(rc, 2)
        self.assertIn("harness.conf", err)
        (self.repo / "docs/specs/x/spec.md").write_text("## harness.conf\n\nPROJECT=p\n")
        commit_all(self.repo, "docs: conf in spec")
        self.assertEqual(self.dispatch("harness:orquestrador", "spec: docs/specs/x/spec.md")[0], 0)

    def test_spec_must_be_committed_for_the_orchestrator(self):
        (self.repo / "docs/specs/x/spec.md").write_text("mudou sem commit")
        self.assertEqual(self.dispatch("harness:orquestrador", "spec: docs/specs/x/spec.md")[0], 2)


class TestTicketOnlyClosesWithGreenTests(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        self.ticket = self.repo / "docs/specs/x/issues/01-a.md"
        self.ticket.parent.mkdir(parents=True)
        self.ticket.write_text("# A\n\nStatus: claimed\nBlocked by:\n")
        commit_all(self.repo, "chore: adopt harness")

    def conf(self, command):
        (self.repo / "harness.conf").write_text(f'VALIDATE_PUSH="{command}"\n')

    def close(self):
        self.ticket.write_text("# A\n\nStatus: done\nBlocked by:\n")
        git(self.repo, "add", "-A")
        return subprocess.run(["git", "commit", "-q", "-m", "feat: a"], cwd=self.repo, capture_output=True, text=True)

    def test_red_tests_refuse_the_commit_that_closes_a_ticket(self):
        self.conf("echo rodei-os-testes; exit 3")
        r = self.close()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Status: done", r.stderr)
        self.assertIn("rodei-os-testes", r.stdout + r.stderr)

    def test_green_tests_let_it_through(self):
        self.conf("true")
        self.assertEqual(self.close().returncode, 0)

    def test_other_commits_do_not_run_the_tests(self):
        self.conf("exit 3")
        commit_file(self.repo, "a.txt", "fix: a")
        self.ticket.write_text("# A\n\nStatus: open\nBlocked by:\n")
        commit_all(self.repo, "chore(tickets): reopen 01")


class TestPushCleansIntegratedAgents(unittest.TestCase):
    def test_merged_agent_worktree_is_gone_after_the_push(self):
        origin = make_repo("origin dir")
        repo = clone_repo(origin)
        self.assertEqual(sync(repo).returncode, 0)
        commit_all(repo, "chore: adopt harness")
        git(repo, "checkout", "-q", "-b", "feat/x")
        agent = repo / ".claude/worktrees/agent-a"
        git(repo, "worktree", "add", "-q", "-b", "worktree-agent-a", str(agent), "HEAD")
        commit_file(agent, "a.txt", "fix: a")
        git(repo, "merge", "-q", "--no-ff", "worktree-agent-a", "-m", "Merge a")
        for gate in ("seguranca", "revisao", "qualidade"):
            owner_approve(repo, gate)
        r = subprocess.run([str(repo / ".harness/push")], cwd=repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(agent.exists())


class TestSetupWorktreeOnANewProject(unittest.TestCase):
    def test_empty_conf_is_not_an_error(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        r = subprocess.run([str(repo / ".harness/setup-worktree")], cwd=repo, capture_output=True, text=True,
                           env=dict(os.environ, HARNESS_SKIP_PLUGIN="1"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("harness.conf", r.stdout + r.stderr)
        self.assertFalse((repo / ".env").exists())


if __name__ == "__main__":
    unittest.main()


class TestOrchestratorWaitsForItsAgents(unittest.TestCase):
    """Subagente em segundo plano avisa a sessão do dono, não quem o despachou: o modelo caro
    virava carteiro entre o orquestrador e os implementadores."""

    def setUp(self):
        self.repo = make_repo()
        for path in ("docs/specs/x/spec.md", "docs/specs/x/issues/01-a.md"):
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_text("x")
        (self.repo / "harness.conf").write_text("PROJECT=p\n")
        commit_all(self.repo, "docs: add spec")

    def dispatch(self, background, caller="harness:orquestrador", agent="harness:implementador"):
        tool_input = {"subagent_type": agent, "prompt": "spec: docs/specs/x/spec.md\nticket: docs/specs/x/issues/01-a.md"}
        if background is not None:
            tool_input["run_in_background"] = background
        return run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(self.repo), "agent_type": caller,
                                              "tool_input": tool_input})

    def test_orchestrator_must_dispatch_in_the_foreground(self):
        self.assertEqual(self.dispatch(False)[0], 0)
        for background in (True, None):
            rc, _, err = self.dispatch(background)
            self.assertEqual(rc, 2, background)
            self.assertIn("run_in_background", err)

    def test_the_owner_session_may_still_run_the_orchestrator_in_the_background(self):
        rc = run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(self.repo), "tool_input": {
            "subagent_type": "harness:orquestrador", "prompt": "spec: docs/specs/x/spec.md", "run_in_background": True}})[0]
        self.assertEqual(rc, 0)
