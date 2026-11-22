"""Plugins registram o próprio portão: apertar é automático; afrouxar é só do dono."""
import json
import os
import shutil
import subprocess
import sys
import unittest

from tests.helpers import ROOT, _tmpdir, commit_all, git, make_repo
from tests.test_plugin_qualidade import fake_claude

TRILHO = ROOT / "plugins/trilho"
NODE = shutil.which("node")


class Base(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.home = _tmpdir()
        self.bin = _tmpdir()
        fake_claude(self.bin)
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", HOME=str(self.home))

    def trilho(self):
        return json.loads((self.repo / ".claude/trilho.json").read_text())

    def put_trilho(self, data):
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/trilho.json").write_text(json.dumps(data))

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
    def test_qualidade_discovers_the_command_from_the_project(self):
        self.pkg({"lint": "x", "test": "y"}, "pnpm-lock.yaml")
        r = self.add("qualidade")
        self.assertEqual(r.returncode, 0, r.stderr)
        gate = self.trilho()["portoes"]["qualidade"]
        self.assertEqual(gate["comando"], "pnpm lint && pnpm test")
        self.assertEqual((gate["momento"], gate["assina"]), ("fim", "comando"))
        self.assertIn("portão `qualidade` registrado", r.stdout)

    def test_qualidade_without_scripts_asks_the_owner_to_define(self):
        self.add("qualidade")
        self.assertEqual(self.trilho()["portoes"]["qualidade"]["comando"], "@definir")

    def test_qualidade_uses_the_old_format_command(self):
        self.put_trilho({"qualidade": {"comando": "x"}})
        self.add("qualidade")
        data = self.trilho()
        self.assertEqual(data["portoes"]["qualidade"]["comando"], "x")
        self.assertEqual(data["qualidade"], {"comando": "x"}, "o formato antigo fica como estava")

    def test_bugs_registers_the_agent_gate(self):
        self.add("bugs")
        gate = self.trilho()["portoes"]["bugs"]
        self.assertEqual((gate["momento"], gate["assina"], gate["agente"]), ("fim", "agente", "bugs:cacador"))

    def test_existing_entry_is_never_overwritten(self):
        self.pkg({"test": "y"})
        self.put_trilho({"portoes": {"qualidade": {"momento": "fim", "assina": "comando", "comando": "make check"}}})
        r = self.add("qualidade")
        self.assertEqual(self.trilho()["portoes"]["qualidade"]["comando"], "make check")
        self.assertNotIn("registrado", r.stdout)

    def test_sandbox_protects_the_registry(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/settings.json").write_text(json.dumps({"sandbox": {"enabled": True}}))
        self.add("bugs")
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertIn(".claude/trilho.json", settings["sandbox"]["filesystem"]["denyWrite"])

    def test_plugin_without_manifest_changes_nothing(self):
        self.add("memoria")
        self.assertFalse((self.repo / ".claude/trilho.json").exists())


class TestSessionStart(Base):
    def cache(self, plugin="qualidade", version="0.1.0", entries=None):
        d = self.home / ".claude/plugins/cache/fullchico" / plugin / version
        d.mkdir(parents=True)
        (d / "portao.json").write_text(json.dumps(entries or {
            plugin: {"momento": "fim", "assina": "comando", "comando": "@descobrir", "descricao": "d"}}))

    def enable(self, *keys):
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {k: True for k in keys}}))

    def hook(self):
        env = dict(self.env, CLAUDE_PROJECT_DIR=str(self.repo))
        return subprocess.run([sys.executable, "-I", str(TRILHO / "scripts/self_register.py")], capture_output=True,
                              text=True, env=env, cwd=self.repo, input="{}")

    def test_registers_the_gate_of_an_enabled_plugin_and_logs_it(self):
        self.pkg({"test": "y"})
        self.cache()
        self.enable("qualidade@fullchico")
        r = self.hook()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.trilho()["portoes"]["qualidade"]["comando"], "npm test")
        msg = json.loads(r.stdout)["systemMessage"]
        self.assertIn("portão `qualidade` registrado automaticamente pelo plugin `qualidade`", msg)
        log = next((self.home / ".claude/trilho").glob("*/log.jsonl")).read_text()
        self.assertIn("qualidade", log)

    def test_uses_the_highest_installed_version(self):
        self.cache(version="0.1.0", entries={"x": {"momento": "fim", "assina": "comando", "comando": "velho"}})
        self.cache(version="0.10.0", entries={"x": {"momento": "fim", "assina": "comando", "comando": "novo"}})
        self.enable("qualidade@fullchico")
        self.hook()
        self.assertEqual(self.trilho()["portoes"]["x"]["comando"], "novo")

    def test_does_not_overwrite_and_stays_quiet(self):
        self.cache()
        self.enable("qualidade@fullchico")
        self.put_trilho({"portoes": {"qualidade": {"momento": "fim", "assina": "comando", "comando": "make"}}})
        r = self.hook()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        self.assertEqual(self.trilho()["portoes"]["qualidade"]["comando"], "make")

    def test_ignores_plugins_that_are_not_enabled(self):
        self.cache()
        self.enable("outro@fullchico")
        self.hook()
        self.assertFalse((self.repo / ".claude/trilho.json").exists())

    def test_project_without_gate_plugins_gets_nothing(self):
        d = self.home / ".claude/plugins/cache/fullchico/memoria/0.1.0"
        d.mkdir(parents=True)
        self.enable("memoria@fullchico")
        r = self.hook()
        self.assertEqual(r.returncode, 0)
        self.assertFalse((self.repo / ".claude/trilho.json").exists())

    def test_internal_error_exits_zero(self):
        self.enable("qualidade@fullchico")
        (self.repo / ".claude/settings.json").write_text("{quebrado")
        self.assertEqual(self.hook().returncode, 0)


class TestDefinir(Base):
    def setUp(self):
        super().setUp()
        self.put_trilho({"codigo": ["src"], "portoes": {
            "qualidade": {"momento": "fim", "assina": "comando", "comando": "@definir"},
            "bugs": {"momento": "fim", "assina": "agente", "agente": "bugs:cacador"}}})
        commit_all(self.repo, "chore: registro")
        git(self.repo, "checkout", "-q", "-b", "feat")

    def portoes(self, *args):
        return self.node("portoes", *args)

    def run_script(self, name, payload):
        env = dict(self.env, CLAUDE_PLUGIN_ROOT=str(TRILHO), CLAUDE_PROJECT_DIR=str(self.repo))
        return subprocess.run([sys.executable, str(TRILHO / "scripts" / name)], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, cwd=self.repo)

    def test_portao_fails_telling_the_owner_what_to_do(self):
        r = subprocess.run([str(TRILHO / "bin/portao"), "qualidade"], capture_output=True, text=True,
                           env=self.env, cwd=self.repo)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('fullchico-harness portoes --definir qualidade "<comando>"', r.stdout)
        self.assertNotIn("qualidade: passou", r.stdout)

    def test_send_gate_lists_it_as_missing(self):
        r = self.run_script("gate.py", {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.repo),
                                        "tool_input": {"command": "git push"}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("qualidade", r.stderr)
        self.assertIn("--definir qualidade", r.stderr)

    def test_definir_swaps_only_that_command(self):
        before = self.trilho()
        r = self.portoes("--definir", "qualidade", "npm test", "--projeto", str(self.repo))
        self.assertEqual(r.returncode, 0, r.stderr)
        after = self.trilho()
        self.assertEqual(after["portoes"]["qualidade"]["comando"], "npm test")
        before["portoes"]["qualidade"]["comando"] = "npm test"
        self.assertEqual(after, before)

    def test_definir_refuses_unknown_or_non_command_gate(self):
        self.assertNotEqual(self.portoes("--definir", "nada", "x", "--projeto", str(self.repo)).returncode, 0)
        self.assertNotEqual(self.portoes("--definir", "bugs", "x", "--projeto", str(self.repo)).returncode, 0)

    def test_the_agent_still_cannot_edit_the_registry(self):
        r = self.run_script("gate.py", {"hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(self.repo),
                                        "tool_input": {"file_path": str(self.repo / ".claude/trilho.json")}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("só o dono", r.stderr)


if __name__ == "__main__":
    unittest.main()
