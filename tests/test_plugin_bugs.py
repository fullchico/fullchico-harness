"""Plugin `bugs`: o caçador assina o carimbo `bugs` do commit do topo; o gate barra o envio sem ele."""
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from tests.helpers import ROOT, _tmpdir, commit_file, make_repo

PLUGIN = ROOT / "plugins/bugs"
SHARED = ROOT / "plugins/_shared"
sys.path.insert(0, str(SHARED))
import ledger  # noqa: E402


class PluginCase(unittest.TestCase):
    plugin = PLUGIN
    stamp = "bugs"

    def setUp(self):
        self.home = _tmpdir()
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        self.repo = make_repo()
        self.head = commit_file(self.repo, "a.py", "feat: a")

    def run_script(self, name, payload, raw=None):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(self.plugin), CLAUDE_PROJECT_DIR=str(self.repo))
        return subprocess.run([sys.executable, str(self.plugin / "scripts" / name)],
                              input=raw if raw is not None else json.dumps(payload),
                              capture_output=True, text=True, env=env, cwd=self.repo)

    def read(self, name):
        with open(f"{ledger.state_dir(str(self.repo))}/{name}") as f:
            return f.read()

    def signed(self, commit=None):
        return ledger.has(str(self.repo), self.stamp, commit or self.head)

    def bash(self, command):
        return self.run_script("gate.py", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                           "tool_input": {"command": command}, "cwd": str(self.repo)})


class GateCases:
    """Os casos do gate, iguais nos dois plugins."""

    def test_blocks_every_form_of_send_without_the_stamp(self):
        for cmd in ("git push", "git add . && git push origin x", "gh pr create --fill", "cd x; git push -u origin y",
                    "git -C . push", "FOO=1 git push", "bash -c 'git push'", "true | git push", "git status\ngit push"):
            r = self.bash(cmd)
            self.assertEqual(r.returncode, 2, cmd)
            self.assertIn(self.stamp, r.stderr)

    def test_lets_through_what_is_not_a_send(self):
        for cmd in ('grep "git push" README.md', "git status", "echo git push", "git log --oneline", "gh pr view",
                    "git commit -m 'git push depois'"):
            self.assertEqual(self.bash(cmd).returncode, 0, cmd)

    def test_lets_the_send_through_with_the_stamp(self):
        ledger.sign(str(self.repo), self.stamp, self.head, self.stamp, "0.1.0", "teste", "ok")
        self.assertEqual(self.bash("git push origin x").returncode, 0)

    def test_a_new_commit_needs_a_new_stamp(self):
        ledger.sign(str(self.repo), self.stamp, self.head, self.stamp, "0.1.0", "teste", "ok")
        commit_file(self.repo, "b.py", "feat: b")
        self.assertEqual(self.bash("git push").returncode, 2)

    def test_it_never_breaks_on_garbage(self):
        self.assertEqual(self.run_script("gate.py", None, raw="não é json").returncode, 0)


class TestLedger(PluginCase):
    def test_copies_are_identical_to_the_source(self):
        source = (SHARED / "ledger.py").read_bytes()
        for name in ("bugs", "qualidade"):
            self.assertEqual((ROOT / f"plugins/{name}/scripts/ledger.py").read_bytes(), source, name)

    def test_sign_has_and_log(self):
        repo = str(self.repo)
        self.assertFalse(ledger.has(repo, "x", self.head))
        ledger.sign(repo, "x", self.head, "p", "1", "quem", "resumo")
        self.assertTrue(ledger.has(repo, "x", self.head))
        d = ledger.state_dir(repo)
        data = json.loads(self.read(f"stamps/x/{self.head}.json"))
        self.assertEqual(sorted(data), ["at", "by", "commit", "plugin", "plugin_version", "stamp", "summary"])
        ledger.log(repo, "p", "assinou", "x")
        line = json.loads(self.read("log.jsonl").splitlines()[-1])
        self.assertEqual((line["plugin"], line["what"], line["detail"]), ("p", "assinou", "x"))
        self.assertTrue(str(d).startswith(str(self.home)))

    def test_the_state_is_the_same_from_a_worktree(self):
        wt = _tmpdir() / "wt"
        subprocess.run(["git", "worktree", "add", "-q", "-b", "w", str(wt)], cwd=self.repo, check=True)
        self.assertEqual(ledger.state_dir(str(wt)), ledger.state_dir(str(self.repo)))

    def test_outside_a_repository_nothing_is_written(self):
        self.assertIsNone(ledger.state_dir(str(_tmpdir())))


class TestBugsStamp(PluginCase, GateCases):
    def block(self, verdict="APPROVED", commit=None, extra=""):
        return f"{extra}VEREDITO: {verdict}\nCOMMIT: {commit or self.head}\nRESUMO: conferi o diff\n"

    def stop(self, text, agent="bugs:cacador"):
        return self.run_script("stamp.py", {"hook_event_name": "SubagentStop", "agent_type": agent,
                                            "cwd": str(self.repo), "last_assistant_message": text})

    def handback(self, text, agent="bugs:cacador"):
        return self.run_script("stamp.py", {"hook_event_name": "PreToolUse", "tool_name": "SubagentHandback",
                                            "agent_type": agent, "cwd": str(self.repo),
                                            "tool_input": {"message": text}})

    def test_approved_signs_head_by_both_paths(self):
        for send in (self.stop, self.handback):
            self.assertFalse(self.signed(), send.__name__)
            r = send(self.block())
            self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
            self.assertTrue(self.signed(), send.__name__)
            os.remove(f"{ledger.state_dir(str(self.repo))}/stamps/bugs/{self.head}.json")

    def test_another_agent_does_not_sign(self):
        self.assertEqual(self.stop(self.block(), agent="harness:revisor-bugs").returncode, 0)
        self.assertEqual(self.handback(self.block(), agent="general-purpose").returncode, 0)
        self.assertFalse(self.signed())

    def test_a_commit_that_is_not_head_does_not_sign(self):
        old = self.head
        commit_file(self.repo, "b.py", "feat: b")
        self.assertEqual(self.stop(self.block(commit=old)).returncode, 0)
        self.assertFalse(self.signed(old))
        self.assertFalse(self.signed(ledger.head(str(self.repo))))
        self.stop(self.block(commit="f" * 40))
        self.assertFalse(self.signed(ledger.head(str(self.repo))))

    def test_rejected_removes_the_stamp(self):
        self.stop(self.block())
        self.assertTrue(self.signed())
        self.stop(self.block("REJECTED"))
        self.assertFalse(self.signed())

    def test_an_ambiguous_block_does_not_sign(self):
        for text in (self.block() + self.block("REJECTED"), self.block() + self.block(), "VEREDITO: APPROVED\n",
                     self.block().replace("APPROVED", "TALVEZ"), self.block(commit=self.head[:10])):
            self.stop(text)
            self.handback(text)
            self.assertFalse(self.signed(), text)

    def test_every_decision_goes_to_the_log(self):
        self.stop(self.block("REJECTED"))
        self.stop(self.block())
        lines = self.read("log.jsonl").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(json.loads(l)["plugin"] == "bugs" for l in lines))

    def test_it_never_breaks(self):
        self.assertEqual(self.run_script("stamp.py", None, raw="lixo").returncode, 0)

    def test_manifest_and_hooks(self):
        meta = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
        self.assertEqual((meta["name"], meta["version"]), ("bugs", "0.3.0"))
        hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
        self.assertEqual(hooks["SubagentStop"][0]["matcher"], "^bugs:cacador$")
        self.assertEqual({g["matcher"] for g in hooks["PreToolUse"]}, {"SubagentHandback", "Bash"})
        agent = (PLUGIN / "agents/cacador.md").read_text()
        self.assertIn("model: sonnet", agent)
        self.assertIn("tools: Read, Grep, Glob, Bash", agent)
        self.assertTrue((PLUGIN / "skills/cacar/SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
