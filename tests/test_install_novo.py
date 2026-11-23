"""O `install` monta o harness do projeto no modelo novo: plugins por projeto e registro de portões.

O dono escolhe o padrão da lib ou a análise do que o projeto já usa. O monólito antigo segue em
`install --legado`, para quem ainda depende dele.
"""
import json
import os
import shutil
import subprocess
import unittest

from tests.helpers import ROOT, _tmpdir, commit_all, make_repo
from tests.test_plugin_qualidade import fake_claude


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        (self.repo / "package.json").write_text(json.dumps({"scripts": {"lint": "x", "test": "y"}}))
        (self.repo / "pnpm-lock.yaml").write_text("")
        (self.repo / "docs/specs").mkdir(parents=True)
        (self.repo / "apps").mkdir()
        commit_all(self.repo, "chore: scaffold")
        self.bin = _tmpdir()
        fake_claude(self.bin)

    def install(self, *args):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")
        return subprocess.run([shutil.which("node"), str(ROOT / "bin/harness.js"), "install", str(self.repo), *args],
                              capture_output=True, text=True, env=env)

    def calls(self):
        return (self.bin / "calls").read_text().splitlines()

    def test_default_installs_the_plugins_and_registers_the_gates_from_the_project(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        # A lib cuida do caminho e da aprendizagem: o núcleo é tr e memoria. Começo e fim são do projeto.
        for name in ("tr", "memoria"):
            self.assertIn(f"plugin install {name}@fullchico --scope project", self.calls())
        for name in ("bugs", "qualidade"):
            self.assertNotIn(f"plugin install {name}@fullchico --scope project", self.calls())
        # ponytail (código mínimo e reutilizável) vem junto, do marketplace dele
        self.assertIn("plugin marketplace add DietrichGebert/ponytail", self.calls())
        self.assertIn("plugin install ponytail@ponytail --scope project", self.calls())
        # mattpocock-skills (processo: grilling, tdd, revisão) vem junto, do marketplace oficial
        self.assertIn("plugin marketplace add anthropics/claude-plugins-official", self.calls())
        self.assertIn("plugin install mattpocock-skills@claude-plugins-official --scope project", self.calls())
        # rtk não é plugin: é um programa da máquina; entra como hook do projeto, que só roda se ele existir
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        hooks = [h["command"] for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertTrue(any("rtk hook claude" in c and "command -v rtk" in c for c in hooks), hooks)
        gates = json.loads((self.repo / ".claude/trilho.json").read_text())["portoes"]
        self.assertEqual(gates["qualidade"]["comando"], "pnpm lint && pnpm test", "veio do package.json do projeto")
        self.assertEqual(gates["processo"]["artefato"], "docs/specs/*/spec.md")
        self.assertIn("`cc`", r.stdout)

    def test_running_it_twice_does_not_duplicate_the_rtk_hook(self):
        self.install()
        self.install()
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        hooks = [h["command"] for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertEqual(sum("rtk hook claude" in c for c in hooks), 1)

    def test_padrao_uses_the_library_default(self):
        self.assertEqual(self.install("--padrao").returncode, 0)
        gates = json.loads((self.repo / ".claude/trilho.json").read_text())["portoes"]
        self.assertEqual(set(gates), {"processo", "qualidade", "bugs"})

    def test_padrao_installs_the_plugin_that_signs_the_agent_gate(self):
        # o padrão grava o portão `bugs` (agente `bugs:cacador`): sem o plugin, ninguém o assinaria
        self.assertEqual(self.install("--padrao").returncode, 0)
        self.assertIn("plugin install bugs@fullchico --scope project", self.calls())
        self.assertNotIn("plugin install qualidade@fullchico --scope project", self.calls())

    def test_padrao_takes_the_quality_command_from_the_project(self):
        self.install("--padrao")
        gates = json.loads((self.repo / ".claude/trilho.json").read_text())["portoes"]
        self.assertEqual(gates["qualidade"]["comando"], "pnpm lint && pnpm test")

    def test_pins_the_marketplace_to_this_version(self):
        settings = self.repo / ".claude/settings.json"
        settings.parent.mkdir(exist_ok=True)
        settings.write_text(json.dumps({"extraKnownMarketplaces": {"fullchico": {"source": {
            "source": "github", "repo": "FullChico/fullchico-harness", "ref": "v0.1.8"}}}}))
        self.assertEqual(self.install().returncode, 0)
        version = json.loads((ROOT / "package.json").read_text())["version"]
        ref = json.loads(settings.read_text())["extraKnownMarketplaces"]["fullchico"]["source"]["ref"]
        self.assertEqual(ref, f"v{version}")

    def legacy_settings(self):
        settings = self.repo / ".claude/settings.json"
        settings.parent.mkdir(exist_ok=True)
        settings.write_text(json.dumps({
            "enabledPlugins": {"harness@fullchico": True},
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
                {"type": "command", "command": 'python3 -I "$CLAUDE_PROJECT_DIR/.harness/hooks/service_guard.py"'},
                {"type": "command", "command": "echo outro"}]}],
                "SessionStart": [{"hooks": [
                    {"type": "command", "command": 'python3 -I "$CLAUDE_PROJECT_DIR/.harness/hooks/session_context.py"'}]}]}}))
        return settings

    def test_the_old_harness_is_reported_and_kept_without_migrar(self):
        settings = self.legacy_settings()
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("harness antigo", r.stdout)
        self.assertIn("--migrar", r.stdout)
        self.assertTrue(json.loads(settings.read_text())["enabledPlugins"]["harness@fullchico"])

    def test_migrar_turns_the_old_harness_off_and_keeps_the_rest(self):
        settings = self.legacy_settings()
        self.assertEqual(self.install("--migrar").returncode, 0)
        data = json.loads(settings.read_text())
        self.assertFalse(data["enabledPlugins"]["harness@fullchico"])
        commands = [h["command"] for groups in data["hooks"].values() for g in groups for h in g["hooks"]]
        self.assertFalse(any(".harness/hooks/" in c for c in commands), commands)
        self.assertIn("echo outro", commands)
        self.assertNotIn("SessionStart", data["hooks"])

    def test_refuses_to_start_when_the_settings_cannot_be_written(self):
        # dentro de uma sessão com sandbox o settings é protegido: nada pela metade, e o recado é claro
        settings = self.repo / ".claude/settings.json"
        settings.parent.mkdir(exist_ok=True)
        settings.write_text("{}\n")
        settings.chmod(0o444)
        self.addCleanup(settings.chmod, 0o644)
        r = self.install("--padrao")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fora da sessão", r.stderr)
        self.assertFalse((self.bin / "calls").exists(), "nenhum plugin instalado")
        self.assertFalse((self.repo / ".claude/trilho.json").exists())
        self.assertNotIn("Próximos passos", r.stdout)

    def test_legacy_still_runs_the_old_installer(self):
        r = self.install("--legado")
        self.assertTrue((self.repo / ".harness").exists() or "harness" in (r.stdout + r.stderr).lower(), r.stderr)
        self.assertNotIn("plugin install tr@fullchico --scope project", self.calls() if (self.bin / "calls").exists() else [])

    def test_not_a_repository_is_refused(self):
        r = subprocess.run([shutil.which("node"), str(ROOT / "bin/harness.js"), "install", "/caminho/que/nao/existe"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("não é um repositório git", r.stderr)


if __name__ == "__main__":
    unittest.main()
