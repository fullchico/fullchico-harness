"""Worktrees de agente já integrados são removidos por um comando só."""
import subprocess
import unittest

from tests.helpers import commit_all, git, make_repo, sync


class TestAgentsClean(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        commit_all(self.repo, "chore: adopt harness")
        self.feature = self.repo.parent / "feat dir"
        git(self.repo, "worktree", "add", "-q", "-b", "feat/x", str(self.feature))

    def agent(self, name, commit=True):
        path = self.repo / ".claude/worktrees" / name
        git(self.feature, "worktree", "add", "-q", "-b", f"worktree-{name}", str(path), "HEAD")
        (path / ".env").write_text("X=1\n")  # arquivo não versionado, como num worktree real
        if commit:
            (path / f"{name}.txt").write_text("x\n")
            commit_all(path, f"feat: {name}")
        return path

    def clean(self):
        return subprocess.run([str(self.feature / ".harness/agents-clean")], cwd=self.feature,
                              capture_output=True, text=True)

    def test_merged_agents_go_and_unmerged_or_locked_stay(self):
        merged, pending, locked = self.agent("agent-a"), self.agent("agent-b"), self.agent("agent-c")
        git(self.feature, "merge", "-q", "--no-ff", "worktree-agent-a", "-m", "Merge a")
        git(self.feature, "merge", "-q", "--no-ff", "worktree-agent-c", "-m", "Merge c")
        git(self.repo, "worktree", "lock", str(locked))
        r = self.clean()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(merged.exists())
        self.assertTrue(pending.exists(), "trabalho ainda não integrado não se apaga")
        self.assertTrue(locked.exists(), "agente ainda rodando")
        branches = git(self.repo, "branch", "--list", "worktree-*")
        self.assertNotIn("worktree-agent-a", branches)
        self.assertIn("worktree-agent-b", branches)
        self.assertIn("agent-a", r.stdout)
        self.assertIn("agent-b", r.stdout)  # avisa o que ficou

    def test_nothing_to_do(self):
        self.assertEqual(self.clean().returncode, 0)

    def test_never_touches_a_feature_worktree(self):
        self.clean()
        self.assertTrue(self.feature.exists())


if __name__ == "__main__":
    unittest.main()


class TestSupersededAfterDelivery(unittest.TestCase):
    """Depois do envio, a branch recusada e refeita não serve mais: sobrava no repositório."""

    def test_only_this_features_leftovers_are_removed(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        commit_all(repo, "chore: adopt harness")
        feature = repo.parent / "feat dir"
        git(repo, "worktree", "add", "-q", "-b", "feat/x", str(feature))
        (feature / "a.txt").write_text("a\n")
        commit_all(feature, "feat: a")
        mine = repo / ".claude/worktrees/agent-mine"
        git(feature, "worktree", "add", "-q", "-b", "worktree-agent-mine", str(mine), "HEAD")
        (mine / "recusado.txt").write_text("x\n")
        commit_all(mine, "feat: refused attempt")
        other = repo / ".claude/worktrees/agent-other"  # de outra feature, saída direto da branch padrão
        git(repo, "worktree", "add", "-q", "-b", "worktree-agent-other", str(other), "HEAD")
        (other / "outro.txt").write_text("y\n")
        commit_all(other, "feat: other feature work")
        r = subprocess.run([str(feature / ".harness/agents-clean"), "--superseded"], cwd=feature, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(mine.exists())
        self.assertTrue(other.exists(), "worktree de agente de outra feature não é desta entrega")
        self.assertTrue(feature.exists())
