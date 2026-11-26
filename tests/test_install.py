"""O `install` monta o harness do projeto no modelo novo: plugins por projeto e registro de portões.

O dono escolhe o padrão do plugin ou a análise do que o projeto já usa; o `--migrate` tira o harness antigo
e os plugins que o tr absorveu.
"""
import json
import os
import fcntl
import pty
import struct
import termios
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

    def test_default_installs_the_plugins_without_registering_gates(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        # O plugin cuida do caminho e da aprendizagem: o núcleo é tr e memory. Começo e fim são do projeto.
        for name in ("tr", "memory"):
            self.assertIn(f"plugin install {name}@fullchico --scope project", self.calls())
            self.assertIn(f"plugin update {name}@fullchico --scope project", self.calls())
        self.assertIn("plugin marketplace update fullchico", self.calls())
        for name in ("bugs", "quality"):
            self.assertNotIn(f"plugin install {name}@fullchico --scope project", self.calls())
        # ponytail (código mínimo e reutilizável) vem junto, do marketplace dele
        self.assertIn("plugin marketplace add DietrichGebert/ponytail", self.calls())
        self.assertIn("plugin install ponytail@ponytail --scope project", self.calls())
        # mattpocock-skills (process: grilling, tdd, revisão) vem junto, do marketplace oficial
        self.assertIn("plugin marketplace add anthropics/claude-plugins-official", self.calls())
        self.assertIn("plugin install mattpocock-skills@claude-plugins-official --scope project", self.calls())
        # rtk não é plugin: é um programa da máquina; entra como hook do projeto, que só roda se ele existir
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertNotIn("sandbox", settings, "o harness não liga o sandbox nativo por padrão")
        hooks = [h["command"] for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertTrue(any("rtk hook claude" in c and "command -v rtk" in c for c in hooks), hooks)
        self.assertFalse((self.repo / ".claude/harness.json").exists())
        self.assertIn("Nenhum portão cadastrado", r.stdout)
        self.assertIn("Abra o projeto com `claude`", r.stdout)
        self.assertTrue((self.repo / ".agents/plugins/marketplace.json").exists(), "sem TTY, o padrão também instala Codex")

    def test_ambos_installs_claude_and_codex_with_one_registry(self):
        r = self.install("--target", "both", "--default")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("plugin install tr@fullchico --scope project", self.calls())
        self.assertTrue((self.repo / ".agents/plugins/marketplace.json").exists())
        self.assertTrue((self.repo / ".claude/harness.json").exists())
        self.assertEqual(json.loads((self.repo / ".claude/harness.json").read_text())["gates"]["bugs"]["agent"],
                         "tr:bug-hunter")

    def test_codex_selection_does_not_call_claude(self):
        r = self.install("--target", "codex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.bin / "calls").exists())
        self.assertTrue((self.repo / ".agents/plugins/marketplace.json").exists())
        self.assertFalse((self.repo / ".claude/harness.json").exists())
        calls = (self.bin / "npx-calls").read_text()
        self.assertIn("skills add DietrichGebert/ponytail", calls)
        self.assertIn("skills add mattpocock/skills --skill grilling domain-modeling tdd", calls)

    def test_invalid_environment_stops_before_changes(self):
        r = self.install("--target", "outro")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--target deve ser", r.stderr)
        self.assertFalse((self.bin / "calls").exists())
        self.assertFalse((self.repo / ".codex").exists())

    def test_interactive_menu_selects_codex(self):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))  # terminal de verdade, com largura
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")
        try:
            proc = subprocess.Popen([shutil.which("node"), str(ROOT / "bin/harness.js"), "install",
                                     str(self.repo), "--default"], stdin=slave, stdout=slave,
                                    stderr=subprocess.PIPE, env=env)
            os.close(slave)
            output, deadline = b"", time.monotonic() + 10
            while b"qual ambiente" not in output and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    output += os.read(master, 4096)
            os.write(master, b"\x1b[B\x1b[B\r")  # duas setas para baixo: Codex
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
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))  # terminal de verdade, com largura
        os.set_blocking(slave, False)
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")
        try:
            proc = subprocess.Popen([shutil.which("node"), str(ROOT / "bin/harness.js"), "install",
                                     str(self.repo), "--default"], stdin=slave, stdout=slave,
                                    stderr=subprocess.PIPE, env=env)
            os.close(slave)
            output = b""
            deadline = time.monotonic() + 5
            while b"qual ambiente" not in output and proc.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        output += os.read(master, 4096)
                    except OSError:
                        break
            self.assertIn(b"qual ambiente", output)
            time.sleep(0.2)
            self.assertIsNone(proc.poll(), "o menu deve esperar a resposta mesmo com stdin não bloqueante")
            os.write(master, b"\x1b[B\x1b[B\r")
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

    def test_the_flow_is_written_where_the_agent_always_reads(self):
        (self.repo / "CLAUDE.md").write_text("# Meu projeto\n\nRegras do dono.\n")
        self.assertEqual(self.install().returncode, 0)
        self.install()
        for name in ("CLAUDE.md", "AGENTS.md"):
            text = (self.repo / name).read_text()
            self.assertEqual(text.count("<!-- fullchico-harness:begin -->"), 1, name)
            self.assertIn("/tr:process-plan", text)
        self.assertTrue((self.repo / "CLAUDE.md").read_text().startswith("# Meu projeto\n\nRegras do dono.\n\n"))

    def test_sandbox_profile_is_opt_in_and_keeps_docker_outside(self):
        self.assertEqual(self.install("--sandbox").returncode, 0)
        self.install("--sandbox")
        sandbox = json.loads((self.repo / ".claude/settings.json").read_text())["sandbox"]
        self.assertIs(sandbox["enabled"], True)
        self.assertEqual(sandbox["filesystem"]["denyWrite"], [".claude/harness.json"])
        self.assertEqual(sandbox["excludedCommands"], ["docker", "fullchico-harness"])

    def test_padrao_uses_the_library_default(self):
        self.assertEqual(self.install("--default").returncode, 0)
        gates = json.loads((self.repo / ".claude/harness.json").read_text())["gates"]
        self.assertEqual(set(gates), {"process", "domain", "quality", "bugs", "scope"})

    def test_the_bug_gate_is_signed_by_the_tr_agent(self):
        # o caçador é do tr: nenhum plugin a mais para o portão `bugs`
        self.assertEqual(self.install("--default").returncode, 0)
        gates = json.loads((self.repo / ".claude/harness.json").read_text())["gates"]
        self.assertEqual(gates["bugs"]["agent"], "tr:bug-hunter")
        self.assertNotIn("plugin install bugs@fullchico --scope project", self.calls())

    def test_an_existing_registry_is_kept(self):
        reg = {"gates": {"e2e": {"stage": "end", "signs": "command", "command": "pnpm e2e"}}}
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/harness.json").write_text(json.dumps(reg))
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((self.repo / ".claude/harness.json").read_text()), reg)
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
        self.install("--default")
        gates = json.loads((self.repo / ".claude/harness.json").read_text())["gates"]
        self.assertEqual(gates["quality"]["command"], "pnpm lint && pnpm test")

    def test_pins_the_marketplace_to_this_version(self):
        settings = self.repo / ".claude/settings.json"
        settings.parent.mkdir(exist_ok=True)
        settings.write_text(json.dumps({"extraKnownMarketplaces": {"fullchico": {"source": {
            "source": "github", "repo": "FullChico/fullchico-harness", "ref": "v0.1.8"}}}}))
        self.assertEqual(self.install().returncode, 0)
        version = json.loads((ROOT / "package.json").read_text())["version"]
        ref = json.loads(settings.read_text())["extraKnownMarketplaces"]["fullchico"]["source"]["ref"]
        self.assertEqual(ref, f"v{version}")

    def test_a_local_source_is_installed_before_publishing(self):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", FULLCHICO_HARNESS_SOURCE=str(ROOT))
        r = subprocess.run([shutil.which("node"), str(ROOT / "bin/harness.js"), "install", str(self.repo)],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        source = json.loads((self.repo / ".claude/settings.json").read_text())["extraKnownMarketplaces"]["fullchico"]["source"]
        self.assertEqual(source, {"source": "directory", "path": str(ROOT)})
        self.assertIn(f"plugin marketplace add {ROOT}", self.calls())

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

    def test_the_old_harness_is_reported_and_kept_without_migrate(self):
        settings = self.legacy_settings()
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("harness antigo", r.stdout)
        self.assertIn("--migrate", r.stdout)
        self.assertTrue(json.loads(settings.read_text())["enabledPlugins"]["harness@fullchico"])

    def test_migrate_turns_the_old_harness_off_and_keeps_the_rest(self):
        settings = self.legacy_settings()
        self.assertEqual(self.install("--migrate").returncode, 0)
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
        r = self.install("--default")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fora da sessão", r.stderr)
        self.assertFalse((self.bin / "calls").exists(), "nenhum plugin instalado")
        self.assertFalse((self.repo / ".claude/harness.json").exists())
        self.assertNotIn("Próximos passos", r.stdout)

    def test_migrate_cleans_what_the_old_harness_and_the_absorbed_plugins_left(self):
        """O caso do elephantfish: o AGENTS.md mandava `.harness/push`, e as permissões deixavam."""
        settings = self.repo / ".claude/settings.json"
        settings.parent.mkdir(exist_ok=True)
        settings.write_text(json.dumps({
            "permissions": {"allow": ["Bash(.harness/push)", "Bash(ls)"], "deny": ["Edit(/.harness/**)"],
                            "ask": ["Bash(./.harness/destroy)"]},
            "hooks": {"SubagentStop": [{"matcher": "^harness:(security|revisor)$", "hooks": [
                {"type": "command", "command": "python3 x.py"}]}],
                "SessionStart": [{"hooks": [{"type": "command", "command": '"$CLAUDE_PROJECT_DIR/.harness/ports-free"'}]}]},
            "sandbox": {"enabled": True, "excludedCommands": [".harness/up", "docker"]},
            "enabledPlugins": {"tr@fullchico": True, "bugs@fullchico": True, "qualidade@fullchico": True}}))
        (self.repo / ".claude/harness.json").write_text(json.dumps({"gates": {
            "bugs": {"stage": "end", "signs": "agent", "agent": "bugs:cacador"},
            "seo": {"stage": "end", "signs": "command", "command": "pnpm seo"}}}))
        r = self.install("--migrate")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(settings.read_text())
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"], "deny": [], "ask": []})
        self.assertNotIn("SubagentStop", data["hooks"])
        self.assertNotIn("SessionStart", data["hooks"])
        self.assertEqual(data["sandbox"]["excludedCommands"], ["docker"])
        self.assertNotIn("bugs@fullchico", data["enabledPlugins"])
        self.assertNotIn("qualidade@fullchico", data["enabledPlugins"])
        gates = json.loads((self.repo / ".claude/harness.json").read_text())["gates"]
        self.assertEqual(gates["bugs"]["agent"], "tr:bug-hunter")
        self.assertEqual(gates["seo"]["command"], "pnpm seo", "os portões do dono ficam")
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
                              "--target", "claude", "--default"], capture_output=True, text=True, env=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue((project / ".git").is_dir())
        remotes = subprocess.run(["git", "-C", str(project), "remote"], capture_output=True, text=True)
        self.assertEqual(remotes.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
