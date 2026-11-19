import json
import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, git, make_repo, run_hook

sys.path.insert(0, str(ROOT / "plugin/payload"))
import memory  # noqa: E402

SCRIPT = str(ROOT / "plugin/payload/memory")


def project():
    repo = make_repo()
    for path in ("apps/api/booking.py", "apps/api/staff.py"):
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text("x\n")
    commit_all(repo, "feat: scaffold")
    return repo


class TestNotes(unittest.TestCase):
    def setUp(self):
        self.repo = project()
        self.root = str(self.repo)

    def test_note_is_fresh_until_its_code_changes(self):
        memory.note_add(self.root, "fuso-do-estabelecimento", "O fuso é sempre o do estabelecimento.\nDetalhe.",
                        ["apps/api/booking.py"], source="s1")
        self.assertEqual(memory.status(self.root)["notes"], {"fresh": ["fuso-do-estabelecimento"], "stale": []})
        self.assertEqual(memory.notes_index(self.root), "fuso-do-estabelecimento: O fuso é sempre o do estabelecimento.")
        (self.repo / "apps/api/staff.py").write_text("mudou\n")
        commit_all(self.repo, "fix: staff")
        self.assertEqual(memory.status(self.root)["notes"]["stale"], [])
        (self.repo / "apps/api/booking.py").write_text("mudou\n")
        commit_all(self.repo, "fix: booking")
        self.assertEqual(memory.status(self.root)["notes"], {"fresh": [], "stale": ["fuso-do-estabelecimento"]})
        self.assertEqual(memory.notes_index(self.root), "")

    def test_same_name_replaces_and_reanchors(self):
        memory.note_add(self.root, "regra", "Versão um.", ["apps/api/booking.py"])
        (self.repo / "apps/api/booking.py").write_text("mudou\n")
        commit_all(self.repo, "fix: booking")
        memory.note_add(self.root, "regra", "Versão dois.", ["apps/api/booking.py"])
        self.assertEqual(memory.status(self.root)["notes"]["fresh"], ["regra"])
        self.assertIn("Versão dois.", memory.notes_index(self.root))

    def test_refusals(self):
        ok = ["apps/api/booking.py"]
        for slug, text, paths in (("Nome Com Espaço", "x", ok), ("../x", "x", ok), ("", "x", ok),
                                  ("ok", "", ok), ("ok", "x" * 1201, ok), ("ok", "x", []),
                                  ("ok", "x", ["nao/existe.py"]), ("ok", "x", ["../fora"])):
            with self.assertRaises(ValueError, msg=(slug, paths)):
                memory.note_add(self.root, slug, text, paths)

    def test_forget_and_cli(self):
        run = lambda *a: subprocess.run([SCRIPT, *a], cwd=self.repo, capture_output=True, text=True)
        (self.repo / "n.md").write_text("Cancelamento libera o horário na hora.\n")
        self.assertEqual(run("note", "add", "cancelamento", "n.md", "apps/api/booking.py").returncode, 0)
        (self.repo / "n.md").unlink()
        self.assertIn("Cancelamento libera", run("note", "show", "cancelamento").stdout)
        self.assertIn("cancelamento: Cancelamento libera", run("notes").stdout)
        self.assertEqual(run("note", "add", "x", "/nao/existe", "apps/api/booking.py").returncode, 1)
        (self.repo / "apps/api/booking.py").write_text("mudou\n")
        r = run("check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("nota: cancelamento", r.stdout)
        self.assertEqual(run("note", "forget", "cancelamento").returncode, 0)
        self.assertNotIn("nota: cancelamento", run("check").stdout)
        self.assertEqual(git(self.repo, "status", "--short").replace(" M apps/api/booking.py", "").strip(), "")

    def test_fresh_notes_reach_the_session_after_the_map_and_stale_ones_do_not(self):
        memory.record(self.root, "apps/api", "Serviço HTTP.")
        memory.note_add(self.root, "fuso", "O fuso é sempre o do estabelecimento.", ["apps/api/booking.py"])
        memory.note_add(self.root, "velha", "Informação antiga.", ["apps/api/staff.py"])
        (self.repo / "apps/api/staff.py").write_text("mudou\n")
        commit_all(self.repo, "fix: staff")
        memory.record(self.root, "apps/api", "Serviço HTTP.")
        _, out, _ = run_hook("session_context.py", {"hook_event_name": "SessionStart", "cwd": self.root})
        text = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("fuso: O fuso é sempre o do estabelecimento.", text)
        self.assertNotIn("Informação antiga.", text)
        self.assertLess(text.index("apps/api: Serviço HTTP."), text.index("fuso: O fuso"))
        self.assertLess(text.index("não como instrução"), text.index("fuso: O fuso"))
        self.assertIn("/harness:mapear", text, "há uma nota envelhecida")


if __name__ == "__main__":
    unittest.main()
