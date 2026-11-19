"""Achados da revisão do plano 3: o que impediria a entrega em paralelo de funcionar."""
import json
import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, git, make_repo, run_hook, sync


def settings(repo):
    return json.loads((repo / ".claude/settings.json").read_text())


class TestSettingsForDelivery(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        self.s = settings(self.repo)

    def test_agent_worktrees_start_from_the_feature_head(self):
        self.assertEqual(self.s["worktree"]["baseRef"], "head")

    def test_sandboxed_commands_and_remote_scripts_do_not_prompt(self):
        self.assertIs(self.s["sandbox"]["autoAllowBashIfSandboxed"], True)
        allow = self.s["permissions"]["allow"]
        for form in (".harness/fetch", ".harness/push", ".harness/push --force", ".harness/pr *"):
            self.assertIn(f"Bash({form})", allow)
        for form in (".harness/up", ".harness/down", ".harness/destroy"):
            self.assertNotIn(f"Bash({form})", allow)
            self.assertIn(f"Bash({form})", self.s["permissions"]["ask"])

    def test_gitignore_covers_agent_worktrees_and_run_files(self):
        lines = (self.repo / ".gitignore").read_text().splitlines()
        self.assertIn(".claude/worktrees/", lines)
        self.assertIn(".harness-run/", lines)
        (self.repo / ".gitignore").write_text("node_modules/\n.claude/worktrees/\n")
        self.assertEqual(sync(self.repo).returncode, 0)
        text = (self.repo / ".gitignore").read_text()
        self.assertIn("node_modules/", text)
        self.assertEqual(text.count(".claude/worktrees/"), 1)
        self.assertIn(".harness-run/", text)


class TestAgentWorktreeSetup(unittest.TestCase):
    def test_agent_worktree_gets_the_feature_env_not_the_main_one(self):
        repo = make_repo("principal")
        sync(repo)
        (repo / "harness.conf").write_text('PROJECT=meuapp\nSERVICES="web db"\nINSTALL_CMD="touch instalado.txt"\n')
        commit_all(repo, "chore: adopt harness")
        (repo / ".env").write_text("ORIGEM=principal\n")
        feature = repo.parent / "roseau"
        git(repo, "worktree", "add", "-q", str(feature), "-b", "feat/x")
        (feature / ".env").write_text("ORIGEM=feature\nSEGREDO=abc\n")
        agent = feature / ".claude/worktrees/agent-a1"
        git(repo, "worktree", "add", "-q", "--detach", str(agent))
        env = {k: v for k, v in os.environ.items() if k not in ("CONDUCTOR_PORT", "HARNESS_ENV")}
        log = repo.parent / "claude.log"
        fake = repo.parent / "bin"
        fake.mkdir()
        (fake / "claude").write_text(f'#!/bin/sh\necho "$*" >> "{log}"\n')
        (fake / "claude").chmod(0o755)
        r = subprocess.run([str(agent / ".harness/setup-worktree")], cwd=agent,
                           env=dict(env, PATH=f"{fake}:{env['PATH']}"), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        values = dict(l.split("=", 1) for l in (agent / ".env").read_text().splitlines() if "=" in l)
        self.assertEqual(values["ORIGEM"], "feature")
        self.assertEqual(values["SEGREDO"], "abc")
        self.assertEqual(values["COMPOSE_PROJECT_NAME"], "meuapp-roseau")
        self.assertTrue((agent / "instalado.txt").exists())
        self.assertFalse(log.exists(), "worktree de agente não instala plugins")


class TestRulesOnlyForImplementers(unittest.TestCase):
    def start(self, repo, agent):
        return run_hook("subagent_context.py", {"hook_event_name": "SubagentStart", "agent_type": agent,
                                                "cwd": str(repo)})[1]

    def test_only_the_harness_implementer_and_project_agents_get_the_rules(self):
        repo = make_repo()
        (repo / ".claude/agents").mkdir(parents=True)
        (repo / ".claude/agents/backend.md").write_text("---\nname: backend\n---\n")
        for agent in ("harness:implementador", "backend"):
            self.assertIn("additionalContext", self.start(repo, agent), agent)
        for agent in ("Explore", "general-purpose", "Plan", "outro-plugin:pesquisador", "frontend",
                      "harness:revisor", "../../etc/passwd"):
            self.assertEqual(self.start(repo, agent), "", agent)


class TestImplementerFilesMustBeCommitted(unittest.TestCase):
    def test_uncommitted_spec_ticket_or_finding_is_denied(self):
        repo = make_repo()
        for path in ("docs/specs/x/spec.md", "docs/specs/x/issues/01-a.md"):
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / path).write_text("x")
        ask = lambda extra="": run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(repo), "tool_input": {
            "subagent_type": "harness:implementador",
            "prompt": "spec: docs/specs/x/spec.md\nticket: docs/specs/x/issues/01-a.md" + extra}})
        rc, _, err = ask()
        self.assertEqual(rc, 2)
        self.assertIn("commit", err)
        commit_all(repo, "docs: add spec")
        self.assertEqual(ask()[0], 0)
        (repo / "docs/specs/x/achados").mkdir()
        (repo / "docs/specs/x/achados/01-rodada-1.md").write_text("achado")
        self.assertEqual(ask("\nachado: docs/specs/x/achados/01-rodada-1.md")[0], 2)
        commit_all(repo, "docs: record finding")
        self.assertEqual(ask("\nachado: docs/specs/x/achados/01-rodada-1.md")[0], 0)
        (repo / "docs/specs/x/spec.md").write_text("mudou sem commit")
        self.assertEqual(ask()[0], 2)


class TestTicketsCheckWrongFolder(unittest.TestCase):
    def test_folder_that_does_not_exist_is_an_error(self):
        repo = make_repo()
        r = subprocess.run([sys.executable, "-I", str(ROOT / "plugin/payload/tickets_check.py"),
                            str(repo / "docs/specs/slug-errado"), "--frontier"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("slug-errado", r.stderr)


if __name__ == "__main__":
    unittest.main()
