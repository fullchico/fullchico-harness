"""Achado simples não bloqueia o ticket, mas fica registrado e barra o push até ser conferido."""
import subprocess
import unittest

from tests.helpers import clone_repo, commit_all, commit_file, git, make_repo, owner_approve, run_hook, sync


def hunter_says(repo, sha, body, verdict="APPROVED", agent="harness:revisor-bugs"):
    return run_hook("gate_stamp.py", {"hook_event_name": "SubagentStop", "agent_type": agent,
                                      "cwd": str(repo),
                                      "last_assistant_message": f"{body}\nVEREDITO: {verdict}\nCOMMIT: {sha}\nRESUMO: x"})


class TestPendings(unittest.TestCase):
    def setUp(self):
        self.origin = make_repo("origin dir")
        self.repo = clone_repo(self.origin)
        self.assertEqual(sync(self.repo).returncode, 0)
        commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "fix/x")
        self.sha = commit_file(self.repo, "a.txt", "fix: a")

    def pendings(self):
        r = subprocess.run([str(self.repo / ".harness/pendings")], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def push(self):
        return subprocess.run([str(self.repo / ".harness/push")], cwd=self.repo, capture_output=True, text=True)

    def approve_everything(self):
        for gate in ("seguranca", "revisao", "qualidade"):
            owner_approve(self.repo, gate)

    def test_simple_finding_lets_the_ticket_through_and_is_recorded(self):
        hunter_says(self.repo, self.sha, "PENDENCIA: src/a.ts:10 mensagem de erro sem ponto final | teste: a.test.ts 'ends with a period'")
        listed = self.pendings()
        self.assertIn("P1", listed)
        self.assertIn("mensagem de erro sem ponto final", listed)
        hunter_says(self.repo, self.sha, "PENDENCIA: src/a.ts:10 mensagem de erro sem ponto final | teste: a.test.ts 'ends with a period'")
        self.assertNotIn("P2", self.pendings(), "o mesmo achado dito de novo não vira outro")

    def test_rejected_review_records_nothing(self):
        hunter_says(self.repo, self.sha, "PENDENCIA: algo simples | teste: t", verdict="REJECTED")
        self.assertEqual(self.pendings().strip(), "")

    def test_open_pending_blocks_the_push_until_the_hunter_checks_it(self):
        hunter_says(self.repo, self.sha, "PENDENCIA: algo simples | teste: t")
        self.approve_everything()
        r = self.push()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("P1", r.stderr)
        self.assertIn("algo simples", r.stderr)
        hunter_says(self.repo, self.sha, "RESOLVIDA: P1")
        self.assertEqual(self.pendings().strip(), "")
        self.assertEqual(self.push().returncode, 0)

    def test_the_environment_reviewer_opens_pendings_too(self):
        hunter_says(self.repo, self.sha, "PENDENCIA: aviso no log da instalação | teste: t", agent="harness:revisor-ambiente")
        self.assertIn("aviso no log da instalação", self.pendings())

    def test_too_many_pendings_is_not_an_approval(self):
        import os
        import common
        body = "\n".join(f"PENDENCIA: item {n} | teste: t" for n in range(3))
        hunter_says(self.repo, self.sha, body)
        self.assertEqual(self.pendings().strip(), "", "viram achado da rodada de correção, não pendência")
        self.assertFalse(os.path.exists(common.approval_path(common.state_dir(str(self.repo)), "bugs", self.sha)))
        hunter_says(self.repo, self.sha, "PENDENCIA: item 0 | teste: t\nPENDENCIA: item 1 | teste: t")
        self.assertTrue(os.path.exists(common.approval_path(common.state_dir(str(self.repo)), "bugs", self.sha)))
        self.assertIn("P2", self.pendings())

    def test_only_reviewers_open_or_close(self):
        hunter_says(self.repo, self.sha, "PENDENCIA: algo simples | teste: t")
        run_hook("gate_stamp.py", {"hook_event_name": "SubagentStop", "agent_type": "harness:implementador", "cwd": str(self.repo),
                                   "last_assistant_message": f"RESOLVIDA: P1\nVEREDITO: APPROVED\nCOMMIT: {self.sha}\nRESUMO: x"})
        self.assertIn("P1", self.pendings())

    def test_pendings_of_another_feature_do_not_count(self):
        other = self.repo.parent / "outra feature"
        git(self.repo, "worktree", "add", "-q", "-b", "fix/y", str(other), "HEAD")
        hunter_says(other, git(other, "rev-parse", "HEAD"), "PENDENCIA: da outra feature | teste: t")
        self.assertEqual(self.pendings().strip(), "")
