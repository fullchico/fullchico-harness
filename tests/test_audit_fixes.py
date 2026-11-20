"""Conflitos achados na auditoria de coerência, cada um com o teste que o reproduz."""
import json
import os
import subprocess
import unittest

from tests.helpers import ROOT, _tmpdir, bug_review_passes, commit_all, commit_file, git, make_repo, run_hook, sync


def ticket(repo, text, name="01-agenda"):
    path = repo / "docs/specs/x/issues" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


class TestIntegrateInstallsBeforeChecking(unittest.TestCase):
    def test_new_dependency_is_installed_before_the_check(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        (repo / "harness.conf").write_text('INSTALL_CMD="cp manifest instalado"\nVALIDATE_PUSH="grep -q nova instalado"\n')
        (repo / "manifest").write_text("antiga\n")
        (repo / ".gitignore").write_text((repo / ".gitignore").read_text() + "instalado\n")
        ticket(repo, "# a\n\nStatus: claimed\nBlocked by:\nOwns: manifest, src\n")
        commit_all(repo, "chore: adopt harness")
        git(repo, "checkout", "-q", "-b", "feat/x")
        agent = repo / ".claude/worktrees/agent-a"
        git(repo, "worktree", "add", "-q", "-b", "worktree-agent-a", str(agent), "HEAD")
        (agent / "manifest").write_text("nova\n")
        (agent / "instalado").write_text("nova\n")  # no worktree dele a dependência já está instalada
        path = agent / "docs/specs/x/issues/01-agenda.md"
        path.write_text(path.read_text().replace("claimed", "done"))
        commit_all(agent, "feat: add dependency")
        bug_review_passes(repo, "worktree-agent-a")
        r = subprocess.run([str(repo / ".harness/integrate"), "docs/specs/x/issues/01-agenda.md", "worktree-agent-a"],
                           cwd=repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)


class TestFreshRemote(unittest.TestCase):
    def test_reviewer_approvals_are_accepted_when_the_remote_is_empty(self):
        remote = _tmpdir() / "vazio.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        repo = make_repo()
        git(repo, "remote", "add", "origin", str(remote))
        self.assertEqual(sync(repo).returncode, 0)
        commit_all(repo, "chore: adopt harness")
        git(repo, "checkout", "-q", "-b", "fix/x")
        sha = commit_file(repo, "a.txt", "fix: a")
        base = git(repo, "merge-base", "HEAD", git(repo, "rev-parse", "HEAD~1"))
        for agent in ("harness:seguranca", "harness:revisor"):
            rc, _, err = run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(repo), "tool_input": {
                "subagent_type": agent, "prompt": f"diff: {base}...{sha}\ncommit: {sha}"}})
            self.assertEqual(rc, 0, err)
            run_hook("gate_stamp.py", {"hook_event_name": "SubagentStop", "agent_type": agent, "cwd": str(repo),
                                       "last_assistant_message": f"VEREDITO: APPROVED\nCOMMIT: {sha}\nRESUMO: ok"})
        run_hook("gate_stamp.py", {"hook_event_name": "SubagentStop", "agent_type": "harness:qualidade", "cwd": str(repo),
                                   "last_assistant_message": f"VEREDITO: APPROVED\nCOMMIT: {sha}\nRESUMO: ok"})
        bug_review_passes(repo, "HEAD")
        r = subprocess.run([str(repo / ".harness/push")], cwd=repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestOldSpecsAreHistory(unittest.TestCase):
    def test_finished_spec_in_the_old_format_does_not_break_the_check(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        ticket(repo, "# antigo\n\nStatus: done\nBlocked by:\n")  # sem Owns: é do formato anterior
        validate = lambda: subprocess.run([str(repo / ".harness/validate"), "--profile", "push"], cwd=repo,
                                          capture_output=True, text=True)
        self.assertEqual(validate().returncode, 0)
        ticket(repo, "# novo\n\nStatus: open\nBlocked by:\n", name="02-novo")  # spec em andamento é conferida
        self.assertNotEqual(validate().returncode, 0)


class TestDiscardRefusedWork(unittest.TestCase):
    def test_discard_removes_an_unmerged_agent_worktree_by_branch(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        commit_all(repo, "chore: adopt harness")
        agent = repo / ".claude/worktrees/agent-a"
        git(repo, "worktree", "add", "-q", "-b", "worktree-agent-a", str(agent), "HEAD")
        commit_file(agent, "a.txt", "fix: a")
        clean = lambda *a: subprocess.run([str(repo / ".harness/agents-clean"), *a], cwd=repo, capture_output=True, text=True)
        clean()
        self.assertTrue(agent.exists())
        self.assertNotEqual(clean("--discard", "main").returncode, 0, "só worktree de agente")
        self.assertEqual(clean("--discard", "worktree-agent-a").returncode, 0)
        self.assertFalse(agent.exists())
        self.assertEqual(git(repo, "branch", "--list", "worktree-agent-a"), "")


class TestProjectWithoutServices(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        self.conf = 'PROJECT=lib\nPROFILE=livre\nINSTALL_CMD="touch instalou"\n'

    def test_setup_worktree_installs_without_ports(self):
        (self.repo / "harness.conf").write_text(self.conf)
        r = subprocess.run([str(self.repo / ".harness/setup-worktree")], cwd=self.repo, capture_output=True, text=True,
                           env=dict(os.environ, HARNESS_SKIP_PLUGIN="1"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.repo / "instalou").exists())

    def test_conf_apply_succeeds_without_services(self):
        (self.repo / ".harness-run").mkdir(exist_ok=True)
        (self.repo / ".harness-run/harness.conf").write_text(self.conf)
        rc = run_hook("service_guard.py", {"tool_name": "Bash", "cwd": str(self.repo),
                                           "tool_input": {"command": ".harness/conf-apply"}})[0]
        self.assertEqual(rc, 0)
        r = subprocess.run([str(self.repo / ".harness/conf-apply")], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestClosingRunsTheWholeCheck(unittest.TestCase):
    def test_architecture_check_also_gates_the_closing_commit(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        path = ticket(repo, "# a\n\nStatus: claimed\nBlocked by:\nOwns: src\n")
        (repo / "harness.conf").write_text('VALIDATE_PUSH="true"\nVALIDATE_ARCH="echo fronteira-violada; exit 4"\n')
        commit_all(repo, "chore: adopt harness")
        path.write_text(path.read_text().replace("claimed", "done"))
        git(repo, "add", "-A")
        r = subprocess.run(["git", "commit", "-q", "-m", "feat: a"], cwd=repo, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("fronteira-violada", r.stdout + r.stderr)


class TestSmallThings(unittest.TestCase):
    def test_env_file_is_ignored_from_the_first_sync(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        self.assertIn(".env", (repo / ".gitignore").read_text().splitlines())

    def test_reviewer_can_load_its_rubric(self):
        head = (ROOT / "plugin/agents/revisor.md").read_text().split("---")[1]
        self.assertIn("Skill", head)
        self.assertNotIn("Edit", head)
        self.assertNotIn("Write", head)


if __name__ == "__main__":
    unittest.main()


class TestSecondAudit(unittest.TestCase):
    def test_validate_gives_the_project_command_the_feature_env(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        (repo / ".env").write_text("POSTGRES_PORT=37752\n")
        (repo / "harness.conf").write_text("VALIDATE_PUSH='test \"$POSTGRES_PORT\" = 37752'\n")
        r = subprocess.run([str(repo / ".harness/validate"), "--profile", "push"], cwd=repo, capture_output=True,
                           text=True, env={k: v for k, v in os.environ.items() if k != "POSTGRES_PORT"})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_setup_worktree_survives_a_failing_install(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        (repo / "harness.conf").write_text('PROJECT=novo\nINSTALL_CMD="exit 7"\n')
        commit_all(repo, "chore: adopt harness")
        agent = repo / ".claude/worktrees/agent-a"
        git(repo, "worktree", "add", "-q", "-b", "worktree-agent-a", str(agent), "HEAD")
        run = lambda where: subprocess.run([str(where / ".harness/setup-worktree")], cwd=where, capture_output=True,
                                           text=True, env=dict(os.environ, HARNESS_SKIP_PLUGIN="1"))
        r = run(agent)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("INSTALL_CMD", r.stdout + r.stderr)
        self.assertEqual(run(repo).returncode, 7, "num worktree de feature a falha continua aparecendo")

    def test_texts_agree_on_three_gates_english_examples_and_who_runs_the_app(self):
        run = ROOT / "plugin/payload/entrega"
        closing = (run / "fechamento.md").read_text()
        self.assertIn("Os quatro aprovaram", closing)
        self.assertNotIn("Os dois aprovaram", closing)
        self.assertNotIn(".harness/dev --background", closing)
        tickets = (run / "tickets.md").read_text()
        for portuguese in ("modules/arquivos", "pages/perfil"):
            self.assertNotIn(portuguese, tickets)
        stack = (ROOT / "plugin/templates/docs/agents/stack.md").read_text()
        for needed in ("webServer", "host.docker.internal", "VALIDATE_MERGE", "shm_size"):
            self.assertIn(needed, stack, needed)
        security = (ROOT / "plugin/agents/seguranca.md").read_text()
        self.assertIn("Skill", security.split("---")[1])
        self.assertIn("owasp-security", security)
        self.assertIn("accessibility", (ROOT / "plugin/agents/revisor.md").read_text())
        self.assertIn("Critérios de aceite", (ROOT / "plugin/skills/entregar/references/spec.md").read_text())
