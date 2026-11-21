"""Marcar ticket como em andamento ou reabri-lo é um comando: o `sed` que os agentes
improvisavam falhava no macOS em toda entrega."""
import subprocess
import unittest

from tests.helpers import commit_all, git, make_repo, sync


def write(repo, number, status):
    path = repo / "docs/specs/x/issues" / f"{number:02d}-t{number}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# t{number}\n\nStatus: {status}\nBlocked by:\nOwns: src/t{number}\n\nStatus: open aparece no corpo\n")
    return path


class TestTicketCommand(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        self.a, self.b, self.c = write(self.repo, 1, "open"), write(self.repo, 2, "open"), write(self.repo, 3, "done")
        commit_all(self.repo, "chore: adopt harness")

    def run_cmd(self, *args):
        return subprocess.run([str(self.repo / ".harness/ticket"), *args], cwd=self.repo, capture_output=True, text=True)

    def status(self, path):
        return [l for l in path.read_text().splitlines() if l.startswith("Status:")][0]

    def test_claim_marks_and_commits_in_one_go(self):
        r = self.run_cmd("claim", "docs/specs/x", "01", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.status(self.a), self.status(self.b)), ("Status: claimed", "Status: claimed"))
        self.assertIn("Status: open aparece no corpo", self.a.read_text(), "só a linha do cabeçalho muda")
        self.assertEqual(git(self.repo, "log", "-1", "--format=%s"), "chore(tickets): claim 01, 02")
        self.assertEqual(git(self.repo, "status", "--short"), "")

    def test_claim_refuses_what_is_not_open(self):
        r = self.run_cmd("claim", "docs/specs/x", "03")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("03", r.stderr)
        self.assertEqual(self.status(self.c), "Status: done")
        r = self.run_cmd("claim", "docs/specs/x", "01", "09")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.status(self.a), "Status: open", "ou marca todos, ou nenhum")

    def test_reopen_brings_a_ticket_back_with_the_reason(self):
        r = self.run_cmd("reopen", "docs/specs/x", "03", "falta o prefixo de fila para os testes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.status(self.c), "Status: open")
        self.assertIn("reopen 03", git(self.repo, "log", "-1", "--format=%s"))
        self.assertIn("prefixo de fila", git(self.repo, "log", "-1", "--format=%b"))

    def test_usage(self):
        self.assertNotEqual(self.run_cmd().returncode, 0)
        self.assertNotEqual(self.run_cmd("apagar", "docs/specs/x", "01").returncode, 0)
        self.assertNotEqual(self.run_cmd("reopen", "docs/specs/x", "03").returncode, 0, "reabrir pede o motivo")


if __name__ == "__main__":
    unittest.main()
