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
        for name in ("trilho", "bugs", "qualidade", "memoria"):
            self.assertIn(f"plugin install {name}@fullchico --scope project", self.calls())
        gates = json.loads((self.repo / ".claude/trilho.json").read_text())["portoes"]
        self.assertEqual(gates["qualidade"]["comando"], "pnpm lint && pnpm test", "veio do package.json do projeto")
        self.assertEqual(gates["processo"]["artefato"], "docs/specs/*/spec.md")
        self.assertIn("claude-projeto", r.stdout)

    def test_padrao_uses_the_library_default(self):
        self.assertEqual(self.install("--padrao").returncode, 0)
        gates = json.loads((self.repo / ".claude/trilho.json").read_text())["portoes"]
        self.assertEqual(set(gates), {"processo", "qualidade", "bugs"})

    def test_legacy_still_runs_the_old_installer(self):
        r = self.install("--legado")
        self.assertTrue((self.repo / ".harness").exists() or "harness" in (r.stdout + r.stderr).lower(), r.stderr)
        self.assertNotIn("plugin install trilho@fullchico --scope project", self.calls() if (self.bin / "calls").exists() else [])

    def test_not_a_repository_is_refused(self):
        r = subprocess.run([shutil.which("node"), str(ROOT / "bin/harness.js"), "install", "/caminho/que/nao/existe"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("não é um repositório git", r.stderr)


if __name__ == "__main__":
    unittest.main()
