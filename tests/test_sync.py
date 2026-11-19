import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import ROOT, git, make_repo, sync
import managed_guard


def check(repo):
    return subprocess.run([sys.executable, str(repo / ".harness/manifest_check.py"), str(repo)],
                          capture_output=True, text=True)


def settings(repo):
    return json.loads((repo / ".claude/settings.json").read_text())


class TestSync(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        r = sync(self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_layout(self):
        payload = ROOT / "plugin/payload"
        sources = [p for p in payload.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        self.assertIn(payload / "hooks/gate_stamp.py", sources)
        self.assertIn(payload / "approve", sources)
        for src in sources:
            dst = self.repo / ".harness" / src.relative_to(payload)
            self.assertEqual(dst.read_bytes(), src.read_bytes(), dst)
            self.assertEqual(os.access(dst, os.X_OK), os.access(src, os.X_OK), dst)
        for p in [".harness/manifest_check.py", ".harness/MANIFEST", ".harness/map.env",
                  ".claude/settings.json", "CLAUDE.md", "AGENTS.md", "harness.conf",
                  "docs/agents/issue-tracker.md", "docs/agents/domain.md"]:
            self.assertTrue((self.repo / p).exists(), p)
        self.assertEqual(git(self.repo, "config", "core.hooksPath"), ".harness/git-hooks")
        self.assertFalse(list((self.repo / ".harness").rglob("__pycache__")))

    def test_map_env_comes_from_map_json(self):
        env = (self.repo / ".harness/map.env").read_text()
        self.assertIn("SPEC_GLOB=docs/specs/*/spec.md\n", env)
        self.assertIn("TICKETS_GLOB=docs/specs/*/issues/*.md\n", env)

    def test_settings_pins_version_and_denies_managed_edits(self):
        s = settings(self.repo)
        self.assertEqual(s["extraKnownMarketplaces"]["fullchico"]["source"]["ref"], "v0.1.0")
        self.assertTrue(s["enabledPlugins"]["harness@fullchico"])
        self.assertTrue(s["enabledPlugins"]["mattpocock-skills@claude-plugins-official"])
        self.assertTrue(s["enabledPlugins"]["ponytail@ponytail"])
        for rule in ["Edit(/.harness/**)", "Edit(/harness.conf)", "Edit(/harness.d/**)",
                     "Edit(/.claude/settings.json)", "Edit(/CLAUDE.md)", "Edit(/docs/agents/**)"]:
            self.assertIn(rule, s["permissions"]["deny"])
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", json.dumps(s))

    def test_settings_registers_every_hook(self):
        text = json.dumps(settings(self.repo))
        for name in ["service_guard.py", "dispatch_guard.py", "managed_guard.py", "gate_stamp.py", "rtk hook claude"]:
            self.assertIn(name, text)
        stops = settings(self.repo)["hooks"]["SubagentStop"]
        self.assertEqual(stops[0]["matcher"], "^harness:(seguranca|revisor)$")

    def test_template_conf_has_no_active_keys(self):
        import common
        self.assertEqual(common.read_conf(str(self.repo / "harness.conf")), {})

    def test_manifest_check_clean_then_detects_drift(self):
        self.assertEqual(check(self.repo).returncode, 0, check(self.repo).stdout)
        (self.repo / ".harness/approve").write_text("#!/bin/sh\nexit 0\n")
        r = check(self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn(".harness/approve", r.stdout)

    def test_manifest_check_detects_missing_file_and_region_change(self):
        (self.repo / "CLAUDE.md").unlink()
        f = self.repo / "AGENTS.md"
        f.write_text(f.read_text().replace(managed_guard.END, "regra infiltrada\n" + managed_guard.END))
        out = check(self.repo).stdout
        self.assertIn("CLAUDE.md", out)
        self.assertIn("AGENTS.md", out)

    def test_project_region_change_is_not_drift(self):
        f = self.repo / "AGENTS.md"
        f.write_text(f.read_text().replace("## Produto", "## Produto\n\nmeu texto de projeto"))
        self.assertEqual(check(self.repo).returncode, 0)

    def test_agents_md_region_only(self):
        f = self.repo / "AGENTS.md"
        f.write_text(f.read_text().replace("## Produto", "## Produto\n\nmeu texto de projeto"))
        self.assertEqual(sync(self.repo).returncode, 0)
        self.assertIn("meu texto de projeto", f.read_text())
        self.assertIsNotNone(managed_guard.region(f.read_text()))

    def test_agents_md_under_codex_limit(self):
        self.assertLess(len((self.repo / "AGENTS.md").read_bytes()), 8 * 1024)

    def test_existing_agents_md_without_markers_is_kept(self):
        repo = make_repo()
        (repo / "AGENTS.md").write_text("# Antigo\n\nconteúdo do projeto\n")
        self.assertEqual(sync(repo).returncode, 0)
        text = (repo / "AGENTS.md").read_text()
        self.assertIn("conteúdo do projeto", text)
        self.assertIsNotNone(managed_guard.region(text))

    def test_manual_drift_blocks_resync_unless_forced(self):
        (self.repo / "CLAUDE.md").write_text("mexi à mão\n")
        r = sync(self.repo)
        self.assertEqual(r.returncode, 1)
        self.assertIn("CLAUDE.md", r.stderr)
        self.assertEqual((self.repo / "CLAUDE.md").read_text(), "mexi à mão\n")
        self.assertEqual(sync(self.repo, "--force").returncode, 0)
        self.assertNotEqual((self.repo / "CLAUDE.md").read_text(), "mexi à mão\n")

    def test_resync_is_idempotent(self):
        before = (self.repo / ".harness/MANIFEST").read_text()
        self.assertEqual(sync(self.repo).returncode, 0)
        self.assertEqual((self.repo / ".harness/MANIFEST").read_text(), before)

    def test_project_files_are_never_touched(self):
        (self.repo / "harness.conf").write_text("PROJECT=meu\n")
        (self.repo / "harness.d").mkdir()
        frag = {"permissions": {"ask": ["mcp__x"]}, "hooks": {"Stop": [{"hooks": []}]}}
        (self.repo / "harness.d/settings.json").write_text(json.dumps(frag))
        (self.repo / "CLAUDE.local.md").write_text("meu\n")
        self.assertEqual(sync(self.repo).returncode, 0)
        self.assertEqual((self.repo / "harness.conf").read_text(), "PROJECT=meu\n")
        self.assertEqual((self.repo / "CLAUDE.local.md").read_text(), "meu\n")
        s = settings(self.repo)
        self.assertEqual(s["permissions"]["ask"], ["mcp__x"])
        self.assertIn("Stop", s["hooks"])
        self.assertIn("Edit(/.harness/**)", s["permissions"]["deny"])
        self.assertIn("PreToolUse", s["hooks"])

    def test_fragment_cannot_drop_harness_rules(self):
        (self.repo / "harness.d").mkdir(exist_ok=True)
        (self.repo / "harness.d/settings.json").write_text(
            json.dumps({"permissions": {"deny": []}, "hooks": {"PreToolUse": []},
                        "enabledPlugins": {"harness@fullchico": False}}))
        self.assertEqual(sync(self.repo).returncode, 0)
        s = settings(self.repo)
        self.assertIn("Edit(/.harness/**)", s["permissions"]["deny"])
        self.assertTrue(s["hooks"]["PreToolUse"])
        self.assertTrue(s["enabledPlugins"]["harness@fullchico"])

    def test_usage_errors(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sync(pathlib.Path(d)).returncode, 2)
        r = subprocess.run([sys.executable, str(ROOT / "plugin/bin/sync"), str(self.repo)], capture_output=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
