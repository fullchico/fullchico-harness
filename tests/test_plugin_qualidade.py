"""Plugin `qualidade`: a checagem é do projeto; o hook carimba o commit limpo que passou; o gate barra o envio sem ele."""
import json
import os
import shutil
import stat
import subprocess
import unittest

from tests.helpers import ROOT, _tmpdir, commit_all, git
from tests.test_plugin_bugs import GateCases, PluginCase, ledger

PLUGIN = ROOT / "plugins/qualidade"
CHECK = PLUGIN / "bin/qualidade-check"


def fake_claude(folder):
    """Um `claude` de mentira que só registra os argumentos, um comando por linha."""
    path = folder / "claude"
    path.write_text(f'#!/bin/sh\necho "$*" >> "{folder}/calls"\n')
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return folder


class QualidadeCase(PluginCase):
    plugin = PLUGIN
    stamp = "qualidade"

    def configure(self, comando):
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/trilho.json").write_text(json.dumps({"qualidade": {"comando": comando}}))
        commit_all(self.repo, "chore: trilho")
        self.head = git(self.repo, "rev-parse", "HEAD")

    def check(self):
        return subprocess.run([str(CHECK)], cwd=self.repo, capture_output=True, text=True)


class TestCheck(QualidadeCase):
    def test_without_configuration_it_explains_and_fails(self):
        r = self.check()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("trilho.json", r.stdout + r.stderr)
        self.assertNotIn("qualidade: passou", r.stdout)

    def test_passing_command(self):
        self.configure("echo ok-do-projeto")
        r = self.check()
        self.assertEqual(r.returncode, 0)
        self.assertIn("ok-do-projeto", r.stdout)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "qualidade: passou")

    def test_failing_command_keeps_its_exit_code(self):
        self.configure("printf sem-fim-de-linha; exit 3")
        r = self.check()
        self.assertEqual(r.returncode, 3)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "qualidade: FALHOU (printf sem-fim-de-linha; exit 3)")

    def test_it_runs_at_the_project_root_from_a_subfolder(self):
        self.configure("ls .claude/trilho.json")
        r = subprocess.run([str(CHECK)], cwd=self.repo / ".claude", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_it_writes_nothing(self):
        self.configure("true")
        self.check()
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertFalse(self.signed())

    def test_manifest_and_hooks(self):
        meta = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
        self.assertEqual((meta["name"], meta["version"]), ("qualidade", "0.1.0"))
        hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
        self.assertEqual(hooks["PostToolUse"][0]["matcher"], "Bash")
        self.assertEqual(hooks["PreToolUse"][0]["matcher"], "Bash")
        self.assertTrue(os.access(CHECK, os.X_OK))
        self.assertTrue((PLUGIN / "skills/qualidade/SKILL.md").exists())


class TestStamp(QualidadeCase, GateCases):
    def post(self, command="qualidade-check", response=None, event="PostToolUse"):
        if response is None:
            response = {"stdout": "tudo certo\n\nqualidade: passou\n", "stderr": "", "interrupted": False}
        return self.run_script("stamp.py", {"hook_event_name": event, "tool_name": "Bash", "cwd": str(self.repo),
                                            "tool_input": {"command": command}, "tool_response": response})

    def test_the_exact_form_on_a_clean_tree_signs_head(self):
        r = self.post()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.signed())

    def test_spaces_at_the_ends_are_accepted(self):
        self.assertEqual(self.post("  qualidade-check \n").returncode, 0)
        self.assertTrue(self.signed())

    def test_other_forms_do_not_sign(self):
        for cmd in ("qualidade-check && echo x", "echo qualidade-check", "qualidade-check; true", "true; qualidade-check",
                    "qualidade-check --x", "./qualidade-check", "ls"):
            self.assertEqual(self.post(cmd).returncode, 0, cmd)
            self.assertFalse(self.signed(), cmd)

    def test_a_dirty_tree_does_not_sign_and_tells_the_agent(self):
        (self.repo / "sujo.txt").write_text("x")
        r = self.post()
        self.assertEqual(r.returncode, 2)
        self.assertIn("faça o commit antes de rodar qualidade-check", r.stderr)
        self.assertFalse(self.signed())
        self.assertIn("árvore suja", self.read("log.jsonl"))

    def test_a_failure_does_not_sign(self):
        self.assertEqual(self.post(event="PostToolUseFailure", response="erro").returncode, 0)
        self.assertFalse(self.signed())
        self.post(response={"stdout": "qualidade: FALHOU (x)\n"})
        self.assertFalse(self.signed())

    def test_an_unreadable_response_trusts_the_success_event(self):
        self.post(response={"algo": "novo"})
        self.assertTrue(self.signed())

    def test_it_never_breaks(self):
        self.assertEqual(self.run_script("stamp.py", None, raw="lixo").returncode, 0)


class TestAdd(unittest.TestCase):
    def run_add(self, *args, with_claude=True):
        self.bin = _tmpdir()
        if with_claude:
            fake_claude(self.bin)
            path = f"{self.bin}:{os.environ['PATH']}"
        else:  # sem claude: o PATH só tem uma pasta vazia (o node é chamado pelo caminho)
            path = str(self.bin)
        self.project = getattr(self, "project", None) or _tmpdir()
        return subprocess.run([shutil.which("node"), str(ROOT / "bin/harness.js"), "add", *args, "--project", str(self.project)],
                              capture_output=True, text=True, env=dict(os.environ, PATH=path))

    def calls(self):
        return (self.bin / "calls").read_text().splitlines()

    def test_add_registers_the_marketplace_and_installs_each_plugin_in_the_project(self):
        r = self.run_add("bugs", "qualidade")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), ["plugin marketplace add FullChico/fullchico-harness",
                                        "plugin install bugs@fullchico --scope project",
                                        "plugin install qualidade@fullchico --scope project"])
        self.assertIn("claude plugin install bugs@fullchico --scope project", r.stdout)

    def test_without_claude_it_prints_the_commands(self):
        r = self.run_add("bugs", with_claude=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("claude plugin marketplace add FullChico/fullchico-harness", r.stdout)
        self.assertIn("claude plugin install bugs@fullchico --scope project", r.stdout)

    def test_warns_when_the_project_has_no_sandbox(self):
        # Sem sandbox o agente consegue gravar no estado dos carimbos: o portão vira sugestão.
        r = self.run_add("bugs")
        self.assertIn("sandbox", r.stdout)
        self.assertIn("forjar", r.stdout)
        (self.project / ".claude").mkdir(exist_ok=True)
        (self.project / ".claude/settings.json").write_text('{"sandbox": {"enabled": true}}')
        self.assertNotIn("forjar", self.run_add("bugs").stdout)

    def test_without_plugin_names_it_shows_usage(self):
        r = subprocess.run(["node", str(ROOT / "bin/harness.js"), "add"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("add <plugin>", r.stderr)


if __name__ == "__main__":
    unittest.main()
