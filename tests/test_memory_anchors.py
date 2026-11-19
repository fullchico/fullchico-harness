import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, commit_file, git, make_repo

sys.path.insert(0, str(ROOT / "plugin/payload"))
import memory  # noqa: E402

SCRIPT = str(ROOT / "plugin/payload/memory")
GLOSSARY = "# Glossário\n\n## Agendamento\nReserva de um horário.\n\n### Profissional\nQuem atende.\n\n**Encaixe**: horário extra.\n"


def project():
    repo = make_repo()
    files = {"GLOSSARY.md": GLOSSARY, "docs/adr/0001-fila-de-eventos.md": "# Fila\n",
             "docs/adr/0002-multi-tenant.md": "# Tenant\n", "docs/adr/README.md": "índice\n",
             "apps/api/booking.py": "x\n", "apps/api/staff.py": "x\n", "apps/api/queue.py": "x\n"}
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    commit_all(repo, "feat: scaffold")
    return repo


class TestAnchors(unittest.TestCase):
    def setUp(self):
        self.repo = project()
        self.root = str(self.repo)

    def test_terms_and_adrs_start_unanchored(self):
        state = memory.status(self.root)
        self.assertEqual(state["glossary"]["unanchored"], ["Agendamento", "Encaixe", "Profissional"])
        self.assertEqual(state["adr"]["unanchored"], ["0001-fila-de-eventos", "0002-multi-tenant"])
        self.assertEqual(state["glossary"]["gone"], [])
        self.assertEqual(state["adr"]["review"], [])

    def test_term_whose_code_is_gone_is_flagged(self):
        memory.anchor(self.root, "glossary", "Agendamento", ["apps/api/booking.py"])
        memory.anchor(self.root, "glossary", "Profissional", ["apps/api/staff.py", "apps/api/booking.py"])
        self.assertEqual(memory.status(self.root)["glossary"]["gone"], [])
        git(self.repo, "rm", "-q", "apps/api/booking.py")
        commit_all(self.repo, "refactor: drop booking")
        state = memory.status(self.root)
        self.assertEqual(state["glossary"]["gone"], ["Agendamento"])
        self.assertEqual(state["glossary"]["unanchored"], ["Encaixe"])

    def test_adr_with_many_commits_in_its_area_asks_for_review(self):
        (self.repo / "harness.conf").write_text("ADR_REVIEW_COMMITS=3\n")
        commit_all(self.repo, "chore: conf")
        memory.anchor(self.root, "adr", "0001-fila-de-eventos", ["apps/api/queue.py"])
        for n in range(2):
            commit_file(self.repo, "apps/api/queue.py", f"fix: queue {n}")
        commit_file(self.repo, "apps/api/staff.py", "fix: unrelated")
        self.assertEqual(memory.status(self.root)["adr"]["review"], [])
        commit_file(self.repo, "apps/api/queue.py", "fix: queue again")
        self.assertEqual(memory.status(self.root)["adr"]["review"], ["0001-fila-de-eventos"])
        memory.anchor(self.root, "adr", "0001-fila-de-eventos", ["apps/api/queue.py"])
        self.assertEqual(memory.status(self.root)["adr"]["review"], [])

    def test_anchor_refuses_unknown_keys_and_paths(self):
        for kind, key, paths in (("glossary", "Inexistente", ["apps/api/staff.py"]),
                                 ("adr", "9999-nada", ["apps/api/staff.py"]),
                                 ("glossary", "Agendamento", ["nao/existe.py"]),
                                 ("glossary", "Agendamento", ["../fora"]),
                                 ("glossary", "Agendamento", []),
                                 ("outro", "Agendamento", ["apps/api/staff.py"])):
            with self.assertRaises(ValueError, msg=(kind, key, paths)):
                memory.anchor(self.root, kind, key, paths)

    def test_author_files_are_never_modified(self):
        before = (self.repo / "GLOSSARY.md").read_text()
        memory.anchor(self.root, "glossary", "Agendamento", ["apps/api/booking.py"])
        memory.status(self.root)
        self.assertEqual((self.repo / "GLOSSARY.md").read_text(), before)
        self.assertEqual(git(self.repo, "status", "--short"), "")

    def test_project_without_glossary_or_adrs(self):
        state = memory.status(str(make_repo()))
        self.assertEqual(state["glossary"], {"gone": [], "unanchored": []})
        self.assertEqual(state["adr"], {"review": [], "unanchored": []})

    def test_cli(self):
        run = lambda *a: subprocess.run([SCRIPT, *a], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(run("anchor", "glossary", "Agendamento", "apps/api/booking.py").returncode, 0)
        self.assertIn("Agendamento", run("anchors").stdout)
        self.assertEqual(run("anchor", "glossary", "Nada", "apps/api/booking.py").returncode, 1)
        out = run("check").stdout
        self.assertIn("Encaixe", out)
        self.assertIn("sem âncora", out)
        git(self.repo, "rm", "-q", "apps/api/booking.py")
        commit_all(self.repo, "refactor: drop booking")
        r = run("check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("glossário: Agendamento", r.stdout)

    def test_unanchored_alone_does_not_fail_the_check(self):
        repo = make_repo()
        (repo / "GLOSSARY.md").write_text(GLOSSARY)
        commit_all(repo, "docs: glossary")
        (repo / "r.md").write_text("Raiz.\n")
        subprocess.run([SCRIPT, "record", ".", "r.md"], cwd=repo, check=True, capture_output=True)
        (repo / "r.md").unlink()
        r = subprocess.run([SCRIPT, "check"], cwd=repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("sem âncora", r.stdout)


if __name__ == "__main__":
    unittest.main()
