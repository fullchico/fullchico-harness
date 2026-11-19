import subprocess
import unittest

from tests.helpers import ROOT, clone_repo, commit_all, commit_file, git, make_repo, sync, write_tmp

COMMIT_MSG = str(ROOT / "plugin/payload/git-hooks/commit-msg")


class TestCommitMsg(unittest.TestCase):
    def check(self, text):
        return subprocess.run([COMMIT_MSG, write_tmp(text)], capture_output=True).returncode

    def test_accepts(self):
        for m in ["feat(api): add booking endpoint",
                  "fix: keep notes multiline\n\nLong body explaining why.\n",
                  "feat!: drop legacy auth",
                  "refactor(web/ui): split panel",
                  "# comentário do git\nfix: a",
                  "Merge branch 'x' into y",
                  'Revert "feat: x"',
                  "fix: " + "x" * 75]:
            self.assertEqual(self.check(m), 0, m)

    def test_rejects(self):
        for m in ["add stuff", "feature: x", "feat:sem espaço", "Feat: x", "",
                  "feat: " + "x" * 80,
                  "fix: a\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
                  "fix: a\n\nco-authored-by: GPT <x@openai.com>",
                  "fix: a\n\n🤖 Generated with Claude Code",
                  "fix: a\n\nGenerated with some tool"]:
            self.assertEqual(self.check(m), 1, m)

    def test_human_coauthor_is_allowed(self):
        self.assertEqual(self.check("fix: a\n\nCo-authored-by: Maria <maria@example.com>"), 0)

    def test_rejection_explains_itself(self):
        r = subprocess.run([COMMIT_MSG, write_tmp("add stuff")], capture_output=True, text=True)
        self.assertIn("tipo(escopo): descrição", r.stderr)


class TestPrePush(unittest.TestCase):
    def setUp(self):
        self.origin = make_repo("origin dir")
        self.repo = clone_repo(self.origin)
        self.assertEqual(sync(self.repo).returncode, 0)
        commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "feat/x")

    def push(self, ref="feat/x"):
        return subprocess.run(["git", "push", "-q", "origin", ref], cwd=self.repo, capture_output=True, text=True)

    def approve_both(self):
        for g in ("seguranca", "revisao"):
            subprocess.run([str(self.repo / ".harness/approve"), g, "ok"], cwd=self.repo,
                           check=True, capture_output=True)

    def test_push_without_approvals_is_denied(self):
        commit_file(self.repo, "a.txt", "fix: a")
        r = self.push()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("seguranca", r.stderr)
        self.assertIn("revisao", r.stderr)

    def test_one_approval_is_not_enough(self):
        commit_file(self.repo, "a.txt", "fix: a")
        subprocess.run([str(self.repo / ".harness/approve"), "seguranca", "ok"], cwd=self.repo,
                       check=True, capture_output=True)
        r = self.push()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("revisao", r.stderr)
        self.assertNotIn("falta a aprovação de seguranca", r.stderr)

    def test_fix_with_both_approvals_passes(self):
        commit_file(self.repo, "a.txt", "fix: a")
        self.approve_both()
        r = self.push()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git(self.origin, "rev-parse", "feat/x"), git(self.repo, "rev-parse", "HEAD"))

    def test_new_commit_invalidates_approvals(self):
        commit_file(self.repo, "a.txt", "fix: a")
        self.approve_both()
        commit_file(self.repo, "b.txt", "fix: b")
        self.assertNotEqual(self.push().returncode, 0)

    def test_feat_requires_spec_in_branch(self):
        commit_file(self.repo, "a.txt", "feat(api): add booking")
        self.approve_both()
        r = self.push()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("docs/specs", r.stderr)
        commit_file(self.repo, "docs/specs/booking/spec.md", "docs: add booking spec")
        self.approve_both()
        self.assertEqual(self.push().returncode, 0)

    def test_spec_in_wrong_place_does_not_count(self):
        commit_file(self.repo, "docs/specs/spec.md", "docs: misplaced spec")
        commit_file(self.repo, "a.txt", "feat!: add booking")
        self.approve_both()
        self.assertNotEqual(self.push().returncode, 0)

    def test_second_push_of_same_feat_branch_is_not_blocked_by_spec(self):
        commit_file(self.repo, "docs/specs/booking/spec.md", "docs: add booking spec")
        commit_file(self.repo, "a.txt", "feat: add booking")
        self.approve_both()
        self.assertEqual(self.push().returncode, 0)
        commit_file(self.repo, "b.txt", "feat: add cancel")
        self.approve_both()
        r = self.push()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_validate_push_command_blocks(self):
        (self.repo / "harness.conf").write_text('VALIDATE_PUSH="exit 3"\n')
        commit_all(self.repo, "chore: set validation")
        self.approve_both()
        self.assertNotEqual(self.push().returncode, 0)

    def test_validate_push_command_runs_in_repo_root(self):
        (self.repo / "harness.conf").write_text('VALIDATE_PUSH="test -f README.md && test -d .harness"\n')
        commit_all(self.repo, "chore: set validation")
        self.approve_both()
        r = self.push()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_manifest_drift_blocks(self):
        (self.repo / "CLAUDE.md").write_text("mexi\n")
        commit_all(self.repo, "chore: x")
        self.approve_both()
        r = self.push()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("CLAUDE.md", r.stderr + r.stdout)

    def test_new_branch_without_origin_head(self):
        git(self.repo, "remote", "set-head", "origin", "-d")
        commit_file(self.repo, "a.txt", "feat: a")
        self.approve_both()
        r = self.push()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("docs/specs", r.stderr)
        commit_file(self.repo, "b.txt", "fix: b")
        git(self.repo, "reset", "-q", "--hard", "HEAD~2")
        commit_file(self.repo, "c.txt", "fix: c")
        self.approve_both()
        self.assertEqual(self.push().returncode, 0)

    def test_tag_push_is_ignored(self):
        git(self.repo, "tag", "v0")
        self.assertEqual(self.push("v0").returncode, 0)

    def test_branch_delete_is_ignored(self):
        commit_file(self.repo, "a.txt", "fix: a")
        self.approve_both()
        self.assertEqual(self.push().returncode, 0)
        self.assertEqual(self.push(":feat/x").returncode, 0)

    def test_approval_from_another_worktree_counts(self):
        commit_file(self.repo, "a.txt", "fix: a")
        wt = self.repo.parent / "wt two"
        git(self.repo, "worktree", "add", "-q", "--detach", str(wt))
        for g in ("seguranca", "revisao"):
            subprocess.run([str(wt / ".harness/approve"), g, "ok"], cwd=wt, check=True, capture_output=True)
        self.assertEqual(self.push().returncode, 0)


class TestValidate(unittest.TestCase):
    def test_profiles(self):
        repo = make_repo()
        sync(repo)
        v = str(repo / ".harness/validate")
        run = lambda *a: subprocess.run([v, *a], cwd=repo, capture_output=True, text=True).returncode
        self.assertEqual(run("--profile", "push"), 0)
        (repo / "harness.conf").write_text('VALIDATE_PUSH="exit 0"\nVALIDATE_MERGE="exit 4"\n')
        self.assertEqual(run("--profile", "push"), 0)
        self.assertEqual(run("--profile", "merge"), 4)
        self.assertEqual(run("--profile", "outro"), 2)
        self.assertEqual(run(), 2)


if __name__ == "__main__":
    unittest.main()
