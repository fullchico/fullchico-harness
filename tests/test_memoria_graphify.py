"""Índice grafo local e reconstruível da memória compartilhada."""
import os
import json
import subprocess
import sys
import unittest

from tests.helpers import ROOT, _tmpdir, commit_all, git, make_repo

PLUGIN = ROOT / "plugins/memoria"
sys.path.insert(0, str(PLUGIN / "scripts"))
import graphify  # noqa: E402
import memory  # noqa: E402


class TestGraphify(unittest.TestCase):
    def setUp(self):
        self.home = _tmpdir()
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self.addCleanup(self._restore_home)
        self.repo = make_repo()
        (self.repo / "apps/api").mkdir(parents=True)
        (self.repo / "apps/api/booking.py").write_text("def reserve(): pass\n")
        (self.repo / "apps/web").mkdir(parents=True)
        (self.repo / "apps/web/page.tsx").write_text("export const page = 1\n")
        commit_all(self.repo, "feat: scaffold")
        memory.record(str(self.repo), "apps/api", "Agendamento usa a janela de disponibilidade.")
        memory.note_add(str(self.repo), "fuso-agendamento", "O horário é interpretado no fuso do salão.",
                        ["apps/api/booking.py"], source="codex")

    def _restore_home(self):
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home

    def test_search_returns_note_and_path_reference(self):
        results = graphify.search(str(self.repo), "fuso salão booking.py")
        self.assertTrue(results)
        note = next(result for result in results if result["id"] == "note:fuso-agendamento")
        self.assertEqual(note["source"], "codex")
        self.assertIn("apps/api/booking.py", note["refs"])
        self.assertEqual(note["commit"], git(self.repo, "rev-parse", "HEAD"))

    def test_query_by_path_reaches_referencing_memory(self):
        results = graphify.search(str(self.repo), "apps/api/booking.py")
        self.assertIn("note:fuso-agendamento", [result["id"] for result in results])

    def test_index_is_stored_in_common_git_dir_not_worktree(self):
        fake_bin = self.home / "bin"
        fake_bin.mkdir()
        fake = fake_bin / "graphify"
        fake.write_text("#!" + sys.executable + "\n"
                        "import json, os, pathlib, sys\n"
                        "p = pathlib.Path(os.environ['GRAPHIFY_OUT'])\n"
                        "p.mkdir(parents=True, exist_ok=True)\n"
                        "(p / 'invocation.json').write_text(json.dumps({'args': sys.argv[1:], 'backend': os.environ.get('GRAPHIFY_BACKEND')}))\n")
        fake.chmod(0o755)
        original_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(fake_bin) + os.pathsep + original_path
        self.addCleanup(lambda: os.environ.__setitem__("PATH", original_path))
        result = subprocess.run([str(PLUGIN / "bin/memoria"), "graph", "rebuild"], cwd=self.repo,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        common_dir = git(self.repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
        self.assertTrue(os.path.isfile(os.path.join(common_dir, "harness-memory", "graphify.json")))
        out = os.path.join(common_dir, "harness-memory", "graphify-out")
        with open(os.path.join(out, "invocation.json"), encoding="utf-8") as stream:
            invocation = json.load(stream)
        self.assertEqual(invocation["args"], ["update", str(self.repo)])
        self.assertEqual(invocation["backend"], "none")
        self.assertNotIn("graphify", git(self.repo, "status", "--porcelain"))

    def test_no_match_is_empty_and_safe(self):
        self.assertEqual(graphify.search(str(self.repo), ""), [])
        self.assertEqual(graphify.search(str(self.repo), "xyzzynotfound"), [])


if __name__ == "__main__":
    unittest.main()
