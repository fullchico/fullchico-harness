"""Barreira por sandbox: o estado dos portões mora onde o Bash do agente não escreve,
e o que o push decide vem do remoto de verdade, não de referências locais."""
import json
import os
import pwd
import subprocess
import sys
import unittest

from tests.helpers import (ROOT, clone_repo, commit_all, commit_file, git, make_repo, owner_approve,
                           run_hook, sync)
import common

HOME = pwd.getpwuid(os.getuid()).pw_dir


def ask_review(repo, agent, diff=None):
    """Passa pelo dispatch_guard como o elefante faria; devolve o código de saída."""
    sha = git(repo, "rev-parse", "HEAD")
    diff = diff or f"{common.branch_base(str(repo), sha)}...HEAD"
    return run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(repo), "tool_input": {
        "subagent_type": agent, "prompt": f"diff: {diff}\ncommit: {sha}"}})[0]


def reviewer_approves(repo, agent):
    sha = git(repo, "rev-parse", "HEAD")
    return run_hook("gate_stamp.py", {"agent_type": agent, "cwd": str(repo),
                                      "last_assistant_message": f"VEREDITO: APPROVED\nCOMMIT: {sha}\nRESUMO: ok"})[0]


class TestStateLocation(unittest.TestCase):
    def test_state_lives_under_claude_home_not_in_the_repo(self):
        repo = make_repo()
        state = common.state_dir(str(repo))
        self.assertTrue(state.startswith(os.path.join(HOME, ".claude", "harness") + os.sep), state)
        self.assertNotIn(str(repo), state)

    def test_state_is_shared_between_worktrees_and_distinct_between_repos(self):
        repo = make_repo()
        wt = repo.parent / "wt two"
        git(repo, "worktree", "add", "-q", "--detach", str(wt))
        self.assertEqual(common.state_dir(str(repo)), common.state_dir(str(wt)))
        self.assertNotEqual(common.state_dir(str(repo)), common.state_dir(str(make_repo())))

    def test_spoofed_home_does_not_move_the_state(self):
        repo = make_repo()
        expected = common.state_dir(str(repo))
        r = subprocess.run([sys.executable, str(ROOT / "plugin/payload/hooks/common.py"), "state-dir"],
                           cwd=repo, env=dict(os.environ, HOME="/tmp/fake-home"), capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), expected)

    def test_hook_dispatchers_live_in_the_state_dir(self):
        repo = make_repo()
        sync(repo)
        hooks = git(repo, "config", "core.hooksPath")
        self.assertEqual(hooks, os.path.join(common.state_dir(str(repo)), "git-hooks"))
        self.assertTrue(os.access(os.path.join(hooks, "pre-push"), os.X_OK))


class TestSandboxSettings(unittest.TestCase):
    def test_generated_settings_turn_the_sandbox_on(self):
        repo = make_repo()
        sync(repo)
        sandbox = json.loads((repo / ".claude/settings.json").read_text())["sandbox"]
        self.assertIs(sandbox["enabled"], True)
        self.assertIs(sandbox["failIfUnavailable"], True)
        self.assertIs(sandbox["allowUnsandboxedCommands"], False)
        for path in (".harness", "harness.conf", "harness.d", "CLAUDE.md", "docs/agents"):
            self.assertIn(path, sandbox["filesystem"]["denyWrite"])

    def test_fragment_cannot_turn_the_sandbox_off(self):
        repo = make_repo()
        (repo / "harness.d").mkdir()
        (repo / "harness.d/settings.json").write_text(json.dumps(
            {"sandbox": {"enabled": False, "allowUnsandboxedCommands": True,
                         "filesystem": {"denyWrite": [], "allowWrite": ["build"]}}}))
        sync(repo)
        sandbox = json.loads((repo / ".claude/settings.json").read_text())["sandbox"]
        self.assertIs(sandbox["enabled"], True)
        self.assertIs(sandbox["allowUnsandboxedCommands"], False)
        self.assertIn(".harness", sandbox["filesystem"]["denyWrite"])
        self.assertEqual(sandbox["filesystem"]["allowWrite"], ["build"])


class TestServiceGuardIsNarrow(unittest.TestCase):
    """Escrita é com o sandbox. O guard de texto só cuida do que não é escrita."""

    def bash(self, command):
        return run_hook("service_guard.py", {"tool_name": "Bash", "cwd": str(self.repo),
                                             "tool_input": {"command": command}})[0]

    def setUp(self):
        self.repo = make_repo()

    def test_everyday_commands_pass(self):
        for c in ["grep -rn harness.conf plugin/",
                  'git commit -m "docs: document .harness/ layout"',
                  'git commit -m "fix: husky=0 was breaking CI"',
                  'echo "see .claude/settings.json for hooks" >> notes.txt',
                  "cat .harness/MANIFEST", "ls -la .harness", 'find . -name "harness.d"',
                  "docker compose up -d", "pnpm install && pnpm test"]:
            self.assertEqual(self.bash(c), 0, c)

    def test_hook_skipping_is_still_denied(self):
        for c in ["git push --no-verify", "bash -c 'git push --no-verify origin x'",
                  "git -c core.hooksPath=/dev/null push", "git -c core.hookspath=/dev/null push",
                  "git push --no-verif"]:
            self.assertEqual(self.bash(c), 2, c)


class TestPushUsesTheRealRemote(unittest.TestCase):
    def setUp(self):
        self.origin = make_repo("origin dir")
        git(self.origin, "branch", "-m", "trunk")
        self.repo = clone_repo(self.origin)
        git(self.repo, "remote", "set-head", "origin", "-d")
        self.assertEqual(sync(self.repo).returncode, 0)
        commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "feat/x")

    def push(self, ref="feat/x"):
        return subprocess.run(["git", "push", "-q", "origin", ref], cwd=self.repo, capture_output=True, text=True)

    def review(self):
        for agent in ("harness:seguranca", "harness:revisor"):
            self.assertEqual(ask_review(self.repo, agent), 0)
            reviewer_approves(self.repo, agent)

    def test_default_branch_comes_from_the_remote(self):
        commit_file(self.repo, "a.txt", "fix: a")
        for g in ("seguranca", "revisao"):
            owner_approve(self.repo, g)
        r = self.push()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_reviewed_branch_passes(self):
        commit_file(self.repo, "a.txt", "fix: a")
        self.review()
        r = self.push()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_forged_remote_ref_does_not_let_a_tag_through(self):
        commit_file(self.repo, "a.txt", "feat: unreviewed")
        git(self.repo, "update-ref", "refs/remotes/origin/fake", "HEAD")
        git(self.repo, "tag", "evilrel")
        r = self.push("evilrel")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("seguranca", r.stderr)

    def test_tag_on_commit_really_on_the_remote_passes(self):
        git(self.repo, "tag", "v0", "origin/trunk")
        self.assertEqual(self.push("v0").returncode, 0)

    def test_forged_default_branch_does_not_empty_the_spec_lock(self):
        commit_file(self.repo, "a.txt", "feat: no spec")
        for g in ("seguranca", "revisao"):
            owner_approve(self.repo, g)
        git(self.repo, "update-ref", "refs/remotes/origin/trunk", "HEAD")
        git(self.repo, "update-ref", "refs/remotes/origin/HEAD", "HEAD")
        r = self.push()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("docs/specs", r.stderr)

    def forge_local_default_branch(self):
        """O agente move as referências locais da branch padrão para esconder o primeiro commit."""
        git(self.repo, "update-ref", "refs/remotes/origin/trunk", "HEAD~1")
        git(self.repo, "update-ref", "refs/remotes/origin/HEAD", "HEAD~1")

    def test_partial_review_request_is_denied_when_the_remote_answers(self):
        commit_file(self.repo, "a.txt", "fix: a")
        commit_file(self.repo, "b.txt", "fix: b")
        self.forge_local_default_branch()
        self.assertEqual(ask_review(self.repo, "harness:revisor", diff="HEAD~1...HEAD"), 2)

    def test_partial_review_made_offline_does_not_approve_the_branch(self):
        commit_file(self.repo, "a.txt", "fix: a")
        commit_file(self.repo, "b.txt", "fix: b")
        self.forge_local_default_branch()
        url = git(self.repo, "remote", "get-url", "origin")
        git(self.repo, "remote", "set-url", "origin", "/nao/existe")
        for agent in ("harness:seguranca", "harness:revisor"):
            self.assertEqual(ask_review(self.repo, agent, diff="HEAD~1...HEAD"), 0)
            reviewer_approves(self.repo, agent)
        git(self.repo, "remote", "set-url", "origin", url)
        r = self.push()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("revis", r.stderr)


if __name__ == "__main__":
    unittest.main()
