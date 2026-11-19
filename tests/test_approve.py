import json
import subprocess
import unittest

from tests.helpers import ROOT, git, make_repo, read_approval
import common

APPROVE = str(ROOT / "plugin/payload/approve")


class TestApprove(unittest.TestCase):
    def test_owner_stamp(self):
        repo = make_repo()
        sha = git(repo, "rev-parse", "HEAD")
        r = subprocess.run([APPROVE, "revisao", "li o diff"], cwd=repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        a = read_approval(repo, "revisao")
        self.assertEqual((a["gate"], a["sha"], a["by"], a["status"], a["resumo"], a["agent_type"]),
                         ("revisao", sha, "owner", "PASS", "li o diff", None))

    def test_resumo_with_quotes_is_stored_verbatim(self):
        repo = make_repo()
        sha = git(repo, "rev-parse", "HEAD")
        subprocess.run([APPROVE, "seguranca", 'ok "sem" \\ segredos'], cwd=repo, check=True, capture_output=True)
        a = read_approval(repo, "seguranca")
        self.assertEqual(a["resumo"], 'ok "sem" \\ segredos')

    def test_rejects_bad_usage(self):
        repo = make_repo()
        for args in (["revisao", ""], ["revisao", "   "], ["quality", "x"], ["revisao"], []):
            r = subprocess.run([APPROVE, *args], cwd=repo, capture_output=True)
            self.assertEqual(r.returncode, 1, args)

    def test_outside_git_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(subprocess.run([APPROVE, "revisao", "x"], cwd=d, capture_output=True).returncode, 1)


if __name__ == "__main__":
    unittest.main()
