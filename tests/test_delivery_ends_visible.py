"""A entrega mostra o que fez: o ambiente e a tela são exercitados cedo, e o app fica de pé no fim."""
import unittest

# ver também: o aplicativo fica de pé durante a entrega (test_the_owner_watches_the_app_change)

from tests.helpers import ROOT

RUN = ROOT / "plugin/payload/entrega"


class TestDeliveryEndsVisible(unittest.TestCase):
    def test_environment_is_proven_right_after_the_base_ticket(self):
        text = (RUN / "despacho.md").read_text()
        section = text[text.index("**A base prova que roda.**"):]
        for step in (".harness/up", ".harness/prepare", ".harness/dev --background", ".harness/down"):
            self.assertIn(step, section[:1400], step)
        self.assertIn("não conta como reprovação", section[:1400])

    def test_browser_tests_start_with_the_first_screen(self):
        tickets = (RUN / "tickets.md").read_text()
        self.assertIn("teste de fumaça", tickets)
        self.assertIn("cada ticket de tela", tickets)
        dispatch = (RUN / "despacho.md").read_text()
        self.assertIn(".harness/validate --profile merge", dispatch)

    def test_delivery_ends_with_the_app_running_and_the_link(self):
        text = (RUN / "fechamento.md").read_text()
        last = text[text.index("## 7."):]
        self.assertIn(".harness/dev --background", last)
        self.assertIn("responde", last)
        self.assertNotIn("Não deixe o aplicativo rodando", text)
        self.assertNotIn("Depois do envio, `.harness/down`", text)
        agent = (ROOT / "plugin/agents/orquestrador.md").read_text()
        self.assertIn("o endereço do aplicativo, que você deixou de pé", agent)
