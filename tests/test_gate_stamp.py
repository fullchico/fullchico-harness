import json
import os
import unittest

from tests.helpers import git, make_repo, run_hook, read_approval
import common
import gate_stamp


def payload(repo, agent="harness:seguranca", msg=None, sha=None):
    sha = sha or git(repo, "rev-parse", "HEAD")
    if msg is None:
        msg = f"Revisado.\nVEREDITO: APPROVED\nCOMMIT: {sha}\nRESUMO: sem achados"
    return {"hook_event_name": "SubagentStop", "agent_type": agent, "cwd": str(repo),
            "last_assistant_message": msg, "agent_transcript_path": "/t.jsonl"}


def stamped(repo, gate):
    sha = git(repo, "rev-parse", "HEAD")
    return os.path.exists(common.approval_path(common.state_dir(str(repo)), gate, sha))


class TestGateStamp(unittest.TestCase):
    def test_approved_stamps_the_gate_of_that_agent(self):
        repo = make_repo()
        self.assertEqual(run_hook("gate_stamp.py", payload(repo))[0], 0)
        self.assertTrue(stamped(repo, "seguranca"))
        self.assertFalse(stamped(repo, "revisao"))
        run_hook("gate_stamp.py", payload(repo, agent="harness:revisor"))
        self.assertTrue(stamped(repo, "revisao"))

    def test_approval_file_content(self):
        repo = make_repo()
        run_hook("gate_stamp.py", payload(repo))
        sha = git(repo, "rev-parse", "HEAD")
        a = read_approval(repo, "seguranca")
        self.assertEqual((a["gate"], a["sha"], a["status"], a["by"], a["resumo"], a["agent_type"]),
                         ("seguranca", sha, "PASS", "hook", "sem achados", "harness:seguranca"))
        self.assertEqual(a["transcript"], "/t.jsonl")
        self.assertRegex(a["timestamp"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_never_stamps(self):
        repo = make_repo()
        sha = git(repo, "rev-parse", "HEAD")
        cases = [
            payload(repo, agent="general-purpose"),
            payload(repo, agent="seguranca"),
            payload(repo, agent="outro:seguranca"),
            payload(repo, agent=""),
            payload(repo, msg=f"VEREDITO: REJECTED\nCOMMIT: {sha}\nRESUMO: x"),
            payload(repo, msg=f"VEREDITO: APPROVED\nCOMMIT: {'0' * 40}\nRESUMO: x"),
            payload(repo, msg=f"VEREDITO: APPROVED\nCOMMIT: {sha}\nRESUMO: "),
            payload(repo, msg=f"veredito: approved\nCOMMIT: {sha}\nRESUMO: x"),
            payload(repo, msg=f"o texto diz VEREDITO: APPROVED aqui\nCOMMIT: {sha}\nRESUMO: x"),
            payload(repo, msg=f"VEREDITO: APPROVED\nVEREDITO: REJECTED\nCOMMIT: {sha}\nRESUMO: x"),
            payload(repo, msg=f"VEREDITO: APPROVED\nVEREDITO: APPROVED\nCOMMIT: {sha}\nRESUMO: x"),
            payload(repo, msg=f"VEREDITO: APPROVED\nCOMMIT: {sha}\nCOMMIT: {'0' * 40}\nRESUMO: x"),
            payload(repo, msg="VEREDITO: APPROVED\nRESUMO: x"),
            payload(repo, msg=""),
        ]
        for p in cases:
            self.assertEqual(run_hook("gate_stamp.py", p)[0], 0)
            self.assertFalse(stamped(repo, "seguranca"), (p["agent_type"], p["last_assistant_message"]))

    def test_bad_input_exits_zero_without_stamping(self):
        self.assertEqual(run_hook("gate_stamp.py", None, raw="")[0], 0)
        self.assertEqual(run_hook("gate_stamp.py", None, raw="{nao json")[0], 0)
        self.assertEqual(run_hook("gate_stamp.py", {"agent_type": "harness:revisor", "cwd": "/nao/existe",
                                                    "last_assistant_message": 7})[0], 0)

    def test_rejected_removes_existing_approval(self):
        repo = make_repo()
        sha = git(repo, "rev-parse", "HEAD")
        run_hook("gate_stamp.py", payload(repo))
        self.assertTrue(stamped(repo, "seguranca"))
        run_hook("gate_stamp.py", payload(repo, msg=f"VEREDITO: REJECTED\nCOMMIT: {sha}\nRESUMO: achei x"))
        self.assertFalse(stamped(repo, "seguranca"))

    def test_stamp_in_one_worktree_is_visible_from_another(self):
        repo = make_repo()
        wt = repo.parent / "wt two"
        git(repo, "worktree", "add", "-q", "--detach", str(wt))
        run_hook("gate_stamp.py", payload(wt))
        self.assertTrue(stamped(repo, "seguranca"))

    def test_parse_verdict_tolerates_trailing_spaces_and_crlf(self):
        sha = "a" * 40
        v = gate_stamp.parse_verdict(f"VEREDITO: APPROVED \r\nCOMMIT: {sha}\r\nRESUMO: ok  ")
        self.assertEqual(v, {"verdict": "APPROVED", "commit": sha, "resumo": "ok"})


if __name__ == "__main__":
    unittest.main()
