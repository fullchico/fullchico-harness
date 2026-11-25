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
import gates_cli  # noqa: E402
import registry  # noqa: E402


class GateAttemptsTest(unittest.TestCase):
    def test_fourth_rejection_requires_owner_and_limit_can_increase(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as home:
            root = Path(project)
            (root / ".claude").mkdir()
            (root / ".claude/current-demand").write_text("pedido")
            gate = {"stage": "end", "signs": "command", "command": "true", "attempts": 5}
            (root / ".claude/harness.json").write_text(json.dumps({"gates": {"quality": gate}}))
            with mock.patch.dict(os.environ, {"HOME": home}, clear=False):
                reg = registry.load(project)
                key = registry.stamp_key(project, gate)
                ledger.sign(project, "quality", key, "tr", "1", "fiscal", "ok")
                for _ in range(5):
                    state = attempts.reject(project, "quality", gate)
                    self.assertFalse(state["intervention"])
                self.assertTrue(registry.satisfied(project, "quality", reg))
                state = attempts.reject(project, "quality", gate)
                self.assertEqual(state["rejections"], 6)
                self.assertTrue(state["intervention"])
                self.assertFalse(registry.satisfied(project, "quality", reg))
                with mock.patch.dict(os.environ, {"CLAUDECODE": "", "CODEX_THREAD_ID": ""}):
                    self.assertEqual(gates_cli.approve(project, "quality"), 0)
                self.assertTrue(registry.satisfied(project, "quality", reg))
                (root / "code.py").write_text("x = 1\n")
                self.assertFalse(registry.satisfied(project, "quality", reg))

    def test_default_three_and_duplicate_verdict(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as home:
            gate = {"stage": "end", "signs": "agent", "agent": "revisor"}
            with mock.patch.dict(os.environ, {"HOME": home}, clear=False):
                for i in range(3):
                    self.assertFalse(attempts.reject(project, "bugs", gate, f"veredito-{i}")["intervention"])
                self.assertEqual(attempts.reject(project, "bugs", gate, "veredito-2")["rejections"], 3)
                self.assertTrue(attempts.reject(project, "bugs", gate, "veredito-3")["intervention"])
                self.assertEqual(attempts.status(project, "bugs")["rejections"], 4)

    def test_invalid_limit_rejected(self):
        for value in (-1, True, "5"):
            with self.assertRaises(registry.RegistryError):
                registry._validate("quality", {"stage": "end", "signs": "command", "command": "true", "attempts": value})

    def test_orchestrator_hands_off_escalated_final_gate(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as home:
            root = Path(project)
            (root / ".claude").mkdir()
            (root / ".claude/current-demand").write_text("pedido")
            gate = {"stage": "end", "signs": "command", "command": "true", "attempts": 0}
            (root / ".claude/harness.json").write_text(json.dumps({"gates": {"quality": gate}}))
            payload = {"agent_type": "tr-orchestrator", "cwd": project, "last_assistant_message": ""}
            with mock.patch.dict(os.environ, {"HOME": home}, clear=False):
                self.assertIsNotNone(orchestrator_stop.decision(payload))
                attempts.reject(project, "quality", gate)
                self.assertIn("human intervention", orchestrator_stop.decision(payload)["reason"])
                payload["last_assistant_message"] = "BLOCKER: limit\nATTEMPTS: one\nDECISION NEEDED: review"
                self.assertIsNone(orchestrator_stop.decision(payload))

    def test_orchestrator_is_released_after_retries_without_progress(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as home:
            root = Path(project)
            (root / ".claude").mkdir()
            (root / ".claude/current-demand").write_text("pedido")
            gate = {"stage": "end", "signs": "command", "command": "true"}
            (root / ".claude/harness.json").write_text(json.dumps({"gates": {"quality": gate}}))
            payload = {"agent_type": "tr:orchestrator", "cwd": project, "last_assistant_message": ""}
            with mock.patch.dict(os.environ, {"HOME": home}, clear=False):
                self.assertIsNotNone(orchestrator_stop.decision(payload), "a primeira parada é barrada")
                payload["stop_hook_active"] = True
                for _ in range(orchestrator_stop.NO_PROGRESS_LIMIT - 1):
                    self.assertIsNotNone(orchestrator_stop.decision(payload))
                self.assertIsNone(orchestrator_stop.decision(payload), "sem progresso, o hook solta")
                payload["stop_hook_active"] = False
                self.assertIsNotNone(orchestrator_stop.decision(payload), "uma parada nova recomeça a conta")
