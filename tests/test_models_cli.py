import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tests.helpers import ROOT, make_repo
sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
import ledger
import registry


class ModelsCliTest(unittest.TestCase):
    def run_cli(self, repo, *args, env=None):
        return subprocess.run([sys.executable, "-I", str(ROOT / "plugins/tr/scripts/models_cli.py"), *args],
                              cwd=repo, capture_output=True, text=True, env=env)

    def test_configure_and_show_keeps_other_registry_data_and_displays_mirror(self):
        repo = make_repo()
        (repo / ".claude").mkdir()
        path = repo / ".claude/harness.json"
        path.write_text(json.dumps({"code": ["src"], "gates": {"q": {"stage": "end",
                                                                           "signs": "command", "command": "true"}}}))
        result = self.run_cli(repo, "configure", "planning", "claude:opus", "review", "codex:sol")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(path.read_text())
        self.assertEqual(data["code"], ["src"])
        self.assertEqual(data["models"]["planning"], {"cli": "claude", "model": "opus"})
        shown = self.run_cli(repo, "show")
        self.assertIn("espelho codex:sol", shown.stdout)
        self.assertIn("review: codex:sol", shown.stdout)

    def test_bad_role_is_rejected(self):
        repo = make_repo()
        result = self.run_cli(repo, "configure", "writer", "claude:opus")
        self.assertEqual(result.returncode, 2)
        self.assertFalse((repo / ".claude/harness.json").exists())

    def test_gate_reviewer_model_is_configured_separately(self):
        repo = make_repo()
        (repo / ".claude").mkdir()
        path = repo / ".claude/harness.json"
        path.write_text(json.dumps({"gates": {"design-review": {"stage": "end", "signs": "agent",
                                                               "agent": "design-revisor"}}}))
        result = self.run_cli(repo, "configure", "review", "claude:sonnet",
                              "gate:design-review", "claude:opus")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(path.read_text())
        self.assertEqual(data["models"]["gates"]["design-review"], {"cli": "claude", "model": "opus"})
        self.assertIn("gate:design-review: claude:opus", self.run_cli(repo, "show").stdout)
        blocked = self.run_cli(repo, "configure", "review", "claude:haiku",
                               env=dict(os.environ, CLAUDECODE="1"))
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("Sem permissão", blocked.stderr)
        self.assertEqual(json.loads(path.read_text()), data)

    def test_codex_gate_reviewer_uses_own_model_and_stamps_only_matching_snapshot(self):
        repo = make_repo()
        (repo / ".claude").mkdir()
        (repo / ".claude/harness.json").write_text(json.dumps({"gates": {
            "security": {"stage": "end", "signs": "agent", "agent": "seguranca-revisor"}}}))
        agent = repo / ".codex/agents/seguranca-revisor.toml"
        agent.parent.mkdir(parents=True)
        agent.write_text('developer_instructions = "Procure falhas concretas de segurança."\n')
        self.assertEqual(self.run_cli(repo, "configure", "review", "claude:sonnet",
                                      "gate:security", "codex:sol").returncode, 0)
        listed = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/gate_cli.py")],
                                cwd=repo, capture_output=True, text=True)
        self.assertIn("models validate-gate security", listed.stdout)
        snapshot = ledger.head(str(repo))
        with tempfile.TemporaryDirectory() as bin_dir:
            fake = pathlib.Path(bin_dir) / "codex"
            fake.write_text("#!/bin/sh\n" +
                            "approved=no\n" +
                            "while [ \"$#\" -gt 0 ]; do\n" +
                            "  if [ \"$1\" = --approve-for-me ]; then approved=yes; fi\n" +
                            "  if [ \"$1\" = -o ]; then shift; output=$1; fi\n" +
                            "  shift\n" +
                            "done\n" +
                            "[ \"$approved\" = yes ] || exit 9\n" +
                            "cat >/dev/null\n" +
                            f"printf 'VERDICT: APPROVED\\nCOMMIT: {snapshot}\\nSUMMARY: sem falhas\\n' > \"$output\"\n")
            fake.chmod(0o755)
            env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""), HOME=bin_dir)
            result = self.run_cli(repo, "validate-gate", "security", "--prompt", "Ticket concluído", env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["model"], "codex:sol")
            self.assertTrue(summary["stamped"])
            key = registry.stamp_key(str(repo), registry.load(str(repo))["gates"]["security"])
            with mock.patch.dict(os.environ, HOME=bin_dir):
                self.assertTrue(ledger.has(str(repo), "security", key))
            manifest = json.loads(pathlib.Path(summary["manifesto"]).read_text())
            self.assertIn("Procure falhas concretas", pathlib.Path(summary["manifesto"]).with_name("pedido.txt").read_text())
            self.assertEqual(manifest["attempts"][0]["model_id"], "gpt-6.2-sol")

    def test_gate_reviewer_rejects_wrong_snapshot(self):
        repo = make_repo()
        (repo / ".claude").mkdir()
        (repo / ".claude/harness.json").write_text(json.dumps({"gates": {
            "bugs": {"stage": "end", "signs": "agent", "agent": "tr:bug-hunter"}}}))
        self.assertEqual(self.run_cli(repo, "configure", "gate:bugs", "claude:opus").returncode, 0)
        with tempfile.TemporaryDirectory() as bin_dir:
            fake = pathlib.Path(bin_dir) / "claude"
            fake.write_text("#!/bin/sh\n" +
                            "printf '%s\\n' '{\"result\":\"VERDICT: APPROVED\\\\nCOMMIT: 0000000000000000000000000000000000000000\\\\nSUMMARY: sem falhas\"}'\n")
            fake.chmod(0o755)
            env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""))
            result = self.run_cli(repo, "validate-gate", "bugs", env=env)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(json.loads(result.stdout)["stamped"])

    def test_claude_gate_reviewer_uses_registered_agent(self):
        repo = make_repo()
        (repo / ".claude").mkdir()
        (repo / ".claude/harness.json").write_text(json.dumps({"gates": {
            "security": {"stage": "end", "signs": "agent", "agent": "seguranca-revisor"}}}))
        self.assertEqual(self.run_cli(repo, "configure", "gate:security", "claude:sonnet").returncode, 0)
        snapshot = ledger.head(str(repo))
        with tempfile.TemporaryDirectory() as bin_dir:
            fake = pathlib.Path(bin_dir) / "claude"
            fake.write_text("#!/usr/bin/env python3\nimport json, sys\n" +
                            f"assert '--agent' in sys.argv and sys.argv[sys.argv.index('--agent') + 1] == 'seguranca-revisor'\n" +
                            "sys.stdin.read()\n" +
                            f"print(json.dumps({{'result': 'VERDICT: APPROVED\\nCOMMIT: {snapshot}\\nSUMMARY: sem falhas'}}))\n")
            fake.chmod(0o755)
            env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""), HOME=bin_dir,
                       CLAUDECODE="1")
            result = self.run_cli(repo, "validate-gate", "security", env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["stamped"])

    def test_invalid_registry_is_preserved(self):
        repo = make_repo()
        (repo / ".claude").mkdir()
        path = repo / ".claude/harness.json"
        path.write_text("{invalid")
        result = self.run_cli(repo, "configure", "execution", "codex:luna")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_text(), "{invalid")

    def test_execute_records_real_cli_and_falls_back_on_limit(self):
        repo = make_repo()
        self.assertEqual(self.run_cli(repo, "configure", "planning", "claude:opus").returncode, 0)
        with tempfile.TemporaryDirectory() as bin_dir:
            for name, script in {
                "claude": "#!/bin/sh\necho 'rate limit reached' >&2\nexit 1\n",
                "codex": "#!/bin/sh\necho '{\"type\":\"turn.completed\"}'\n",
            }.items():
                path = pathlib.Path(bin_dir) / name
                path.write_text(script)
                path.chmod(0o755)
            env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""))
            result = self.run_cli(repo, "run", "planning", "--prompt", "Planeje a soma", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["models"], ["opus", "gpt-6.2-sol"])
        manifest = json.loads(pathlib.Path(summary["manifesto"]).read_text())
        self.assertEqual([item["cli"] for item in manifest["attempts"]], ["claude", "codex"])
        self.assertIn("harness-runs", summary["manifesto"])
        self.assertFalse((repo / "harness-runs").exists())

    def test_codex_executor_keeps_auto_review_and_requests_targeted_escalation(self):
        repo = make_repo()
        self.assertEqual(self.run_cli(repo, "configure", "execution", "codex:luna").returncode, 0)
        with tempfile.TemporaryDirectory() as bin_dir:
            fake = pathlib.Path(bin_dir) / "codex"
            fake.write_text("#!/bin/sh\n" +
                            "case \" $* \" in *' --sandbox workspace-write '*);; *) exit 7;; esac\n" +
                            "case \" $* \" in *' --approve-for-me '*);; *) exit 8;; esac\n" +
                            "cat > prompt.txt\n" +
                            "grep -q 'request escalation' prompt.txt || exit 9\n" +
                            "touch \"$FULLCHICO_RUN_DIR/hooks-alive\"\n" +
                            "echo '{\"type\":\"turn.completed\"}'\n")
            fake.chmod(0o755)
            env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""))
            result = self.run_cli(repo, "run", "execution", "--prompt", "Suba a infra com Docker", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_codex_executor_without_project_hooks_is_refused(self):
        # Hook de projeto não confiado não roda no `codex exec` e nada avisa: o executor ficaria sem trilho.
        repo = make_repo()
        self.assertEqual(self.run_cli(repo, "configure", "execution", "codex:luna").returncode, 0)
        with tempfile.TemporaryDirectory() as bin_dir:
            fake = pathlib.Path(bin_dir) / "codex"
            fake.write_text("#!/bin/sh\ncat > /dev/null\necho '{\"type\":\"turn.completed\"}'\n")
            fake.chmod(0o755)
            env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""))
            result = self.run_cli(repo, "run", "execution", "--prompt", "Some", env=env)
        self.assertEqual(result.returncode, 1)
        manifest = json.loads(pathlib.Path(json.loads(result.stdout)["manifesto"]).read_text())
        self.assertEqual(manifest["attempts"][0]["code"], 125)
        self.assertIn("hooks do tr não rodaram", pathlib.Path(manifest["attempts"][0]["erros"]).read_text())

    def test_detached_run_returns_at_once_and_wait_reports_the_result(self):
        # O Bash do agente tem limite de minutos: o executor longo roda à parte e é consultado por `wait`.
        repo = make_repo()
        self.assertEqual(self.run_cli(repo, "configure", "execution", "claude:sonnet").returncode, 0)
        with tempfile.TemporaryDirectory() as bin_dir:
            fake = pathlib.Path(bin_dir) / "claude"
            fake.write_text("#!/bin/sh\nsleep 2\necho '{\"result\":\"feito\"}'\n")
            fake.chmod(0o755)
            env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""))
            started = self.run_cli(repo, "run", "execution", "--prompt", "Some", "--detach", env=env)
            self.assertEqual(started.returncode, 0, started.stderr)
            run_id = json.loads(started.stdout)["id"]
            pending = self.run_cli(repo, "wait", run_id, "--timeout", "0", env=env)
            self.assertEqual((pending.returncode, json.loads(pending.stdout)["status"]), (3, "running"))
            done = self.run_cli(repo, "wait", run_id, "--timeout", "30", env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["id"], run_id)
        self.assertEqual(self.run_cli(repo, "wait", "../fora").returncode, 2)


if __name__ == "__main__":
    unittest.main()
