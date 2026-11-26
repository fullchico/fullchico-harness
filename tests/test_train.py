"""O trem: auditoria só na chegada; o trem de ajuste revalida só o que reprovou."""
import json
import sys
import unittest

from tests.helpers import ROOT, accept, commit_all, make_repo
sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
import certs  # noqa: E402
import registry  # noqa: E402
import tasks  # noqa: E402

GATES = {"quality": {"stage": "end", "signs": "command", "command": "true"},
         "bugs": {"stage": "end", "signs": "agent", "agent": "tr:bug-hunter"}}


class Base(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.root = str(self.repo)
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/harness.json").write_text(json.dumps({"gates": GATES}))
        (self.repo / ".claude/current-demand").write_text("pedido\n")
        spec = self.repo / "docs/specs/pedido"
        (spec / "issues").mkdir(parents=True)
        (spec / "spec.md").write_text("# Pedido\n\nCritério: somar.\n")
        self.ticket = spec / "issues/01-soma.md"
        self.ticket.write_text("# 01\n\nStatus: open\nBlocked by: none\nStart: none\nGates: none\nFiles: src/**\n")
        (self.repo / "src").mkdir()
        (self.repo / "src/soma.py").write_text("def soma(a, b): return a + b\n")
        commit_all(self.repo, "feat: soma")
        accept(self.repo)

    def certify(self, name, verdict="APPROVED"):
        gate = GATES[name]
        certs.certify(self.root, name, registry.stamp_key(self.root, gate), verdict, registry.responsible(gate), name)

    def ok(self, name):
        return registry.satisfied(self.root, name, registry.load(self.root))

    def adjust(self, status, files="src/**"):
        folder = self.repo / "docs/specs/pedido/progress"
        folder.mkdir(exist_ok=True)
        (folder / "adjust-01-bugs.md").write_text(
            f"# Ajuste 01: o bugs reprovou\n\nStatus: {status}\nGates: bugs\nFiles: {files}\n")
        commit_all(self.repo, f"chore: ajuste {status}")



class TrainTest(Base):
    def test_the_audit_waits_for_the_train_and_the_adjustment_round_reruns_only_what_failed(self):
        self.assertEqual(tasks.open_work(self.root), ["docs/specs/pedido/issues/01-soma.md"], "o trem não chegou")
        self.ticket.write_text(self.ticket.read_text().replace("Status: open", "Status: done"))
        commit_all(self.repo, "chore: chegou")
        self.assertEqual(tasks.open_work(self.root), [])
        self.certify("quality")
        self.certify("bugs")
        self.certify("bugs", "REJECTED")  # a chegada reprovou o bugs
        self.assertFalse(self.ok("bugs"))
        self.adjust("open")
        self.assertTrue(certs.accepted(self.root), "o ajuste é andamento: o aceite do dono continua")
        self.assertEqual(tasks.open_work(self.root), ["docs/specs/pedido/progress/adjust-01-bugs.md"])
        (self.repo / "src/soma.py").write_text("def soma(a, b):\n    return int(a) + int(b)\n")
        self.adjust("done")
        self.assertFalse(self.ok("quality"), "o código mudou: o quality roda de novo")
        self.assertFalse(self.ok("bugs"), "quem reprovou revalida")

    def test_the_frontier_advances_on_integrated_tickets_without_end_certificates(self):
        """Na viagem não roda portão de fim: o ticket integrado já libera quem depende dele."""
        second = self.repo / "docs/specs/pedido/issues/02-subtrai.md"
        second.write_text("# 02\n\nStatus: open\nBlocked by: 01\nStart: none\nGates: none\nFiles: lib/**\n")
        commit_all(self.repo, "docs: ticket 02")
        accept(self.repo)
        reg = registry.load(self.root)
        self.assertEqual(tasks.audit(self.root, reg)[1], ["docs/specs/pedido/issues/01-soma.md"])
        self.ticket.write_text(self.ticket.read_text().replace("Status: open", "Status: done"))
        commit_all(self.repo, "chore: 01 integrado")
        problems, ready = tasks.audit(self.root, reg)
        self.assertEqual(ready, ["docs/specs/pedido/issues/02-subtrai.md"], "sem certificado de fim, o 02 já pode sair")
        self.assertTrue(any("falta carimbo `quality`" in p for p in problems), "a entrega continua exigindo")

    def test_the_arrival_balance_says_what_arrived_and_what_failed(self):
        import balance_cli
        self.ticket.write_text(self.ticket.read_text().replace("Status: open", "Status: done"))
        commit_all(self.repo, "chore: chegou")
        self.certify("quality")
        self.certify("bugs", "REJECTED")
        text = balance_cli.balance(self.root)
        self.assertIn("ticket `01-soma.md`: done", text)
        self.assertIn("`quality`: certificado", text)
        self.assertIn("`bugs`: reprovado: bugs (reprovações: 1/3)", text)

    def test_an_approval_rides_the_adjustment_round_only_inside_what_it_declared(self):
        self.ticket.write_text(self.ticket.read_text().replace("Status: open", "Status: done"))
        commit_all(self.repo, "chore: chegou")
        self.certify("bugs")
        self.adjust("open")
        (self.repo / "src/soma.py").write_text("def soma(a, b):\n    return a + b  # ajuste\n")
        self.adjust("done")
        self.assertTrue(self.ok("bugs"), "a aprovação segue: o ajuste ficou nos arquivos que declarou")
        (self.repo / "outro.py").write_text("x = 1\n")
        commit_all(self.repo, "feat: fora do declarado")
        self.assertFalse(self.ok("bugs"), "mudou fora do declarado: a aprovação cai")

    def test_an_approval_does_not_ride_a_changed_criterion(self):
        self.ticket.write_text(self.ticket.read_text().replace("Status: open", "Status: done"))
        commit_all(self.repo, "chore: chegou")
        self.certify("bugs")
        self.adjust("done")
        spec = self.repo / "docs/specs/pedido/spec.md"
        spec.write_text(spec.read_text().replace("somar", "somar e subtrair"))
        commit_all(self.repo, "docs: critério novo")
        self.assertFalse(self.ok("bugs"))


class RescueTest(Base):
    def hook(self, script, payload):
        import os
        import subprocess
        return subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts" / script)], capture_output=True,
                              text=True, input=json.dumps(dict(payload, cwd=self.root)),
                              env=dict(os.environ, CLAUDE_PROJECT_DIR=self.root))

    def dispatch(self):
        job = {"subagent_type": "general-purpose", "isolation": "worktree",  # como o orquestrador real dispara
               "prompt": "Implemente docs/specs/pedido/issues/01-soma.md"}
        out = self.hook("guard.py", {"hook_event_name": "PreToolUse", "tool_name": "Agent", "agent_type": "tr:orchestrator",
                                     "tool_input": job})
        return job, json.loads(out.stdout)["hookSpecificOutput"]

    def test_the_executor_carries_the_branch_and_the_handoff_and_keeps_its_seat_until_it_stops(self):
        job, decision = self.dispatch()
        prompt = decision["updatedInput"]["prompt"]
        self.assertIn(f"git merge --ff-only {registry.branch(self.root)}", prompt, "alinha à branch da demanda")
        self.assertIn("docs/specs/pedido/progress/handoff-01-soma.md", prompt, "quem para deixa handoff")
        self.hook("dispatch_done.py", {"hook_event_name": "SubagentStart", "agent_id": "ex1", "agent_type": "general-purpose"})
        self.assertIn("docs/specs/pedido/issues/01-soma.md", tasks._in_flight(self.root))
        self.hook("executor_report.py", {"hook_event_name": "SubagentStop", "agent_id": "ex1",
                                         "last_assistant_message": "DONE: docs/specs/pedido/issues/01-soma.md — feito"})
        self.assertEqual(tasks._in_flight(self.root), {}, "o executor terminou: a vaga fica livre")
        self.assertEqual(tasks.wait(self.root, seconds=0)[0], 0, "o trem parou")

    def test_wait_keeps_watching_while_the_orchestrator_drives(self):
        import time
        board = tasks.board(self.root)
        board.setdefault("agents", {})["orq"] = {"type": "tr:orchestrator", "last": time.time()}
        tasks._save_board(self.root, board)
        self.assertEqual(tasks.wait(self.root, seconds=0)[0], 3, "entre ondas, com o orquestrador ativo, ainda roda")

    def test_a_failing_command_gate_counts_as_a_rejection(self):
        """Comando que sai com erro chega ao hook por PostToolUseFailure, com a saída em `error`."""
        self.ticket.write_text(self.ticket.read_text().replace("Status: open", "Status: done"))
        commit_all(self.repo, "chore: chegou")
        self.hook("sign.py", {"hook_event_name": "PostToolUseFailure", "tool_name": "Bash",
                              "agent_type": registry.CHECKER, "tool_input": {"command": "gate quality"},
                              "error": "Exit code 1\nteste quebrou\n\ngate quality: FALHOU (true)"})
        import attempts
        self.assertEqual(attempts.status(self.root, "quality", GATES["quality"])["rejections"], 1)

    def test_wait_wakes_the_orchestrator_when_an_executor_is_stuck(self):
        import time
        self.dispatch()
        self.hook("dispatch_done.py", {"hook_event_name": "SubagentStart", "agent_id": "ex1", "agent_type": "general-purpose"})
        self.assertEqual(tasks.wait(self.root, seconds=0)[0], 3, "ainda rodando")
        board = tasks.board(self.root)
        board.setdefault("agents", {})["ex1"] = {"type": "general-purpose", "last": time.time() - 3600}
        tasks._save_board(self.root, board)
        code, state = tasks.wait(self.root, seconds=0)
        self.assertEqual(code, 4)
        self.assertEqual(state["stuck"], {"docs/specs/pedido/issues/01-soma.md": "ex1"})


if __name__ == "__main__":
    unittest.main()
