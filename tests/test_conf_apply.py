"""O agente propõe o harness.conf; o dono confirma; só o que o dono viu é gravado."""
import json
import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, make_repo, sync

HOOKS = ROOT / "plugin/payload/hooks"
GOOD = ('# proposto na entrega\nPROJECT=barbearia\nSERVICES="web api postgres"\n'
        'VALIDATE_PUSH="pnpm test"\n')


class TestConfApply(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        (self.repo / ".harness-run").mkdir(exist_ok=True)
        self.proposal = self.repo / ".harness-run/harness.conf"
        self.before = (self.repo / "harness.conf").read_text()

    def guard(self, command=".harness/conf-apply"):
        payload = {"tool_name": "Bash", "cwd": str(self.repo), "tool_input": {"command": command}}
        r = subprocess.run([sys.executable, str(HOOKS / "service_guard.py")], input=json.dumps(payload),
                           capture_output=True, text=True)
        return r.returncode, (json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else None), r.stderr

    def apply(self):
        return subprocess.run([str(self.repo / ".harness/conf-apply")], cwd=self.repo, capture_output=True, text=True)

    def test_settings_put_the_command_outside_the_sandbox_and_always_ask(self):
        s = json.loads((self.repo / ".claude/settings.json").read_text())
        for form in (".harness/conf-apply", "./.harness/conf-apply"):
            self.assertIn(form, s["sandbox"]["excludedCommands"])
            self.assertIn(f"Bash({form})", s["permissions"]["ask"])

    def test_owner_sees_the_whole_proposal_and_it_is_applied(self):
        self.proposal.write_text(GOOD)
        rc, hook, _ = self.guard()
        self.assertEqual(rc, 0)
        self.assertEqual(hook["permissionDecision"], "ask")
        for piece in ("PROJECT=barbearia", 'VALIDATE_PUSH="pnpm test"', "fora do sandbox"):
            self.assertIn(piece, hook["permissionDecisionReason"])
        r = self.apply()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.repo / "harness.conf").read_text(), GOOD)
        self.assertIn("WEB_PORT", (self.repo / ".env").read_text())
        self.assertNotEqual(self.apply().returncode, 0, "a aprovação vale uma vez")

    def test_without_the_question_nothing_is_written(self):
        self.proposal.write_text(GOOD)
        r = self.apply()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual((self.repo / "harness.conf").read_text(), self.before)

    def test_what_is_applied_is_what_was_shown(self):
        self.proposal.write_text(GOOD)
        self.guard()
        self.proposal.write_text(GOOD + 'VALIDATE_PUSH="true"\n')
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual((self.repo / "harness.conf").read_text(), GOOD)

    def test_bad_proposals_are_denied(self):
        self.assertEqual(self.guard()[0], 2, "sem proposta")
        for content in ("PROJECT=x\nrm -rf /\n", "", "# só comentário\n", "PROJECT=x\n" + "A=1\n" * 2000,
                        "SERVICES=web\n"):
            self.proposal.write_text(content)
            rc, hook, err = self.guard()
            self.assertEqual(rc, 2, repr(content[:30]))
        self.proposal.unlink()
        os.symlink("/etc/hosts", self.proposal)
        self.assertEqual(self.guard()[0], 2, "link")

    def test_other_spellings_do_not_reach_the_script_quietly(self):
        self.proposal.write_text(GOOD)
        rc, hook, _ = self.guard(".harness/conf-apply outro")
        self.assertIsNone(hook)  # não é a forma exata: fica no sandbox, onde o script não consegue gravar


class TestAutonomy(unittest.TestCase):
    def test_skill_teaches_the_autonomous_mode_and_the_conf_proposal(self):
        skill = (ROOT / "plugin/skills/entregar/SKILL.md").read_text()
        refs = "".join(p.read_text() for p in (ROOT / "plugin/skills/entregar/references").glob("*.md"))
        self.assertIn("Modo autônomo", skill)
        self.assertIn("Decisões tomadas sem o dono", skill + refs)
        self.assertIn(".harness/conf-apply", skill + refs)
        self.assertIn(".harness-run/harness.conf", skill + refs)


if __name__ == "__main__":
    unittest.main()
