"""Limite por portão final e aprovação humana do estado validado."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import ROOT
import sys
sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
import attempts  # noqa: E402
import ledger  # noqa: E402
import orchestrator_stop  # noqa: E402
import portoes  # noqa: E402
import registry  # noqa: E402


class GateAttemptsTest(unittest.TestCase):
    def test_fourth_rejection_requires_owner_and_limit_can_increase(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as home:
            root = Path(project)
            (root / ".claude").mkdir()
            (root / ".claude/demanda-atual").write_text("pedido")
            gate = {"momento": "fim", "assina": "comando", "comando": "true", "tentativas": 5}
            (root / ".claude/trilho.json").write_text(json.dumps({"portoes": {"qualidade": gate}}))
            with mock.patch.dict(os.environ, {"HOME": home}, clear=False):
                reg = registry.load(project)
                key = registry.stamp_key(project, gate)
                ledger.sign(project, "qualidade", key, "tr", "1", "fiscal", "ok")
                for _ in range(5):
                    state = attempts.reject(project, "qualidade", gate)
                    self.assertFalse(state["intervencao"])
                self.assertTrue(registry.satisfied(project, "qualidade", reg))
                state = attempts.reject(project, "qualidade", gate)
                self.assertEqual(state["reprovacoes"], 6)
                self.assertTrue(state["intervencao"])
                self.assertFalse(registry.satisfied(project, "qualidade", reg))
                with mock.patch.dict(os.environ, {"CLAUDECODE": "", "CODEX_THREAD_ID": ""}):
                    self.assertEqual(portoes.aprovar(project, "qualidade"), 0)
                self.assertTrue(registry.satisfied(project, "qualidade", reg))
                (root / "code.py").write_text("x = 1\n")
                self.assertFalse(registry.satisfied(project, "qualidade", reg))

    def test_default_three_and_duplicate_verdict(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as home:
            gate = {"momento": "fim", "assina": "agente", "agente": "revisor"}
            with mock.patch.dict(os.environ, {"HOME": home}, clear=False):
                for i in range(3):
                    self.assertFalse(attempts.reject(project, "bugs", gate, f"veredito-{i}")["intervencao"])
                self.assertEqual(attempts.reject(project, "bugs", gate, "veredito-2")["reprovacoes"], 3)
                self.assertTrue(attempts.reject(project, "bugs", gate, "veredito-3")["intervencao"])
                self.assertEqual(attempts.status(project, "bugs")["reprovacoes"], 4)

    def test_invalid_limit_rejected(self):
        for value in (-1, True, "5"):
            with self.assertRaises(registry.RegistryError):
                registry._validate("quality", {"momento": "fim", "assina": "comando", "comando": "true", "tentativas": value})

    def test_orchestrator_hands_off_escalated_final_gate(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as home:
            root = Path(project)
            (root / ".claude").mkdir()
            (root / ".claude/demanda-atual").write_text("pedido")
            gate = {"momento": "fim", "assina": "comando", "comando": "true", "tentativas": 0}
            (root / ".claude/trilho.json").write_text(json.dumps({"portoes": {"qualidade": gate}}))
            payload = {"agent_type": "tr-orquestrador", "cwd": project, "last_assistant_message": ""}
            with mock.patch.dict(os.environ, {"HOME": home}, clear=False):
                self.assertIsNotNone(orchestrator_stop.decision(payload))
                attempts.reject(project, "qualidade", gate)
                self.assertIn("intervenção humana", orchestrator_stop.decision(payload)["reason"])
                payload["last_assistant_message"] = "BLOQUEIO: limite\nTENTATIVAS: uma\nDECISÃO NECESSÁRIA: revisar"
                self.assertIsNone(orchestrator_stop.decision(payload))
