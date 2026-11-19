import json
import subprocess
import unittest

from tests.helpers import ROOT, git, make_repo, read_approval
import common

APPROVE = str(ROOT / "plugin/payload/approve")


def approve(repo, *args):
    """Roda o carimbo como o dono: com um terminal na entrada."""
    import os
    import pty
    master, slave = pty.openpty()
    try:
        return subprocess.run([APPROVE, *args], cwd=repo, stdin=slave, capture_output=True, text=True)
    finally:
        os.close(master)
        os.close(slave)


class TestApprove(unittest.TestCase):
    def test_owner_stamp(self):
        repo = make_repo()
        sha = git(repo, "rev-parse", "HEAD")
        r = approve(repo, "revisao", "li o diff")
        self.assertEqual(r.returncode, 0, r.stderr)
        a = read_approval(repo, "revisao")
        self.assertEqual((a["gate"], a["sha"], a["by"], a["status"], a["resumo"], a["agent_type"]),
                         ("revisao", sha, "owner", "PASS", "li o diff", None))

    def test_resumo_with_quotes_is_stored_verbatim(self):
        repo = make_repo()
        sha = git(repo, "rev-parse", "HEAD")
        self.assertEqual(approve(repo, "seguranca", 'ok "sem" \\ segredos').returncode, 0)
        a = read_approval(repo, "seguranca")
        self.assertEqual(a["resumo"], 'ok "sem" \\ segredos')

    def test_rejects_bad_usage(self):
        repo = make_repo()
        for args in (["revisao", ""], ["revisao", "   "], ["quality", "x"], ["revisao"], []):
            self.assertEqual(approve(repo, *args).returncode, 1, args)

    def test_outside_git_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(approve(d, "revisao", "x").returncode, 1)


if __name__ == "__main__":
    unittest.main()
