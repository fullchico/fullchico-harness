"""O instalador inicia Git e a entrega não exige push nem PR."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
import certs  # noqa: E402
import ledger  # noqa: E402
import registry  # noqa: E402


class TestDeliveryWithoutGit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        (self.project / ".claude").mkdir()
        (self.project / ".claude/harness.json").write_text(json.dumps({"gates": {
            "plano": {"stage": "start", "signs": "artifact", "artifact": "docs/specs/*/spec.md"},
            "quality": {"stage": "end", "signs": "command", "command": "true"}}}))
        (self.project / "docs/specs/a").mkdir(parents=True)
        (self.project / "docs/specs/a/spec.md").write_text("# Pedido\n")
        (self.project / "src.py").write_text("value = 1\n")
        self.env = dict(os.environ, HOME=self.home.name)

    def tearDown(self):
        self.tmp.cleanup()
        self.home.cleanup()

    def deliver(self):
        return subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/gate_cli.py"), "delivery"],
                              cwd=self.project, env=self.env, capture_output=True, text=True)

    def test_delivery_checks_current_snapshot(self):
        self.assertEqual(self.deliver().returncode, 1)
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.home.name
        try:
            root = str(self.project)
            reg = registry.load(root)
            certs.certify(root, "plano", registry.stamp_key(root, reg["gates"]["plano"]), "APPROVED", "fiscal", "ok")
            certs.certify(root, "quality", registry.stamp_key(root, reg["gates"]["quality"]), "APPROVED", registry.CHECKER, "ok")
            self.assertEqual(self.deliver().returncode, 0)
            (self.project / "src.py").write_text("value = 2\n")
            self.assertEqual(self.deliver().returncode, 1)
        finally:
            if old_home is None:
                del os.environ["HOME"]
            else:
                os.environ["HOME"] = old_home

    def test_push_is_not_the_delivery_gate(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.project),
                   "tool_input": {"command": "git push"}}
        run = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/guard.py")],
                             input=json.dumps(payload), cwd=self.project, env=self.env,
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn('"permissionDecision": "deny"', run.stdout)

    def test_stop_checks_only_declared_delivery(self):
        script = str(ROOT / "plugins/tr/scripts/delivery_stop.py")
        def stop(message):
            return subprocess.run([sys.executable, script], cwd=self.project, env=self.env,
                                  input=json.dumps({"cwd": str(self.project), "last_assistant_message": message}),
                                  capture_output=True, text=True)
        self.assertEqual(stop("Preciso esclarecer um requisito.").stdout, "")
        blocked = stop("DELIVERY: done")
        self.assertEqual(blocked.returncode, 0)
        self.assertEqual(json.loads(blocked.stdout)["decision"], "block")

    def test_active_demand_filters_old_tickets_and_subdirectory_resolves_project(self):
        old = self.project / "docs/specs/old/issues/01-old.md"
        old.parent.mkdir(parents=True)
        old.write_text("Status: open\nBlocked by: none\nStart: none\nGates: none\nFiles: src.py\n")
        (self.project / ".claude/current-demand").write_text("a\n")
        nested = self.project / "src"
        nested.mkdir()
        self.assertEqual(registry.toplevel(str(nested)), os.path.realpath(self.project))
        result = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/gate_cli.py"), "delivery"],
                                cwd=nested, env=self.env, capture_output=True, text=True)
        self.assertNotIn("01-old.md", result.stdout)

    def test_codex_installs_and_memory_lists_units_without_git(self):
        fake_bin = self.project / "fake-bin"
        fake_bin.mkdir()
        fake_npx = fake_bin / "npx"
        fake_npx.write_text("#!/bin/sh\nexit 0\n")
        fake_npx.chmod(0o755)
        self.env["PATH"] = str(fake_bin) + os.pathsep + self.env.get("PATH", "")
        install = subprocess.run([sys.executable, str(ROOT / "tools/install_codex.py"), str(self.project)],
                                 cwd=self.project, env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(install.returncode, 0, install.stderr)
        self.assertTrue((self.project / ".git").is_dir())
        memory = subprocess.run([str(ROOT / "plugins/memory/bin/memory"), "units"],
                                cwd=self.project, env=self.env, capture_output=True, text=True)
        self.assertEqual(memory.returncode, 0, memory.stderr)
        self.assertIn(".", memory.stdout)

    def test_project_remote_gate_is_optional(self):
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        subprocess.run(["git", "-C", str(self.project), "remote", "add", "review", "https://example.invalid/repo.git"],
                       check=True)
        config = self.project / ".claude/harness.json"
        data = json.loads(config.read_text())
        data["gates"]["remoto"] = {"stage": "end", "signs": "command", "command": "git remote get-url review"}
        config.write_text(json.dumps(data))
        for args in (["config", "user.email", "t@example.com"], ["config", "user.name", "T"], ["add", "-A"],
                     ["commit", "-q", "-m", "plano"]):
            subprocess.run(["git", "-C", str(self.project), *args], check=True)
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.home.name
        try:
            root = str(self.project)
            reg = registry.load(root)
            certs.certify(root, "plano", registry.stamp_key(root, reg["gates"]["plano"]), "APPROVED", "fiscal", "ok")
            for gate in ("quality", "remoto"):
                certs.certify(root, gate, registry.stamp_key(root, reg["gates"][gate]), "APPROVED", registry.CHECKER, "ok")
            self.assertEqual(self.deliver().returncode, 0)
        finally:
            if old_home is None:
                del os.environ["HOME"]
            else:
                os.environ["HOME"] = old_home


if __name__ == "__main__":
    unittest.main()
