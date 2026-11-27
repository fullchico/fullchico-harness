"""Tickets independentes carregam só os carimbos que seu trabalho exige."""
import json
import time
import os
import shlex
import subprocess
import sys
import unittest
from unittest import mock

from tests.helpers import ROOT, accept, commit_all, commit_plan, git, make_repo

sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
import certs  # noqa: E402
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
        commit_plan(self.repo, "plan")
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
        commit_plan(self.repo, "plan")
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
        commit_plan(self.repo, "plan with middle gate")
        rel = str(ticket.relative_to(self.repo))
        reg = registry.load(str(self.repo))
        key = registry.stamp_key(str(self.repo), GATES["execution"], rel)
        self.assertTrue(key)
        self.assertFalse(registry.satisfied(str(self.repo), "execution", reg, ticket=rel))
        ticket.write_text(ticket.read_text() + "Resultado: atualizado\n")
        accept(self.repo)  # texto novo no ticket é critério novo: o dono aceita de novo
        self.assertNotEqual(key, registry.stamp_key(str(self.repo), GATES["execution"], rel))
        problems, ready = tasks.audit(str(self.repo), reg)
        self.assertFalse(any("falta carimbo de meio `execution`" in item for item in problems))
        self.assertIn(rel, ready)
        before_done = registry.stamp_key(str(self.repo), GATES["execution"], rel)
        ticket.write_text(ticket.read_text().replace("Status: open", "Status: done"))
        self.assertEqual(before_done, registry.stamp_key(str(self.repo), GATES["execution"], rel))
        with mock.patch.object(certs, "has", side_effect=lambda root, name, key, ticket=None, by=None:
                               name == certs.ACCEPT or name == "execution" and ticket == rel and key == before_done):
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
        commit_plan(self.repo, "plan")
        (self.repo / "front.tsx").write_text("export const x = 1\n")
        front_commit = commit_all(self.repo, "front")
        (self.repo / "back.py").write_text("x = 1\n")
        back_commit = commit_all(self.repo, "back")
        front.write_text(front.read_text().replace("Status: open", f"Status: done\nDelivery: {front_commit}"))
        back.write_text(back.read_text().replace("Status: open", f"Status: done\nDelivery: {back_commit}"))
        commit_plan(self.repo, "passports")
        reg_now = registry.load(str(self.repo))
        current = {name: registry.stamp_key(str(self.repo), reg_now["gates"][name]) for name in ("a11y", "api", "quality")}
        signed = {("a11y", current["a11y"]), ("api", current["api"])}
        with mock.patch.object(certs, "has", side_effect=lambda root, gate, key, ticket=None, by=None: gate == certs.ACCEPT or (gate, key) in signed):
            problems, _ = tasks.audit(str(self.repo), registry.load(str(self.repo)))
            self.assertTrue(problems and all("falta carimbo `quality`" in p for p in problems),
                            "o portão de comando sempre obrigatório vale a cada ticket integrado")
            signed.discard(("api", current["api"]))
            signed.add(("quality", current["quality"]))
            problems, _ = tasks.audit(str(self.repo), registry.load(str(self.repo)))
            self.assertEqual(len(problems), 1)
            self.assertIn("falta carimbo `api`", problems[0])
            signed.add(("api", current["api"]))
            self.assertEqual(tasks.audit(str(self.repo), registry.load(str(self.repo)))[0], [])
            (self.repo / "front.tsx").write_text("export const x = 2\n")
            commit_all(self.repo, "change front after approval")
            stale, _ = tasks.audit(str(self.repo), registry.load(str(self.repo)))
            self.assertTrue(any("falta carimbo `a11y`" in p for p in stale))
            for name in ("a11y", "api", "quality"):
                signed.add((name, registry.stamp_key(str(self.repo), reg_now["gates"][name])))
            self.assertEqual(tasks.audit(str(self.repo), registry.load(str(self.repo)))[0], [])

    def test_cycle_blocks_frontier(self):
        one = self.ticket("01", "a11y")
        self.ticket("02", "api", "01")
        commit_plan(self.repo, "plan")
        one.write_text(one.read_text().replace("Gates: a11y", "Gates: none")
                       .replace("Blocked by: none", "Blocked by: 02"))
        commit_plan(self.repo, "weaken")
        problems, _ = tasks.audit(str(self.repo), registry.load(str(self.repo)))
        self.assertTrue(any("ciclo" in p for p in problems))

    def test_same_wave_tickets_cannot_claim_the_same_area(self):
        self.ticket("01", "api", paths="apps/api/src/availability/**, apps/api/src/app.module.ts")
        self.ticket("02", "api", paths="apps/api/**")
        self.ticket("03", "api", paths="apps/api/src/search/**, apps/api/src/app.module.ts")
        self.ticket("04", "api", "02", paths="apps/api/src/availability/x.ts")
        commit_plan(self.repo, "plan")
        problems, ready = tasks.audit(str(self.repo), registry.load(str(self.repo)))
        overlaps = [p for p in problems if "ocupam" in p]
        # 02 (a API inteira) colide com 01 e 03; 01 e 03 só dividem um arquivo exato; 04 depende do 02.
        self.assertEqual(len(overlaps), 2, overlaps)
        self.assertTrue(all("02-task.md" in p for p in overlaps))
        self.assertEqual(ready, [])
        two = self.repo / "docs/specs/a/issues/02-task.md"
        two.write_text(two.read_text().replace("Blocked by: none", "Blocked by: 01, 03"))
        commit_plan(self.repo, "chain")
        problems, ready = tasks.audit(str(self.repo), registry.load(str(self.repo)))
        self.assertFalse([p for p in problems if "ocupam" in p])
        self.assertEqual(len(ready), 2)

    def test_command_gates_run_one_at_a_time_per_checkout(self):
        sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
        import gate_cli
        first = gate_cli.checkout_lock(str(self.repo))
        self.assertIsNotNone(first)
        probe = subprocess.run([sys.executable, "-c", (
            "import sys, fcntl; sys.path.insert(0, sys.argv[2]); import gate_cli\n"
            "fcntl_flock = fcntl.flock\n"
            "def nb(f, op): return fcntl_flock(f, op | fcntl.LOCK_NB)\n"
            "fcntl.flock = nb\n"
            "try:\n gate_cli.checkout_lock(sys.argv[1]); print('livre')\n"
            "except OSError: print('ocupado')"), str(self.repo), str(ROOT / "plugins/tr/scripts")],
            capture_output=True, text=True)
        self.assertIn("ocupado", probe.stdout)
        first.close()
        probe = subprocess.run([sys.executable, "-c", (
            "import sys; sys.path.insert(0, sys.argv[2]); import gate_cli\n"
            "gate_cli.checkout_lock(sys.argv[1]); print('livre')"), str(self.repo), str(ROOT / "plugins/tr/scripts")],
            capture_output=True, text=True)
        self.assertIn("livre", probe.stdout)

    def test_invalid_status_does_not_enter_the_frontier(self):
        ticket = self.ticket("01", "api")
        ticket.write_text(ticket.read_text().replace("Status: open", "Status: cancelled"))
        commit_plan(self.repo, "plan")
        problems, ready = tasks.audit(str(self.repo), registry.load(str(self.repo)))
        self.assertEqual(ready, [])
        self.assertTrue(any("deve ser open ou done" in p for p in problems))

    def test_delivery_is_blocked_by_task_passport(self):
        self.ticket("01", "a11y")
        commit_plan(self.repo, "plan")
        run = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/gate_cli.py"), "delivery"],
                             cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertIn("Status ainda não é done", run.stdout)

    def test_hook_refuses_executor_before_blocker_finishes(self):
        self.ticket("01", "api")
        self.ticket("02", "a11y", "01")
        commit_plan(self.repo, "plan")
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
        commit_plan(self.repo, "plan")
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
        commit_plan(self.repo, "plan")
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
        self._bash("t-sleep", "sleep 1", "tr:orchestrator")
        (self.repo / "src/b.py").write_text("y = 1\n")
        self.assertEqual(self.post("t-sleep", "sleep 1"), {},
                         "o que um executor escreve em paralelo não é culpa de quem só esperou")
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

    def owner_hook(self, command, mode="default"):
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
        auto = self.owner_hook(f"tr-harness gates --register {shlex.quote(str(draft))}", "auto")
        self.assertEqual(auto["permissionDecision"], "deny", "no modo auto não há diálogo para o dono")
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

    def test_in_auto_mode_the_owner_approves_by_answering_the_question_in_the_session(self):
        (self.repo / ".claude/harness.json").unlink()
        draft = self.repo.parent / "draft.json"
        draft.write_text(json.dumps({"quality": {"stage": "end", "signs": "command", "command": "true"}}))
        command = f"tr-harness gates --register {shlex.quote(str(draft))}"
        cli = [str(ROOT / "plugins/tr/bin/tr-harness"), "gates", "--register", str(draft)]
        in_session = dict(os.environ, CLAUDECODE="1")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo))

        def run(script, payload):
            out = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts" / script)], capture_output=True,
                                 text=True, input=json.dumps(dict(payload, cwd=str(self.repo))), env=env).stdout
            return json.loads(out) if out.strip() else {}

        combined = self.owner_hook(f"git add -A && {command} 2>&1 | tail -5", "auto")
        self.assertEqual(combined["permissionDecision"], "deny")
        self.assertIn("sozinho", combined["permissionDecisionReason"], "combinado, o hook não consegue perguntar")
        denied = self.owner_hook(command, "auto")
        self.assertEqual(denied["permissionDecision"], "deny")
        canonical = registry.owner_canonical(["gates", "--register", str(draft)])
        question = registry.owner_question(canonical)
        self.assertIn(question, denied["permissionDecisionReason"], "o agente recebe a pergunta exata")
        ask = {"questions": [{"question": question, "header": "Dono", "multiSelect": False,
                              "options": [{"label": "Aprovo", "description": "grava"},
                                          {"label": "Não aprovo", "description": "não grava"}]}]}
        forged = run("guard.py", {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
                                  "tool_input": dict(ask, answers={question: "Aprovo"})})
        self.assertEqual(forged["hookSpecificOutput"]["permissionDecision"], "deny", "o agente não responde pelo dono")
        self.assertEqual(run("guard.py", {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
                                          "tool_input": ask}), {}, "a pergunta limpa passa")
        answered = lambda reply, asked=ask: run("owner_answer.py", {
            "hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion", "tool_input": asked,
            "tool_response": {"questions": asked["questions"], "answers": {question: reply}}})
        answered("Não aprovo")
        self.assertEqual(self.owner_hook(command, "auto")["permissionDecision"], "deny", "não aprovou, não libera")
        answered("Aprovo", {"questions": []})
        self.assertEqual(self.owner_hook(command, "auto")["permissionDecision"], "deny",
                         "resposta a uma pergunta que não foi feita não libera")
        answered("Aprovo")
        allowed = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/guard.py")], capture_output=True,
                                 text=True, env=env, input=json.dumps({
                                     "hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.repo),
                                     "permission_mode": "auto", "tool_input": {"command": command}}))
        self.assertEqual(allowed.stdout.strip(), "", "com o Aprovo do dono, o comando passa")
        done = subprocess.run(cli, cwd=self.repo, capture_output=True, text=True, env=in_session)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.owner_hook(command, "auto")["permissionDecision"], "deny", "a aprovação é de uso único")

    def test_tool_files_are_not_code_and_listing_gates_may_be_piped(self):
        self.assertFalse(registry.is_code(str(self.repo), "skills-lock.json"))
        self.assertTrue(registry.is_code(str(self.repo), "package.json"))
        listing = self.hook("Bash", {"command": "gate 2>&1 | tail -30"})
        self.assertEqual(listing, {}, "listar portões não carimba")
        stamped = self.hook("Bash", {"command": "gate quality 2>&1 | tail -30"})
        self.assertEqual(stamped.get("permissionDecision"), "deny", "rodar um portão com pipe continua barrado")

    def test_register_accepts_the_code_paths(self):
        import gates_cli
        draft = {"code": ["apps", "packages"], "e2e": {"stage": "end", "signs": "command", "command": "true"}}
        with mock.patch.dict(os.environ, {"CLAUDECODE": ""}):
            self.assertEqual(gates_cli.merge(str(self.repo), draft), ["e2e", "code"])
            self.assertEqual(gates_cli.merge(str(self.repo), {"code": ["outro"]}), [], "code existente não muda")
        self.assertEqual(registry.load(str(self.repo))["code"], ["apps", "packages"])

    def test_the_orchestrator_runs_executors_in_the_background_once_per_ticket(self):
        ticket = self.ticket("01", "api")
        commit_plan(self.repo, "plan")
        rel = str(ticket.relative_to(self.repo))
        job = {"subagent_type": "general-purpose", "prompt": f"Implemente {rel}", "isolation": "worktree",
               "run_in_background": True}
        job.pop("run_in_background")  # o Agent de um subagente não tem esse parâmetro
        self.assertNotEqual(self.hook("Agent", job, "tr:orchestrator").get("permissionDecision"), "deny")
        twice = self.hook("Agent", job, "tr:orchestrator")
        self.assertEqual(twice.get("permissionDecision"), "deny", "o mesmo ticket não ganha dois executores")
        self.assertIn("já tem um executor", twice["permissionDecisionReason"])
        done = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/dispatch_done.py")],
                              input=json.dumps({"tool_name": "Agent", "cwd": str(self.repo), "tool_input": job,
                                                "hook_event_name": "PostToolUse"}),
                              capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotEqual(self.hook("Agent", job, "tr:orchestrator").get("permissionDecision"), "deny",
                            "depois que o executor volta, o ticket pode ser disparado de novo")

    def test_a_dispatch_that_never_opened_frees_its_ticket(self):
        ticket = self.ticket("01", "api")
        commit_plan(self.repo, "plan")
        rel = str(ticket.relative_to(self.repo))
        job = {"subagent_type": "general-purpose", "prompt": f"Implemente {rel}", "isolation": "worktree",
               "run_in_background": True}
        done = lambda payload: subprocess.run(
            [sys.executable, str(ROOT / "plugins/tr/scripts/dispatch_done.py")], input=json.dumps(payload),
            capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))
        age = lambda seconds: tasks._save_in_flight(str(self.repo), {
            k: [v[0] - seconds, v[1]] for k, v in tasks._raw_in_flight(str(self.repo)).items()})
        busy = lambda: self.hook("Agent", job, "tr:orchestrator").get("permissionDecision") == "deny"
        self.assertFalse(busy())
        done({"hook_event_name": "PermissionDenied", "tool_name": "Agent", "cwd": str(self.repo), "tool_input": job})
        self.assertFalse(busy(), "o classificador negou depois do guard: o ticket volta a ficar livre")
        age(tasks.PENDING_TTL + 1)
        self.assertFalse(busy(), "disparo sem subagente aberto expira em minutos, não em horas")
        done({"hook_event_name": "SubagentStart", "cwd": str(self.repo), "agent_id": "x1",
              "agent_type": "general-purpose"})
        age(tasks.PENDING_TTL + 1)
        self.assertTrue(busy(), "com o subagente aberto, o ticket segue ocupado")

    def test_status_board_comes_from_hooks(self):
        first = self.ticket("01", "api")
        second = self.ticket("02", "api", blockers="01")
        commit_plan(self.repo, "plan")
        rel1, rel2 = str(first.relative_to(self.repo)), str(second.relative_to(self.repo))
        dispatched = self.hook("Agent", {"subagent_type": "general-purpose", "prompt": f"Implemente {rel1}",
                                         "isolation": "worktree", "run_in_background": True}, "tr:orchestrator")
        self.assertIn(f"DONE: {rel1}", dispatched["updatedInput"]["prompt"], "o hook pede o aviso de fim ao executor")
        self.assertIn("ports 3100–3199", dispatched["updatedInput"]["prompt"], "portas próprias pelo número do ticket")
        self.assertIn("app_t01", dispatched["updatedInput"]["prompt"], "banco próprio pelo número do ticket")
        beat = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.repo), "agent_id": "abc123",
                "agent_type": "general-purpose", "tool_input": {"command": "ls"}}
        subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/guard.py")], input=json.dumps(beat),
                       capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))
        status = lambda: subprocess.run([str(ROOT / "plugins/tr/bin/tr-harness"), "status"], cwd=self.repo,
                                        capture_output=True, text=True).stdout
        out = status()
        self.assertIn("01-task.md", out)
        self.assertIn("em execução", out)
        self.assertIn("na fila", out)
        self.assertIn("general-purpose", out, "o subagente ativo aparece com o batimento")
        import time
        orch = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.repo), "agent_id": "orch01",
                "agent_type": "tr:orchestrator", "tool_input": {"command": "ls"}}
        subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/guard.py")], input=json.dumps(orch),
                       capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))
        board = tasks.board(str(self.repo))
        for agent_id in board["agents"]:
            board["agents"][agent_id]["last"] = time.time() - 3600  # todos sem atividade há 1 h
        tasks._save_board(str(self.repo), board)
        out = status()
        orchestrator_line = next(line for line in out.splitlines() if "tr:orchestrator" in line)
        self.assertIn("aguardando 1 executor", orchestrator_line, "esperar o executor não é travamento")
        executor_line = next(line for line in out.splitlines() if "abc123" in line)
        self.assertIn("possivelmente parado", executor_line, "o executor sem atividade continua alarmado")
        stop = {"hook_event_name": "SubagentStop", "cwd": str(self.repo), "agent_id": "abc123",
                "last_assistant_message": f"Pronto.\nBLOCKED: {rel1} — falta a variável DATABASE_URL"}
        subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/executor_report.py")], input=json.dumps(stop),
                       capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))
        subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/dispatch_done.py")],
                       input=json.dumps({"tool_name": "Agent", "cwd": str(self.repo), "tool_input": {"prompt": rel1}}),
                       capture_output=True, text=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))
        out = status()
        self.assertIn("bloqueado", out)
        self.assertIn("DATABASE_URL", out)
        self.assertNotIn("abc123", out, "o executor que terminou sai da lista de ativos")
        self.assertIn(rel2.split("/")[-1], out)

    def test_executors_run_in_worktrees_up_to_the_parallel_limit(self):
        tickets = [self.ticket(f"0{n}", "api", paths=f"src/m{n}/**") for n in (1, 2, 3)]
        commit_plan(self.repo, "plan")
        rels = [str(t.relative_to(self.repo)) for t in tickets]
        shared = self.hook("Agent", {"subagent_type": "general-purpose", "prompt": f"Implemente {rels[0]}",
                                     "run_in_background": True}, "tr:orchestrator")
        self.assertEqual(shared.get("permissionDecision"), "deny")
        self.assertIn("worktree", shared["permissionDecisionReason"])
        reg = json.loads((self.repo / ".claude/harness.json").read_text())
        (self.repo / ".claude/harness.json").write_text(json.dumps(dict(reg, max_parallel=2)))
        job = lambda rel: {"subagent_type": "general-purpose", "prompt": f"Implemente {rel}", "isolation": "worktree",
               "run_in_background": True}
        for rel in rels[:2]:
            self.assertNotEqual(self.hook("Agent", job(rel), "tr:orchestrator").get("permissionDecision"), "deny")
        third = self.hook("Agent", job(rels[2]), "tr:orchestrator")
        self.assertEqual(third.get("permissionDecision"), "deny")
        self.assertIn("max_parallel", third["permissionDecisionReason"])
        self.assertEqual(registry.load(str(self.repo))["max_parallel"], 2)
        (self.repo / ".claude/harness.json").write_text(json.dumps(reg))
        self.assertEqual(registry.load(str(self.repo))["max_parallel"], 3, "padrão: 3")

    def test_the_owner_sets_the_parallel_limit(self):
        import gates_cli
        with mock.patch.dict(os.environ, {"CLAUDECODE": ""}):
            self.assertEqual(gates_cli.main(["--parallel", "3", "--project", str(self.repo)]), 0)
        self.assertEqual(registry.load(str(self.repo))["max_parallel"], 3)
        self.assertEqual(self.owner_hook("tr-harness gates --parallel 8")["permissionDecision"], "ask")

    def test_the_orchestrator_acts_inside_the_project_and_the_executor_inside_the_demand(self):
        deny = lambda got: got.get("permissionDecision") == "deny"
        for command in ("git push origin HEAD", "gh pr create --fill", "gh pr merge 5 --merge", "npm publish"):
            self.assertTrue(deny(self.hook("Bash", {"command": command}, "tr:orchestrator")), command)
            self.assertTrue(deny(self.hook("Bash", {"command": command}, "general-purpose")), command)
            self.assertFalse(deny(self.hook("Bash", {"command": command}, None)), "o maestro é livre: " + command)
        self.assertFalse(deny(self.hook("Bash", {"command": "gh pr view 5"}, "tr:orchestrator")), "ler não sai do projeto")
        self.assertFalse(deny(self.hook("Bash", {"command": "git merge --no-ff tr-exec-1"}, "tr:orchestrator")),
                         "integrar é o trabalho do orquestrador")
        away = self.hook("Write", {"file_path": os.path.expanduser("~/fora-do-projeto.txt"), "content": "x"}, "general-purpose")
        self.assertTrue(deny(away))
        self.assertIn("fora do projeto", away["permissionDecisionReason"])
        with mock.patch.dict(os.environ, {"FULLCHICO_ROLE": "execution"}):
            for command in ("git merge main", "git switch main", "git worktree add ../x"):
                self.assertTrue(deny(self.hook("Bash", {"command": command}, None)), command)
            self.assertFalse(deny(self.hook("Bash", {"command": "git commit -m 'feat: x'"}, None)))

    def test_the_project_git_hooks_cannot_be_skipped(self):
        for command in ("git commit --no-verify -m x", "git -c core.hooksPath=/dev/null commit -m x", "HUSKY=0 git commit -m x"):
            got = self.hook("Bash", {"command": command}, "general-purpose")
            self.assertEqual(got.get("permissionDecision"), "deny", command)
        self.assertNotEqual(self.hook("Bash", {"command": "git commit -m 'docs: explain --no-verify'"}, "general-purpose")
                            .get("permissionDecision"), "allow-never")

    def test_the_owner_registers_how_a_seat_is_prepared(self):
        import gates_cli
        with mock.patch.dict(os.environ, {"CLAUDECODE": ""}):
            self.assertEqual(gates_cli.main(["--project", str(self.repo), "--prepare-seat", "echo ok"]), 0)
        self.assertEqual(registry.load(str(self.repo))["prepare_seat"], "echo ok")
        self.assertEqual(self.owner_hook("tr-harness gates --prepare-seat 'pnpm install'")["permissionDecision"], "ask")

    def test_processes_of_other_projects_cannot_be_killed(self):
        import tempfile
        outside_dir = tempfile.mkdtemp()
        outside = subprocess.Popen(["sleep", "30"], cwd=outside_dir)
        mine = subprocess.Popen(["sleep", "30"], cwd=self.repo)
        try:
            other = self.hook("Bash", {"command": f"kill {outside.pid}"}, "general-purpose")
            self.assertEqual(other.get("permissionDecision"), "deny")
            self.assertIn("de fora deste projeto", other["permissionDecisionReason"])
            self.assertEqual(self.hook("Bash", {"command": f"kill {mine.pid}"}, "general-purpose"), {})
            for command in ("pkill node", "killall node", "lsof -ti:3000 | xargs kill", "kill $(lsof -ti:3000)"):
                self.assertEqual(self.hook("Bash", {"command": command}, "general-purpose").get("permissionDecision"),
                                 "deny", command)
        finally:
            outside.kill(); mine.kill(); outside.wait(); mine.wait()

    def test_only_containers_of_removed_worktrees_of_this_project_are_orphans(self):
        gone = str(self.repo.resolve() / ".claude/worktrees/agent-gone")
        alive = self.repo / ".claude/worktrees/agent-alive"
        alive.mkdir(parents=True)
        rows = [{"Names": "gone-db", "Labels": f"com.docker.compose.project.working_dir={gone}"},
                {"Names": "alive-db", "Labels": f"com.docker.compose.project.working_dir={alive.resolve()}"},
                {"Names": "other-project-db", "Labels": "com.docker.compose.project.working_dir=/srv/other-project"}]
        fake = subprocess.CompletedProcess([], 0, stdout="\n".join(json.dumps(r) for r in rows), stderr="")
        with mock.patch("subprocess.run", return_value=fake):
            self.assertEqual(tasks.orphan_containers(str(self.repo)), ["gone-db"])

    def test_ignored_build_outputs_do_not_change_the_content(self):
        (self.repo / ".gitignore").write_text("*.tsbuildinfo\n")
        (self.repo / "src.py").write_text("x = 1\n")
        before = ledger.head(str(self.repo))
        (self.repo / "app.tsbuildinfo").write_text("gerado pelo typecheck")
        self.assertEqual(ledger.head(str(self.repo)), before, "rodar um portão não invalida o carimbo de outro")
        (self.repo / "novo.py").write_text("y = 2\n")
        self.assertNotEqual(ledger.head(str(self.repo)), before, "arquivo novo não ignorado conta")

    def test_done_with_a_prefix_and_a_short_ticket_number_is_recorded(self):
        ticket = str(self.ticket("02", "api").relative_to(self.repo))
        tasks.report(str(self.repo), "x", "texto\n\nresult: DONE: 02 — conta e sessão; commit 5d29013.")
        self.assertEqual(tasks.board(str(self.repo))["tickets"][ticket]["state"], "done")

    def test_a_stamp_that_still_holds_is_not_validated_again(self):
        ticket = self.ticket("01", "api")
        commit_plan(self.repo, "plan")
        request = {"subagent_type": registry.CHECKER, "description": "gate", "prompt": "gate: quality"}
        early = self.hook("Agent", request, "tr:orchestrator")
        self.assertEqual(early.get("permissionDecision"), "deny", "com ticket aberto, o trem não chegou")
        self.assertIn("o trem ainda não chegou", early["permissionDecisionReason"])
        ticket.write_text(ticket.read_text().replace("Status: open", "Status: done"))
        commit_all(self.repo, "done")
        self.assertNotEqual(self.hook("Agent", request, "tr:orchestrator").get("permissionDecision"), "deny",
                            "sem carimbo, valida")
        key = registry.stamp_key(str(self.repo), registry.load(str(self.repo))["gates"]["quality"])
        certs.certify(str(self.repo), "quality", key, "APPROVED", registry.CHECKER, "ok")
        again = self.hook("Agent", request, "tr:orchestrator")
        self.assertEqual(again.get("permissionDecision"), "deny")
        self.assertIn("validação desnecessária", again["permissionDecisionReason"])

    def test_executor_worktrees_do_not_change_the_main_state(self):
        (self.repo / "src.py").write_text("x = 1\n")
        before = ledger.head(str(self.repo))
        work = self.repo / ".claude/worktrees/agent-x"
        work.mkdir(parents=True)
        (work / "novo.py").write_text("y = 2\n")
        self.assertEqual(ledger.head(str(self.repo)), before, "o trabalho de um executor não invalida os carimbos do principal")

    def test_other_demands_and_old_agents_do_not_count(self):
        import time
        ticket = self.ticket("01", "api")
        tasks._save_in_flight(str(self.repo), {"docs/specs/antiga/issues/01-x.md": time.time(),
                                               str(ticket.relative_to(self.repo)): time.time()})
        self.assertEqual(list(tasks._in_flight(str(self.repo))), [str(ticket.relative_to(self.repo))])
        tasks._save_board(str(self.repo), {"agents": {"velho": {"type": "general-purpose", "last": time.time() - 3 * 3600},
                                                      "novo": {"type": "general-purpose", "last": time.time()}}})
        self.assertEqual(list(tasks.board(str(self.repo))["agents"]), ["novo"])

    def test_keep_awake_renews_only_when_needed_and_can_be_turned_off(self):
        with mock.patch.object(tasks, "_spawn") as popen, mock.patch("shutil.which", return_value="/usr/bin/x"), \
                mock.patch.dict(os.environ, {"FULLCHICO_KEEP_AWAKE": "1"}):
            tasks.keep_awake(str(self.repo))
            tasks.keep_awake(str(self.repo))
            self.assertEqual(popen.call_count, 1, "dentro da janela não pede de novo")
            self.assertGreater(tasks.awake_until(str(self.repo)), time.time())
            os.remove(tasks._awake_path(str(self.repo)))
            reg = json.loads((self.repo / ".claude/harness.json").read_text())
            reg["keep_awake"] = False
            (self.repo / ".claude/harness.json").write_text(json.dumps(reg))
            tasks.keep_awake(str(self.repo))
            self.assertEqual(popen.call_count, 1, "desligado no registro")

    def test_reading_git_is_not_writing(self):
        import guard
        self.assertFalse(guard.git_mutates("git cat-file -t a6d; git log -5; git branch -a | head; git worktree list"))
        for command in ("git worktree add x", "git branch -D x", "git tag v1", "git -C /x commit -m a"):
            self.assertTrue(guard.git_mutates(command), command)

    def test_a_new_session_releases_tickets_nobody_is_running(self):
        import time
        ticket = str(self.ticket("01", "api").relative_to(self.repo))
        tasks._save_in_flight(str(self.repo), {ticket: time.time()})
        tasks._save_board(str(self.repo), {"agents": {"vivo": {"type": "general-purpose", "last": time.time()}}})
        self.assertEqual(tasks.release_if_idle(str(self.repo)), [], "alguém ainda trabalha: não libera")
        tasks._save_board(str(self.repo), {"agents": {"morto": {"type": "general-purpose", "last": time.time() - 900}}})
        self.assertEqual(tasks.release_if_idle(str(self.repo)), [ticket])
        self.assertEqual(tasks._in_flight(str(self.repo)), {})
        self.assertEqual(tasks.board(str(self.repo))["agents"], {}, "agentes da sessão que caiu saem do quadro")

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
        commit_plan(self.repo, "plan")
        loose = self.hook("Agent", {"subagent_type": "general-purpose", "prompt": "Implemente a soma"},
                          "tr:orchestrator")
        self.assertEqual(loose.get("permissionDecision"), "deny")
        self.assertIn("caminho do ticket", loose["permissionDecisionReason"])
        rel = str(ticket.relative_to(self.repo))
        self.assertNotEqual(self.hook("Agent", {"subagent_type": "general-purpose", "prompt": f"Implemente {rel}",
                                       "isolation": "worktree", "run_in_background": True}, "tr:orchestrator").get("permissionDecision"), "deny")
        self.assertEqual(self.hook("Agent", {"subagent_type": "Explore", "prompt": "Ache a soma"}, "tr:orchestrator"), {})
        self.assertEqual(self.hook("Agent", {"subagent_type": "general-purpose", "prompt": "Pesquise"}), {},
                         "a sessão principal ainda explora sem ticket")

    def test_done_ticket_needs_its_blocker_complete(self):
        first = self.ticket("01", "api", paths="first.py")
        second = self.ticket("02", "api", blockers="01", paths="second.py")
        commit_plan(self.repo, "plan")
        (self.repo / "second.py").write_text("second = 1\n")
        second_commit = commit_plan(self.repo, "second too early")
        (self.repo / "first.py").write_text("first = 1\n")
        first_commit = commit_plan(self.repo, "first")
        second.write_text(second.read_text().replace("Status: open", f"Status: done\nDelivery: {second_commit}"))
        commit_plan(self.repo, "mark done")
        signed = {("api", ledger.head(str(self.repo)))}
        with mock.patch.object(ledger, "has", side_effect=lambda root, gate, commit: (gate, commit) in signed):
            problems, ready = tasks.audit(str(self.repo), registry.load(str(self.repo)))
        self.assertTrue(any("Status ainda não é done" in p for p in problems))
        self.assertEqual(ready, [str(first.relative_to(self.repo))])


if __name__ == "__main__":
    unittest.main()
