"""Um dono por arquivo, contrato antes do paralelo, e integração de um ticket por vez."""
import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, git, make_repo, sync

sys.path.insert(0, str(ROOT / "plugin/payload"))
import tickets_check  # noqa: E402


def write(repo, number, name, owns, blocked="", status="open"):
    path = repo / "docs/specs/x/issues" / f"{number:02d}-{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: {status}\nBlocked by: {blocked}\nOwns: {owns}\n")
    return path


def found(repo):
    spec = str(repo / "docs/specs/x")
    return tickets_check.problems(tickets_check.load(spec + "/issues"), tickets_check.contract_paths(spec))


class TestOwnership(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()

    def test_every_ticket_declares_what_it_owns(self):
        path = self.repo / "docs/specs/x/issues/01-a.md"
        path.parent.mkdir(parents=True)
        path.write_text("# a\n\nStatus: open\nBlocked by:\n")
        with self.assertRaises(ValueError) as ctx:
            tickets_check.load(str(path.parent))
        self.assertIn("Owns", str(ctx.exception))
        for bad in ("", "/abs/path", "../fora", "a/../../b"):
            write(self.repo, 1, "a", bad)
            with self.assertRaises(ValueError, msg=bad):
                tickets_check.load(str(path.parent))

    def test_parallel_tickets_cannot_own_the_same_path(self):
        write(self.repo, 1, "base", "packages/contracts")
        write(self.repo, 2, "api", "apps/api/src/modules/agenda", blocked="01")
        write(self.repo, 3, "web", "apps/web/src/pages/agenda, apps/api/src/modules/agenda/dto", blocked="01")
        problems = found(self.repo)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("02", problems[0])
        self.assertIn("03", problems[0])
        self.assertIn("apps/api/src/modules/agenda", problems[0])

    def test_tickets_in_sequence_may_touch_the_same_path(self):
        write(self.repo, 1, "base", "apps/api/src/modules/agenda")
        write(self.repo, 2, "mais", "apps/api/src/modules/agenda", blocked="01")
        write(self.repo, 3, "depois", "apps/api/src/modules/agenda/use-cases", blocked="02")
        self.assertEqual(found(self.repo), [])

    def test_sibling_folders_do_not_overlap(self):
        write(self.repo, 1, "a", "apps/web/src/pages/agenda")
        write(self.repo, 2, "b", "apps/web/src/pages/agenda-publica")
        self.assertEqual(found(self.repo), [])

    def test_contract_comes_before_everything_else(self):
        (self.repo / "harness.conf").write_text('CONTRACT_PATHS="packages/contracts apps/web/src/shared"\n')
        write(self.repo, 1, "contrato", "packages/contracts, apps/web/src/shared")
        write(self.repo, 2, "api", "apps/api/src/modules/agenda", blocked="01")
        write(self.repo, 3, "web", "apps/web/src/pages/agenda")  # não espera o contrato
        problems = found(self.repo)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("03", problems[0])
        self.assertIn("contrato", problems[0])
        write(self.repo, 3, "web", "apps/web/src/pages/agenda", blocked="02")  # espera por transitividade
        self.assertEqual(found(self.repo), [])

    def test_without_contract_paths_there_is_no_contract_rule(self):
        write(self.repo, 1, "a", "src/a")
        write(self.repo, 2, "b", "src/b")
        self.assertEqual(found(self.repo), [])


class TestIntegrate(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        self.ticket = write(self.repo, 1, "agenda", "src/agenda", status="claimed")
        commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "feat/x")
        self.agent = self.repo / ".claude/worktrees/agent-a"
        git(self.repo, "worktree", "add", "-q", "-b", "worktree-agent-a", str(self.agent), "HEAD")

    def work(self, *paths, done=True):
        for path in paths:
            target = self.agent / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x\n")
        if done:
            ticket = self.agent / self.ticket.relative_to(self.repo)
            ticket.write_text(ticket.read_text().replace("Status: claimed", "Status: done"))
        commit_all(self.agent, "feat: agenda")

    def integrate(self, branch="worktree-agent-a"):
        return subprocess.run([str(self.repo / ".harness/integrate"), "docs/specs/x/issues/01-agenda.md", branch],
                              cwd=self.repo, capture_output=True, text=True)

    def test_work_inside_the_ownership_is_merged_and_the_worktree_removed(self):
        self.work("src/agenda/criar.py", "src/agenda/tests/test_criar.py")
        r = self.integrate()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.repo / "src/agenda/criar.py").exists())
        self.assertIn("Status: done", self.ticket.read_text())
        self.assertFalse(self.agent.exists())
        self.assertIn("Merge", git(self.repo, "log", "-1", "--format=%s"))

    def test_file_outside_the_ownership_refuses_the_merge(self):
        head = git(self.repo, "rev-parse", "HEAD")
        self.work("src/agenda/criar.py", "package.json", "src/outro/modulo.py")
        r = self.integrate()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("package.json", r.stderr)
        self.assertIn("src/outro/modulo.py", r.stderr)
        self.assertNotIn("src/agenda/criar.py", r.stderr)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)
        self.assertTrue(self.agent.exists(), "o trabalho recusado não se apaga")

    def test_failing_check_undoes_the_merge(self):
        (self.repo / "harness.conf").write_text('VALIDATE_PUSH="test ! -f src/agenda/quebra.py"\n')
        commit_all(self.repo, "chore: set validation")
        git(self.agent, "merge", "-q", "feat/x")
        head = git(self.repo, "rev-parse", "HEAD")
        self.work("src/agenda/quebra.py", done=False)  # sem fechar o ticket: o hook de commit não entra aqui
        r = self.integrate()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)
        self.assertFalse((self.repo / "src/agenda/quebra.py").exists())

    def test_ticket_not_done_or_dirty_tree_is_refused(self):
        self.work("src/agenda/criar.py", done=False)
        r = self.integrate()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Status: done", r.stderr)
        (self.repo / "solto.txt").write_text("x\n")
        git(self.repo, "add", "solto.txt")
        self.assertNotEqual(self.integrate().returncode, 0)


if __name__ == "__main__":
    unittest.main()
