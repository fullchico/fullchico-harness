"""Regras que eram só texto nos roteiros e viraram recusa por máquina."""
import subprocess
import time
import unittest

from tests.helpers import bug_review_passes, commit_all, git, make_repo, run_hook, sync

CONF = ('PROJECT=p\nPROFILE=livre\nVALIDATE_PUSH="true"\nVALIDATE_MERGE="true"\nVALIDATE_ARCH="true"\n'
        'MODULE_ROOTS="src/modules"\nCONTRACT_PATHS="packages/contract"\n')


def bash(repo, command, agent=None):
    payload = {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": command}}
    if agent:
        payload["agent_type"] = agent
    return run_hook("service_guard.py", payload)


class TestChecksStayOn(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        (self.repo / "harness.conf").write_text(CONF)
        (self.repo / ".harness-run").mkdir(exist_ok=True)

    def propose(self, text):
        (self.repo / ".harness-run/harness.conf").write_text(text)
        return bash(self.repo, ".harness/conf-apply")

    def test_a_check_already_set_cannot_be_removed_or_emptied(self):
        for key in ("VALIDATE_PUSH", "VALIDATE_MERGE", "VALIDATE_ARCH", "MODULE_ROOTS", "CONTRACT_PATHS"):
            lines = [l for l in CONF.splitlines() if not l.startswith(key + "=")]
            for proposal in ("\n".join(lines) + "\n", "\n".join(lines + [f'{key}=""']) + "\n",
                             "\n".join(lines + [f"#{key}=x"]) + "\n"):
                rc, _, err = self.propose(proposal)
                self.assertEqual(rc, 2, key)
                self.assertIn(key, err)

    def test_a_check_can_change_and_new_ones_can_come(self):
        self.assertEqual(self.propose(CONF.replace('VALIDATE_ARCH="true"', 'VALIDATE_ARCH="pnpm arch"') + "SERVICES=web\n")[0], 0)


class TestWhoRunsWhat(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)

    def test_only_the_owner_and_the_orchestrator_touch_the_environment_and_the_remote(self):
        for agent in ("harness:implementador", "harness:revisor-bugs", "harness:revisor-ambiente", "harness:revisor",
                      "harness:seguranca", "harness:qualidade", "harness:revisor-spec"):
            for command in (".harness/up", ".harness/down", ".harness/destroy", ".harness/push", ".harness/dev --background",
                            '.harness/pr create "feat: a" body.md'):
                rc, _, err = bash(self.repo, command, agent)
                self.assertEqual(rc, 2, f"{agent}: {command}")
                self.assertIn("orquestrador", err)
        for agent in ("harness:orquestrador", None):
            self.assertEqual(bash(self.repo, ".harness/up", agent)[0], 0, str(agent))

    def test_the_orchestrator_joins_only_through_integrate(self):
        for command in ("git merge worktree-agent-a", "git rebase main", "git cherry-pick abc1234", "cd x && git merge -q b"):
            rc, _, err = bash(self.repo, command, "harness:orquestrador")
            self.assertEqual(rc, 2, command)
            self.assertIn(".harness/integrate", err)
        self.assertEqual(bash(self.repo, "git merge --abort", "harness:orquestrador")[0], 0)
        self.assertEqual(bash(self.repo, "git merge worktree-agent-a", "harness:implementador")[0], 0)
        self.assertEqual(bash(self.repo, "git merge origin/main", None)[0], 0)

    def test_implementer_always_gets_its_own_worktree(self):
        issues = self.repo / "docs/specs/x/issues"
        issues.mkdir(parents=True)
        (issues / "01-a.md").write_text("# a\n\nStatus: claimed\nBlocked by:\nOwns: src/a\n")
        (self.repo / "docs/specs/x/spec.md").write_text("spec\n")
        commit_all(self.repo, "chore: adopt harness")
        ask = lambda **extra: run_hook("dispatch_guard.py", {
            "tool_name": "Agent", "cwd": str(self.repo), "agent_type": "harness:orquestrador",
            "tool_input": {"subagent_type": "harness:implementador", "run_in_background": False,
                           "prompt": "spec: docs/specs/x/spec.md\nticket: docs/specs/x/issues/01-a.md", **extra}})
        rc, _, err = ask()
        self.assertEqual(rc, 2)
        self.assertIn("isolation", err)
        self.assertEqual(ask(isolation="worktree")[0], 0)


class TestCleaning(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        (self.repo / "harness.conf").write_text('PROFILE=livre\nVALIDATE_PUSH="true"\n')
        (self.repo / ".gitignore").write_text((self.repo / ".gitignore").read_text() + "node_modules/\n")
        ticket = self.repo / "docs/specs/x/issues/01-agenda.md"
        ticket.parent.mkdir(parents=True)
        ticket.write_text("# a\n\nStatus: claimed\nBlocked by:\nOwns: src/agenda\n")
        commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "feat/x")
        self.agent = self.repo / ".claude/worktrees/agent-a"
        git(self.repo, "worktree", "add", "-q", "-b", "worktree-agent-a", str(self.agent), "HEAD")

    def clean(self):
        return subprocess.run([str(self.repo / ".harness/agents-clean")], cwd=self.repo, capture_output=True, text=True)

    def test_work_in_progress_is_not_thrown_away(self):
        (self.agent / "rascunho.txt").write_text("ainda sem commit\n")
        r = self.clean()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.agent / "rascunho.txt").exists())
        self.assertIn("alteração sem commit", r.stdout)
        (self.agent / "rascunho.txt").unlink()
        self.clean()
        self.assertFalse(self.agent.exists(), "sem nada pendente, o worktree já integrado sai")

    def test_integrating_frees_what_can_be_rebuilt_even_when_the_worktree_is_in_use(self):
        (self.agent / "src/agenda").mkdir(parents=True)
        (self.agent / "src/agenda/a.py").write_text("x\n")
        (self.agent / "node_modules/pkg").mkdir(parents=True)
        (self.agent / "node_modules/pkg/big.bin").write_text("x" * 1000)
        path = self.agent / "docs/specs/x/issues/01-agenda.md"
        path.write_text(path.read_text().replace("claimed", "done"))
        commit_all(self.agent, "feat: agenda")
        git(self.repo, "worktree", "lock", str(self.agent))
        bug_review_passes(self.repo, "worktree-agent-a")
        r = subprocess.run([str(self.repo / ".harness/integrate"), "docs/specs/x/issues/01-agenda.md", "worktree-agent-a"],
                           cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.agent.exists(), "em uso: a pasta fica")
        self.assertFalse((self.agent / "node_modules").exists(), "mas o que se reconstrói sai do disco")
        self.assertTrue((self.agent / "src/agenda/a.py").exists())

    def test_setup_refuses_to_start_without_disk_space(self):
        r = subprocess.run([str(self.agent / ".harness/setup-worktree")], cwd=self.agent, capture_output=True, text=True,
                           env={**__import__("os").environ, "HARNESS_MIN_FREE_MB": "999999999", "HARNESS_SKIP_PLUGIN": "1"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("espaço", r.stderr)


class TestDownStopsTheWholeApp(unittest.TestCase):
    def test_children_of_the_app_do_not_keep_running(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        (repo / "harness.conf").write_text("PROFILE=livre\nDEV_CMD=\"sh -c 'sleep 31337 & sleep 31337 & wait'\"\n")
        alive = lambda: subprocess.run(["pgrep", "-f", "sleep 31337"], capture_output=True, text=True).stdout.split()
        before = set(alive())
        r = subprocess.run([str(repo / ".harness/dev"), "--background"], cwd=repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        time.sleep(1)
        self.assertGreaterEqual(len(set(alive()) - before), 2)
        try:
            r = subprocess.run([str(repo / ".harness/down")], cwd=repo, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            time.sleep(1)
            self.assertEqual(set(alive()) - before, set())
        finally:
            for pid in set(alive()) - before:
                subprocess.run(["kill", pid])


class TestPendingsPerTicket(unittest.TestCase):
    """O teto de pendências é do ticket, somando rodadas e revisores, e o mesmo ponto não conta duas vezes."""

    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        issues = self.repo / "docs/specs/x/issues"
        issues.mkdir(parents=True)
        for name in ("01-a", "02-b"):
            (issues / f"{name}.md").write_text("# t\n\nStatus: claimed\nBlocked by:\nOwns: src/" + name + "\n")
        (self.repo / "docs/specs/x/spec.md").write_text("spec\n")
        commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "feat/x")
        self.base = git(self.repo, "rev-parse", "HEAD")
        (self.repo / "a.txt").write_text("a\n")
        self.sha = commit_all(self.repo, "feat: a")

    def review(self, body, ticket="01-a", agent="harness:revisor-bugs"):
        prompt = f"spec: docs/specs/x/spec.md\nticket: docs/specs/x/issues/{ticket}.md\ndiff: {self.base}...{self.sha}\ncommit: {self.sha}"
        rc = run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(self.repo), "agent_type": "harness:orquestrador",
                                            "tool_input": {"subagent_type": agent, "prompt": prompt, "run_in_background": False}})[0]
        self.assertEqual(rc, 0)
        run_hook("gate_stamp.py", {"hook_event_name": "SubagentStop", "agent_type": agent, "cwd": str(self.repo),
                                   "last_assistant_message": f"{body}\nVEREDITO: APPROVED\nCOMMIT: {self.sha}\nRESUMO: x"})

    def approved(self, gate="bugs"):
        import os
        import common
        return os.path.exists(common.approval_path(common.state_dir(str(self.repo)), gate, self.sha))

    def pendings(self):
        return subprocess.run([str(self.repo / ".harness/pendings")], cwd=self.repo, capture_output=True, text=True).stdout

    def test_cap_adds_up_across_reviewers_and_rounds_of_the_same_ticket(self):
        self.review("PENDENCIA: src/a.ts:1 um | teste: t\nPENDENCIA: src/a.ts:2 dois | teste: t")
        self.assertTrue(self.approved())
        self.review("PENDENCIA: src/a.ts:3 três | teste: t", agent="harness:revisor-ambiente")
        self.assertFalse(self.approved("ambiente"), "o ticket já tinha duas abertas")
        self.assertNotIn("três", self.pendings())
        self.review("PENDENCIA: src/b.ts:1 de outro ticket | teste: t", ticket="02-b")
        self.assertIn("de outro ticket", self.pendings())

    def test_the_same_spot_seen_twice_is_one_pending(self):
        self.review("PENDENCIA: package.json:13 o script sai com zero | teste: t")
        self.review("PENDENCIA: package.json:13 script passa calado quando falta o arquivo | teste: t2", agent="harness:revisor-ambiente")
        self.assertEqual(len(self.pendings().strip().splitlines()), 1)
        self.assertTrue(self.approved("ambiente"))


class TestDispatchAndPr(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        issues = self.repo / "docs/specs/x/issues"
        issues.mkdir(parents=True)
        self.ticket = issues / "01-a.md"
        self.ticket.write_text("# a\n\nStatus: open\nBlocked by:\nOwns: src/a\n")
        (self.repo / "docs/specs/x/spec.md").write_text("spec\n")
        commit_all(self.repo, "chore: adopt harness")

    def test_only_a_claimed_ticket_is_dispatched(self):
        ask = lambda: run_hook("dispatch_guard.py", {
            "tool_name": "Agent", "cwd": str(self.repo), "agent_type": "harness:orquestrador",
            "tool_input": {"subagent_type": "harness:implementador", "run_in_background": False, "isolation": "worktree",
                           "prompt": "spec: docs/specs/x/spec.md\nticket: docs/specs/x/issues/01-a.md"}})
        rc, _, err = ask()
        self.assertEqual(rc, 2)
        self.assertIn(".harness/ticket claim", err)
        self.ticket.write_text(self.ticket.read_text().replace("open", "claimed"))
        commit_all(self.repo, "chore(tickets): claim 01")
        self.assertEqual(ask()[0], 0)

    def test_pr_title_follows_the_commit_format_and_the_body_carries_no_ai_signature(self):
        body = self.repo / "body.md"
        good = "Corrige a.\n\n## Critérios de aceite\n\nx\n\n## Validação\n\nok\n"
        run = lambda title: subprocess.run([str(self.repo / ".harness/pr"), "create", title, "body.md"], cwd=self.repo,
                                           capture_output=True, text=True, env={**__import__("os").environ, "PATH": __import__("os").environ["PATH"]})
        git(self.repo, "checkout", "-q", "-b", "fix/x")
        body.write_text(good)
        r = run("Arrumei umas coisas")
        self.assertEqual(r.returncode, 1)
        self.assertIn("tipo(escopo): descrição", r.stderr)
        body.write_text(good + "\n🤖 Generated with Claude Code\n")
        r = run("fix: a")
        self.assertEqual(r.returncode, 1)
        self.assertIn("assinatura", r.stderr)


class TestHeavyChecksTakeTurns(unittest.TestCase):
    """Várias checagens ao mesmo tempo, cada uma compilando e testando, derrubaram a máquina."""

    def test_two_checks_never_run_at_the_same_time(self):
        import os
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        log = repo.parent / "turnos.log"
        (repo / "harness.conf").write_text(f'PROFILE=livre\nVALIDATE_PUSH="echo in >> \'{log}\'; sleep 2; echo out >> \'{log}\'"\n')
        commit_all(repo, "chore: adopt harness")
        env = {**os.environ, "HARNESS_LOCK_DIR": str(repo.parent / "locks")}
        runs = [subprocess.Popen([str(repo / ".harness/validate"), "--profile", "push"], cwd=repo, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(3)]
        for r in runs:
            r.communicate(timeout=60)
            self.assertEqual(r.returncode, 0)
        self.assertEqual(log.read_text().split(), ["in", "out"] * 3)

    def test_a_lock_left_by_a_dead_process_does_not_block(self):
        import os
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        (repo / "harness.conf").write_text('PROFILE=livre\nVALIDATE_PUSH="true"\n')
        commit_all(repo, "chore: adopt harness")
        locks = repo.parent / "locks"
        (locks / "validate.lock").mkdir(parents=True)
        (locks / "validate.lock/pid").write_text("999999\n")
        r = subprocess.run([str(repo / ".harness/validate"), "--profile", "push"], cwd=repo, capture_output=True, text=True,
                           env={**os.environ, "HARNESS_LOCK_DIR": str(locks)}, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestDeliveryWithoutRemote(unittest.TestCase):
    """Projeto sem remoto não é entrega falha: os portões valem igual, e só o envio fica para depois."""

    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "fix/x")
        (self.repo / "a.txt").write_text("a\n")
        self.sha = commit_all(self.repo, "fix: a")

    def push(self):
        return subprocess.run([str(self.repo / ".harness/push")], cwd=self.repo, capture_output=True, text=True)

    def test_gates_are_still_required(self):
        r = self.push()
        self.assertEqual(r.returncode, 1)
        self.assertIn("falta a aprovação", r.stderr)

    def test_approved_delivery_ends_ready_and_says_how_to_publish(self):
        from tests.helpers import owner_approve
        for gate in ("seguranca", "revisao", "qualidade", "bugs"):
            owner_approve(self.repo, gate)
        r = self.push()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sem remoto", r.stdout)
        self.assertIn("git remote add origin", r.stdout)
        self.assertNotIn("enviada", r.stdout)
