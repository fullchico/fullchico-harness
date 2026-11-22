"""O pacote do npm: a versão é uma só, a entrada repassa ao instalador, e nada pessoal vai junto."""
import json
import os
import re
import subprocess
import unittest

from tests.helpers import ROOT, make_repo, sync

PUBLIC_EXCLUDED = ("docs/", "interno/")


def public_files():
    listed = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split("\n")
    return [f for f in listed if f and not f.startswith(PUBLIC_EXCLUDED)]


class TestPackage(unittest.TestCase):
    def test_one_version_everywhere(self):
        package = json.loads((ROOT / "package.json").read_text())
        plugin = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text())
        self.assertEqual(package["version"], plugin["version"])
        self.assertEqual(package["name"], "@fullchico/harness")
        self.assertEqual(package["publishConfig"]["access"], "public")
        # O npm compara este endereço, letra por letra, com o que o GitHub informa na procedência.
        self.assertEqual(package["repository"]["url"], "git+https://github.com/fullchico/fullchico-harness.git")

    def test_entry_point_answers_and_refuses_unknown_commands(self):
        run = lambda *args: subprocess.run(["node", str(ROOT / "bin/harness.js"), *args], capture_output=True, text=True)
        self.assertEqual(run("--version").stdout.strip(), json.loads((ROOT / "package.json").read_text())["version"])
        self.assertEqual(run().returncode, 2)
        self.assertEqual(run("publish").returncode, 2)
        r = run("install", "/caminho/que/nao/existe")
        self.assertEqual(r.returncode, 2)
        self.assertIn("não é um repositório git", r.stderr)

    def test_update_brings_an_installed_project_to_the_package_version(self):
        env = dict(os.environ, HARNESS_SKIP_PLUGIN="1")
        run = lambda *args: subprocess.run(["node", str(ROOT / "bin/harness.js"), *args], capture_output=True,
                                           text=True, env=env)
        fresh = make_repo()
        r = run("update", str(fresh))
        self.assertEqual(r.returncode, 2)
        self.assertIn("install", r.stderr, "projeto sem harness: o caminho é instalar")
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        (repo / ".harness/push").write_text("versão antiga\n")
        r = run("update", str(repo), "--force")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("versão antiga", (repo / ".harness/push").read_text())
        # sem pasta, vale a atual
        self.assertEqual(subprocess.run(["node", str(ROOT / "bin/harness.js"), "update", "--force"], cwd=repo,
                                        capture_output=True, text=True, env=env).returncode, 0)

    def test_everything_the_package_ships_exists(self):
        package = json.loads((ROOT / "package.json").read_text())
        for entry in package["files"]:
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
