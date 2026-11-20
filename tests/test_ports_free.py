"""Processo esquecido numa porta da feature trava a entrega: o harness o encerra, sem tocar no que é da feature."""
import os
import socket
import subprocess
import sys
import time
import unittest

from tests.helpers import _tmpdir, make_repo, sync


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def listening(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


class TestPortsFree(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            p.kill()
            p.wait()

    def serve(self, port, cwd):
        p = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=cwd,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs.append(p)
        for _ in range(50):
            if listening(port):
                return p
            time.sleep(0.1)
        self.fail("o servidor de teste não subiu")

    def run_script(self):
        return subprocess.run([str(self.repo / ".harness/ports-free")], cwd=self.repo, capture_output=True, text=True)

    def test_stranger_on_a_feature_port_is_stopped_and_the_feature_itself_is_not(self):
        api, web, other = free_port(), free_port(), free_port()
        (self.repo / ".env").write_text(f"API_PORT={api}\nWEB_PORT={web}\nDATABASE_URL=postgres://x\n")
        self.serve(api, str(_tmpdir()))          # cópia temporária de um revisor
        self.serve(web, str(self.repo))          # o aplicativo da própria feature
        self.serve(other, str(_tmpdir()))        # porta que não é da feature
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        time.sleep(0.5)
        self.assertFalse(listening(api))
        self.assertTrue(listening(web))
        self.assertTrue(listening(other))
        self.assertIn(str(api), r.stdout)

    def test_nothing_to_do_without_env(self):
        self.assertEqual(self.run_script().returncode, 0)

    def test_runs_outside_the_sandbox_alone_and_when_a_reviewer_stops(self):
        import json
        s = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertIn(".harness/ports-free", s["sandbox"]["excludedCommands"])
        self.assertIn("Bash(.harness/ports-free)", s["permissions"]["allow"])
        stop = [h["command"] for group in s["hooks"]["SubagentStop"] for h in group["hooks"]]
        self.assertTrue(any("ports-free" in c for c in stop))
