"""Achados menores das revisões adversariais, cada um com o teste que o reproduz."""
import os
import subprocess
import sys
import unittest

from tests.helpers import (ROOT, clone_repo, clone_self_with_tags, commit_all, commit_file, git, make_repo,
                           owner_approve, run_hook, sync, write_tmp)

PAYLOAD = ROOT / "plugin/payload"
DOC = "# Proj\n\nlivre\n\n<!-- harness:begin -->\nregra 1\n<!-- harness:end -->\n"


class TestSpecLock(unittest.TestCase):
    def test_deleting_a_spec_does_not_count_as_bringing_one(self):
        origin = make_repo("origin dir")
        commit_file(origin, "docs/specs/old/spec.md", "docs: old spec")
        repo = clone_repo(origin)
        self.assertEqual(sync(repo).returncode, 0)
        commit_all(repo, "chore: adopt harness")
        git(repo, "checkout", "-q", "-b", "feat/x")
        git(repo, "rm", "-q", "docs/specs/old/spec.md")
        commit_all(repo, "feat: add booking")
        for gate in ("seguranca", "revisao"):
            owner_approve(repo, gate)
        r = subprocess.run([str(repo / ".harness/push")], cwd=repo,
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("docs/specs", r.stderr)


class TestManifestExtras(unittest.TestCase):
    def test_file_planted_in_harness_folder_is_drift(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        check = [sys.executable, "-I", str(repo / ".harness/manifest_check.py"), str(repo)]
        self.assertEqual(subprocess.run(check, capture_output=True).returncode, 0)
        (repo / ".harness/hooks/extra.py").write_text("print('oi')\n")
        r = subprocess.run(check, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn(".harness/hooks/extra.py", r.stdout)


class TestUpdateWantsATag(unittest.TestCase):
    def test_branch_name_is_refused(self):
        up = clone_self_with_tags("up stream", {"v0.1.0": None})
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        commit_all(repo, "chore: adopt harness")
        env = dict(os.environ, HARNESS_REPO=f"file://{up}", HARNESS_SKIP_PLUGIN="1")
        r = subprocess.run([str(repo / ".harness/update"), "main"], cwd=repo, env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("tag", r.stderr)
        self.assertEqual(git(repo, "status", "--short"), "")


class TestCommitSignature(unittest.TestCase):
    def check(self, text):
        return subprocess.run([str(PAYLOAD / "git-hooks/commit-msg"), write_tmp(text)], capture_output=True).returncode

    def test_the_words_in_the_middle_of_a_sentence_are_fine(self):
        self.assertEqual(self.check("fix: a\n\nThe fixture is generated with the seed script.\n"), 0)

    def test_signature_lines_are_still_refused(self):
        for body in ("Generated with Claude Code", "🤖 Generated with [Claude Code](https://claude.com)",
                     "  generated with some tool"):
            self.assertEqual(self.check("fix: a\n\n" + body + "\n"), 1, body)


class TestProjectFragment(unittest.TestCase):
    def test_invalid_fragment_is_explained_without_traceback(self):
        for content in ("{ não é json", '["lista"]'):
            repo = make_repo()
            (repo / "harness.d").mkdir()
            (repo / "harness.d/settings.json").write_text(content)
            r = sync(repo)
            self.assertNotEqual(r.returncode, 0, content)
            self.assertIn("harness.d/settings.json", r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertFalse((repo / ".harness").exists(), "nada pode ser gravado")


class TestManagedGuardCase(unittest.TestCase):
    def test_other_spelling_of_the_same_file_is_guarded(self):
        repo = make_repo()
        (repo / "AGENTS.md").write_text(DOC)
        if not (repo / "agents.md").exists():
            self.skipTest("sistema de arquivos distingue maiúsculas")
        rc = run_hook("managed_guard.py", {"tool_name": "Edit", "cwd": str(repo), "tool_input": {
            "file_path": str(repo / "agents.md"), "old_string": "regra 1", "new_string": "regra 2"}})[0]
        self.assertEqual(rc, 2)


class TestDevPid(unittest.TestCase):
    def pid(self, content):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        (repo / ".harness-run").mkdir(exist_ok=True)
        (repo / ".harness-run/dev.pid").write_text(content)
        # $0 precisa estar em .harness/ para o trecho comum achar a raiz.
        return subprocess.run(["bash", "-c", f'cd "$1" && . .harness/env-common.sh; dev_pid', str(repo / ".harness/x"),
                               str(repo)], capture_output=True, text=True)

    def test_only_a_positive_number_is_a_pid(self):
        for content in ("-1\n", "0\n", "abc\n", "12 34\n", ""):
            r = self.pid(content)
            self.assertNotEqual(r.returncode, 0, repr(content))
            self.assertEqual(r.stdout.strip(), "")

    def test_live_pid_is_returned(self):
        r = self.pid(f"{os.getpid()}\n")
        self.assertEqual(r.stdout.strip(), str(os.getpid()))


if __name__ == "__main__":
    unittest.main()
