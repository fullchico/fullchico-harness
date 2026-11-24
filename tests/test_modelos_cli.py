import json
import pathlib
import subprocess
import sys
import unittest

from tests.helpers import ROOT, make_repo


class ModelosCliTest(unittest.TestCase):
    def run_cli(self, repo, *args):
        return subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/modelos.py"), *args],
                              cwd=repo, capture_output=True, text=True)

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


if __name__ == "__main__":
    unittest.main()
