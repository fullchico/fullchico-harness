import os
import stat
import subprocess
import unittest

from tests.helpers import ROOT, _tmpdir, make_repo

INSTALL = str(ROOT / "install")


def fake_claude():
    """Um `claude` de mentira no PATH, que só anota como foi chamado."""
    folder = _tmpdir()
    script = folder / "claude"
    script.write_text('#!/usr/bin/env bash\necho "$PWD|$*" >> "$CLAUDE_LOG"\n')
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    # Um `npx` de mentira que, como o de verdade, consome a entrada padrão.
    npx = folder / "npx"
    npx.write_text('#!/usr/bin/env bash\ncat >/dev/null\necho "npx $*" >> "$CLAUDE_LOG"\n')
    npx.chmod(npx.stat().st_mode | stat.S_IXUSR)
    return folder


class TestInstall(unittest.TestCase):
    def run_install(self, *args, cwd=None):
        self.bin = fake_claude()
        self.log = self.bin / "log"
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", CLAUDE_LOG=str(self.log))
        return subprocess.run([INSTALL, *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)

    def test_one_command_adopts_the_harness(self):
        repo = make_repo()
        r = self.run_install(str(repo))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((repo / ".harness/push").exists())
        self.assertTrue((repo / ".claude/settings.json").exists())
        self.assertFalse((repo / ".env").exists(), "sem harness.conf preenchido não há portas a gravar")
        calls = self.log.read_text()
        self.assertIn(f"plugin marketplace add {ROOT}", calls)
        self.assertIn("plugin marketplace add DietrichGebert/ponytail", calls)
        for plugin in ("harness@fullchico", "ponytail@ponytail", "mattpocock-skills@claude-plugins-official"):
            self.assertIn(f"plugin install {plugin} --scope project", calls)
        installs = [line for line in calls.splitlines() if "plugin install" in line]
        self.assertTrue(all(line.startswith(str(repo.resolve())) for line in installs), installs)
        self.assertIn("/harness:setup", r.stdout)
        for skill in ("hexagonal-architecture", "feature-sliced-design", "parallel-feature-development",
                      "clean-code-guard"):
            self.assertIn(f"-s {skill} -a claude-code -y --copy", calls, skill)

    def test_defaults_to_the_current_folder_and_can_run_twice(self):
        repo = make_repo()
        self.assertEqual(self.run_install(cwd=repo).returncode, 0)
        r = self.run_install(cwd=repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_filled_conf_also_prepares_the_worktree(self):
        repo = make_repo()
        self.assertEqual(self.run_install(str(repo)).returncode, 0)
        conf = (repo / "harness.conf").read_text()
        (repo / "harness.conf").write_text(conf + '\nPROJECT="salao"\nSERVICES="web api"\n')
        r = self.run_install(str(repo))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("_PORT", (repo / ".env").read_text())
        self.assertNotIn("/harness:setup", r.stdout)

    def test_outside_a_repository_is_refused(self):
        r = self.run_install(str(_tmpdir()))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("git", r.stderr)

    def test_hand_edited_managed_file_stops_before_any_plugin(self):
        repo = make_repo()
        self.assertEqual(self.run_install(str(repo)).returncode, 0)
        (repo / "CLAUDE.md").write_text("mexido\n")
        r = self.run_install(str(repo))
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.run_install(str(repo), "--force").returncode, 0)


if __name__ == "__main__":
    unittest.main()


class TestSettingsRewrittenByTheCli(unittest.TestCase):
    """`claude plugin install` regrava o settings.json com as chaves em outra ordem."""

    def setUp(self):
        import json
        from tests.helpers import sync
        self.json, self.sync = json, sync
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        self.path = self.repo / ".claude/settings.json"
        self.check = ["python3", "-I", str(self.repo / ".harness/manifest_check.py"), str(self.repo)]

    def rewrite(self, change=None):
        data = self.json.loads(self.path.read_text())
        if change:
            change(data)
        self.path.write_text(self.json.dumps(dict(reversed(list(data.items()))), indent=4))

    def test_same_content_in_another_order_is_not_drift(self):
        self.rewrite()
        self.assertEqual(subprocess.run(self.check, capture_output=True).returncode, 0)
        r = self.sync(self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_changed_content_is_still_drift(self):
        self.rewrite(lambda d: d["sandbox"].update(enabled=False))
        r = subprocess.run(self.check, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn(".claude/settings.json", r.stdout)
        self.assertEqual(self.sync(self.repo).returncode, 1)
