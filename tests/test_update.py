import json
import os
import subprocess
import unittest

from tests.helpers import clone_self_with_tags, commit_all, make_repo, sync


class TestUpdate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.up = clone_self_with_tags("up stream", {
            "v0.1.0": None,
            "v0.2.0": ("plugin/templates/CLAUDE.md", "\nlinha nova v2\n"),
        })

    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        commit_all(self.repo, "chore: adopt harness")
        self.env = dict(os.environ, HARNESS_REPO=f"file://{self.up}", HARNESS_SKIP_PLUGIN="1")

    def update(self, *args):
        return subprocess.run([str(self.repo / ".harness/update"), *args], cwd=self.repo,
                              env=self.env, capture_output=True, text=True)

    def manifest_version(self):
        return json.loads((self.repo / ".harness/MANIFEST").read_text())["version"]

    def test_update_brings_new_managed_content_and_version(self):
        r = self.update("v0.2.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("linha nova v2", (self.repo / "CLAUDE.md").read_text())
        self.assertEqual(self.manifest_version(), "v0.2.0")
        s = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertEqual(s["extraKnownMarketplaces"]["fullchico"]["source"]["ref"], "v0.2.0")
        self.assertIn("CLAUDE.md", r.stdout)
        self.assertIn("/reload-plugins", r.stdout)

    def test_update_runs_from_a_subdirectory(self):
        (self.repo / "src").mkdir()
        r = subprocess.run([str(self.repo / ".harness/update"), "v0.2.0"], cwd=self.repo / "src",
                           env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.manifest_version(), "v0.2.0")

    def test_manual_drift_stops_update(self):
        (self.repo / "CLAUDE.md").write_text("mexi\n")
        r = self.update("v0.2.0")
        self.assertEqual(r.returncode, 1)
        self.assertIn("CLAUDE.md", r.stderr)
        self.assertEqual(self.manifest_version(), "v0.1.0")
        self.assertEqual(self.update("v0.2.0", "--force").returncode, 0)
        self.assertEqual(self.manifest_version(), "v0.2.0")

    def test_unknown_tag_and_missing_arg(self):
        r = self.update("v9.9.9")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.manifest_version(), "v0.1.0")
        self.assertEqual(self.update().returncode, 2)
        self.assertEqual(self.update("--force").returncode, 2)

    def test_leaves_no_temp_clone_behind(self):
        tmp = self.repo.parent / "tmp dir"
        tmp.mkdir()
        env = dict(self.env, TMPDIR=str(tmp))
        subprocess.run([str(self.repo / ".harness/update"), "v0.2.0"], cwd=self.repo, env=env, capture_output=True)
        subprocess.run([str(self.repo / ".harness/update"), "v9.9.9"], cwd=self.repo, env=env, capture_output=True)
        self.assertEqual(list(tmp.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
