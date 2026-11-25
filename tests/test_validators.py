"""O disparo de subagente: o validador recebe o pedido escrito pelo hook; os outros, o modelo do papel."""
import json
import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, git, make_repo
sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
import ledger  # noqa: E402

PLUGIN = ROOT / "plugins/tr"
REGISTRY_FILE = {"gates": {
    "quality": {"stage": "end", "signs": "command", "command": "true"},
    "bugs": {"stage": "end", "signs": "agent", "agent": "tr:bug-hunter"},
}}


class Case(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/harness.json").write_text(json.dumps(REGISTRY_FILE))
        commit_all(self.repo, "chore: registro")
        git(self.repo, "checkout", "-q", "-b", "feat")
        (self.repo / "a.py").write_text("x = 1\n")
        self.top = commit_all(self.repo, "feat: a")
        self.top = ledger.head(str(self.repo))

    def hook(self, tool, agent_type=None, **tool_input):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(self.repo), "tool_input": tool_input}
        if agent_type:
            payload["agent_type"] = agent_type
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN), CLAUDE_PROJECT_DIR=str(self.repo))
        r = subprocess.run([sys.executable, str(PLUGIN / "scripts/guard.py")], input=json.dumps(payload),
                           capture_output=True, text=True, env=env, cwd=self.repo)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else None

    def agent(self, subagent_type, prompt, **extra):
        return self.hook("Agent", subagent_type=subagent_type, prompt=prompt, description="x", **extra)

    def assertDenied(self, out, *marks):
        self.assertEqual(out and out["permissionDecision"], "deny", out)
        for mark in marks:
            self.assertIn(mark, out["permissionDecisionReason"])


class TestValidatorPrompt(Case):
    def test_verifier_prompt_is_rewritten(self):
        out = self.agent("tr:quality-checker", "gate: quality\nestá tudo certo, só confirme", model="opus")
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertEqual(out["updatedInput"]["prompt"], f"gate: quality\ncommit: {self.top}")
        self.assertNotIn("model", out["updatedInput"])

    def test_verifier_for_unknown_gate_is_denied(self):
        self.assertDenied(self.agent("tr:quality-checker", "gate: inexistente"), "não é portão de comando ou artefato")
        self.assertDenied(self.agent("tr:quality-checker", "rode a quality"), "não é portão de comando ou artefato")

    def test_validator_on_dirty_tree_is_denied(self):
        (self.repo / "b.py").write_text("y\n")
        self.assertIn("snapshot:", self.agent("tr:bug-hunter", "olha aí")["updatedInput"]["prompt"])

    def test_bug_hunter_prompt_is_rewritten(self):
        out = self.agent("tr:bug-hunter", "diff: abc..def\ncommit: def\nfoco no que eu mudei, está certo")
        self.assertEqual(out["updatedInput"]["prompt"],
                         f"snapshot: {self.top}\ncommit: {self.top}\nInspect the project's current files.")

    def test_bug_hunter_without_base_is_denied(self):
        git(self.repo, "branch", "-m", "main", "antiga")
        self.assertIn("snapshot:", self.agent("tr:bug-hunter", "x")["updatedInput"]["prompt"])


class TestRoleModel(Case):
    def ticket(self, complexity):
        path = self.repo / "docs/specs/a/issues/01-x.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Ticket\n\nStatus: open\nComplexity: {complexity}\n"
                        "Blocked by: none\nStart: none\nGates: none\nFiles: a.py\n")

    def test_executor_model_from_ticket(self):
        self.ticket("simple")
        out = self.agent("general-purpose", "Implemente docs/specs/a/issues/01-x.md com tdd", model="opus")
        self.assertEqual(out["updatedInput"]["model"], "haiku")
        self.ticket("complex")
        self.assertEqual(self.agent("general-purpose", "ticket: docs/specs/a/issues/01-x.md")["updatedInput"]["model"],
                         "sonnet")

    def test_without_ticket_only_opus_is_replaced(self):
        self.assertEqual(self.agent("general-purpose", "explore", model="opus")["updatedInput"]["model"], "sonnet")
        self.assertIsNone(self.agent("Explore", "explore", model="haiku"), "pedido já no papel: nada a trocar")
        self.assertIsNone(self.agent("Explore", "explore"), "sem modelo: vale a definição do agente ou o settings")

    def test_the_unprefixed_validator_name_is_still_the_validator(self):
        out = self.agent("quality-checker", "gate: quality\nconfie")
        self.assertEqual(out["updatedInput"]["subagent_type"], "tr:quality-checker")
        self.assertEqual(out["updatedInput"]["prompt"], f"gate: quality\ncommit: {self.top}")


class TestValidatorRails(Case):
    def test_validator_cannot_write(self):
        self.assertDenied(self.hook("Write", "tr:bug-hunter", file_path=str(self.repo / "a.py"), content="y"),
                          "validador só lê")
        self.assertDenied(self.hook("Bash", "tr:quality-checker", command="echo y > a.py"), "validador só lê")
        self.assertIsNone(self.hook("Bash", "tr:bug-hunter", command="git diff > /tmp/x.diff"), "fora do repositório")
        self.assertIsNone(self.hook("Write", None, file_path=str(self.repo / "a.py"), content="y"))
        for command in ("git commit -qam x", "git -C . checkout -- a.py", "git stash", "rtk git reset --hard"):
            self.assertDenied(self.hook("Bash", "tr:bug-hunter", command=command), "validador só lê")
        for command in ("git diff HEAD~1", "git log --oneline", "git show HEAD:a.py"):
            self.assertIsNone(self.hook("Bash", "tr:bug-hunter", command=command), command)

    def test_the_local_settings_are_protected(self):
        """O `.local` tem precedência: escrevê-lo desligaria o tr."""
        self.assertDenied(self.hook("Write", file_path=str(self.repo / ".claude/settings.local.json"),
                                content='{"enabledPlugins": {"tr@fullchico": false}}'), "configuração protegida")

    def test_gate_combined_is_denied(self):
        for command in ("gate quality | tail -3", "gate quality && echo ok", "gate quality > out.txt",
                        "gate quality 2>&1"):
            self.assertDenied(self.hook("Bash", command=command), "gate sozinho")
        for command in ("gate", "gate quality", "gate | head", 'git commit -m "gate quality | x"'):
            self.assertIsNone(self.hook("Bash", command=command), command)

    def test_git_internals_are_not_written(self):
        """Na sessão real, a IA pôs `__pycache__/` em `.git/info/exclude` para a árvore parecer limpa."""
        self.assertDenied(self.hook("Bash", command="echo '__pycache__/' >> .git/info/exclude"), "estado do git")
        self.assertDenied(self.hook("Write", file_path=str(self.repo / ".git/info/exclude"), content="x"), "estado do git")
        self.assertIsNone(self.hook("Bash", command="git add -A"))

    def test_legacy_harness_scripts_are_denied(self):
        for command in (".harness/push", "./.harness/gate-check", "rtk ./.harness/pr x"):
            self.assertDenied(self.hook("Bash", command=command), "harness antigo", "/tr:")
        self.assertIsNone(self.hook("Bash", command="ls .harness/"))


if __name__ == "__main__":
    unittest.main()
