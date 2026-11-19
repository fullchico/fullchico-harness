"""Os scripts do harness rodam fora do sandbox com a raiz do projeto como pasta atual.
Um módulo Python plantado ali pelo agente (json.py, os.py...) não pode ser importado."""
import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, _tmpdir, clone_repo, commit_all, commit_file, make_repo, owner_approve, run_hook, sync

PLANT = "import os\nopen(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'PWNED'), 'w').write('x')\n" \
        "raise SystemExit('módulo plantado foi importado')\n"
NAMES = ("json.py", "common.py", "re.py", "hashlib.py", "socket.py", "zlib.py", "subprocess.py",
         "compose_check.py", "sitecustomize.py", "usercustomize.py")


class TestPlantedModules(unittest.TestCase):
    def setUp(self):
        self.origin = make_repo("origin dir")
        self.repo = clone_repo(self.origin)
        self.assertEqual(sync(self.repo).returncode, 0)
        (self.repo / "harness.conf").write_text(
            'PROJECT=meuapp\nSERVICES="web db"\nCOMPOSE_FILE=dc.yml\nVALIDATE_PUSH="true"\n')
        (self.repo / "dc.yml").write_text("services: {}\n")
        commit_all(self.repo, "chore: adopt harness")
        subprocess.run(["git", "checkout", "-q", "-b", "feat/x"], cwd=self.repo, check=True)
        commit_file(self.repo, "a.txt", "fix: a")
        for name in NAMES:
            (self.repo / name).write_text(PLANT)
        tmp = _tmpdir()
        (tmp / "bin").mkdir()
        os.symlink(ROOT / "tests/fake_docker", tmp / "bin/docker")
        config = tmp / "config.json"
        config.write_text('{"services": {"db": {"image": "postgres:16"}}}')
        self.env = dict(os.environ, PATH=f"{tmp / 'bin'}:{os.environ['PATH']}", FAKE_DOCKER_CONFIG=str(config),
                        PYTHONPATH=str(self.repo), PYTHONSTARTUP=str(self.repo / "json.py"))

    def script(self, name, *args):
        return subprocess.run([str(self.repo / ".harness" / name), *args], cwd=self.repo, env=self.env,
                              capture_output=True, text=True)

    def assert_clean(self, label, result=None):
        self.assertFalse((self.repo / "PWNED").exists(), f"{label}: módulo plantado executou")
        if result is not None:
            self.assertNotIn("módulo plantado", result.stderr + result.stdout, label)

    def test_gate_check_with_one_legitimate_approval(self):
        self.assertEqual(owner_approve(self.repo, "seguranca").returncode, 0)
        self.assert_clean("approve")
        r = self.script("push")
        self.assert_clean("push", r)
        self.assertEqual(r.returncode, 1)
        self.assertIn("revisao", r.stderr)

    def test_environment_scripts(self):
        for name in ("worktree-env", "up", "prepare", "down", "destroy", "setup-worktree"):
            r = subprocess.run([str(self.repo / ".harness" / name)], cwd=self.repo,
                               env=dict(self.env, HARNESS_SKIP_PLUGIN="1"), capture_output=True, text=True)
            self.assert_clean(name, r)

    def test_validate_fetch_and_pr(self):
        for name, args in (("validate", ["--profile", "push"]), ("fetch", []), ("pr", ["create", "t", "a.txt"])):
            self.assert_clean(name, self.script(name, *args))

    def test_hooks_as_registered_in_settings(self):
        import json
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        commands = [h["command"] for event in settings["hooks"].values() for group in event for h in group["hooks"]]
        harness = [c for c in commands if ".harness/hooks/" in c]
        self.assertTrue(harness)
        for command in harness:
            self.assertIn("python3 -I ", command, command)
        payload = {"tool_name": "Bash", "cwd": str(self.repo), "tool_input": {"command": ".harness/up"}}
        r = subprocess.run([sys.executable, "-I", str(self.repo / ".harness/hooks/service_guard.py")],
                           input=json.dumps(payload), cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assert_clean("service_guard", r)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
