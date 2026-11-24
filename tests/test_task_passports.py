"""Tickets independentes carregam só os carimbos que seu trabalho exige."""
import json
import os
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
    "qualidade": {"momento": "fim", "assina": "comando", "comando": "true"},
    "a11y": {"momento": "fim", "assina": "comando", "comando": "true", "sempre": False},
    "api": {"momento": "fim", "assina": "comando", "comando": "true", "sempre": False},
    "design": {"momento": "inicio", "assina": "artefato", "artefato": "docs/specs/*/design.md", "sempre": False},
    "execucao": {"momento": "meio", "assina": "comando", "comando": "true", "sempre": False},
}


class TestTaskPassports(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/trilho.json").write_text(json.dumps({"portoes": GATES}))
        commit_all(self.repo, "registry")
        git(self.repo, "checkout", "-q", "-b", "feat")

    def ticket(self, number, gates, blockers="nenhum", paths="src/**", entry="nenhum"):
        path = self.repo / f"docs/specs/a/issues/{number}-task.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Task\nStatus: open\nBloqueado por: {blockers}\nEntrada: {entry}\n"
                        f"Portões: {gates}\nArquivos: {paths}\n")
        return path

    def test_frontier_and_independent_gate_sets(self):
        front = self.ticket("01", "a11y", paths="front.tsx")
        back = self.ticket("02", "api", paths="back.py")
        dependent = self.ticket("03", "api", "01, 02")
        commit_all(self.repo, "plan")
        problems, ready = tasks.audit(str(self.repo), registry.load(str(self.repo)))
        self.assertEqual(ready, [str(front.relative_to(self.repo)), str(back.relative_to(self.repo))])
        self.assertTrue(any("Status ainda não é done" in p for p in problems))
        self.assertNotIn("a11y", registry.exigidos(str(self.repo), "fim", registry.load(str(self.repo))))
        status = subprocess.run([str(ROOT / "plugins/tr/bin/portao")], cwd=self.repo,
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
        self.assertNotIn("design", registry.exigidos(str(self.repo), "inicio", reg))
        status = subprocess.run([str(ROOT / "plugins/tr/bin/portao")], cwd=self.repo,
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
        ticket = self.ticket("01", "nenhum")
        ticket.write_text(ticket.read_text().replace("Portões: nenhum", "Meio: execucao\nPortões: nenhum"))
        commit_all(self.repo, "plan with middle gate")
        rel = str(ticket.relative_to(self.repo))
        reg = registry.load(str(self.repo))
        key = registry.stamp_key(str(self.repo), GATES["execucao"], rel)
        self.assertTrue(key)
        self.assertFalse(registry.satisfied(str(self.repo), "execucao", reg, ticket=rel))
        ticket.write_text(ticket.read_text() + "Resultado: atualizado\n")
        self.assertNotEqual(key, registry.stamp_key(str(self.repo), GATES["execucao"], rel))
        problems, ready = tasks.audit(str(self.repo), reg)
        self.assertFalse(any("falta carimbo de meio `execucao`" in item for item in problems))
        self.assertIn(rel, ready)
        before_done = registry.stamp_key(str(self.repo), GATES["execucao"], rel)
        ticket.write_text(ticket.read_text().replace("Status: open", "Status: done"))
        self.assertEqual(before_done, registry.stamp_key(str(self.repo), GATES["execucao"], rel))
        scoped = registry.scoped_stamp("execucao", rel)
        with mock.patch.object(ledger, "has", side_effect=lambda root, stamp, key: stamp == scoped and key == before_done):
            self.assertTrue(registry.satisfied(str(self.repo), "execucao", reg, ticket=rel))
            problems, ready = tasks.audit(str(self.repo), reg)
        self.assertFalse(any("falta carimbo de meio `execucao`" in item for item in problems))
        self.assertEqual(ready, [])
        current_key = registry.stamp_key(str(self.repo), GATES["execucao"], rel)
        (self.repo / "source.py").write_text("print('changed')\n")
        self.assertNotEqual(current_key, registry.stamp_key(str(self.repo), GATES["execucao"], rel))

    def test_final_requires_each_ticket_stamp_on_current_snapshot(self):
        front = self.ticket("01", "a11y", paths="front.tsx")
        back = self.ticket("02", "api", paths="back.py")
        commit_all(self.repo, "plan")
        (self.repo / "front.tsx").write_text("export const x = 1\n")
        front_commit = commit_all(self.repo, "front")
        (self.repo / "back.py").write_text("x = 1\n")
        back_commit = commit_all(self.repo, "back")
        front.write_text(front.read_text().replace("Status: open", f"Status: done\nEntrega: {front_commit}"))
        back.write_text(back.read_text().replace("Status: open", f"Status: done\nEntrega: {back_commit}"))
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
        one.write_text(one.read_text().replace("Portões: a11y", "Portões: nenhum")
                       .replace("Bloqueado por: nenhum", "Bloqueado por: 02"))
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
        run = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/portao.py"), "entrega"],
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
        run = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/gate.py")],
                             input=json.dumps(payload), capture_output=True, text=True,
                             env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)["hookSpecificOutput"]
        self.assertEqual(result["permissionDecision"], "deny")
        self.assertIn("fora da fronteira", result["permissionDecisionReason"])

    def test_done_ticket_needs_its_blocker_complete(self):
        first = self.ticket("01", "api", paths="first.py")
        second = self.ticket("02", "api", blockers="01", paths="second.py")
        commit_all(self.repo, "plan")
        (self.repo / "second.py").write_text("second = 1\n")
        second_commit = commit_all(self.repo, "second too early")
        (self.repo / "first.py").write_text("first = 1\n")
        first_commit = commit_all(self.repo, "first")
        second.write_text(second.read_text().replace("Status: open", f"Status: done\nEntrega: {second_commit}"))
        commit_all(self.repo, "mark done")
        signed = {("api", ledger.head(str(self.repo)))}
        with mock.patch.object(ledger, "has", side_effect=lambda root, gate, commit: (gate, commit) in signed):
            problems, ready = tasks.audit(str(self.repo), registry.load(str(self.repo)))
        self.assertTrue(any("Status ainda não é done" in p for p in problems))
        self.assertEqual(ready, [str(first.relative_to(self.repo))])


if __name__ == "__main__":
    unittest.main()
