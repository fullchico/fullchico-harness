"""Escolher o design: protótipos rápidos, o dono escolhe um caminho, a escolha vira DESIGN.md.

O agente escreve as direções; quem monta a vitrine, calcula o selo de leitura e grava a
escolha é o harness, para que direção ilegível não vire o design do projeto.
"""
import subprocess
import unittest

from tests.helpers import ROOT, commit_all, make_repo, run_hook, sync
from tests.test_contrast import GOOD, SHADCN


class TestDesignChoice(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        commit_all(self.repo, "chore: adopt harness")
        self.shop = self.repo / ".harness-run/design/agenda"

    def direction(self, name, css=GOOD, title="Direção"):
        folder = self.shop / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text("<!doctype html><html><body><h1>Agenda</h1></body></html>")
        (folder / "tokens.css").write_text(css)
        (folder / "direcao.md").write_text(f"{title}\nCalma e direta, para quem usa todo dia.\n")
        return folder

    def run_design(self, *args):
        return subprocess.run([str(self.repo / ".harness/design"), *args], cwd=self.repo, capture_output=True, text=True)

    def test_gallery_puts_the_directions_side_by_side_with_the_reading_seal(self):
        self.direction("a-sereno", title="Sereno")
        self.direction("b-vivo", css=SHADCN, title="Vivo")
        r = self.run_design("gallery", ".harness-run/design/agenda")
        self.assertEqual(r.returncode, 0, r.stderr)
        page = (self.shop / "index.html").read_text()
        for needed in ("Sereno", "Vivo", "Calma e direta", "a-sereno/index.html", "b-vivo/index.html", "escuro", "celular"):
            self.assertIn(needed, page, needed)
        self.assertIn("Legível", page)
        self.assertIn("Texto difícil de ler", page, "a direção reprovada aparece marcada, com a razão em português")
        self.assertIn(str(self.shop / "index.html"), r.stdout, "diz ao dono qual arquivo abrir")

    def test_gallery_needs_two_to_four_complete_directions(self):
        self.direction("a")
        self.assertNotEqual(self.run_design("gallery", ".harness-run/design/agenda").returncode, 0, "uma só não é escolha")
        (self.direction("b") / "tokens.css").unlink()
        r = self.run_design("gallery", ".harness-run/design/agenda")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("tokens.css", r.stderr)
        for name in "bcde":
            self.direction(name)
        self.assertNotEqual(self.run_design("gallery", ".harness-run/design/agenda").returncode, 0, "cinco é demais")

    def test_only_a_readable_direction_becomes_the_design(self):
        self.direction("a-sereno", title="Sereno")
        self.direction("b-vivo", css=SHADCN, title="Vivo")
        bad = self.run_design("choose", ".harness-run/design/agenda", "b-vivo")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("contraste", bad.stderr)
        self.assertFalse((self.repo / "DESIGN.md").exists())
        ok = self.run_design("choose", ".harness-run/design/agenda", "a-sereno")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        doc = (self.repo / "DESIGN.md").read_text()
        for needed in ("Sereno", "Calma e direta", "--muted-foreground", ".dark"):
            self.assertIn(needed, doc, needed)
        self.assertEqual(self.run_design("choose", ".harness-run/design/agenda", "nao-existe").returncode, 1)
        self.assertEqual(self.run_design("choose", ".harness-run/design/agenda", "../../x").returncode, 1)

    def test_a_project_with_screens_does_not_start_without_its_design(self):
        spec = self.repo / "docs/specs/x/spec.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("# x\n\n## harness.conf\n\nPROJECT=p\n")
        (self.repo / "harness.conf").write_text('PROJECT=p\nTOKENS_CSS="apps/web/app/globals.css"\n')
        commit_all(self.repo, "docs: add spec")
        ask = lambda: run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(self.repo), "tool_input": {
            "subagent_type": "harness:orquestrador", "prompt": "spec: docs/specs/x/spec.md"}})
        rc, _, err = ask()
        self.assertEqual(rc, 2)
        self.assertIn("DESIGN.md", err)
        (self.repo / "DESIGN.md").write_text("# Design\n")
        self.assertEqual(ask()[0], 2, "precisa estar em commit")
        commit_all(self.repo, "docs: choose design")
        self.assertEqual(ask()[0], 0, ask()[2])

    def test_texts_lead_to_the_step(self):
        skill = (ROOT / "plugin/skills/entregar/SKILL.md").read_text()
        for needed in (".harness/design gallery", ".harness/design choose", "DESIGN.md", "PARADA"):
            self.assertIn(needed, skill, needed)
        rules = (ROOT / "plugin/payload/subagent-rules.md").read_text()
        self.assertIn("DESIGN.md", rules)


if __name__ == "__main__":
    unittest.main()
