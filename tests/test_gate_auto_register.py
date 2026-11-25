"""Plugins registram o próprio portão: apertar é automático; afrouxar é só do dono."""
import json
import os
import shutil
import subprocess
import sys
import unittest

from tests.helpers import ROOT, _tmpdir, commit_all, fake_claude, git, make_repo, hook_verdict

TR_PLUGIN = ROOT / "plugins/tr"
NODE = shutil.which("node")


class Base(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.home = _tmpdir()
        self.bin = _tmpdir()
        fake_claude(self.bin)
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", HOME=str(self.home))

    def registry_data(self):
        return json.loads((self.repo / ".claude/harness.json").read_text())

    def put_registry(self, data):
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/harness.json").write_text(json.dumps(data))

    def node(self, *args):
        return subprocess.run([NODE, str(ROOT / "bin/harness.js"), *args], capture_output=True, text=True,
                              env=self.env, cwd=self.repo)

    def add(self, *names):
        return self.node("add", *names, "--project", str(self.repo))

    def pkg(self, scripts, lock=None):
        (self.repo / "package.json").write_text(json.dumps({"scripts": scripts}))
        if lock:
            (self.repo / lock).write_text("")


class TestAdd(Base):
    def test_plugin_without_manifest_changes_nothing(self):
        self.add("memory")
        self.assertFalse((self.repo / ".claude/harness.json").exists())


class TestSessionStart(Base):
    def cache(self, plugin="quality", version="0.1.0", entries=None):
        d = self.home / ".claude/plugins/cache/fullchico" / plugin / version
        d.mkdir(parents=True)
        (d / "gate.json").write_text(json.dumps(entries or {
            plugin: {"stage": "end", "signs": "command", "command": "@discover", "description": "d"}}))

    def enable(self, *keys):
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {k: True for k in keys}}))

    def hook(self):
        env = dict(self.env, CLAUDE_PROJECT_DIR=str(self.repo))
        return subprocess.run([sys.executable, "-I", str(TR_PLUGIN / "scripts/self_register.py")], capture_output=True,
                              text=True, env=env, cwd=self.repo, input="{}")

    def test_registers_the_gate_of_an_enabled_plugin_and_logs_it(self):
        self.pkg({"test": "y"})
        self.cache()
        self.enable("quality@fullchico")
        r = self.hook()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.registry_data()["gates"]["quality"]["command"], "npm test")
        msg = json.loads(r.stdout)["systemMessage"]
        self.assertIn("portão `quality` registrado automaticamente pelo plugin `quality`", msg)
        log = next((self.home / ".claude/tr").glob("*/log.jsonl")).read_text()
        self.assertIn("quality", log)

    def test_uses_the_highest_installed_version(self):
        self.cache(version="0.1.0", entries={"x": {"stage": "end", "signs": "command", "command": "velho"}})
        self.cache(version="0.10.0", entries={"x": {"stage": "end", "signs": "command", "command": "novo"}})
        self.enable("quality@fullchico")
        self.hook()
        self.assertEqual(self.registry_data()["gates"]["x"]["command"], "novo")

    def test_does_not_overwrite_and_stays_quiet(self):
        self.cache()
        self.enable("quality@fullchico")
        self.put_registry({"gates": {"quality": {"stage": "end", "signs": "command", "command": "make"}}})
        r = self.hook()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        self.assertEqual(self.registry_data()["gates"]["quality"]["command"], "make")

    def test_ignores_plugins_that_are_not_enabled(self):
        self.cache()
        self.enable("outro@fullchico")
        self.hook()
        self.assertFalse((self.repo / ".claude/harness.json").exists())

    def test_project_without_gate_plugins_gets_nothing(self):
        d = self.home / ".claude/plugins/cache/fullchico/memory/0.1.0"
        d.mkdir(parents=True)
        self.enable("memory@fullchico")
        r = self.hook()
        self.assertEqual(r.returncode, 0)
        self.assertFalse((self.repo / ".claude/harness.json").exists())

    def test_internal_error_exits_zero(self):
        self.enable("quality@fullchico")
        (self.repo / ".claude/settings.json").write_text("{quebrado")
        self.assertEqual(self.hook().returncode, 0)


class TestSetCommand(Base):
    def setUp(self):
        super().setUp()
        self.put_registry({"code": ["src"], "gates": {
            "quality": {"stage": "end", "signs": "command", "command": "@define"},
            "bugs": {"stage": "end", "signs": "agent", "agent": "bugs:cacador"}}})
        commit_all(self.repo, "chore: registro")
        git(self.repo, "checkout", "-q", "-b", "feat")

    def gates(self, *args):
        return self.node("gates", *args)

    def run_script(self, name, payload):
        env = dict(self.env, CLAUDE_PLUGIN_ROOT=str(TR_PLUGIN), CLAUDE_PROJECT_DIR=str(self.repo))
        return hook_verdict(subprocess.run([sys.executable, str(TR_PLUGIN / "scripts" / name)], input=json.dumps(payload),
                                           capture_output=True, text=True, env=env, cwd=self.repo))

    def test_gate_fails_telling_the_owner_what_to_do(self):
        r = subprocess.run([str(TR_PLUGIN / "bin/gate"), "quality"], capture_output=True, text=True,
                           env=self.env, cwd=self.repo)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("npx @fullchico/harness gates --set quality '<command>'", r.stdout)
        self.assertNotIn("quality: passou", r.stdout)

    def test_delivery_gate_lists_it_as_missing(self):
        r = self.run_script("guard.py", {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.repo),
                                        "tool_input": {"command": "git push"}})
        self.assertEqual(r.returncode, 0)
        delivery = subprocess.run([str(TR_PLUGIN / "bin/gate"), "delivery"], cwd=self.repo,
                                  capture_output=True, text=True, env=self.env)
        self.assertEqual(delivery.returncode, 1)
        self.assertIn("--set quality", delivery.stdout)

    def test_set_swaps_only_that_command(self):
        before = self.registry_data()
        r = self.gates("--set", "quality", "npm test", "--project", str(self.repo))
        self.assertEqual(r.returncode, 0, r.stderr)
        after = self.registry_data()
        self.assertEqual(after["gates"]["quality"]["command"], "npm test")
        before["gates"]["quality"]["command"] = "npm test"
        self.assertEqual(after, before)

    def test_set_refuses_unknown_or_non_command_gate(self):
        self.assertNotEqual(self.gates("--set", "nada", "x", "--project", str(self.repo)).returncode, 0)
        self.assertNotEqual(self.gates("--set", "bugs", "x", "--project", str(self.repo)).returncode, 0)

    def test_the_agent_still_cannot_edit_the_registry(self):
        r = self.run_script("guard.py", {"hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(self.repo),
                                        "tool_input": {"file_path": str(self.repo / ".claude/harness.json")}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("só o dono", r.stderr)


if __name__ == "__main__":
    unittest.main()
