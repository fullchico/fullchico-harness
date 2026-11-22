"""Um orquestrador por onda.

Um orquestrador só para a entrega inteira carregava o contexto de todos os tickets e era o ponto
único de queda. Agora cada um conduz uma onda e encerra; o próximo começa limpo e lê o estado no
repositório. "Só mais uma onda" não fica por conta do texto: o harness nega o segundo lote.
"""
import unittest

from tests.helpers import ROOT, commit_all, git, make_repo, run_hook, sync


def claim(repo, numbers, agent_id="orq-1", agent="harness:orquestrador", command=None):
    payload = {"tool_name": "Bash", "cwd": str(repo), "session_id": "s1",
               "tool_input": {"command": command or f".harness/ticket claim docs/specs/x {numbers}"}}
    if agent:
        payload.update(agent_type=agent, agent_id=agent_id)
    return run_hook("service_guard.py", payload)


class TestWaves(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        issues = self.repo / "docs/specs/x/issues"
        issues.mkdir(parents=True)
        for number in ("01", "02", "03", "04"):
            (issues / f"{number}-t.md").write_text(f"# t\n\nStatus: open\nBlocked by:\nOwns: src/t{number}\n")
        (self.repo / "docs/specs/x/spec.md").write_text("spec\n")
        commit_all(self.repo, "docs: add spec and tickets")

    def test_an_orchestrator_takes_one_batch_of_new_tickets(self):
        self.assertEqual(claim(self.repo, "01 02")[0], 0)
        rc, _, err = claim(self.repo, "03")
        self.assertEqual(rc, 2)
        self.assertIn("ENTREGA: CONTINUA", err)
        self.assertIn("01", err)
        # pegar de novo os mesmos, numa rodada de correção, é a mesma onda
        self.assertEqual(claim(self.repo, "02")[0], 0)
        self.assertEqual(claim(self.repo, "01 02")[0], 0)
        self.assertEqual(claim(self.repo, "01 03")[0], 2, "um lote que mistura ticket novo é onda nova")

    def test_the_next_orchestrator_starts_clean(self):
        self.assertEqual(claim(self.repo, "01 02")[0], 0)
        self.assertEqual(claim(self.repo, "03 04", agent_id="orq-2")[0], 0)

    def test_the_form_agents_really_type_is_read(self):
        chained = 'D=docs/specs/x && .harness/ticket reopen $D 01 "x" && .harness/ticket claim $D 01'
        self.assertEqual(claim(self.repo, None, command=chained)[0], 0)
        self.assertEqual(claim(self.repo, None, command="D=docs/specs/x; .harness/ticket claim $D 03 04")[0], 2)

    def test_a_reopened_ticket_can_always_be_taken_again(self):
        # No fechamento, o orquestrador reabre tickets já concluídos para corrigir pendências, em mais de um lote.
        (self.repo / "docs/specs/x/issues/04-t.md").write_text("# t\n\nStatus: open\nBlocked by:\nOwns: src/t04\n\n")
        commit_all(self.repo, "chore(tickets): reopen 04")
        self.assertEqual(claim(self.repo, "01")[0], 0)
        self.assertEqual(claim(self.repo, "04")[0], 0)

    def test_only_the_orchestrator_is_bound(self):
        self.assertEqual(claim(self.repo, "01", agent=None)[0], 0)
        self.assertEqual(claim(self.repo, "02", agent=None)[0], 0)

    def test_texts_carry_the_protocol(self):
        agent = (ROOT / "plugin/agents/orquestrador.md").read_text()
        for line in ("ENTREGA: CONTINUA", "ENTREGA: CONCLUIDA", "ENTREGA: PARADA", "uma onda", ".harness/resume"):
            self.assertIn(line, agent, line)
        skill = (ROOT / "plugin/skills/entregar/SKILL.md").read_text()
        for line in ("ENTREGA: CONTINUA", "ENTREGA: CONCLUIDA", "dispare de novo"):
            self.assertIn(line, skill, line)
        self.assertEqual(skill.count("**PARADA"), 2)


if __name__ == "__main__":
    unittest.main()
