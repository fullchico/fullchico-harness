import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tests.helpers import ROOT, make_repo
sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
import ledger
import registry


class ModelosCliTest(unittest.TestCase):
    def run_cli(self, repo, *args, env=None):
        return subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/modelos.py"), *args],
                              cwd=repo, capture_output=True, text=True, env=env)

    def test_configure_and_show_keeps_other_registry_data_and_displays_mirror(self):
        repo = make_repo()
        (repo / ".claude").mkdir()
        path = repo / ".claude/trilho.json"
        path.write_text(json.dumps({"codigo": ["src"], "portoes": {"q": {"momento": "fim",
                                                                           "assina": "comando", "comando": "true"}}}))
        result = self.run_cli(repo, "configurar", "planejamento", "claude:opus", "revisao", "codex:sol")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(path.read_text())
        self.assertEqual(data["codigo"], ["src"])
        self.assertEqual(data["modelos"]["planejamento"], {"cli": "claude", "modelo": "opus"})
        shown = self.run_cli(repo, "mostrar")
        self.assertIn("espelho codex:sol", shown.stdout)
        self.assertIn("revisao: codex:sol", shown.stdout)

    def test_bad_role_is_rejected(self):
        repo = make_repo()
        result = self.run_cli(repo, "configurar", "writer", "claude:opus")
        self.assertEqual(result.returncode, 2)
        self.assertFalse((repo / ".claude/trilho.json").exists())

    def test_gate_reviewer_model_is_configured_separately(self):
        repo = make_repo()
        (repo / ".claude").mkdir()
        path = repo / ".claude/trilho.json"
        path.write_text(json.dumps({"portoes": {"design-revisao": {"momento": "fim", "assina": "agente",
                                                               "agente": "design-revisor"}}}))
        result = self.run_cli(repo, "configurar", "revisao", "claude:sonnet",
                              "portao:design-revisao", "claude:opus")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(path.read_text())
        self.assertEqual(data["modelos"]["portoes"]["design-revisao"], {"cli": "claude", "modelo": "opus"})
        self.assertIn("portao:design-revisao: claude:opus", self.run_cli(repo, "mostrar").stdout)
        blocked = self.run_cli(repo, "configurar", "revisao", "claude:haiku",
                               env=dict(os.environ, CLAUDECODE="1"))
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("Sem permissão", blocked.stderr)
        self.assertEqual(json.loads(path.read_text()), data)

    def test_codex_gate_reviewer_uses_own_model_and_stamps_only_matching_snapshot(self):
        repo = make_repo()
        (repo / ".claude").mkdir()
        (repo / ".claude/trilho.json").write_text(json.dumps({"portoes": {
            "seguranca": {"momento": "fim", "assina": "agente", "agente": "seguranca-revisor"}}}))
        agent = repo / ".codex/agents/seguranca-revisor.toml"
        agent.parent.mkdir(parents=True)
        agent.write_text('developer_instructions = "Procure falhas concretas de segurança."\n')
        self.assertEqual(self.run_cli(repo, "configurar", "revisao", "claude:sonnet",
                                      "portao:seguranca", "codex:sol").returncode, 0)
        listed = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/portao.py")],
                                cwd=repo, capture_output=True, text=True)
        self.assertIn("modelos validar-portao seguranca", listed.stdout)
        snapshot = ledger.head(str(repo))
        with tempfile.TemporaryDirectory() as bin_dir:
            fake = pathlib.Path(bin_dir) / "codex"
            fake.write_text("#!/bin/sh\n" +
                            "approved=no\n" +
                            "while [ \"$#\" -gt 0 ]; do\n" +
                            "  if [ \"$1\" = --approve-for-me ]; then approved=yes; fi\n" +
                            "  if [ \"$1\" = -o ]; then shift; output=$1; fi\n" +
                            "  shift\n" +
                            "done\n" +
                            "[ \"$approved\" = yes ] || exit 9\n" +
                            "cat >/dev/null\n" +
                            f"printf 'VEREDITO: APPROVED\\nCOMMIT: {snapshot}\\nRESUMO: sem falhas\\n' > \"$output\"\n")
            fake.chmod(0o755)
            env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""), HOME=bin_dir)
            result = self.run_cli(repo, "validar-portao", "seguranca", "--pedido", "Ticket concluído", env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["modelo"], "codex:sol")
            self.assertTrue(summary["carimbado"])
            key = registry.stamp_key(str(repo), registry.load(str(repo))["portoes"]["seguranca"])
            with mock.patch.dict(os.environ, HOME=bin_dir):
                self.assertTrue(ledger.has(str(repo), "seguranca", key))
            manifest = json.loads(pathlib.Path(summary["manifesto"]).read_text())
            self.assertIn("Procure falhas concretas", pathlib.Path(summary["manifesto"]).with_name("pedido.txt").read_text())
            self.assertEqual(manifest["tentativas"][0]["id_modelo"], "gpt-6.2-sol")

    def test_gate_reviewer_rejects_wrong_snapshot(self):
        repo = make_repo()
        (repo / ".claude").mkdir()
        (repo / ".claude/trilho.json").write_text(json.dumps({"portoes": {
            "bugs": {"momento": "fim", "assina": "agente", "agente": "tr:bugs-cacador"}}}))
        self.assertEqual(self.run_cli(repo, "configurar", "portao:bugs", "claude:opus").returncode, 0)
        with tempfile.TemporaryDirectory() as bin_dir:
            fake = pathlib.Path(bin_dir) / "claude"
            fake.write_text("#!/bin/sh\n" +
                            "printf '%s\\n' '{\"result\":\"VEREDITO: APPROVED\\\\nCOMMIT: 0000000000000000000000000000000000000000\\\\nRESUMO: sem falhas\"}'\n")
            fake.chmod(0o755)
            env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""))
            result = self.run_cli(repo, "validar-portao", "bugs", env=env)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(json.loads(result.stdout)["carimbado"])

    def test_claude_gate_reviewer_uses_registered_agent(self):
        repo = make_repo()
        (repo / ".claude").mkdir()
        (repo / ".claude/trilho.json").write_text(json.dumps({"portoes": {
            "seguranca": {"momento": "fim", "assina": "agente", "agente": "seguranca-revisor"}}}))
        self.assertEqual(self.run_cli(repo, "configurar", "portao:seguranca", "claude:sonnet").returncode, 0)
        snapshot = ledger.head(str(repo))
        with tempfile.TemporaryDirectory() as bin_dir:
            fake = pathlib.Path(bin_dir) / "claude"
            fake.write_text("#!/usr/bin/env python3\nimport json, sys\n" +
                            f"assert '--agent' in sys.argv and sys.argv[sys.argv.index('--agent') + 1] == 'seguranca-revisor'\n" +
                            "sys.stdin.read()\n" +
                            f"print(json.dumps({{'result': 'VEREDITO: APPROVED\\nCOMMIT: {snapshot}\\nRESUMO: sem falhas'}}))\n")
            fake.chmod(0o755)
            env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""), HOME=bin_dir,
                       CLAUDECODE="1")
            result = self.run_cli(repo, "validar-portao", "seguranca", env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["carimbado"])

    def test_invalid_registry_is_preserved(self):
        repo = make_repo()
        (repo / ".claude").mkdir()
        path = repo / ".claude/trilho.json"
        path.write_text("{invalid")
        result = self.run_cli(repo, "configurar", "execucao", "codex:luna")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_text(), "{invalid")

    def test_execute_records_real_cli_and_falls_back_on_limit(self):
        repo = make_repo()
        self.assertEqual(self.run_cli(repo, "configurar", "planejamento", "claude:opus").returncode, 0)
        with tempfile.TemporaryDirectory() as bin_dir:
            for name, script in {
                "claude": "#!/bin/sh\necho 'rate limit reached' >&2\nexit 1\n",
                "codex": "#!/bin/sh\necho '{\"type\":\"turn.completed\"}'\n",
            }.items():
                path = pathlib.Path(bin_dir) / name
                path.write_text(script)
                path.chmod(0o755)
            env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""))
            result = self.run_cli(repo, "executar", "planejamento", "--pedido", "Planeje a soma", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["modelos"], ["opus", "gpt-6.2-sol"])
        manifest = json.loads(pathlib.Path(summary["manifesto"]).read_text())
        self.assertEqual([item["cli"] for item in manifest["tentativas"]], ["claude", "codex"])
        self.assertIn("harness-runs", summary["manifesto"])
        self.assertFalse((repo / "harness-runs").exists())


if __name__ == "__main__":
    unittest.main()
