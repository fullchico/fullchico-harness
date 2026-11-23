"""Passaporte por demanda: a spec diz quais portões opcionais a demanda pede; o registro diz o mínimo."""
import json
import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, git, make_repo

sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
import registry  # noqa: E402

PORTOES = {
    "processo": {"momento": "inicio", "assina": "artefato", "artefato": "docs/specs/*/spec.md"},
    "qualidade": {"momento": "fim", "assina": "comando", "comando": "true"},
    "e2e": {"momento": "fim", "assina": "comando", "comando": "true", "sempre": False},
    "seo": {"momento": "fim", "assina": "comando", "comando": "true", "sempre": False},
}


class TestPassport(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/trilho.json").write_text(json.dumps({"portoes": PORTOES}))
        commit_all(self.repo, "chore: registro")
        git(self.repo, "checkout", "-q", "-b", "feat")

    def spec(self, text):
        path = self.repo / "docs/specs/a/spec.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        commit_all(self.repo, "docs: spec")

    def missing(self):
        return registry.missing(str(self.repo), "fim", registry.load(str(self.repo)))

    def test_without_the_line_every_end_gate_is_required(self):
        self.spec("# Spec\n\nsem passaporte\n")
        self.assertEqual(self.missing(), ["qualidade", "e2e", "seo"])

    def test_the_line_adds_the_optional_ones_it_names(self):
        self.spec("# Spec\n\nPortões: e2e\n")
        self.assertEqual(self.missing(), ["qualidade", "e2e"], "qualidade é sempre; seo ficou fora")

    def test_names_are_read_as_the_registry_writes_them(self):
        self.spec("# Spec\n\n**Portões:** `e2e`, **seo**.\n")
        self.assertEqual(self.missing(), ["qualidade", "e2e", "seo"])

    def test_an_end_gate_by_artifact_is_validated_by_the_verifier(self):
        portoes = dict(PORTOES, relatorio={"momento": "fim", "assina": "artefato", "artefato": "docs/relatorio.md"})
        reg = {"portoes": portoes}
        self.assertIn("relatorio", registry.validadores(reg)[registry.VERIFICADOR])
        self.assertIn("/tr:qualidade-verificar", registry.howto("relatorio", portoes["relatorio"]))

    def test_the_passport_cannot_drop_a_required_gate(self):
        self.spec("# Spec\n\nPortões: seo\n")
        self.assertIn("qualidade", self.missing())

    def test_sempre_must_be_a_boolean(self):
        bad = dict(PORTOES, e2e={**PORTOES["e2e"], "sempre": "não"})
        (self.repo / ".claude/trilho.json").write_text(json.dumps({"portoes": bad}))
        with self.assertRaises(registry.RegistryError):
            registry.load(str(self.repo))

    def test_portao_lists_what_is_out_and_warns_about_unknown_names(self):
        self.spec("# Spec\n\nPortões: e2e, inexistente\n")
        out = subprocess.run([str(ROOT / "plugins/tr/bin/portao")], cwd=self.repo, capture_output=True, text=True).stdout
        self.assertIn("[fora] seo", out)
        self.assertIn("[falta] e2e", out)
        self.assertIn("`inexistente`", out)


if __name__ == "__main__":
    unittest.main()
