"""Instalação e contrato básico dos hooks do Codex."""
import json
import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, _tmpdir, fake_npx, make_repo


class TestCodex(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.bin = _tmpdir()
        fake_npx(self.bin)
        self.cli = ["node", str(ROOT / "bin/harness.js"), "install-codex", str(self.repo), "--padrao"]

    def install(self):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")
        return subprocess.run(self.cli, capture_output=True, text=True, env=env)

    def hook(self, event, tool, value):
        payload = {"cwd": str(self.repo), "hook_event_name": event, "tool_name": tool,
                   "tool_input": value}
        run = subprocess.run([sys.executable, "-I", str(self.repo / ".codex/harness/tr/scripts/codex_hook.py")],
                             input=json.dumps(payload), capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout) if run.stdout.strip() else {}

    def test_install_is_repeatable_and_preserves_other_hooks(self):
        hooks = self.repo / ".codex/hooks.json"
        hooks.parent.mkdir()
        hooks.write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}))
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.install().returncode, 0)
        data = json.loads(hooks.read_text())["hooks"]
        self.assertNotIn("PreToolUse", data, "os hooks do trilho vêm do plugin Codex")
        self.assertEqual(data["SessionStart"][0]["hooks"][0]["command"], "echo hi")
        self.assertTrue((self.repo / ".agents/skills/tr-codex/SKILL.md").exists())
        self.assertTrue((self.repo / ".agents/skills/graphify/SKILL.md").exists())
        self.assertFalse((self.repo / ".agents/skills/memoria-codex/SKILL.md").exists())
        for name in ("mapear", "dream", "aprender"):
            self.assertTrue((self.repo / f".codex/harness/tr/codex-skills/tr-memory-{name}/SKILL.md").exists())
            self.assertFalse((self.repo / f".codex/harness/memoria/codex-skills/memoria-{name}/SKILL.md").exists())
        self.assertTrue((self.repo / ".codex/agents/tr-bugs-cacador.toml").exists())
        self.assertTrue((self.repo / ".claude/trilho.json").exists())
        market = json.loads((self.repo / ".agents/plugins/marketplace.json").read_text())
        self.assertEqual([p["name"] for p in market["plugins"]], ["tr", "memoria"])
        self.assertEqual([p["source"]["path"] for p in market["plugins"]],
                         ["./.codex/harness/tr", "./.codex/harness/memoria"])
        config = (self.repo / ".codex/config.toml").read_text()
        self.assertIn('approval_policy = "on-request"', config)
        self.assertIn('approvals_reviewer = "auto_review"', config)
        self.assertNotIn("sandbox_mode =", config, "o harness não escolhe o sandbox do Codex")
        self.assertEqual(config.count('approvals_reviewer = "auto_review"'), 1)
        self.assertEqual(config.count('[plugins."tr@fullchico-project"]'), 1)
        self.assertEqual(config.count('[plugins."memoria@fullchico-project"]'), 1)
        for name in ("tr", "memoria"):
            manifest = json.loads((self.repo / f".codex/harness/{name}/.codex-plugin/plugin.json").read_text())
            self.assertEqual(manifest["name"], name)
            self.assertEqual(manifest["hooks"], "./codex-hooks/hooks.json")

    def test_reinstall_removes_old_memory_skill_names(self):
        old = self.repo / ".codex/harness/memoria/codex-skills/memoria-dream"
        old.mkdir(parents=True)
        (old / "SKILL.md").write_text("---\nname: memoria-dream\n---\n")
        helper = self.repo / ".agents/skills/memoria-codex"
        helper.mkdir(parents=True)
        (helper / "SKILL.md").write_text("---\nname: memoria-codex\n---\n")
        self.assertEqual(self.install().returncode, 0)
        self.assertFalse(old.exists())
        self.assertFalse(helper.exists())
        new = self.repo / ".codex/harness/tr/codex-skills/tr-memory-dream/SKILL.md"
        self.assertIn("name: tr-memory-dream", new.read_text())

    def test_existing_marketplace_config_and_old_hooks_are_migrated(self):
        market = self.repo / ".agents/plugins/marketplace.json"
        market.parent.mkdir(parents=True)
        market.write_text(json.dumps({"name": "my-team", "plugins": [{"name": "other", "source": "./plugins/other"}]}))
        config = self.repo / ".codex/config.toml"
        config.parent.mkdir()
        config.write_text('[plugins."other@my-team"]\nenabled = false\n')
        hooks = config.parent / "hooks.json"
        hooks.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "echo keep"},
            {"type": "command", "command": 'python3 -I "$(git rev-parse --show-toplevel)/.codex/harness/tr/scripts/codex_hook.py"'}
        ]}]}}))
        self.assertEqual(self.install().returncode, 0)
        data = json.loads(market.read_text())
        self.assertEqual([p["name"] for p in data["plugins"]], ["other", "tr", "memoria"])
        self.assertIn('[plugins."other@my-team"]\nenabled = false', config.read_text())
        self.assertIn('[plugins."tr@my-team"]\nenabled = true', config.read_text())
        commands = [h["command"] for g in json.loads(hooks.read_text())["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertEqual(commands, ["echo keep"])

    def test_explicit_permission_settings_are_preserved(self):
        config = self.repo / ".codex/config.toml"
        config.parent.mkdir()
        config.write_text('approval_policy = "never"\napprovals_reviewer = "user"\nsandbox_mode = "read-only"\n')
        self.assertEqual(self.install().returncode, 0)
        written = config.read_text()
        self.assertIn('approval_policy = "never"', written)
        self.assertIn('approvals_reviewer = "user"', written)
        self.assertIn('sandbox_mode = "read-only"', written)
        self.assertNotIn('auto_review', written)

    def test_conflicting_plugin_name_stops_before_writing(self):
        market = self.repo / ".agents/plugins/marketplace.json"
        market.parent.mkdir(parents=True)
        original = {"name": "my-team", "plugins": [{"name": "tr", "source": "./plugins/another-tr"}]}
        market.write_text(json.dumps(original))
        run = self.install()
        self.assertEqual(run.returncode, 1)
        self.assertIn("outro plugin", run.stderr)
        self.assertEqual(json.loads(market.read_text()), original)
        self.assertFalse((self.repo / ".codex").exists())

    def test_patch_is_blocked_and_push_is_separate_from_delivery(self):
        self.assertEqual(self.install().returncode, 0)
        patch = "*** Begin Patch\n*** Add File: .claude/trilho.json\n+x\n*** End Patch"
        result = self.hook("PreToolUse", "apply_patch", {"command": patch})
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        patch = "*** Begin Patch\n*** Delete File: .codex/config.toml\n*** End Patch"
        result = self.hook("PreToolUse", "apply_patch", {"command": patch})
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        result = self.hook("PreToolUse", "Bash", {"command": "git push"})
        self.assertNotEqual(result.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")
        self.assertEqual(self.hook("SubagentStop", "", {}), {}, "Codex exige JSON válido no fim do subagente")

    def test_invalid_registry_stops_before_install(self):
        file = self.repo / ".claude/trilho.json"
        file.parent.mkdir()
        file.write_text("{")
        run = self.install()
        self.assertEqual(run.returncode, 1)
        self.assertFalse((self.repo / ".codex").exists())

    def test_all_project_skills_and_memory_extractor_are_installed(self):
        self.assertEqual(self.install().returncode, 0)
        for plugin, names in (("tr", ("processo-planejar", "configurar", "portoes", "qualidade-verificar", "bugs-cacar", "grill-me",
                                      "memory-mapear", "memory-dream", "memory-aprender")),):
            for name in names:
                file = self.repo / f".codex/harness/{plugin}/codex-skills/{plugin}-{name}/SKILL.md"
                self.assertTrue(file.exists(), name)
                self.assertIn(f"name: {plugin}-{name}", file.read_text())
                self.assertNotIn("/tr:", file.read_text())
        self.assertTrue((self.repo / ".codex/agents/memoria-extrator.toml").exists())
        hooks = json.loads((self.repo / ".codex/harness/memoria/codex-hooks/hooks.json").read_text())["hooks"]["SubagentStop"]
        self.assertTrue(any("codex_candidates.py" in h["command"] for g in hooks for h in g["hooks"]))
        payload = {"hook_event_name": "SubagentStop", "agent_type": "memoria-extrator",
                   "cwd": str(self.repo), "last_assistant_message": "NOTA: fuso\nTexto\nCAMINHOS: README.md"}
        script = self.repo / ".codex/harness/memoria/scripts/codex_candidates.py"
        run = subprocess.run([sys.executable, "-I", str(script)], input=json.dumps(payload),
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), {})

    def test_codex_session_commands_read_codex_transcript(self):
        self.assertEqual(self.install().returncode, 0)
        home = _tmpdir()
        folder = home / ".codex/sessions/2026/11/23"
        folder.mkdir(parents=True)
        sid = "12345678-aaaa-bbbb-cccc-123456789abc"
        entries = [
            {"type": "session_meta", "payload": {"id": sid, "cwd": str(self.repo)}},
            {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                 "content": [{"type": "input_text", "text": "faça X"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                                 "content": [{"type": "output_text", "text": "feito"}]}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage":
                {"input_tokens": 10, "output_tokens": 3, "cached_input_tokens": 2}}}},
        ]
        (folder / f"rollout-{sid}.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        executable = self.repo / ".codex/harness/bin/memoria-sessoes"
        env = dict(os.environ, HOME=str(home))
        run = lambda *args: subprocess.run([str(executable), *args], cwd=self.repo, env=env,
                                           capture_output=True, text=True)
        self.assertIn(sid, run("sessions").stdout)
        self.assertIn("10\t3\t2", run("usage").stdout)
        output = self.repo / "digest.md"
        self.assertEqual(run("digest", sid[:8], str(output)).returncode, 0)
        self.assertIn("DONO: faça X", output.read_text())
        self.assertIn("AGENTE: feito", output.read_text())


if __name__ == "__main__":
    unittest.main()
