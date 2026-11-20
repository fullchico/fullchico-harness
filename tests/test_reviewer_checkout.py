"""Revisor lê e roda; não muda de commit o worktree da feature, que é de todos."""
import unittest

from tests.helpers import make_repo, run_hook, sync


class TestReviewerKeepsTheCheckout(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)

    def bash(self, command, agent="harness:revisor-bugs"):
        payload = {"tool_name": "Bash", "cwd": str(self.repo), "tool_input": {"command": command}}
        if agent:
            payload["agent_type"] = agent
        return run_hook("service_guard.py", payload)

    def test_reviewers_cannot_move_the_feature_worktree(self):
        for agent in ("harness:revisor-bugs", "harness:revisor", "harness:seguranca", "harness:qualidade", "harness:revisor-spec"):
            for command in ("git checkout abc1234", "git switch --detach abc1234", "cd apps && git checkout -q abc1234 && pnpm test",
                            "git reset --hard abc1234", "git stash", "git restore .", "git -C . checkout abc1234"):
                rc, _, err = self.bash(command, agent)
                self.assertEqual(rc, 2, f"{agent}: {command}")
                self.assertIn("git worktree list", err)

    def test_reading_is_free(self):
        for command in ("git diff a...b", "git show abc1234:src/a.ts", "git log --oneline -5", "git worktree list",
                        "pnpm test", "grep -rn checkout src"):
            self.assertEqual(self.bash(command)[0], 0, command)

    def test_other_agents_and_the_owner_are_not_affected(self):
        for agent in ("harness:implementador", "harness:orquestrador", None):
            self.assertEqual(self.bash("git checkout -b feat/x", agent)[0], 0, str(agent))
