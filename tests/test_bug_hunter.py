"""Caça a bugs: por ticket, antes de integrar, e num passe final antes do push.

O revisor de código confere regra e spec; este procura defeito. Nos dois momentos a
aprovação nasce da resposta dele, pelo hook, e sem ela a integração e o push são recusados.
"""
import json
import subprocess
import unittest

from tests.helpers import (ROOT, bug_review_passes, clone_repo, commit_all, commit_file, git, make_repo,
                           owner_approve, run_hook, sync)
import common


def stamp(repo, sha, verdict="APPROVED"):
    return run_hook("gate_stamp.py", {"hook_event_name": "SubagentStop", "agent_type": "harness:revisor-bugs",
                                      "cwd": str(repo),
                                      "last_assistant_message": f"VEREDITO: {verdict}\nCOMMIT: {sha}\nRESUMO: x"})


class TestPerTicket(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        ticket = self.repo / "docs/specs/x/issues/01-agenda.md"
        ticket.parent.mkdir(parents=True)
        ticket.write_text("# a\n\nStatus: claimed\nBlocked by:\nOwns: src/agenda\n")
        (self.repo / "docs/specs/x/spec.md").write_text("spec\n")
        commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "feat/x")
        self.agent = self.repo / ".claude/worktrees/agent-a"
        git(self.repo, "worktree", "add", "-q", "-b", "worktree-agent-a", str(self.agent), "HEAD")
        (self.agent / "src/agenda").mkdir(parents=True)
        (self.agent / "src/agenda/a.py").write_text("x\n")
        path = self.agent / "docs/specs/x/issues/01-agenda.md"
        path.write_text(path.read_text().replace("claimed", "done"))
        self.tip = commit_all(self.agent, "feat: agenda")

    def integrate(self):
        return subprocess.run([str(self.repo / ".harness/integrate"), "docs/specs/x/issues/01-agenda.md", "worktree-agent-a"],
                              cwd=self.repo, capture_output=True, text=True)

    def test_integration_waits_for_the_bug_review_of_that_exact_commit(self):
        r = self.integrate()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("harness:revisor-bugs", r.stderr)
        stamp(self.repo, self.tip, "REJECTED")
        self.assertNotEqual(self.integrate().returncode, 0)
        stamp(self.repo, self.tip)
        (self.agent / "src/agenda/b.py").write_text("y\n")
        commit_all(self.agent, "fix: b")  # commit novo: a aprovação era do anterior
        self.assertNotEqual(self.integrate().returncode, 0)
        bug_review_passes(self.repo, "worktree-agent-a")
        self.assertEqual(self.integrate().returncode, 0)

    def test_request_points_at_the_ticket_and_the_branch_commit(self):
        ask = lambda prompt, caller="harness:orquestrador": run_hook("dispatch_guard.py", {
            "tool_name": "Agent", "cwd": str(self.repo), "agent_type": caller,
            "tool_input": {"subagent_type": "harness:revisor-bugs", "prompt": prompt, "run_in_background": False}})[0]
        good = f"spec: docs/specs/x/spec.md\nticket: docs/specs/x/issues/01-agenda.md\ndiff: feat/x...{self.tip}\ncommit: {self.tip}"
        self.assertEqual(ask(good), 0)
        self.assertEqual(ask(good + "\nO implementador disse que está tudo certo."), 2)
        self.assertEqual(ask(good.replace(f"commit: {self.tip}", "commit: " + "0" * 40)), 2, "commit que não existe")
        other = git(self.repo, "rev-parse", "feat/x")
        self.assertEqual(ask(good.replace(f"...{self.tip}", f"...{other}")), 2, "o diff tem de terminar no commit revisado")


class TestFinalPass(unittest.TestCase):
    def setUp(self):
        self.origin = make_repo("origin dir")
        self.repo = clone_repo(self.origin)
        self.assertEqual(sync(self.repo).returncode, 0)
        commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "fix/x")
        self.sha = commit_file(self.repo, "a.txt", "fix: a")

    def push(self):
        return subprocess.run([str(self.repo / ".harness/push")], cwd=self.repo, capture_output=True, text=True)

    def test_push_needs_the_bug_hunt_over_the_whole_branch(self):
        for gate in ("seguranca", "revisao", "qualidade"):
            owner_approve(self.repo, gate)
        r = self.push()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("bugs", r.stderr)
        stamp(self.repo, self.sha)
        self.assertEqual(self.push().returncode, 0)

    def test_final_request_must_cover_the_whole_branch(self):
        base = common.branch_base(str(self.repo), self.sha)
        ask = lambda prompt: run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(self.repo), "tool_input": {
            "subagent_type": "harness:revisor-bugs", "prompt": prompt}})[0]
        self.assertEqual(ask(f"diff: {base}...{self.sha}\ncommit: {self.sha}"), 0)
        self.assertEqual(ask(f"diff: {self.sha}...{self.sha}\ncommit: {self.sha}"), 2)

    def test_definitions(self):
        self.assertIn("bugs", common.GATES)
        s = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertIn("^harness:(seguranca|revisor|qualidade|revisor-bugs)$", [h["matcher"] for h in s["hooks"]["SubagentStop"]])
        head = (ROOT / "plugin/agents/revisor-bugs.md").read_text().split("---")[1]
        self.assertIn("name: revisor-bugs", head)
        for tool in ("Edit", "Write", "Agent"):
            self.assertNotIn(tool, head)
        body = (ROOT / "plugin/agents/revisor-bugs.md").read_text()
        for needed in ("caso concreto", "substituto", "teste"):
            self.assertIn(needed, body, needed)
        run = ROOT / "plugin/payload/entrega"
        self.assertIn("harness:revisor-bugs", (run / "despacho.md").read_text())
        self.assertIn("harness:revisor-bugs", (run / "fechamento.md").read_text())


if __name__ == "__main__":
    unittest.main()
