"""Tickets independentes carregam só os carimbos que seu trabalho exige."""
import json
import os
import shlex
import subprocess
import sys
import unittest
from unittest import mock

from tests.helpers import ROOT, commit_all, git, make_repo

sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
import ledger  # noqa: E402
import registry  # noqa: E402
import tasks  # noqa: E402

GATES = {
    "quality": {"stage": "end", "signs": "command", "command": "true"},
    "a11y": {"stage": "end", "signs": "command", "command": "true", "always": False},
    "api": {"stage": "end", "signs": "command", "command": "true", "always": False},
    "design": {"stage": "start", "signs": "artifact", "artifact": "docs/specs/*/design.md", "always": False},
    "execution": {"stage": "middle", "signs": "command", "command": "true", "always": False},
}


class TestTaskPassports(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/harness.json").write_text(json.dumps({"gates": GATES}))
        commit_all(self.repo, "registry")
        git(self.repo, "checkout", "-q", "-b", "feat")

    def ticket(self, number, gates, blockers="none", paths="src/**", entry="none"):
        path = self.repo / f"docs/specs/a/issues/{number}-task.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Task\nStatus: open\nBlocked by: {blockers}\nStart: {entry}\n"
                        f"Gates: {gates}\nFiles: {paths}\n")
        return path

    def test_frontier_and_independent_gate_sets(self):
        front = self.ticket("01", "a11y", paths="front.tsx")
        back = self.ticket("02", "api", paths="back.py")
        dependent = self.ticket("03", "api", "01, 02")
        commit_all(self.repo, "plan")
        problems, ready = tasks.audit(str(self.repo), registry.load(str(self.repo)))
        self.assertEqual(ready, [str(front.relative_to(self.repo)), str(back.relative_to(self.repo))])
        self.assertTrue(any("Status ainda não é done" in p for p in problems))
        self.assertNotIn("a11y", registry.required(str(self.repo), "end", registry.load(str(self.repo))))
        status = subprocess.run([str(ROOT / "plugins/tr/bin/gate")], cwd=self.repo,
                                capture_output=True, text=True)
        self.assertIn("[task] a11y", status.stdout)
        self.assertTrue(dependent.exists())
        self.assertIsNone(tasks.dispatch_problem(str(self.repo), registry.load(str(self.repo)),
                                                  str(front.relative_to(self.repo))))
        self.assertIn("fora da fronteira", tasks.dispatch_problem(
            str(self.repo), registry.load(str(self.repo)), str(dependent.relative_to(self.repo))))

    def test_optional_entry_gate_applies_only_to_its_ticket(self):
        front = self.ticket("01", "a11y", paths="front.tsx", entry="design")
        back = self.ticket("02", "api", paths="back.py")
        commit_all(self.repo, "plan")
        reg = registry.load(str(self.repo))
        self.assertNotIn("design", registry.required(str(self.repo), "start", reg))
        status = subprocess.run([str(ROOT / "plugins/tr/bin/gate")], cwd=self.repo,
                                capture_output=True, text=True)
        self.assertIn("[task] design", status.stdout)
        problems, ready = tasks.audit(str(self.repo), reg)
        self.assertIn(str(back.relative_to(self.repo)), ready)
        self.assertNotIn(str(front.relative_to(self.repo)), ready)
        self.assertTrue(any("falta carimbo de entrada `design`" in p for p in problems))
        self.assertIn("falta carimbo de entrada `design`", tasks.dispatch_problem(
            str(self.repo), reg, str(front.relative_to(self.repo))))
        with mock.patch.object(registry, "satisfied", return_value=True):
            self.assertIn(str(front.relative_to(self.repo)), tasks.audit(str(self.repo), reg)[1])

    def test_middle_gate_is_ticket_scoped_and_result_versioned(self):
        ticket = self.ticket("01", "none")
        ticket.write_text(ticket.read_text().replace("Gates: none", "Middle: execution\nGates: none"))
        commit_all(self.repo, "plan with middle gate")
        rel = str(ticket.relative_to(self.repo))
        reg = registry.load(str(self.repo))
        key = registry.stamp_key(str(self.repo), GATES["execution"], rel)
        self.assertTrue(key)
        self.assertFalse(registry.satisfied(str(self.repo), "execution", reg, ticket=rel))
        ticket.write_text(ticket.read_text() + "Resultado: atualizado\n")
        self.assertNotEqual(key, registry.stamp_key(str(self.repo), GATES["execution"], rel))
        problems, ready = tasks.audit(str(self.repo), reg)
        self.assertFalse(any("falta carimbo de meio `execution`" in item for item in problems))
        self.assertIn(rel, ready)
        before_done = registry.stamp_key(str(self.repo), GATES["execution"], rel)
        ticket.write_text(ticket.read_text().replace("Status: open", "Status: done"))
        self.assertEqual(before_done, registry.stamp_key(str(self.repo), GATES["execution"], rel))
        scoped = registry.scoped_stamp("execution", rel)
        with mock.patch.object(ledger, "has", side_effect=lambda root, stamp, key: stamp == scoped and key == before_done):
            self.assertTrue(registry.satisfied(str(self.repo), "execution", reg, ticket=rel))
            problems, ready = tasks.audit(str(self.repo), reg)
        self.assertFalse(any("falta carimbo de meio `execution`" in item for item in problems))
        self.assertEqual(ready, [])
        current_key = registry.stamp_key(str(self.repo), GATES["execution"], rel)
        (self.repo / "source.py").write_text("print('changed')\n")
        self.assertNotEqual(current_key, registry.stamp_key(str(self.repo), GATES["execution"], rel))

    def test_final_requires_each_ticket_stamp_on_current_snapshot(self):
        front = self.ticket("01", "a11y", paths="front.tsx")
        back = self.ticket("02", "api", paths="back.py")
        commit_all(self.repo, "plan")
        (self.repo / "front.tsx").write_text("export const x = 1\n")
        front_commit = commit_all(self.repo, "front")
        (self.repo / "back.py").write_text("x = 1\n")
        back_commit = commit_all(self.repo, "back")
        front.write_text(front.read_text().replace("Status: open", f"Status: done\nDelivery: {front_commit}"))
        back.write_text(back.read_text().replace("Status: open", f"Status: done\nDelivery: {back_commit}"))
        commit_all(self.repo, "passports")
        current = ledger.head(str(self.repo))
        signed = {("a11y", current)}
        with mock.patch.object(ledger, "has", side_effect=lambda root, gate, commit: (gate, commit) in signed):
            problems, _ = tasks.audit(str(self.repo), registry.load(str(self.repo)))
            self.assertEqual(len(problems), 1)
            self.assertIn("falta carimbo `api`", problems[0])
            signed.add(("api", current))
            self.assertEqual(tasks.audit(str(self.repo), registry.load(str(self.repo)))[0], [])
            (self.repo / "front.tsx").write_text("export const x = 2\n")
            commit_all(self.repo, "change front after approval")
            stale, _ = tasks.audit(str(self.repo), registry.load(str(self.repo)))
            self.assertTrue(any("falta carimbo `a11y`" in p for p in stale))
            signed.add(("a11y", ledger.head(str(self.repo))))
            signed.add(("api", ledger.head(str(self.repo))))
            self.assertEqual(tasks.audit(str(self.repo), registry.load(str(self.repo)))[0], [])

    def test_cycle_blocks_frontier(self):
        one = self.ticket("01", "a11y")
        self.ticket("02", "api", "01")
        commit_all(self.repo, "plan")
        one.write_text(one.read_text().replace("Gates: a11y", "Gates: none")
                       .replace("Blocked by: none", "Blocked by: 02"))
        commit_all(self.repo, "weaken")
        problems, _ = tasks.audit(str(self.repo), registry.load(str(self.repo)))
        self.assertTrue(any("ciclo" in p for p in problems))

    def test_invalid_status_does_not_enter_the_frontier(self):
        ticket = self.ticket("01", "api")
        ticket.write_text(ticket.read_text().replace("Status: open", "Status: cancelled"))
        commit_all(self.repo, "plan")
        problems, ready = tasks.audit(str(self.repo), registry.load(str(self.repo)))
        self.assertEqual(ready, [])
        self.assertTrue(any("deve ser open ou done" in p for p in problems))

    def test_delivery_is_blocked_by_task_passport(self):
        self.ticket("01", "a11y")
        commit_all(self.repo, "plan")
        run = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/gate_cli.py"), "delivery"],
                             cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertIn("Status ainda não é done", run.stdout)

    def test_hook_refuses_executor_before_blocker_finishes(self):
        self.ticket("01", "api")
        self.ticket("02", "a11y", "01")
        commit_all(self.repo, "plan")
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Agent", "cwd": str(self.repo),
                   "tool_input": {"subagent_type": "general-purpose",
                                  "prompt": "Implemente docs/specs/a/issues/02-task.md"}}
        run = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/guard.py")],
                             input=json.dumps(payload), capture_output=True, text=True,
                             env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)["hookSpecificOutput"]
        self.assertEqual(result["permissionDecision"], "deny")
        self.assertIn("fora da fronteira", result["permissionDecisionReason"])

    def hook(self, tool, tool_input, agent_type=None, **env):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(self.repo), "tool_input": tool_input}
        if agent_type:
            payload["agent_type"] = agent_type
        run = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/guard.py")], input=json.dumps(payload),
                             capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo), **env))
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)["hookSpecificOutput"] if run.stdout.strip() else {}

    def test_whoever_plans_does_not_write_code_while_tickets_are_open(self):
        ticket = self.ticket("01", "api", paths="src/**")
        commit_all(self.repo, "plan")
        edit = {"file_path": str(self.repo / "src/a.py")}
        main = self.hook("Edit", edit)
        self.assertEqual(main.get("permissionDecision"), "deny")
        self.assertIn("quem planeja não executa", main["permissionDecisionReason"])
        self.assertEqual(self.hook("Edit", edit, "tr:orchestrator").get("permissionDecision"), "deny")
        self.assertEqual(self.hook("Edit", edit, "general-purpose"), {})
        self.assertEqual(self.hook("Edit", edit, FULLCHICO_ROLE="execution"), {})
        self.assertEqual(self.hook("Edit", edit, "default"), {}, "subagente do Codex chega com agent_type")
        self.assertEqual(self.hook("Edit", {"file_path": str(ticket)}), {}, "o plano em docs/ segue livre")
        ticket.write_text(ticket.read_text().replace("Status: open", "Status: done"))
        self.assertEqual(self.hook("Edit", edit), {}, "sem ticket aberto, a sessão principal volta a escrever")

    def post(self, tool_use_id, command):
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": str(self.repo),
                   "tool_use_id": tool_use_id, "tool_input": {"command": command}}
        run = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/write_watch.py")],
                             input=json.dumps(payload), capture_output=True, text=True,
                             env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout) if run.stdout.strip() else {}

    def test_indirect_writes_to_code_are_caught_by_their_effect(self):
        self.ticket("01", "api", paths="src/**")
        commit_all(self.repo, "plan")
        sneaky = "python3 -c \"open('src/a.py','w').write('x = 1')\""
        bash = lambda tid, agent=None: self._bash(tid, sneaky, agent)  # noqa: E731
        self.assertEqual(bash("t1"), {}, "o texto do comando não mostra a escrita: o PreToolUse deixa passar")
        (self.repo / "src").mkdir()
        (self.repo / "src/a.py").write_text("x = 1\n")
        caught = self.post("t1", sneaky)
        self.assertEqual(caught.get("decision"), "block")
        self.assertIn("src/a.py", caught["reason"])
        self.assertEqual(bash("t2"), {})
        self.assertEqual(self.post("t2", "ls"), {}, "sem mudança nova, nada a dizer")
        self.assertEqual(bash("t3", "general-purpose"), {})
        (self.repo / "src/a.py").write_text("x = 2\n")
        self.assertEqual(self.post("t3", sneaky), {}, "o executor pode escrever")

    def _bash(self, tool_use_id, command, agent_type=None):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.repo),
                   "tool_use_id": tool_use_id, "tool_input": {"command": command}}
        if agent_type:
            payload["agent_type"] = agent_type
        run = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/guard.py")], input=json.dumps(payload),
                             capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)["hookSpecificOutput"] if run.stdout.strip() else {}

    def test_the_agent_that_signs_a_gate_is_protected_and_config_dirs_are_not_code(self):
        reg = {"gates": dict(GATES, ui={"stage": "end", "signs": "agent", "agent": "ui-reviewer", "always": False})}
        (self.repo / ".claude/harness.json").write_text(json.dumps(reg))
        for path in (".claude/agents/ui-reviewer.md", ".codex/agents/ui-reviewer.toml"):
            out = self.hook("Edit", {"file_path": str(self.repo / path)}, "general-purpose")
            self.assertEqual(out.get("permissionDecision"), "deny", path)
            self.assertIn("agente de portão", out["permissionDecisionReason"])
        self.assertEqual(self.hook("Edit", {"file_path": str(self.repo / ".claude/agents/outro.md")}), {})
        self.assertEqual(self.hook("Edit", {"file_path": str(self.repo / ".codex/agents/outro.toml")}), {},
                         "configuração do Codex não é código do app")

    def test_the_plugin_cli_runs_at_its_own_version_and_pins_owner_commands(self):
        cli = str(ROOT / "plugins/tr/bin/tr-harness")
        settings = {"extraKnownMarketplaces": {"fullchico": {"source": {"source": "github", "repo": "x/y", "ref": "v9.9.9-rc.1"}}}}
        (self.repo / ".claude/settings.json").write_text(json.dumps(settings))
        owner = subprocess.run([cli, "owner", "gates", "--set", "quality", "pnpm test"], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(owner.stdout.strip(), "npx @fullchico/harness@9.9.9-rc.1 gates --set quality 'pnpm test'")
        analyze = subprocess.run([cli, "gates", "--analyze"], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(analyze.returncode, 0, analyze.stderr)
        refused = subprocess.run([cli, "gates", "--write"], cwd=self.repo, capture_output=True, text=True,
                                 env=dict(os.environ, CLAUDECODE="1"))
        self.assertIn("npx @fullchico/harness@9.9.9-rc.1 gates --write", refused.stderr)

    def owner_hook(self, command, mode="auto"):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.repo),
                   "permission_mode": mode, "tool_input": {"command": command}}
        run = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/guard.py")], input=json.dumps(payload),
                             capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))
        return json.loads(run.stdout)["hookSpecificOutput"]

    def test_the_owner_approves_registry_writes_in_the_permission_dialog(self):
        (self.repo / ".claude/harness.json").unlink()
        draft = self.repo.parent / "draft.json"
        draft.write_text(json.dumps({"quality": {"stage": "end", "signs": "command", "command": "true"}}))
        cli = [str(ROOT / "plugins/tr/bin/tr-harness"), "gates", "--register", str(draft)]
        in_session = dict(os.environ, CLAUDECODE="1")
        refused = subprocess.run(cli, cwd=self.repo, capture_output=True, text=True, env=in_session)
        self.assertNotEqual(refused.returncode, 0, "sem aprovação, a sessão não grava")
        bypass = self.owner_hook(f"tr-harness gates --register {shlex.quote(str(draft))}", "bypassPermissions")
        self.assertEqual(bypass["permissionDecision"], "deny", "sem diálogo possível, o dono grava no terminal")
        asked = self.owner_hook(f"tr-harness gates --register {shlex.quote(str(draft))}")
        self.assertEqual(asked["permissionDecision"], "ask")
        done = subprocess.run(cli, cwd=self.repo, capture_output=True, text=True, env=in_session)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("quality", json.loads((self.repo / ".claude/harness.json").read_text())["gates"])
        again = subprocess.run(cli, cwd=self.repo, capture_output=True, text=True, env=in_session)
        self.assertEqual(again.returncode, 0, "registrar de novo não regrava nada")
        models = [str(ROOT / "plugins/tr/bin/tr-harness"), "models", "configure", "review", "claude:sonnet"]
        self.assertNotEqual(subprocess.run(models, cwd=self.repo, capture_output=True, env=in_session).returncode, 0,
                            "a aprovação é de uso único e de um comando só")
        self.assertEqual(self.owner_hook("tr-harness models configure review claude:sonnet")["permissionDecision"], "ask")
        pin = self.owner_hook("claude plugin install vercel@claude-plugins-official --scope project")
        self.assertEqual(pin["permissionDecision"], "ask", "fixar plugin no projeto é decisão do dono")
        self.assertEqual(subprocess.run(models, cwd=self.repo, capture_output=True, env=in_session).returncode, 0)

    def test_session_start_points_to_the_flow(self):
        import flow_context
        root = str(self.repo)
        self.assertIn("/tr:process-plan", flow_context.context(root))
        self.ticket("01", "api")
        self.assertIn("open tickets", flow_context.context(root))
        (self.repo / ".claude/harness.json").unlink()
        self.assertIn("/tr:configure", flow_context.context(root))
        self.assertIn("tools inside this flow", flow_context.context(root))

    def test_the_orchestrator_dispatches_executors_only_with_a_ticket(self):
        ticket = self.ticket("01", "api")
        commit_all(self.repo, "plan")
        loose = self.hook("Agent", {"subagent_type": "general-purpose", "prompt": "Implemente a soma"},
                          "tr:orchestrator")
        self.assertEqual(loose.get("permissionDecision"), "deny")
        self.assertIn("caminho do ticket", loose["permissionDecisionReason"])
        rel = str(ticket.relative_to(self.repo))
        self.assertNotEqual(self.hook("Agent", {"subagent_type": "general-purpose", "prompt": f"Implemente {rel}"},
                                      "tr:orchestrator").get("permissionDecision"), "deny")
        self.assertEqual(self.hook("Agent", {"subagent_type": "Explore", "prompt": "Ache a soma"}, "tr:orchestrator"), {})
        self.assertEqual(self.hook("Agent", {"subagent_type": "general-purpose", "prompt": "Pesquise"}), {},
                         "a sessão principal ainda explora sem ticket")

    def test_done_ticket_needs_its_blocker_complete(self):
        first = self.ticket("01", "api", paths="first.py")
        second = self.ticket("02", "api", blockers="01", paths="second.py")
        commit_all(self.repo, "plan")
        (self.repo / "second.py").write_text("second = 1\n")
        second_commit = commit_all(self.repo, "second too early")
        (self.repo / "first.py").write_text("first = 1\n")
        first_commit = commit_all(self.repo, "first")
        second.write_text(second.read_text().replace("Status: open", f"Status: done\nDelivery: {second_commit}"))
        commit_all(self.repo, "mark done")
        signed = {("api", ledger.head(str(self.repo)))}
        with mock.patch.object(ledger, "has", side_effect=lambda root, gate, commit: (gate, commit) in signed):
            problems, ready = tasks.audit(str(self.repo), registry.load(str(self.repo)))
        self.assertTrue(any("Status ainda não é done" in p for p in problems))
        self.assertEqual(ready, [str(first.relative_to(self.repo))])


if __name__ == "__main__":
    unittest.main()
