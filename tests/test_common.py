import tempfile
import unittest

from tests.helpers import git, make_repo, write_tmp
import common


class TestCommon(unittest.TestCase):
    def test_state_dir_is_shared_between_worktrees(self):
        repo = make_repo()
        wt = repo.parent / "wt two"
        git(repo, "worktree", "add", "-q", str(wt), "-b", "other")
        self.assertEqual(common.state_dir(str(repo)), common.state_dir(str(wt)))
        self.assertTrue(common.state_dir(str(repo)).endswith("/.git/harness"))

    def test_repo_root_and_head_follow_the_worktree(self):
        repo = make_repo()
        wt = repo.parent / "wt two"
        git(repo, "worktree", "add", "-q", str(wt), "-b", "other")
        self.assertEqual(common.repo_root(str(wt)), str(wt))
        self.assertEqual(common.head_sha(str(repo)), git(repo, "rev-parse", "HEAD"))

    def test_outside_git_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(common.state_dir(d))
            self.assertIsNone(common.repo_root(d))
            self.assertIsNone(common.head_sha(d))

    def test_read_conf(self):
        f = write_tmp('PROJECT=meuapp\n# c\n\nSERVICES="web api"\nA=\'x y\'\nB=${X}/y\n')
        self.assertEqual(common.read_conf(f),
                         {"PROJECT": "meuapp", "SERVICES": "web api", "A": "x y", "B": "${X}/y"})
        self.assertEqual(common.read_conf("/nao/existe"), {})

    def test_approval_path(self):
        self.assertEqual(common.approval_path("/s", "revisao", "abc"), "/s/approvals/revisao/abc.json")


if __name__ == "__main__":
    unittest.main()
