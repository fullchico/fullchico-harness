"""O trem: auditoria só na chegada; o trem de ajuste revalida só o que reprovou."""
import json
import os
import pathlib
import sys
import unittest
import unittest.mock

from tests.helpers import ROOT, accept, commit_all, make_repo
sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
import certs  # noqa: E402
import registry  # noqa: E402
import tasks  # noqa: E402

GATES = {"quality": {"stage": "end", "signs": "command", "command": "true"},
         "bugs": {"stage": "end", "signs": "agent", "agent": "tr:bug-hunter"}}


def subprocess_run(command, cwd):
    import subprocess
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True)


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

    def test_squashing_the_history_erases_the_signatures(self):
        import subprocess
        from tests.helpers import git
        self.ticket.write_text(self.ticket.read_text().replace("Status: open", "Status: done"))
        base = commit_all(self.repo, "chore: chegou")
        self.certify("bugs")
        self.adjust("done")
        self.assertTrue(self.ok("bugs"))
        import os
        out = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/guard.py")], capture_output=True, text=True,
                             input=json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": self.root,
                                               "tool_input": {"command": f"git reset --soft {base} && git commit -m x"}}),
                             env=dict(os.environ, CLAUDE_PROJECT_DIR=self.root)).stdout
        self.assertIn("assinatura protegida", out, "o guard barra reescrever por cima do certificado")
        git(self.repo, "reset", "--soft", base)   # e mesmo que alguém reescreva por fora do agente...
        git(self.repo, "commit", "-q", "-m", "feat: tudo junto")
        self.assertFalse(self.ok("bugs"), "...a linha sem o commit do responsável não vale, nem de carona")

    def test_an_approval_does_not_ride_a_changed_criterion(self):
        self.ticket.write_text(self.ticket.read_text().replace("Status: open", "Status: done"))
        commit_all(self.repo, "chore: chegou")
        self.certify("bugs")
        self.adjust("done")
        spec = self.repo / "docs/specs/pedido/spec.md"
        spec.write_text(spec.read_text().replace("somar", "somar e subtrair"))
        commit_all(self.repo, "docs: critério novo")
        self.assertFalse(self.ok("bugs"))


class MaestroTest(Base):
    def run_cli(self, *args, path=None):
        import os
        import subprocess
        env = dict(os.environ, PATH=path or os.environ["PATH"])
        return subprocess.run([str(ROOT / "plugins/tr/bin/tr-harness"), "orchestrate", *args], cwd=self.root,
                              capture_output=True, text=True, env=env)

    def test_the_train_does_not_leave_without_the_three_models_of_the_wave(self):
        from tests.helpers import _tmpdir, fake_claude
        fake = fake_claude(_tmpdir())
        path = f"{fake}:{os.environ['PATH']}"
        out = self.run_cli("--agent", "claude", "--model", "sonnet", path=path)
        self.assertEqual(out.returncode, 2)
        self.assertIn("AskUserQuestion", out.stderr, "sem os três modelos, o comando manda perguntar ao dono")
        self.assertFalse((fake / "tmux-calls").exists(), "nenhum terminal foi aberto")
        ok = self.run_cli("--model", "sonnet", "--executors", "auto", "--reviewers", "claude:sonnet", path=path)
        self.assertEqual(ok.returncode, 0, ok.stderr)

    def test_an_executor_on_another_cli_opens_in_its_own_terminal(self):
        import subprocess
        from tests.helpers import _tmpdir, fake_claude
        fake = fake_claude(_tmpdir())
        reg = json.loads((self.repo / ".claude/harness.json").read_text())
        reg["models"] = {"execution": {"cli": "codex", "model": "terra"}}
        (self.repo / ".claude/harness.json").write_text(json.dumps(reg))
        env = dict(os.environ, PATH=f"{fake}:{os.environ['PATH']}")
        cli = [str(ROOT / "plugins/tr/bin/tr-harness"), "models"]
        out = subprocess.run([*cli, "run", "execution", "--ticket", "docs/specs/pedido/issues/01-soma.md",
                              "--prompt", "siga a spec", "--detach"], cwd=self.root, capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        run = json.loads(out.stdout)
        call = (fake / "tmux-calls").read_text()
        self.assertIn("new-session -d -s " + run["terminal"], call)
        self.assertIn("FULLCHICO_ROLE=execution", call, "o hook reconhece o executor pelo ambiente do terminal")
        self.assertIn("codex --model", call)
        # o terminal fechou sem relato: é bloqueio, não motivo para trocar de executor
        gone = subprocess.run([*cli, "wait", run["id"]], cwd=self.root, capture_output=True, text=True, env=env)
        self.assertEqual(gone.returncode, 1)
        self.assertIn("não troque de executor", gone.stderr)
        # com o relato gravado, a espera volta com ele
        report = next((self.repo / ".git/harness-runs" / run["id"]).glob("dispatch.json"))
        (self.repo / json.loads(report.read_text())["report"]).write_text("DONE\nfeito\n")
        done = subprocess.run([*cli, "wait", run["id"]], cwd=self.root, capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("feito", done.stdout)

    def test_two_trains_keep_their_own_coordination_state(self):
        """Dois worktrees do mesmo repositório, uma demanda em cada: vagas, quadro, orquestrador e aprovações à parte."""
        import subprocess
        import registry
        import tasks
        other = str(self.repo.parent / "outra")
        subprocess.run(["git", "worktree", "add", "-q", "-b", "outra", other], cwd=self.root, check=True)
        (self.repo.parent / "outra/.claude/current-demand").write_text("outra\n")
        self.assertNotEqual(tasks.coordination(self.root, "orchestrator.json"), tasks.coordination(other, "orchestrator.json"))
        self.assertTrue(tasks.coordination(self.root, "x").startswith(os.path.dirname(os.path.dirname(tasks.coordination(other, "x")))),
                        "o repositório é o mesmo; só a pasta da demanda muda")
        tasks.start_executor(self.root, "docs/specs/pedido/issues/01-soma.md")
        tasks._save_in_flight(other, {})  # o outro trem grava o quadro dele
        self.assertIn("docs/specs/pedido/issues/01-soma.md", tasks._in_flight(self.root), "um trem não apaga a vaga do outro")
        registry.grant_owner(self.root, "gates --accept")
        self.assertTrue(registry.owner_pending(self.root, "gates --accept"))
        self.assertFalse(registry.owner_pending(other, "gates --accept"), "a aprovação vale na demanda em que foi dada")

    def test_demand_open_creates_a_child_worktree_and_the_parent_watches_it(self):
        import subprocess
        subprocess.run(["git", "checkout", "-q", "-b", "time/pedido"], cwd=self.root, check=True)
        cli = [str(ROOT / "plugins/tr/bin/tr-harness")]
        self.assertEqual(subprocess.run([*cli, "demand", "open", "Nome Ruim"], cwd=self.root, capture_output=True).returncode, 2)
        out = subprocess.run([*cli, "demand", "open", "fatia-2"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        child = self.repo.parent / "fatia-2"
        self.assertEqual((child / ".claude/current-demand").read_text().strip(), "fatia-2", "a filha nasce com o ponteiro dela")
        from tests.helpers import git
        self.assertEqual(git(child, "branch", "--show-current"), "time/fatia-2", "nasce da branch do pai, com o prefixo dele")
        self.assertIn("EnterWorktree", out.stdout)
        self.assertEqual(subprocess.run([*cli, "demand", "path", "fatia-2"], cwd=self.root, capture_output=True,
                                        text=True).stdout.strip(), os.path.realpath(child))
        status = subprocess.run([*cli, "--demand", "fatia-2", "status"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(status.returncode, 0, status.stderr)
        refused = subprocess.run([*cli, "--demand", "fatia-2", "gates", "--accept"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(refused.returncode, 2, "o que escreve roda de dentro da pasta da demanda")
        self.assertIn("fatia-2", subprocess.run([*cli, "demand", "list"], cwd=self.root, capture_output=True, text=True).stdout)

    def test_the_maestro_dispatching_the_orchestrator_subagent_is_not_an_executor(self):
        self.hook = lambda script, payload: RescueTest.hook(self, script, payload)
        job = {"subagent_type": "tr:orchestrator", "prompt": "Conduza docs/specs/pedido/issues/01-soma.md",
               "run_in_background": True}
        out = self.hook("guard.py", {"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": job}).stdout
        self.assertNotIn("worktree", out, "o orquestrador coordena na pasta da demanda, não num worktree de executor")

    def test_the_maestro_hands_the_accepted_demand_to_an_orchestrator_in_its_own_terminal(self):
        from tests.helpers import _tmpdir, fake_claude
        import tasks
        fake = fake_claude(_tmpdir())
        path = f"{fake}:{os.environ['PATH']}"
        out = self.run_cli("--agent", "codex", "--model", "sol", "--executors", "claude:haiku", "--reviewers",
                           "claude:sonnet", path=path)
        self.assertEqual(out.returncode, 0, out.stderr)
        call = (fake / "tmux-calls").read_text()
        self.assertIn("new-session -d -s orq-pedido-sol", call, "o nome diz papel, demanda e modelo")
        self.assertIn("TR_ROLE=orchestrator", call)
        self.assertRegex(call, r"codex --model \S*sol ", "o apelido vira o id mais novo que esta máquina conhece")
        self.assertIn("embarque - `quality`", out.stdout, "cada verificador de comando roda uma vez antes da partida")
        self.assertEqual(tasks.run_model(self.root, "executors"), ("claude", "haiku"), "a escolha é da demanda")
        self.assertEqual(registry.ticket_model(self.root, "docs/specs/pedido/issues/01-soma.md"), "haiku")
        self.assertNotIn("models", json.loads((self.repo / ".claude/harness.json").read_text()), "o registro não muda")
        brief = open(tasks.coordination(self.root, "orchestrator-brief.md")).read()
        self.assertIn("report done", brief)
        self.assertIn("docs/specs/pedido/issues/01-soma.md", brief)
        from tests.helpers import git
        self.assertEqual(git(self.repo, "status", "--porcelain"), "", "a partida não suja a árvore")
        # a espera do maestro: sem relato e com o terminal fechado, avisa; com o relato, devolve o que voltou
        self.assertEqual(self.run_cli("--wait", "--seconds", "1", path=path).returncode, 1)
        rep = subprocess_run([str(ROOT / "plugins/tr/bin/tr-harness"), "report", "blocked", "falta o banco"], self.root)
        self.assertEqual(rep.returncode, 0, rep.stderr)
        got = self.run_cli("--wait", "--seconds", "1", path=path)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertIn("BLOCKED", got.stdout)
        self.assertIn("falta o banco", got.stdout)
        self.assertIn("gate delivery (computed now)", got.stdout, "o relato não é só a palavra de quem conduz")

    def test_boarding_warns_about_tickets_of_one_wave_sharing_a_file(self):
        import orchestrate_cli
        issues = self.repo / "docs/specs/pedido/issues"
        (issues / "02-a.md").write_text("# 02\n\nStatus: open\nBlocked by: 01\nFiles: src/a.py, src/app.py\n")
        (issues / "03-b.md").write_text("# 03\n\nStatus: open\nBlocked by: 01\nFiles: src/b.py, src/app.py\n")
        (issues / "04-c.md").write_text("# 04\n\nStatus: open\nBlocked by: 03\nFiles: src/c.py, src/app.py\n")
        lines = orchestrate_cli.shared_files(self.root)
        self.assertEqual(len(lines), 2, lines)  # 02 com 03, e 02 com 04; o 04 espera o 03
        self.assertIn("src/app.py", lines[0])

    def test_several_executor_models_take_turns(self):
        import tasks
        tasks.run_choice(self.root, {"executors": "claude:haiku, codex:terra"})
        self.assertEqual([tasks.next_executor(self.root) for _ in range(3)],
                         [("claude", "haiku"), ("codex", "terra"), ("claude", "haiku")])
        tasks.run_choice(self.root, {"executors": "claude:sonnet"})
        self.assertEqual(tasks.next_executor(self.root), ("claude", "sonnet"))

    def test_integration_keeps_the_seat_when_the_merge_does_not_enter(self):
        """Caso real: um merge pela metade de outra partida fez os merges falharem, e as branches foram apagadas."""
        import models_cli
        from tests.helpers import git
        seat = self.repo / ".claude/worktrees/tr-seat-1"
        git(self.repo, "worktree", "add", "-q", "-b", "tr-exec-aaaa1111", str(seat))
        (seat / "novo.md").write_text("trabalho do executor, sem commit\n")
        folder = os.path.join(models_cli._state_dir(self.root), "20260101T000000Z-aaaa1111")
        os.makedirs(folder)
        with open(os.path.join(folder, "dispatch.json"), "w") as stream:
            json.dump({"worktree": str(seat), "branch": "tr-exec-aaaa1111", "session": "x"}, stream)
        git_dir = git(self.repo, "rev-parse", "--absolute-git-dir")
        open(os.path.join(git_dir, "MERGE_HEAD"), "w").write(git(self.repo, "rev-parse", "HEAD") + "\n")
        self.assertEqual(models_cli.integrate(self.root, ["20260101T000000Z-aaaa1111"]), 1)
        self.assertTrue(seat.is_dir(), "com um merge pela metade, nada é desmontado")
        self.assertEqual(self.run_cli("--model", "sonnet", "--executors", "auto", "--reviewers", "claude:sonnet").returncode, 1,
                         "e o trem não parte")
        os.remove(os.path.join(git_dir, "MERGE_HEAD"))
        self.assertEqual(models_cli.integrate(self.root, ["20260101T000000Z-aaaa1111"]), 0)
        self.assertTrue((self.repo / "novo.md").is_file(), "o trabalho sem commit do executor entrou")
        self.assertFalse(seat.exists())
        self.assertNotIn("tr-exec-aaaa1111", git(self.repo, "branch"))

    def test_a_boxed_executor_asks_and_the_orchestrator_grants_or_refuses(self):
        """O peixe fica na caixa: o que ela nega, ele pede a quem o coordena, e o dono não é interrompido."""
        from unittest import mock
        import models_cli
        import terminal
        seat = self.repo / ".claude/worktrees/tr-seat-9"
        (seat / ".harness-run").mkdir(parents=True)
        asking = seat / ".harness-run/request-bbbb2222.md"
        folder = os.path.join(models_cli._state_dir(self.root), "20260101T000000Z-bbbb2222")
        os.makedirs(folder)
        with open(os.path.join(folder, "dispatch.json"), "w") as stream:
            json.dump({"worktree": str(seat), "branch": "tr-exec-bbbb2222", "session": "exec-x", "request": str(asking),
                       "report": str(seat / ".harness-run/executor-bbbb2222.md")}, stream)
        run, told = "20260101T000000Z-bbbb2222", []
        with mock.patch.object(terminal, "alive", return_value=True), \
                mock.patch.object(terminal, "tell", side_effect=lambda session, text: told.append(text)):
            asking.write_text("RUN: touch instalado.txt\nthe sandbox has no network\n")
            state, text = models_cli._terminal_state(self.root, run, folder)
            self.assertEqual(state, "request")
            self.assertIn("touch instalado.txt", text)
            self.assertEqual(models_cli._terminal_wait(self.root, [run], 5), 6, "volta a quem coordena, sem virar bloqueio do dono")
            self.assertEqual(models_cli.answer_request(self.root, run, True), 0)
            self.assertTrue((seat / "instalado.txt").is_file(), "o comando rodou na vaga do executor")
            self.assertFalse(asking.exists())
            self.assertIn("exit 0", told[-1])
            asking.write_text("RUN: git push origin HEAD\nwant to publish\n")
            self.assertEqual(models_cli.answer_request(self.root, run, True), 1, "o que sai do projeto não se concede")
            self.assertTrue(asking.exists())
            self.assertEqual(models_cli.answer_request(self.root, run, False, "not part of the ticket"), 0)
            self.assertIn("Refused", told[-1])
            asking.write_text("RUN: true\n")
            with mock.patch.dict(os.environ, {"FULLCHICO_ROLE": "execution"}):
                self.assertEqual(models_cli.answer_request(self.root, run, True), 1, "o executor não concede a si mesmo")
        payload = json.dumps({"hook_event_name": "Stop", "cwd": str(seat)})
        script = [sys.executable, str(ROOT / "plugins/tr/scripts/delivery_stop.py")]
        env = dict(os.environ, TR_REPORT=str(seat / ".harness-run/executor-bbbb2222.md"), TR_REQUEST=str(asking))
        import subprocess
        self.assertEqual(subprocess.run(script, input=payload, capture_output=True, text=True, env=env).stdout.strip(), "",
                         "com pedido aberto, parar é esperar a resposta")
        asking.unlink()
        self.assertIn("block", subprocess.run(script, input=payload, capture_output=True, text=True, env=env).stdout)

    def test_no_executor_leaves_while_the_criterion_is_not_accepted(self):
        """Caso real: o orquestrador ampliou os Files de um ticket e despachou antes de o dono aceitar."""
        import models_cli
        ticket = self.repo / "docs/specs/pedido/issues/01-soma.md"
        ticket.write_text(ticket.read_text().replace("Files:", "Files: src/**,"))
        with self.assertRaises(ValueError) as error:
            models_cli.terminal_execute(self.root, "faça", "docs/specs/pedido/issues/01-soma.md")
        self.assertIn("aceite", str(error.exception))

    def test_a_missing_env_file_means_the_gate_does_not_run(self):
        import orchestrate_cli
        reg = {"gates": {"e2e": {"stage": "end", "signs": "command", "command": "echo 'node: .env: not found' >&2; exit 9"},
                         "lint": {"stage": "start", "signs": "command", "command": "true"}}}
        self.assertIn("DOES NOT RUN", orchestrate_cli.preflight(self.root, reg)[0])
        self.assertEqual(len(orchestrate_cli.preflight(self.root, reg)), 1)
        self.assertEqual(len(orchestrate_cli.preflight(self.root, reg, every=True)), 2)

    def test_a_codex_orchestrator_opens_with_the_newest_id_of_the_alias(self):
        """Caso real: `--agent codex --model sol` abriu o Codex com `sol`, que ele recusa, e o trem ficou parado."""
        from unittest import mock
        from tests.helpers import _tmpdir, fake_claude
        import models_cli
        import orchestrate_cli
        import terminal
        opened = []
        with mock.patch.object(models_cli, "_codex_newest", return_value="gpt-9.9-sol"), \
                mock.patch.object(terminal, "executable", return_value="tmux"), \
                mock.patch.object(terminal, "open_agent", side_effect=lambda *a, **k: opened.append(a)), \
                mock.patch.object(orchestrate_cli, "preflight", return_value=[]), \
                mock.patch.object(os, "getcwd", return_value=self.root):
            code = orchestrate_cli.main(["--agent", "codex", "--model", "sol", "--executors", "codex:terra", "--reviewers", "codex:terra"])
        self.assertEqual(code, 0)
        self.assertEqual(opened[0][3], "gpt-9.9-sol")
        self.assertIsNotNone(terminal.waiting_on_human("■ The 'sol' model is not supported when using Codex with a ChatGPT account."))

    def test_boarding_warns_when_a_codex_executor_cannot_write_where_a_ticket_needs(self):
        import orchestrate_cli
        issues = self.repo / "docs/specs/pedido/issues"
        (issues / "02-codex.md").write_text("# 02\n\nStatus: open\nBlocked by: none\nFiles: .codex/hooks.json, .agents/skills/x/**, src/a.py\n")
        self.assertEqual(orchestrate_cli.unwritable_for_codex(self.root, "claude:haiku"), [])
        lines = orchestrate_cli.unwritable_for_codex(self.root, "claude:haiku,codex:terra")
        self.assertEqual(len(lines), 1)
        self.assertIn(".codex/hooks.json", lines[0])
        self.assertNotIn("src/a.py", lines[0])

    def test_the_orchestrator_cannot_stop_without_reporting(self):
        import subprocess
        payload = json.dumps({"hook_event_name": "Stop", "cwd": self.root, "last_assistant_message": "pronto"})
        script = [sys.executable, str(ROOT / "plugins/tr/scripts/delivery_stop.py")]
        quiet = subprocess.run(script, input=payload, capture_output=True, text=True, env=dict(os.environ, TR_ROLE=""))
        self.assertEqual(quiet.stdout.strip(), "", "a sessão do maestro não é cobrada")
        held = subprocess.run(script, input=payload, capture_output=True, text=True, env=dict(os.environ, TR_ROLE="orchestrator"))
        self.assertEqual(json.loads(held.stdout)["decision"], "block")
        import tasks
        tasks.start_executor(self.root, "docs/specs/pedido/issues/01-soma.md")
        waiting = subprocess.run(script, input=payload, capture_output=True, text=True, env=dict(os.environ, TR_ROLE="orchestrator"))
        self.assertEqual(waiting.stdout.strip(), "", "com executor em voo, ele está esperando o aviso: não é cobrado")
        tasks.finish_executor(self.root, "docs/specs/pedido/issues/01-soma.md")
        (self.repo / ".harness-run").mkdir(exist_ok=True)
        (self.repo / ".harness-run/report.md").write_text("DONE\n")
        free = subprocess.run(script, input=payload, capture_output=True, text=True, env=dict(os.environ, TR_ROLE="orchestrator"))
        self.assertEqual(free.stdout.strip(), "")


class ParallelTripsTest(Base):
    def test_a_train_never_adopts_or_integrates_the_fish_of_another_demand(self):
        """Caso real: no embarque do financeiro, o orquestrador recebeu os 3 executores da lista de espera como
        "adotados", com ordem de integrá-los: o código de uma demanda entraria na branch da outra."""
        from unittest import mock
        import models_cli
        import orchestrate_cli
        import terminal
        mine = self.repo / ".claude/worktrees/tr-seat-1"
        other = pathlib.Path(self.root).parent / "outra-demanda" / ".claude/worktrees/tr-seat-1"
        for seat in (mine, other):
            seat.mkdir(parents=True)

        def record(run, data):
            folder = os.path.join(models_cli._state_dir(self.root), run)
            os.makedirs(folder)
            with open(os.path.join(folder, "dispatch.json"), "w") as stream:
                json.dump(dict(data, session="exec-" + run, report="x.md", branch="tr-exec-" + run), stream)
        record("r-minha", {"demand": "pedido", "worktree": str(mine), "ticket": "docs/specs/pedido/issues/01-soma.md"})
        record("r-outra", {"demand": "lista-de-espera", "worktree": str(other), "ticket": "docs/specs/lista-de-espera/issues/02-x.md"})
        record("r-antiga-outra", {"worktree": str(other), "ticket": "docs/specs/lista-de-espera/issues/03-y.md"})
        record("r-antiga-minha", {"worktree": str(mine), "ticket": "docs/specs/pedido/issues/01-soma.md"})
        with mock.patch.object(terminal, "alive", return_value=True):
            adopted = "\n".join(orchestrate_cli.running_executors(self.root))
        self.assertIn("r-minha", adopted)
        self.assertIn("r-antiga-minha", adopted)
        self.assertNotIn("r-outra", adopted, "o peixe de outra demanda não é adotado")
        self.assertNotIn("r-antiga-outra", adopted, "nem o de um registro antigo, sem a demanda gravada")
        self.assertEqual(models_cli.integrate(self.root, ["r-outra"]), 1, "nem integrado, mesmo pedindo pelo id")
        self.assertEqual(models_cli.answer_request(self.root, "r-outra", True, "true"), 1)

    def test_each_trip_has_its_own_signature_and_the_wagons_carry_it(self):
        """A ideia do dono: a viagem tem uma assinatura única e os vagões a recebem. O nome da demanda pode se
        repetir (a mesma pasta, a mesma demanda de novo); a assinatura não."""
        from unittest import mock
        import models_cli
        import orchestrate_cli
        import tasks
        import terminal
        self.assertIsNone(tasks.trip(self.root), "sem partida, não há viagem")
        first = tasks.trip(self.root, create=True)
        self.assertRegex(first, r"^pedido-[0-9a-f]{6}$")
        self.assertEqual(tasks.trip(self.root, create=True), first, "uma nova partida da mesma viagem mantém a assinatura")
        seat = self.repo / ".claude/worktrees/tr-seat-1"
        seat.mkdir(parents=True)

        def record(run, trip):
            folder = os.path.join(models_cli._state_dir(self.root), run)
            os.makedirs(folder)
            with open(os.path.join(folder, "dispatch.json"), "w") as stream:
                json.dump({"demand": "pedido", "trip": trip, "worktree": str(seat), "session": "exec-" + run, "report": "x.md"}, stream)
        record("r-desta-viagem", first)
        with mock.patch.object(terminal, "alive", return_value=True):
            self.assertIn("r-desta-viagem", "\n".join(orchestrate_cli.running_executors(self.root)))
            tasks.close_trip(self.root)  # a viagem chegou
            second = tasks.trip(self.root, create=True)
            self.assertNotEqual(second, first, "a demanda seguinte com o mesmo nome é outra viagem")
            self.assertNotIn("r-desta-viagem", "\n".join(orchestrate_cli.running_executors(self.root)),
                             "um vagão da viagem anterior não é adotado, mesmo com o mesmo nome de demanda")


class DismantleTest(Base):
    def test_only_an_orchestrator_that_really_stopped_is_dismantled(self):
        """Caso real: o orquestrador relatou, ninguém estava na espera, e o terminal ficou aberto por horas.
        E o cuidado do dono: nunca encerrar um terminal que voltou a trabalhar."""
        import subprocess
        import report_cli
        import tasks
        if not __import__("shutil").which("tmux"):
            self.skipTest("precisa do tmux de verdade")
        tag = os.path.basename(self.root)[-6:]
        busy, idle = f"orq-teste-ativo-{tag}", f"orq-teste-parado-{tag}"
        subprocess.run(["tmux", "new-session", "-d", "-s", busy, "while true; do date +%N; sleep 0.2; done"], check=True)
        subprocess.run(["tmux", "new-session", "-d", "-s", idle, "echo relatei; sleep 300"], check=True)
        for name in (busy, idle):
            self.addCleanup(subprocess.run, ["tmux", "kill-session", "-t", name], capture_output=True)
        os.makedirs(os.path.dirname(report_cli.path(self.root)), exist_ok=True)
        with open(report_cli.path(self.root), "w") as stream:
            stream.write("DONE\n")
        stamp = os.path.getmtime(report_cli.path(self.root))
        self.assertIs(report_cli.safe_to_stop(self.root, busy, stamp, quiet=1), False, "a tela muda: ainda trabalha")
        self.assertIs(report_cli.safe_to_stop(self.root, idle, stamp, quiet=1), True, "parado e com o relato feito")
        tasks.start_executor(self.root, "docs/specs/pedido/issues/01-soma.md")
        self.assertIs(report_cli.safe_to_stop(self.root, idle, stamp, quiet=1), False, "com executor em voo, não")
        tasks.finish_executor(self.root, "docs/specs/pedido/issues/01-soma.md")
        os.utime(report_cli.path(self.root), (stamp + 50, stamp + 50))
        self.assertIsNone(report_cli.safe_to_stop(self.root, idle, stamp, quiet=1), "outro relato: é outra partida")
        self.assertIsNone(report_cli.safe_to_stop(self.root, "orq-nao-existe-" + tag, stamp, quiet=1))


class JourneyTest(Base):
    def test_the_panel_shows_the_trip_stage_by_stage(self):
        """Caso real: o dono não achava no painel quem estava revisando nem quantas vezes um portão já tinha reprovado."""
        from unittest import mock
        import terminal
        import watch_cli
        text = "\n".join(watch_cli.journey(self.root, ["rev-quality-opus"]))
        for stage in ("embarque", "partida", "caminho", "chegada"):
            self.assertIn(stage, text)
        self.assertIn("aceite", text)
        self.assertIn("tickets 0/", text)
        with mock.patch.object(terminal, "roster", return_value={"exec-01-x-terra": {"demand": "outra"}}), \
                mock.patch.object(terminal, "read", return_value="trabalhando"):
            tree = "\n".join(watch_cli.topology(self.root, ["orq-pedido-sonnet", "orq-outra-sonnet", "exec-01-x-terra"]))
        other = tree.index("orq-outra-sonnet")
        self.assertGreater(tree.index("exec-01-x-terra"), other, "o executor aparece no trem da demanda dele")
        self.assertLess(tree.index("orq-pedido-sonnet"), other, "a demanda desta pasta vem primeiro")


class AttachTest(unittest.TestCase):
    def test_the_owner_names_an_agent_by_the_start_of_its_name(self):
        import watch_cli
        names = ["orq-fila-sonnet", "exec-01-worker-terra", "exec-02-wiring-terra", "rev-bugs-opus"]
        self.assertEqual(watch_cli.pick(names, "orq"), ("orq-fila-sonnet", None))
        self.assertEqual(watch_cli.pick(names, "exec-02"), ("exec-02-wiring-terra", None))
        self.assertEqual(watch_cli.pick(names, "bugs"), ("rev-bugs-opus", None), "um trecho do nome também serve")
        self.assertEqual(watch_cli.pick(names, "exec"), (None, ["exec-01-worker-terra", "exec-02-wiring-terra"]))
        self.assertEqual(watch_cli.pick(names, "nada"), (None, []))
        self.assertEqual(watch_cli.pick(names[:1], ""), ("orq-fila-sonnet", None), "um só aberto: entra direto")
        self.assertEqual(watch_cli.pick(names, ""), (None, names))


class PrivacyTest(Base):
    def test_a_certificate_never_carries_paths_of_the_machine(self):
        """O certificado é versionado: caminho pessoal, pasta temporária e nome de usuário não entram nele."""
        import certs
        home = os.path.expanduser("~")
        text = certs._clean(f"Full log: /var/folders/k4/abc123/T/tr-gate-1.log; see {home}/segredo/x.txt, "
                            f"{self.root}/src/soma.py and /{'Users'}/outra.pessoa/www/app/a.ts", self.root)
        self.assertNotIn(home, text)
        self.assertNotIn(os.path.basename(home), text)
        self.assertNotIn("/var/folders", text)
        self.assertNotIn("outra.pessoa", text)
        self.assertIn("./src/soma.py", text, "o caminho do projeto continua, relativo")
        self.assertIn("<tmp>/tr-gate-1.log", text)


class DoctorTest(Base):
    def test_the_doctor_says_what_is_missing_and_how_to_fix_it(self):
        import subprocess
        from tests.helpers import _tmpdir
        empty = _tmpdir()
        script = [sys.executable, str(ROOT / "plugins/tr/scripts/doctor_cli.py"), self.root]
        out = subprocess.run(script, capture_output=True, text=True, env=dict(os.environ, PATH=f"{empty}:/usr/bin:/bin"))
        self.assertEqual(out.returncode, 1)
        self.assertIn("✗ tmux: falta", out.stdout)
        self.assertIn("brew install tmux", out.stdout)
        self.assertIn("máquina", out.stdout)
        self.assertIn("projeto", out.stdout)


class OwnerEditTest(Base):
    def edit(self, mode="auto", **extra):
        import subprocess
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Write", "permission_mode": mode, "cwd": self.root,
                   "tool_input": {"file_path": os.path.join(self.root, ".codex/hooks.json"), "content": "{}"}, **extra}
        env = {k: v for k, v in os.environ.items() if k not in ("TR_ROLE", "FULLCHICO_ROLE")}
        out = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/guard.py")], input=json.dumps(payload),
                             capture_output=True, text=True, env=dict(env, CLAUDE_PROJECT_DIR=self.root))
        return json.loads(out.stdout)["hookSpecificOutput"] if out.stdout.strip() else None

    def test_the_owner_approves_a_harness_config_edit_inside_the_session(self):
        """O arquivo é protegido, mas pode fazer parte do trabalho: a decisão é do dono, na sessão, e vale uma vez."""
        first = self.edit()
        self.assertEqual(first["permissionDecision"], "deny")
        self.assertIn("Você aprova, como dono, `edit .codex/hooks.json`?", first["permissionDecisionReason"])
        registry.grant_owner(self.root, "edit .codex/hooks.json")  # o dono respondeu Aprovo
        self.assertIsNone(self.edit(), "com a aprovação, a gravação passa")
        self.assertEqual(self.edit()["permissionDecision"], "deny", "a aprovação vale uma vez")
        self.assertEqual(self.edit(mode="default")["permissionDecision"], "ask", "no modo normal, é o diálogo do Claude")
        registry.grant_owner(self.root, "edit .codex/hooks.json")
        fish = self.edit(agent_type="general-purpose")
        self.assertEqual(fish["permissionDecision"], "deny", "um peixe não pergunta ao dono: reporta o bloqueio")
        self.assertIn("BLOCKED", fish["permissionDecisionReason"])


class TerminalCommandTest(unittest.TestCase):
    def test_the_prompt_is_never_taken_for_an_option_value(self):
        """Com `.mcp.json` no projeto entra `--mcp-config <arquivo>`, que aceita vários valores: o pedido vem depois de `--`."""
        import tempfile
        import terminal
        folder = tempfile.mkdtemp()
        open(os.path.join(folder, ".mcp.json"), "w").write("{}")
        line = terminal.command("claude", "sonnet", "/tmp/pedido.txt", root=folder)
        self.assertIn(".mcp.json -- \"$(cat /tmp/pedido.txt)\"", line)
        self.assertTrue(terminal.command("claude", "sonnet", "/tmp/pedido.txt").endswith('-- "$(cat /tmp/pedido.txt)"'))


class RequirementsTest(unittest.TestCase):
    def run_hook(self, path):
        import subprocess
        return subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/requirements.py")], input="{}",
                              capture_output=True, text=True, env=dict(os.environ, PATH=path))

    def test_the_session_starts_with_a_warning_when_a_required_program_is_missing(self):
        from tests.helpers import _tmpdir, fake_claude
        fake = fake_claude(_tmpdir())  # traz tmux e rtk de mentira
        self.assertEqual(self.run_hook(str(fake)).stdout.strip(), "", "com os dois na máquina, silêncio")
        (fake / "tmux").unlink()
        out = json.loads(self.run_hook(str(fake)).stdout)
        self.assertIn("`tmux`", out["systemMessage"])
        self.assertNotIn("`rtk`", out["systemMessage"])
        self.assertIn("brew install tmux", out["hookSpecificOutput"]["additionalContext"])


class EvidenceTest(Base):
    def cli(self, *args):
        import subprocess
        return subprocess.run([str(ROOT / "plugins/tr/bin/tr-harness"), *args], cwd=self.root, capture_output=True, text=True)

    def test_evidence_belongs_to_the_state_it_was_produced_from(self):
        first = self.cli("evidence").stdout.splitlines()[0].strip()
        self.assertTrue((self.repo / first).is_dir(), "a pasta nasce pronta: o revisor em só leitura a encontra")
        (self.repo / first / "saida.txt").write_text("ok\n")
        self.assertIn("saida.txt", self.cli("evidence").stdout)
        (self.repo / "src/soma.py").write_text("def soma(a, b): return a - b\n")
        self.assertNotIn("saida.txt", self.cli("evidence").stdout, "o código mudou: a prova antiga não é deste estado")
        self.assertEqual(self.cli("ports").returncode, 1, "sem porta escutando, o ambiente não está no ar")
        from tests.helpers import git
        self.assertEqual(git(self.repo, "status", "--porcelain"), " M src/soma.py", "a prova fica fora do Git")

    def test_a_failed_gate_keeps_its_own_output_where_everyone_reads_it(self):
        """Caso real: o e2e reprovou duas vezes e só chegou "FALHOU"; o log era um só por projeto, e o portão seguinte o apagou."""
        import gate_cli
        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(gate_cli.run("echo 'teste X quebrou'; exit 3", self.root, name="e2e"), 3)
            self.assertEqual(gate_cli.run("echo tudo certo", self.root, name="build"), 0)
        import evidence_cli
        kept = os.path.join(evidence_cli.folder(self.root), "gate-e2e.log")
        self.assertIn("teste X quebrou", open(kept).read(), "o log do e2e continua lá depois de outro portão rodar")
        self.assertIn("saída inteira: .harness-run/evidence/", out.getvalue())
        from tests.helpers import git
        self.assertNotIn(".harness-run", git(self.repo, "status", "--porcelain"), "o log fica fora do Git")

    def test_listing_evidence_works_on_a_read_only_disk(self):
        """O revisor Codex roda num sandbox somente leitura: listar a prova não pode falhar nem virar motivo de reprovação."""
        import stat
        os.chmod(self.root, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
        self.addCleanup(os.chmod, self.root, 0o755)
        out = self.cli("evidence")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("nenhuma prova gravada", out.stdout)


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

    def test_a_full_session_orchestrator_follows_the_executor_rules_too(self):
        """O orquestrador aberto pelo Orca é a sessão principal (sem tipo de agente): mesmas regras de executor."""
        job = {"subagent_type": "general-purpose", "prompt": "Implemente docs/specs/pedido/issues/01-soma.md",
               "run_in_background": True}
        out = json.loads(self.hook("guard.py", {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                                                "tool_input": job}).stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("worktree", out["permissionDecisionReason"])
        out = json.loads(self.hook("guard.py", {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                                                "tool_input": dict(job, isolation="worktree")}).stdout)["hookSpecificOutput"]
        self.assertIn("handoff-01-soma.md", out["updatedInput"]["prompt"], "o protocolo do executor entra igual")
        self.assertIn("docs/specs/pedido/issues/01-soma.md", tasks._in_flight(self.root))

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
