"""O `install` monta o harness do projeto no modelo novo: plugins por projeto e registro de portões.

O dono escolhe o padrão da lib ou a análise do que o projeto já usa; o `--migrar` tira o harness antigo
e os plugins que o tr absorveu.
"""
import json
import os
import pty
import select
import time
import shutil
import subprocess
import unittest

from tests.helpers import ROOT, _tmpdir, commit_all, fake_claude, fake_npx, make_repo


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
        fake_npx(self.bin)

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
        self.assertTrue((self.repo / ".agents/plugins/marketplace.json").exists(), "sem TTY, o padrão também instala Codex")

    def test_ambos_installs_claude_and_codex_with_one_registry(self):
        r = self.install("--ambiente", "ambos", "--padrao")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("plugin install tr@fullchico --scope project", self.calls())
        self.assertTrue((self.repo / ".agents/plugins/marketplace.json").exists())
        self.assertTrue((self.repo / ".claude/trilho.json").exists())
        self.assertEqual(json.loads((self.repo / ".claude/trilho.json").read_text())["portoes"]["bugs"]["agente"],
                         "tr:bugs-cacador")

    def test_codex_selection_does_not_call_claude(self):
        r = self.install("--ambiente", "codex", "--padrao")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.bin / "calls").exists())
        self.assertTrue((self.repo / ".agents/plugins/marketplace.json").exists())
        calls = (self.bin / "npx-calls").read_text()
        self.assertIn("skills add DietrichGebert/ponytail", calls)
        self.assertIn("skills add mattpocock/skills", calls)

    def test_invalid_environment_stops_before_changes(self):
        r = self.install("--ambiente", "outro")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--ambiente deve ser", r.stderr)
        self.assertFalse((self.bin / "calls").exists())
        self.assertFalse((self.repo / ".codex").exists())

    def test_interactive_menu_selects_codex(self):
        master, slave = pty.openpty()
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")
        try:
            proc = subprocess.Popen([shutil.which("node"), str(ROOT / "bin/harness.js"), "install",
                                     str(self.repo), "--padrao"], stdin=slave, stdout=slave,
                                    stderr=subprocess.PIPE, env=env)
            os.close(slave)
            os.write(master, b"2\n")
            deadline = time.monotonic() + 15
            while proc.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        os.read(master, 4096)
                    except OSError:
                        break
            if proc.poll() is None:
                proc.kill()
            _, stderr = proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 0, stderr.decode())
        finally:
            os.close(master)
        self.assertTrue((self.repo / ".agents/plugins/marketplace.json").exists())
        self.assertFalse((self.bin / "calls").exists())

    def test_interactive_menu_waits_for_input_on_nonblocking_tty(self):
        master, slave = pty.openpty()
        os.set_blocking(slave, False)
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")
        try:
            proc = subprocess.Popen([shutil.which("node"), str(ROOT / "bin/harness.js"), "install",
                                     str(self.repo), "--padrao"], stdin=slave, stdout=slave,
                                    stderr=subprocess.PIPE, env=env)
            os.close(slave)
            output = b""
            deadline = time.monotonic() + 5
            while b"Escolha [3]:" not in output and proc.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        output += os.read(master, 4096)
                    except OSError:
                        break
            self.assertIn(b"Escolha [3]:", output)
            time.sleep(0.2)
            self.assertIsNone(proc.poll(), "o menu deve esperar a resposta mesmo com EAGAIN")
            os.write(master, b"2\n")
            deadline = time.monotonic() + 15
            while proc.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        os.read(master, 4096)
                    except OSError:
                        break
            if proc.poll() is None:
                proc.kill()
            _, stderr = proc.communicate(timeout=5)
            self.assertEqual(proc.returncode, 0, stderr.decode())
        finally:
            os.close(master)
        self.assertTrue((self.repo / ".agents/plugins/marketplace.json").exists())

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

    def test_the_bug_gate_is_signed_by_the_tr_agent(self):
        # o caçador é do tr: nenhum plugin a mais para o portão `bugs`
        self.assertEqual(self.install("--padrao").returncode, 0)
        gates = json.loads((self.repo / ".claude/trilho.json").read_text())["portoes"]
        self.assertEqual(gates["bugs"]["agente"], "tr:bugs-cacador")
        self.assertNotIn("plugin install bugs@fullchico --scope project", self.calls())

    def test_an_existing_registry_is_kept(self):
        reg = {"portoes": {"e2e": {"momento": "fim", "assina": "comando", "comando": "pnpm e2e"}}}
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/trilho.json").write_text(json.dumps(reg))
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((self.repo / ".claude/trilho.json").read_text()), reg)
        self.assertIn("existente mantido", r.stdout)

    def test_an_unreadable_settings_file_stops_before_changing_anything(self):
        local = self.repo / ".claude/settings.local.json"
        local.parent.mkdir(exist_ok=True)
        local.write_text('{"permissions": {"allow": ["Bash(ls)"],}}')
        r = self.install()
        self.assertEqual(r.returncode, 1)
        self.assertIn("não é JSON válido", r.stderr)
        self.assertEqual(local.read_text(), '{"permissions": {"allow": ["Bash(ls)"],}}')
        self.assertFalse((self.bin / "calls").exists(), "nenhum plugin instalado")

    def test_writes_the_local_model_config_keeping_what_is_there(self):
        local = self.repo / ".claude/settings.local.json"
        local.parent.mkdir(exist_ok=True)
        local.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "env": {"X": "1"}}))
        self.assertEqual(self.install().returncode, 0)
        data = json.loads(local.read_text())
        self.assertEqual(data["model"], "opus")
        self.assertEqual(data["env"], {"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet", "X": "1"})
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})

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

    def test_migrar_cleans_what_the_old_harness_and_the_absorbed_plugins_left(self):
        """O caso do elephantfish: o AGENTS.md mandava `.harness/push`, e as permissões deixavam."""
        settings = self.repo / ".claude/settings.json"
        settings.parent.mkdir(exist_ok=True)
        settings.write_text(json.dumps({
            "permissions": {"allow": ["Bash(.harness/push)", "Bash(ls)"], "deny": ["Edit(/.harness/**)"],
                            "ask": ["Bash(./.harness/destroy)"]},
            "hooks": {"SubagentStop": [{"matcher": "^harness:(seguranca|revisor)$", "hooks": [
                {"type": "command", "command": "python3 x.py"}]}],
                "SessionStart": [{"hooks": [{"type": "command", "command": '"$CLAUDE_PROJECT_DIR/.harness/ports-free"'}]}]},
            "sandbox": {"enabled": True, "excludedCommands": [".harness/up", "docker"]},
            "enabledPlugins": {"tr@fullchico": True, "bugs@fullchico": True, "qualidade@fullchico": True}}))
        (self.repo / ".claude/trilho.json").write_text(json.dumps({"portoes": {
            "bugs": {"momento": "fim", "assina": "agente", "agente": "bugs:cacador"},
            "seo": {"momento": "fim", "assina": "comando", "comando": "pnpm seo"}}}))
        r = self.install("--migrar")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(settings.read_text())
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"], "deny": [], "ask": []})
        self.assertNotIn("SubagentStop", data["hooks"])
        self.assertNotIn("SessionStart", data["hooks"])
        self.assertEqual(data["sandbox"]["excludedCommands"], ["docker"])
        self.assertNotIn("bugs@fullchico", data["enabledPlugins"])
        self.assertNotIn("qualidade@fullchico", data["enabledPlugins"])
        gates = json.loads((self.repo / ".claude/trilho.json").read_text())["portoes"]
        self.assertEqual(gates["bugs"]["agente"], "tr:bugs-cacador")
        self.assertEqual(gates["seo"]["comando"], "pnpm seo", "os portões do dono ficam")
        self.assertIn("AGENTS.md", r.stdout)

    def test_not_a_repository_is_refused(self):
        r = subprocess.run([shutil.which("node"), str(ROOT / "bin/harness.js"), "install", "/caminho/que/nao/existe"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("não é uma pasta do projeto", r.stderr)

    def test_install_initializes_local_git_without_remote(self):
        project = _tmpdir()
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")
        run = subprocess.run([shutil.which("node"), str(ROOT / "bin/harness.js"), "install", str(project),
                              "--ambiente", "claude", "--padrao"], capture_output=True, text=True, env=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue((project / ".git").is_dir())
        remotes = subprocess.run(["git", "-C", str(project), "remote"], capture_output=True, text=True)
        self.assertEqual(remotes.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
