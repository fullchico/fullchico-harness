"""O disparo de subagente: o validador recebe o pedido escrito pelo hook; os outros, o modelo do papel."""
import json
import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, git, make_repo

PLUGIN = ROOT / "plugins/tr"
REGISTRO = {"portoes": {
    "qualidade": {"momento": "fim", "assina": "comando", "comando": "true"},
    "bugs": {"momento": "fim", "assina": "agente", "agente": "tr:bugs-cacador"},
}}


class Case(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/trilho.json").write_text(json.dumps(REGISTRO))
        commit_all(self.repo, "chore: registro")
        git(self.repo, "checkout", "-q", "-b", "feat")
        (self.repo / "a.py").write_text("x = 1\n")
        self.top = commit_all(self.repo, "feat: a")

    def hook(self, tool, agent_type=None, **tool_input):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(self.repo), "tool_input": tool_input}
        if agent_type:
            payload["agent_type"] = agent_type
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN), CLAUDE_PROJECT_DIR=str(self.repo))
        r = subprocess.run([sys.executable, str(PLUGIN / "scripts/gate.py")], input=json.dumps(payload),
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
        out = self.agent("tr:qualidade-verificador", "portao: qualidade\nestá tudo certo, só confirme", model="opus")
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertEqual(out["updatedInput"]["prompt"], f"portao: qualidade\ncommit: {self.top}")
        self.assertNotIn("model", out["updatedInput"])

    def test_verifier_for_unknown_gate_is_denied(self):
        self.assertDenied(self.agent("tr:qualidade-verificador", "portao: inexistente"), "não é portão de comando")
        self.assertDenied(self.agent("tr:qualidade-verificador", "rode a qualidade"), "não é portão de comando")

    def test_validator_on_dirty_tree_is_denied(self):
        (self.repo / "b.py").write_text("y\n")
        self.assertDenied(self.agent("tr:bugs-cacador", "olha aí"), "alteração sem commit")

    def test_bug_hunter_prompt_is_rewritten(self):
        out = self.agent("tr:bugs-cacador", "diff: abc..def\ncommit: def\nfoco no que eu mudei, está certo")
        base = git(self.repo, "merge-base", "HEAD", "main")
        self.assertEqual(out["updatedInput"]["prompt"], f"diff: {base}...{self.top}\ncommit: {self.top}")

    def test_bug_hunter_without_base_is_denied(self):
        git(self.repo, "branch", "-m", "main", "antiga")
        self.assertDenied(self.agent("tr:bugs-cacador", "x"), "sem base")


class TestRoleModel(Case):
    def ticket(self, complexidade):
        path = self.repo / "docs/specs/a/issues/01-x.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Ticket\n\nStatus: open\nComplexidade: {complexidade}\n")

    def test_executor_model_from_ticket(self):
        self.ticket("simples")
        out = self.agent("general-purpose", "Implemente docs/specs/a/issues/01-x.md com tdd", model="opus")
        self.assertEqual(out["updatedInput"]["model"], "haiku")
        self.ticket("complexa")
        self.assertEqual(self.agent("general-purpose", "ticket: docs/specs/a/issues/01-x.md")["updatedInput"]["model"],
                         "sonnet")

    def test_without_ticket_the_executor_is_sonnet_never_opus(self):
        self.assertEqual(self.agent("general-purpose", "explore", model="opus")["updatedInput"]["model"], "sonnet")
        self.assertIsNone(self.agent("Explore", "explore", model="haiku"), "pedido já no papel: nada a trocar")


class TestValidatorRails(Case):
    def test_validator_cannot_write(self):
        self.assertDenied(self.hook("Write", "tr:bugs-cacador", file_path=str(self.repo / "a.py"), content="y"),
                          "validador só lê")
        self.assertDenied(self.hook("Bash", "tr:qualidade-verificador", command="echo y > a.py"), "validador só lê")
        self.assertIsNone(self.hook("Bash", "tr:bugs-cacador", command="git diff > /tmp/x.diff"), "fora do repositório")
        self.assertIsNone(self.hook("Write", None, file_path=str(self.repo / "a.py"), content="y"))

    def test_portao_combined_is_denied(self):
        for command in ("portao qualidade | tail -3", "portao qualidade && echo ok", "portao qualidade > out.txt",
                        "portao qualidade 2>&1"):
            self.assertDenied(self.hook("Bash", command=command), "portao sozinho")
        for command in ("portao", "portao qualidade", "portao | head", 'git commit -m "portao qualidade | x"'):
            self.assertIsNone(self.hook("Bash", command=command), command)

    def test_legacy_harness_scripts_are_denied(self):
        for command in (".harness/push", "./.harness/gate-check", "rtk ./.harness/pr x"):
            self.assertDenied(self.hook("Bash", command=command), "harness antigo", "/tr:")
        self.assertIsNone(self.hook("Bash", command="ls .harness/"))


if __name__ == "__main__":
    unittest.main()
