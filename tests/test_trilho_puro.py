"""Plugin `tr`, passo 1: o modo puro por projeto.

O projeto que se declara puro (`.claude/puro`) roda o Claude Code só com o que ele declara e com o
escopo local; o global do usuário não entra. O lançador liga as opções, e o vigia do plugin avisa
quando a sessão foi aberta sem elas. Testado numa sessão interativa real antes de virar código.
"""
import json
import os
import stat
import subprocess
import sys
import unittest

from tests.helpers import ROOT, _tmpdir, make_repo

PLUGIN = ROOT / "plugins/tr"
LAUNCHER = ROOT / "bin/cc"
FLAGS = "--setting-sources project,local --strict-mcp-config"


def fake_claude(folder):
    """Um `claude` de mentira que só mostra com que argumentos foi chamado."""
    path = folder / "claude"
    path.write_text('#!/bin/sh\necho "ARGS: $*"\n')
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return folder


class TestLauncher(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.bin = fake_claude(_tmpdir())

    def launch(self, *args, cwd=None):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")
        return subprocess.run([str(LAUNCHER), *args], cwd=cwd or self.repo, env=env, capture_output=True, text=True)

    def test_a_project_without_the_mark_starts_as_usual(self):
        out = self.launch("--model", "haiku").stdout
        self.assertEqual(out.strip(), "ARGS: --model haiku")

    def test_a_pure_project_starts_with_only_its_own_settings(self):
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/puro").write_text("")
        out = self.launch("--model", "haiku").stdout
        self.assertIn(FLAGS, out)
        self.assertNotIn("--mcp-config", out)
        self.assertTrue(out.strip().endswith("--model haiku"), "os argumentos do dono vêm depois e são preservados")

    def test_project_mcp_servers_are_passed_explicitly(self):
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/puro").write_text("")
        (self.repo / ".claude/mcp.json").write_text('{"mcpServers": {}}')
        out = self.launch().stdout
        self.assertIn(f"--mcp-config {os.path.realpath(self.repo)}/.claude/mcp.json", out)

    def test_it_finds_the_project_from_a_subfolder(self):
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/puro").write_text("")
        (self.repo / "apps/web").mkdir(parents=True)
        self.assertIn(FLAGS, self.launch(cwd=self.repo / "apps/web").stdout)


class TestWatcher(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()

    def check(self, parent_args):
        payload = {"hook_event_name": "SessionStart", "cwd": str(self.repo)}
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo), TRILHO_PARENT_ARGS=parent_args)
        return subprocess.run([sys.executable, "-I", str(PLUGIN / "scripts/pure_check.py")], input=json.dumps(payload),
                              env=env, capture_output=True, text=True)

    def test_a_project_that_does_not_declare_itself_pure_is_left_alone(self):
        r = self.check("claude --model haiku")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_a_pure_project_opened_without_the_flags_is_warned(self):
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/puro").write_text("")
        r = self.check("claude --model haiku")
        self.assertEqual(r.returncode, 0, "avisa, não impede a sessão")
        out = json.loads(r.stdout)
        self.assertIn("`cc`", out["systemMessage"])
        self.assertIn("global", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_a_pure_project_opened_with_the_flags_is_quiet(self):
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/puro").write_text("")
        r = self.check(f"claude {FLAGS} --mcp-config /x/.claude/mcp.json")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_user_settings_back_in_is_not_pure(self):
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/puro").write_text("")
        for args in ("claude --setting-sources user,project,local --strict-mcp-config",
                     "claude --setting-sources project,local", "claude --setting-sources=project,local --strict-mcp-config x"):
            out = self.check(args).stdout
            self.assertEqual(bool(out), "user" in args or "strict" not in args, args)

    def test_it_never_breaks_the_session(self):
        r = subprocess.run([sys.executable, "-I", str(PLUGIN / "scripts/pure_check.py")], input="não é json",
                           capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR="/nao/existe"))
        self.assertEqual(r.returncode, 0)


class TestMakePure(unittest.TestCase):
    """`fullchico-harness puro`: marca o projeto e traz do global só a ferramenta pessoal, para o escopo local."""

    def setUp(self):
        self.repo = make_repo()
        self.home = _tmpdir()
        (self.home / ".claude").mkdir()
        orca = 'if [ -f "${HOME-}/.orca/agent-hooks/claude-hook.sh" ]; then x; fi'
        (self.home / ".claude/settings.json").write_text(json.dumps({
            "enabledPlugins": {"superpowers@m": True},
            "statusLine": {"type": "command", "command": "orca-statusline"},
            "hooks": {
                "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"},
                                                             {"type": "command", "command": "algo-do-superpowers"}]}],
                "Stop": [{"hooks": [{"type": "command", "command": orca}]}],
                "SubagentStop": [{"hooks": [{"type": "command", "command": orca}]}],
                "SessionStart": [{"hooks": [{"type": "command", "command": "outro-plugin start"}]}]}}))

    def run_cli(self, *args):
        env = dict(os.environ, HOME=str(self.home))
        return subprocess.run(["node", str(ROOT / "bin/harness.js"), "puro", *args], cwd=self.repo, env=env,
                              capture_output=True, text=True)

    def test_marks_the_project_and_copies_only_the_personal_tooling(self):
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.repo / ".claude/puro").exists())
        local = json.loads((self.repo / ".claude/settings.local.json").read_text())
        commands = [h["command"] for groups in local["hooks"].values() for g in groups for h in g["hooks"]]
        self.assertIn("rtk hook claude", commands)
        self.assertTrue(any(".orca/agent-hooks" in c for c in commands))
        self.assertNotIn("algo-do-superpowers", commands)
        self.assertNotIn("outro-plugin start", commands)
        self.assertEqual(local["statusLine"]["command"], "orca-statusline")
        self.assertIn("Stop", local["hooks"])
        self.assertIn("SubagentStop", local["hooks"], "o mesmo comando do Orca em vários eventos: copia em todos")
        self.assertNotIn("enabledPlugins", local)
        self.assertIn("`cc`", r.stdout)

    def test_keeps_what_the_local_file_already_has_and_is_idempotent(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/settings.local.json").write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}}))
        self.run_cli()
        self.run_cli()
        local = json.loads((self.repo / ".claude/settings.local.json").read_text())
        self.assertEqual(local["permissions"], {"allow": ["Bash(ls)"]})
        commands = [h["command"] for groups in local["hooks"].values() for g in groups for h in g["hooks"]]
        self.assertEqual(commands.count("rtk hook claude"), 1)

    def test_the_local_file_never_goes_to_the_repository(self):
        self.run_cli()
        ignored = subprocess.run(["git", "check-ignore", "-q", ".claude/settings.local.json"], cwd=self.repo)
        self.assertEqual(ignored.returncode, 0)


class TestPackaging(unittest.TestCase):
    def test_the_plugin_is_in_the_marketplace_and_wires_its_own_hook(self):
        market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        entry = next(p for p in market["plugins"] if p["name"] == "tr")
        self.assertEqual(entry["source"], "./plugins/tr")
        manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(manifest["name"], "tr")
        hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
        command = hooks["SessionStart"][0]["hooks"][0]["command"]
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/pure_check.py", command)

    def test_the_package_ships_the_launcher_and_the_new_plugins(self):
        package = json.loads((ROOT / "package.json").read_text())
        self.assertEqual(package["bin"]["cc"], "bin/cc")
        self.assertIn("plugins/", package["files"])
        self.assertTrue(os.access(LAUNCHER, os.X_OK))


if __name__ == "__main__":
    unittest.main()
