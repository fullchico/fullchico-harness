"""O ticket de contrato passa por dois revisores antes de integrar: defeito e ambiente.

Uma leitura só não acha tudo, e reler o ticket inteiro a cada rodada não converge. No contrato,
de que todos os outros tickets dependem, as duas leituras acontecem juntas, uma vez.
"""
import subprocess
import unittest

from tests.helpers import ROOT, bug_review_passes, commit_all, git, make_repo, run_hook, sync


def says(repo, agent, sha, verdict="APPROVED"):
    return run_hook("gate_stamp.py", {"hook_event_name": "SubagentStop", "agent_type": agent, "cwd": str(repo),
                                      "last_assistant_message": f"VEREDITO: {verdict}\nCOMMIT: {sha}\nRESUMO: x"})


class TestContractTicket(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        (self.repo / "harness.conf").write_text('PROFILE=livre\nCONTRACT_PATHS="packages/contract"\n')
        issues = self.repo / "docs/specs/x/issues"
        issues.mkdir(parents=True)
        (issues / "01-contract.md").write_text("# c\n\nStatus: claimed\nBlocked by:\nOwns: packages/contract\n")
        (issues / "02-agenda.md").write_text("# a\n\nStatus: claimed\nBlocked by: 01\nOwns: src/agenda\n")
        (self.repo / "docs/specs/x/spec.md").write_text("spec\n")
        commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "feat/x")

    def work(self, name, ticket, folder):
        agent = self.repo / f".claude/worktrees/agent-{name}"
        git(self.repo, "worktree", "add", "-q", "-b", f"worktree-agent-{name}", str(agent), "HEAD")
        (agent / folder).mkdir(parents=True)
        (agent / folder / "a.ts").write_text("export {};\n")
        path = agent / "docs/specs/x/issues" / ticket
        path.write_text(path.read_text().replace("claimed", "done"))
        return commit_all(agent, f"feat: {name}")

    def integrate(self, ticket, name):
        return subprocess.run([str(self.repo / ".harness/integrate"), f"docs/specs/x/issues/{ticket}", f"worktree-agent-{name}"],
                              cwd=self.repo, capture_output=True, text=True)

    def test_contract_needs_both_reviews_of_that_commit(self):
        tip = self.work("c", "01-contract.md", "packages/contract")
        bug_review_passes(self.repo, "worktree-agent-c")
        r = self.integrate("01-contract.md", "c")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("harness:revisor-ambiente", r.stderr)
        says(self.repo, "harness:revisor-ambiente", tip, "REJECTED")
        self.assertNotEqual(self.integrate("01-contract.md", "c").returncode, 0)
        says(self.repo, "harness:revisor-ambiente", tip)
        r = self.integrate("01-contract.md", "c")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_ordinary_ticket_needs_only_the_bug_hunt(self):
        self.work("c", "01-contract.md", "packages/contract")
        self.work("a", "02-agenda.md", "src/agenda")
        bug_review_passes(self.repo, "worktree-agent-a")
        r = self.integrate("02-agenda.md", "a")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_requests(self):
        tip = self.work("c", "01-contract.md", "packages/contract")
        base = git(self.repo, "rev-parse", "feat/x")
        pointers = f"spec: docs/specs/x/spec.md\nticket: docs/specs/x/issues/01-contract.md\ndiff: {base}...{tip}\ncommit: {tip}"
        ask = lambda agent, prompt: run_hook("dispatch_guard.py", {
            "tool_name": "Agent", "cwd": str(self.repo), "agent_type": "harness:orquestrador",
            "tool_input": {"subagent_type": agent, "prompt": prompt, "run_in_background": False}})[0]
        self.assertEqual(ask("harness:revisor-ambiente", pointers), 0)
        self.assertEqual(ask("harness:revisor-ambiente", f"diff: {base}...{tip}\ncommit: {tip}"), 2, "sempre sobre um ticket")
        finding = self.repo / "docs/specs/x/achados/01-rodada-1.md"
        finding.parent.mkdir()
        finding.write_text("achado\n")
        commit_all(self.repo, "docs: finding")
        for agent in ("harness:revisor-bugs", "harness:revisor-ambiente"):
            self.assertEqual(ask(agent, pointers + "\nachado: docs/specs/x/achados/01-rodada-1.md"), 0, agent)

    def test_definitions(self):
        import json
        s = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertIn("^harness:(seguranca|revisor|qualidade|revisor-bugs|revisor-ambiente)$",
                      [h["matcher"] for h in s["hooks"]["SubagentStop"]])
        head = (ROOT / "plugin/agents/revisor-ambiente.md").read_text().split("---")[1]
        self.assertIn("name: revisor-ambiente", head)
        self.assertNotIn("Edit", head)
