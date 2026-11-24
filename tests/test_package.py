"""O pacote do npm: a versão é uma só, a entrada repassa ao instalador, e nada pessoal vai junto."""
import json
import re
import subprocess
import unittest

from tests.helpers import ROOT

PUBLIC_EXCLUDED = ("docs/", "interno/")


def public_files():
    listed = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split("\n")
    return [f for f in listed if f and not f.startswith(PUBLIC_EXCLUDED)]


class TestPackage(unittest.TestCase):
    def test_one_version_everywhere(self):
        package = json.loads((ROOT / "package.json").read_text())
        self.assertRegex(package["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(package["name"], "@fullchico/harness")
        self.assertEqual(package["publishConfig"]["access"], "public")
        # O npm compara este endereço, letra por letra, com o que o GitHub informa na procedência.
        self.assertEqual(package["repository"]["url"], "git+https://github.com/fullchico/fullchico-harness.git")

    def test_entry_point_answers_and_refuses_unknown_commands(self):
        run = lambda *args: subprocess.run(["node", str(ROOT / "bin/harness.js"), *args], capture_output=True, text=True)
        self.assertEqual(run("--version").stdout.strip(), json.loads((ROOT / "package.json").read_text())["version"])
        self.assertEqual(run().returncode, 2)
        self.assertEqual(run("publish").returncode, 2)
        self.assertEqual(run("update").returncode, 2, "o modelo antigo saiu")
        self.assertEqual(run("install", "--legado").returncode, 2, "o modelo antigo saiu")
        r = run("install", "/caminho/que/nao/existe")
        self.assertEqual(r.returncode, 2)
        self.assertIn("não é uma pasta do projeto", r.stderr)

    def test_everything_the_package_ships_exists(self):
        package = json.loads((ROOT / "package.json").read_text())
        for entry in package["files"]:
            if entry.startswith("!"):
                continue
            self.assertTrue((ROOT / entry.rstrip("/")).exists(), entry)
        self.assertTrue((ROOT / package["bin"]["fullchico-harness"]).exists())

    def test_nothing_personal_in_what_goes_public(self):
        home = re.compile(r"/Users/[a-z]|/home/[a-z]")
        mail = re.compile(r"[\w.+-]+@(?:gmail|hotmail|outlook|yahoo|icloud)\.\w+", re.I)
        for name in public_files():
            path = ROOT / name
            if not path.is_file():
                continue
            text = path.read_text(errors="ignore")
            if name != "tests/test_package.py":
                self.assertIsNone(home.search(text), name)
            self.assertIsNone(mail.search(text), name)
        self.assertFalse([f for f in public_files() if f.startswith("docs/")])
