"""Projeto do formato em português (até a 3.x) migra para o formato em inglês, e sem migrar o trilho barra."""
import json
import subprocess
import sys
import unittest

from tests.helpers import ROOT, make_repo

sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
import registry  # noqa: E402

MIGRATE = ROOT / "plugins/tr/scripts/migrate.py"
OLD = {
    "codigo": ["apps"],
    "portoes": {
        "processo": {"momento": "inicio", "assina": "artefato", "artefato": "docs/specs/*/spec.md", "descricao": "spec"},
        "qualidade": {"momento": "fim", "assina": "comando", "comando": "@definir", "tentativas": 2},
        "bugs": {"momento": "fim", "assina": "agente", "agente": "tr:bugs-cacador", "aprovacao": "humana"},
        "design": {"momento": "inicio", "assina": "comando", "comando": "true", "sempre": False},
    },
    "modelos": {"revisao": {"cli": "codex", "modelo": "sol"}, "portoes": {"bugs": {"cli": "claude", "modelo": "opus"}}},
}
TICKET = "# T\nStatus: open\nBloqueado por: nenhum\nEntrada: design\nPortões: nenhum\nArquivos: apps/x\nComplexidade: simples\n"


class TestMigrate(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/trilho.json").write_text(json.dumps(OLD))
        (self.repo / ".claude/demanda-atual").write_text("perfil\n")
        (self.repo / ".claude/settings.json").write_text(json.dumps({
            "enabledPlugins": {"tr@fullchico": True, "memoria@fullchico": True},
            "sandbox": {"enabled": True, "filesystem": {"denyWrite": [".claude/trilho.json"]},
                        "excludedCommands": ["portao", "memoria", "memoria-sessoes"]}}))
        issues = self.repo / "docs/specs/perfil/issues"
        issues.mkdir(parents=True)
        (issues / "01-tela.md").write_text(TICKET)
        (self.repo / "docs/specs/perfil/spec.md").write_text("# Spec\n\n**Portões:** e2e\n")

    def run_migrate(self):
        return subprocess.run([sys.executable, "-I", str(MIGRATE), str(self.repo)], capture_output=True, text=True)

    def test_without_migrating_the_rail_fails_closed(self):
        with self.assertRaisesRegex(registry.RegistryError, "formato antigo"):
            registry.load(str(self.repo))
        self.assertTrue(registry.has_gates(str(self.repo)))

    def test_migrates_registry_tickets_and_settings_once(self):
        r = self.run_migrate()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.repo / ".claude/trilho.json").exists())
        reg = registry.load(str(self.repo))
        self.assertEqual(reg["code"], ["apps"])
        self.assertEqual(reg["gates"]["processo"], {"stage": "start", "signs": "artifact",
                                                    "artifact": "docs/specs/*/spec.md", "description": "spec"})
        self.assertEqual(reg["gates"]["qualidade"]["command"], "@define")
        self.assertEqual(reg["gates"]["qualidade"]["attempts"], 2)
        self.assertEqual(reg["gates"]["bugs"]["agent"], "tr:bug-hunter")
        self.assertEqual(reg["gates"]["bugs"]["approval"], "human")
        self.assertIs(reg["gates"]["design"]["always"], False)
        self.assertEqual(reg["models"], {"review": {"cli": "codex", "model": "sol"},
                                         "gates": {"bugs": {"cli": "claude", "model": "opus"}}})
        self.assertEqual((self.repo / ".claude/current-demand").read_text(), "perfil\n")
        self.assertEqual((self.repo / "docs/specs/perfil/issues/01-tela.md").read_text(),
                         "# T\nStatus: open\nBlocked by: none\nStart: design\nGates: none\nFiles: apps/x\nComplexity: simple\n")
        self.assertEqual((self.repo / "docs/specs/perfil/spec.md").read_text(), "# Spec\n\n**Gates:** e2e\n")
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertEqual(settings["enabledPlugins"], {"tr@fullchico": True, "memory@fullchico": True})
        self.assertEqual(settings["sandbox"]["filesystem"]["denyWrite"], [".claude/harness.json"])
        self.assertEqual(settings["sandbox"]["excludedCommands"], ["gate", "memory", "memory-sessions"])
        again = self.run_migrate()
        self.assertEqual((again.returncode, again.stdout), (0, ""))

    def test_invalid_old_registry_is_left_untouched(self):
        (self.repo / ".claude/trilho.json").write_text("{quebrado")
        r = self.run_migrate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("não é JSON válido", r.stderr)
        self.assertEqual((self.repo / ".claude/trilho.json").read_text(), "{quebrado")
        self.assertFalse((self.repo / ".claude/harness.json").exists())


if __name__ == "__main__":
    unittest.main()
