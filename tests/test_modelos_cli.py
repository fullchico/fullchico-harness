import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import ROOT, make_repo


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
