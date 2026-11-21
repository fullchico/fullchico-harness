import json
import os
import subprocess
import unittest

from tests.helpers import commit_all, git, make_repo, sync


def manifest(repo):
    return json.loads((repo / ".harness/MANIFEST").read_text())["files"]


class TestOrcaAndConductor(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)

    def test_orca_yaml_is_generated_and_managed(self):
        text = (self.repo / "orca.yaml").read_text()
        self.assertIn("orca.yaml", manifest(self.repo))
        self.assertIn("setup:", text)
        self.assertIn(".harness/setup-worktree", text)
        self.assertIn("archive:", text)
        self.assertIn(".harness/destroy", text)
        self.assertNotIn("\t", text)

    def test_conductor_only_when_asked(self):
        self.assertFalse((self.repo / ".conductor/settings.toml").exists())
        (self.repo / "harness.conf").write_text("CONDUCTOR=1\n")
        self.assertEqual(sync(self.repo).returncode, 0)
        text = (self.repo / ".conductor/settings.toml").read_text()
        self.assertIn(os.path.join(".conductor", "settings.toml"), manifest(self.repo))
        for token in (".harness/setup-worktree", ".harness/destroy", ".harness/up && .harness/prepare && .harness/dev"):
            self.assertIn(token, text)

    def test_conductor_removed_when_no_longer_asked(self):
        (self.repo / "harness.conf").write_text("CONDUCTOR=1\n")
        sync(self.repo)
        (self.repo / "harness.conf").write_text("# CONDUCTOR=1\n")
        self.assertEqual(sync(self.repo).returncode, 0)
        self.assertFalse((self.repo / ".conductor/settings.toml").exists())
        self.assertNotIn(os.path.join(".conductor", "settings.toml"), manifest(self.repo))

    def test_stale_managed_file_edited_by_hand_is_kept_and_reported(self):
        (self.repo / "harness.conf").write_text("CONDUCTOR=1\n")
        sync(self.repo)
        (self.repo / ".conductor/settings.toml").write_text("# mexi\n")
        (self.repo / "harness.conf").write_text("")
        r = sync(self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.repo / ".conductor/settings.toml").read_text(), "# mexi\n")
        self.assertIn(".conductor/settings.toml", r.stderr)

    def test_agents_md_has_environment_section_and_fits(self):
        text = (self.repo / "AGENTS.md").read_text()
        self.assertIn("## Ambiente", text)
        for token in (".harness/up", ".harness/prepare", ".harness/dev", ".env"):
            self.assertIn(token, text)
        self.assertLess(len(text.encode("utf-8")), 8 * 1024)

    def test_template_conf_documents_conductor_and_not_parallelism_yet(self):
        text = (self.repo / "harness.conf").read_text()
        self.assertIn("# CONDUCTOR=1", text)


class TestSetupWorktree(unittest.TestCase):
    def test_new_worktree_gets_env_ports_and_dependencies(self):
        repo = make_repo("principal")
        sync(repo)
        (repo / "harness.conf").write_text('PROJECT=meuapp\nSERVICES="web db"\nINSTALL_CMD="touch instalado.txt"\n')
        commit_all(repo, "chore: adopt harness")
        (repo / ".env").write_text("SECRET=abc\n")
        feature = repo.parent / "roseau"
        git(repo, "worktree", "add", "-q", str(feature), "-b", "feat/x")
        env = {k: v for k, v in os.environ.items() if k not in ("CONDUCTOR_PORT", "HARNESS_ENV")}
        r = subprocess.run([str(feature / ".harness/setup-worktree")], cwd=feature,
                           env=dict(env, HARNESS_SKIP_PLUGIN="1"), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        values = dict(l.split("=", 1) for l in (feature / ".env").read_text().splitlines() if "=" in l)
        self.assertEqual(values["SECRET"], "abc")
        self.assertEqual(values["COMPOSE_PROJECT_NAME"], "meuapp-roseau")
        self.assertIn("WEB_PORT", values)
        self.assertTrue((feature / "instalado.txt").exists())

    def test_install_failure_fails_the_setup(self):
        repo = make_repo()
        sync(repo)
        (repo / "harness.conf").write_text('PROJECT=x\nSERVICES=web\nINSTALL_CMD="exit 5"\n')
        r = subprocess.run([str(repo / ".harness/setup-worktree")], cwd=repo,
                           env=dict(os.environ, HARNESS_SKIP_PLUGIN="1"), capture_output=True, text=True)
        self.assertEqual(r.returncode, 5)


if __name__ == "__main__":
    unittest.main()
