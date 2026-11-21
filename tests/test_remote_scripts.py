"""O remoto só é alcançado pelos scripts do harness, que rodam fora do sandbox."""
import json
import os
import subprocess
import unittest

from tests.helpers import (ROOT, _tmpdir, clone_repo, commit_all, commit_file, git, make_repo, owner_approve,
                           sync)


class RemoteCase(unittest.TestCase):
    def setUp(self):
        self.origin = make_repo("origin dir")
        self.repo = clone_repo(self.origin)
        self.assertEqual(sync(self.repo).returncode, 0)
        commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "feat/x")

    def script(self, name, *args, **extra):
        return subprocess.run([str(self.repo / ".harness" / name), *args], cwd=self.repo,
                              env=dict(os.environ, **extra), capture_output=True, text=True)

    def approve(self):
        for gate in ("seguranca", "revisao", "qualidade", "bugs"):
            self.assertEqual(owner_approve(self.repo, gate).returncode, 0)

    def remote_tip(self, branch="feat/x"):
        r = subprocess.run(["git", "rev-parse", "-q", "--verify", branch], cwd=self.origin,
                           capture_output=True, text=True)
        return r.stdout.strip()


class TestPush(RemoteCase):
    def test_push_without_approvals_is_denied(self):
        commit_file(self.repo, "a.txt", "fix: a")
        r = self.script("push")
        self.assertEqual(r.returncode, 1)
        self.assertIn("seguranca", r.stderr)
        self.assertEqual(self.remote_tip(), "")

    def test_push_with_approvals_reaches_the_remote(self):
        sha = commit_file(self.repo, "a.txt", "fix: a")
        self.approve()
        r = self.script("push")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.remote_tip(), sha)

    def test_feat_without_spec_is_denied(self):
        commit_file(self.repo, "a.txt", "feat: no spec")
        self.approve()
        r = self.script("push")
        self.assertEqual(r.returncode, 1)
        self.assertIn("docs/specs", r.stderr)
        self.assertEqual(self.remote_tip(), "")

    def test_git_environment_cannot_redirect_the_push(self):
        commit_file(self.repo, "a.txt", "fix: a")
        other = make_repo("outro repo")
        r = self.script("push", GIT_DIR=str(other / ".git"), GIT_WORK_TREE=str(other),
                        GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="remote.origin.url", GIT_CONFIG_VALUE_0=str(other))
        self.assertEqual(r.returncode, 1)
        self.assertIn("seguranca", r.stderr)
        self.assertEqual(self.remote_tip(), "")

    def test_push_does_not_run_project_commands(self):
        (self.repo / "harness.conf").write_text('VALIDATE_PUSH="touch ran-validate"\n')
        commit_all(self.repo, "chore: validation")
        self.approve()
        self.assertEqual(self.script("push").returncode, 0)
        self.assertFalse((self.repo / "ran-validate").exists())

    def test_detached_head_and_unknown_argument_are_refused(self):
        self.assertEqual(self.script("push", "--mirror").returncode, 2)
        self.assertEqual(self.script("push", "origin", "main").returncode, 2)
        git(self.repo, "checkout", "-q", "--detach")
        r = self.script("push")
        self.assertEqual(r.returncode, 1)
        self.assertIn("branch", r.stderr)

    def test_force_replaces_the_remote_branch_after_a_rewrite(self):
        commit_file(self.repo, "a.txt", "fix: a")
        self.approve()
        self.assertEqual(self.script("push").returncode, 0)
        git(self.repo, "commit", "-q", "--amend", "-m", "fix: a, reworded")
        self.approve()
        self.assertNotEqual(self.script("push").returncode, 0)
        r = self.script("push", "--force")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.remote_tip(), git(self.repo, "rev-parse", "HEAD"))

    def test_manual_git_push_is_still_gated_by_the_hook(self):
        commit_file(self.repo, "a.txt", "fix: a")
        r = subprocess.run(["git", "push", "-q", "origin", "feat/x"], cwd=self.repo, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("seguranca", r.stderr)


class TestFetch(RemoteCase):
    def test_fetch_brings_new_remote_commits(self):
        new = commit_file(self.origin, "upstream.txt", "fix: upstream")
        self.assertNotEqual(git(self.repo, "rev-parse", "origin/main"), new)
        r = self.script("fetch", GIT_DIR="/nao/existe")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git(self.repo, "rev-parse", "origin/main"), new)

    def test_fetch_takes_no_arguments(self):
        self.assertEqual(self.script("fetch", "outro-remoto").returncode, 2)


PR_BODY = """Corrige a.

## Critérios de aceite

| Critério | Teste |
|---|---|
| a funciona | a.test.ts |

## Validação

Os quatro aprovaram.
"""


class TestPr(RemoteCase):
    def setUp(self):
        super().setUp()
        tmp = _tmpdir()
        (tmp / "bin").mkdir()
        os.symlink(ROOT / "tests/fake_gh", tmp / "bin/gh")
        self.log = tmp / "gh.log"
        self.path = f"{tmp / 'bin'}:{os.environ['PATH']}"
        commit_file(self.repo, "a.txt", "fix: a")
        (self.repo / "pr-body.md").write_text(PR_BODY)

    def pr(self, *args):
        return self.script("pr", *args, PATH=self.path, FAKE_GH_LOG=str(self.log))

    def gh_calls(self):
        return self.log.read_text().split("--fim--\n")[:-1] if self.log.exists() else []

    def test_create_refuses_a_branch_that_did_not_go_through_push(self):
        r = self.pr("create", "fix: a", "pr-body.md")
        self.assertEqual(r.returncode, 1)
        self.assertIn(".harness/push", r.stderr)
        self.assertEqual(self.gh_calls(), [])

    def test_create_passes_title_and_body_file_intact(self):
        self.approve()
        self.assertEqual(self.script("push").returncode, 0)
        r = self.pr("create", "fix: título com espaço; e $(perigo)", "pr-body.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        args = self.gh_calls()[0].splitlines()
        self.assertEqual(args[:2], ["pr", "create"])
        self.assertIn("fix: título com espaço; e $(perigo)", args)
        self.assertIn(str(self.repo / "pr-body.md"), args)
        self.assertIn("feat/x", args)

    def test_create_refuses_a_body_outside_the_standard(self):
        self.approve()
        self.script("push")
        (self.repo / "pr-body.md").write_text("Corrige a.\n\n## Validação\n\nok\n")
        r = self.pr("create", "fix: a", "pr-body.md")
        self.assertEqual(r.returncode, 1)
        self.assertIn("## Critérios de aceite", r.stderr)
        (self.repo / "pr-body.md").write_text("## Critérios de aceite\n\nx\n\n## Validação\n\nok\n")
        r = self.pr("create", "fix: a", "pr-body.md")
        self.assertEqual(r.returncode, 1, "sem o parágrafo de abertura antes do primeiro título")
        self.assertEqual(self.gh_calls(), [])

    def test_create_refuses_body_file_outside_the_project_and_stale_remote(self):
        self.approve()
        self.script("push")
        self.assertEqual(self.pr("create", "fix: a", "/etc/hosts").returncode, 1)
        self.assertEqual(self.pr("create", "fix: a", "nao-existe.md").returncode, 1)
        commit_file(self.repo, "b.txt", "fix: b")
        self.assertEqual(self.pr("create", "fix: a", "pr-body.md").returncode, 1)
        self.assertEqual(self.gh_calls(), [])

    def test_view_is_read_only_and_other_subcommands_are_refused(self):
        self.assertEqual(self.pr("view").returncode, 0)
        self.assertEqual(self.gh_calls()[0].splitlines()[:2], ["pr", "view"])
        for sub in (["merge"], ["close"], ["create"], []):
            self.assertEqual(self.pr(*sub).returncode, 2, sub)


class TestRemoteSettings(unittest.TestCase):
    def settings(self, repo):
        return json.loads((repo / ".claude/settings.json").read_text())["sandbox"]

    def test_git_host_is_denied_and_only_harness_scripts_reach_it(self):
        repo = make_repo()
        sync(repo)
        sandbox = self.settings(repo)
        for domain in ("github.com", "*.github.com"):
            self.assertIn(domain, sandbox["network"]["deniedDomains"])
            self.assertNotIn(domain, sandbox["network"]["allowedDomains"])
        for form in (".harness/push", "./.harness/push", ".harness/push --force", ".harness/fetch",
                     ".harness/pr *", "./.harness/pr *"):
            self.assertIn(form, sandbox["excludedCommands"])
        self.assertNotIn(".harness/push *", sandbox["excludedCommands"])

    def test_the_project_remote_host_is_denied_too(self):
        for url, host in (("https://gitlab.com/time/app.git", "gitlab.com"),
                          ("git@git.empresa.com.br:time/app.git", "git.empresa.com.br"),
                          ("ssh://git@codigo.exemplo.org:2222/time/app.git", "codigo.exemplo.org"),
                          ("HTTPS://Git.Exemplo.COM/time/app.git", "git.exemplo.com"),
                          ("git@gh:time/app.git", "gh"),
                          ("https://usuario:senha@git.interno./time/app.git", "git.interno")):
            repo = make_repo()
            git(repo, "remote", "add", "origin", url)
            sync(repo)
            denied = self.settings(repo)["network"]["deniedDomains"]
            self.assertIn(host, denied, url)
            self.assertIn("github.com", denied)

    def test_fragment_cannot_allow_the_git_host_back(self):
        repo = make_repo()
        (repo / "harness.d").mkdir()
        (repo / "harness.d/settings.json").write_text(json.dumps(
            {"sandbox": {"network": {"allowedDomains": ["github.com"], "deniedDomains": []}}}))
        sync(repo)
        net = self.settings(repo)["network"]
        self.assertIn("github.com", net["deniedDomains"])
        self.assertNotIn("github.com", net["allowedDomains"])


if __name__ == "__main__":
    unittest.main()
