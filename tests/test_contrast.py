"""Contraste dos tokens: a direção visual reprova ou passa antes de existir tela.

É do harness, em Python puro: não depende de pacote do projeto nem de rede. Os números de
referência são os do tema neutro padrão do shadcn, conferidos com outra biblioteca.
"""
import subprocess
import sys
import unittest

from tests.helpers import ROOT, _tmpdir, commit_all, make_repo, sync

sys.path.insert(0, str(ROOT / "plugin/payload"))
import contrast_check as cc  # noqa: E402

SCRIPT = str(ROOT / "plugin/payload/contrast_check.py")
SHADCN = """
@import "tailwindcss";
:root {
  --radius: 0.625rem;
  --background: oklch(1 0 0);
  --foreground: oklch(0.145 0 0);
  --muted: oklch(0.97 0 0);
  --muted-foreground: oklch(0.556 0 0);
  --primary: oklch(0.205 0 0);
  --primary-foreground: oklch(0.985 0 0);
  --border: oklch(0.922 0 0);
  --ring: oklch(0.708 0 0);
}
.dark {
  --background: oklch(0.145 0 0);
  --foreground: oklch(0.985 0 0);
  --muted: oklch(0.269 0 0);
  --muted-foreground: oklch(0.708 0 0);
  --primary: oklch(0.922 0 0);
  --primary-foreground: oklch(0.205 0 0);
  --border: oklch(1 0 0 / 10%);
  --ring: oklch(0.556 0 0);
}
"""
GOOD = SHADCN.replace("--muted-foreground: oklch(0.556 0 0)", "--muted-foreground: oklch(0.45 0 0)") \
             .replace("--ring: oklch(0.708 0 0)", "--ring: oklch(0.5 0 0)")


class TestContrast(unittest.TestCase):
    def test_ratio_matches_the_reference_values(self):
        white, grey = cc.color("oklch(1 0 0)"), cc.color("oklch(0.556 0 0)")
        self.assertAlmostEqual(cc.ratio(grey, white), 4.73, delta=0.06)
        self.assertAlmostEqual(cc.ratio(grey, cc.color("oklch(0.97 0 0)")), 4.34, delta=0.06)
        self.assertAlmostEqual(cc.ratio(cc.color("oklch(0.708 0 0)"), white), 2.59, delta=0.06)
        self.assertAlmostEqual(cc.ratio(cc.color("#000"), cc.color("#ffffff")), 21.0, delta=0.01)
        self.assertAlmostEqual(cc.ratio(cc.color("rgb(118 118 118)"), white), 4.54, delta=0.03)

    def test_every_colour_notation_the_stack_writes(self):
        for text in ("#767676", "rgb(118, 118, 118)", "hsl(0 0% 46.3%)", "0 0% 46.3%", "oklch(55.6% 0 0)",
                     "oklch(0.556 0 0deg)"):
            self.assertAlmostEqual(cc.ratio(cc.color(text), cc.color("#fff")), 4.6, delta=0.2, msg=text)
        self.assertIsNone(cc.color("0.625rem"))
        self.assertIsNone(cc.color("var(--x)"))

    def test_default_theme_fails_where_the_text_would_be_hard_to_read(self):
        found = cc.check(SHADCN)
        failed = {(f["theme"], f["text"], f["on"]) for f in found if f["level"] == "falha"}
        self.assertIn(("claro", "muted-foreground", "muted"), failed)
        self.assertIn(("claro", "ring", "background"), failed)
        self.assertNotIn(("claro", "foreground", "background"), failed)
        self.assertNotIn(("escuro", "muted-foreground", "muted"), failed)
        # borda fraca é aviso, não reprova: o tema padrão inteiro cairia
        self.assertTrue(any(f["level"] == "aviso" and f["text"] == "border" for f in found))

    def test_translucent_colour_is_measured_over_what_is_behind_it(self):
        css = ":root { --background: #000; --foreground: rgb(255 255 255 / 40%); }"
        (failure,) = [f for f in cc.check(css) if f["level"] == "falha"]
        self.assertLess(failure["ratio"], 4.5)

    def test_cli_and_exit_code(self):
        tmp = _tmpdir()
        (tmp / "bad.css").write_text(SHADCN)
        (tmp / "good.css").write_text(GOOD)
        run = lambda *a: subprocess.run([sys.executable, SCRIPT, *a], capture_output=True, text=True)
        bad = run(str(tmp / "bad.css"))
        self.assertEqual(bad.returncode, 1)
        self.assertIn("muted-foreground", bad.stdout + bad.stderr)
        self.assertIn("4,5", bad.stdout + bad.stderr)
        self.assertEqual(run(str(tmp / "good.css")).returncode, 0)
        self.assertEqual(run(str(tmp / "nao-existe.css")).returncode, 2)
        (tmp / "empty.css").write_text("body { margin: 0 }")
        self.assertEqual(run(str(tmp / "empty.css")).returncode, 2, "sem tokens: é erro de configuração, não aprovação")

    def test_validate_runs_it_when_the_project_declares_its_tokens(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        (repo / "app").mkdir()
        (repo / "app/globals.css").write_text(SHADCN)
        (repo / "harness.conf").write_text('PROJECT=p\nPROFILE=livre\nVALIDATE_PUSH="true"\nTOKENS_CSS="app/globals.css"\n')
        commit_all(repo, "chore: adopt harness")
        run = lambda: subprocess.run([str(repo / ".harness/validate"), "--profile", "push"], cwd=repo,
                                     capture_output=True, text=True)
        r = run()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("contraste", r.stderr)
        (repo / "app/globals.css").write_text(GOOD)
        self.assertEqual(run().returncode, 0, run().stderr)


if __name__ == "__main__":
    unittest.main()
