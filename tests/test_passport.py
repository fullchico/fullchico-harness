"""Passaporte por demanda: a spec diz quais portões opcionais a demanda pede; o registro diz o mínimo."""
import json
import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, git, make_repo

sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
import registry  # noqa: E402

GATES = {
    "process": {"stage": "start", "signs": "artifact", "artifact": "docs/specs/*/spec.md"},
    "quality": {"stage": "end", "signs": "command", "command": "true"},
    "e2e": {"stage": "end", "signs": "command", "command": "true", "always": False},
    "seo": {"stage": "end", "signs": "command", "command": "true", "always": False},
}


class TestPassport(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/harness.json").write_text(json.dumps({"gates": GATES}))
        commit_all(self.repo, "chore: registro")
        git(self.repo, "checkout", "-q", "-b", "feat")

    def spec(self, text):
        path = self.repo / "docs/specs/a/spec.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        commit_all(self.repo, "docs: spec")

    def missing(self):
        return registry.missing(str(self.repo), "end", registry.load(str(self.repo)))

    def test_without_the_line_every_end_gate_is_required(self):
        self.spec("# Spec\n\nsem passaporte\n")
        self.assertEqual(self.missing(), ["quality", "e2e", "seo"])

    def test_the_line_adds_the_optional_ones_it_names(self):
        self.spec("# Spec\n\nGates: e2e\n")
        self.assertEqual(self.missing(), ["quality", "e2e"], "quality é sempre; seo ficou fora")

    def test_names_are_read_as_the_registry_writes_them(self):
        self.spec("# Spec\n\n**Gates:** `e2e`, **seo**.\n")
        self.assertEqual(self.missing(), ["quality", "e2e", "seo"])

    def test_a_bullet_in_another_section_is_not_the_passport(self):
        self.spec("# Spec\n\n## Comandos\n- Gates: pnpm lint && pnpm test\n* Gates: e2e\n")
        self.assertEqual(self.missing(), ["quality", "e2e", "seo"], "sem passaporte: valem todos")

    def test_a_line_inside_a_fenced_block_is_not_the_passport(self):
        self.spec("# Spec\n\n```\nGates: e2e\n```\n")
        self.assertEqual(self.missing(), ["quality", "e2e", "seo"], "sem passaporte: valem todos")

    def test_blockquote_and_bold_label_still_count(self):
        self.spec("# Spec\n\n> **Gates:** seo\n")
        self.assertEqual(self.missing(), ["quality", "seo"])

    def test_an_end_gate_by_artifact_is_validated_by_the_verifier(self):
        gates = dict(GATES, report={"stage": "end", "signs": "artifact", "artifact": "docs/report.md"})
        reg = {"gates": gates}
        self.assertIn("report", registry.validators(reg)[registry.CHECKER])
        self.assertIn("/tr:quality-check", registry.howto("report", gates["report"]))

    def test_the_passport_cannot_drop_a_required_gate(self):
        self.spec("# Spec\n\nGates: seo\n")
        self.assertIn("quality", self.missing())

    def test_always_must_be_a_boolean(self):
        bad = dict(GATES, e2e={**GATES["e2e"], "always": "não"})
        (self.repo / ".claude/harness.json").write_text(json.dumps({"gates": bad}))
        with self.assertRaises(registry.RegistryError):
            registry.load(str(self.repo))

    def test_gate_lists_what_is_out_and_warns_about_unknown_names(self):
        self.spec("# Spec\n\nGates: e2e, inexistente\n")
        out = subprocess.run([str(ROOT / "plugins/tr/bin/gate")], cwd=self.repo, capture_output=True, text=True).stdout
        self.assertIn("[fora] seo", out)
        self.assertIn("[falta] e2e", out)
        self.assertIn("`inexistente`", out)


if __name__ == "__main__":
    unittest.main()
