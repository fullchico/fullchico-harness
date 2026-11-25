"""`fullchico-harness cost`: quanto a entrega da branch custou, lido das transcrições e do livro.

Só lê. Conta cada mensagem uma vez, separa sessão principal de subagente, mede tempo ativo e paradas,
e deixa de fora a sessão que não tocou a janela da branch.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import unittest
from unittest import mock

from tests.helpers import ROOT, _tmpdir, commit_file, git, make_repo

PLUGIN = ROOT / "plugins/tr"
sys.path.insert(0, str(PLUGIN / "scripts"))
import cost_report  # noqa: E402
import ledger  # noqa: E402

UTC = datetime.timezone.utc


def iso(dt):
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def assistant_msg(t, mid, model="claude-opus-5-5", entry=1000, writing=0, reading=0, render=100):
    return {"type": "assistant", "timestamp": iso(t), "message": {
        "id": mid, "model": model, "usage": {"input_tokens": entry, "cache_creation_input_tokens": writing,
                                             "cache_read_input_tokens": reading, "output_tokens": render}}}


class TestCost(unittest.TestCase):
    def setUp(self):
        self.home = _tmpdir()
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        self.repo = make_repo()
        git(self.repo, "checkout", "-q", "-b", "feat")
        self.first = commit_file(self.repo, "a.py", "feat: a")
        out = subprocess.run(["git", "show", "-s", "--format=%cI", self.first], cwd=self.repo,
                             capture_output=True, text=True).stdout.strip()
        self.t0 = datetime.datetime.fromisoformat(out)
        slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(self.repo))
        self.folder = self.home / ".claude/projects" / slug
        self.folder.mkdir(parents=True)

    def transcript(self, name, rows):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def test_counts_each_message_once_prices_it_and_splits_main_from_subagents(self):
        m = datetime.timedelta(minutes=1)
        self.transcript("s1.jsonl", [
            {"type": "user", "timestamp": iso(self.t0)},
            assistant_msg(self.t0 + m, "msg_a", entry=1_000_000, render=0),
            assistant_msg(self.t0 + m, "msg_a", entry=1_000_000, render=0),  # o mesmo id em outra linha
            assistant_msg(self.t0 + 22 * m, "msg_b", entry=0, render=1_000_000),  # depois de 21 min parado
        ])
        self.transcript("s1/subagents/agent-x.jsonl", [
            assistant_msg(self.t0 + 23 * m, "msg_c", model="claude-sonnet-5-5", entry=1_000_000, render=0)])
        now_ts = self.t0 + 30 * m
        r = cost_report.measure(str(self.repo), now_ts=now_ts)
        opus = r["models"]["claude-opus-5-5"]
        self.assertEqual((opus["input"], opus["output"], opus["messages"]), (1_000_000, 1_000_000, 2))
        self.assertAlmostEqual(opus["usd"], 4.00 + 20.00)
        self.assertEqual(r["usd_by_role"], {"main": 24.0, "subagents": 2.0})
        self.assertEqual(r["usd"], 26.0)
        self.assertEqual(r["sessions"], 1)
        self.assertEqual(r["wall_min"], 23)
        self.assertEqual(r["active_min"], 2)
        self.assertEqual([p["minutes"] for p in r["pauses"]], [21])

    def test_a_session_that_did_not_touch_the_branch_is_left_out(self):
        before_ts = self.t0 - datetime.timedelta(days=2)
        self.transcript("velha.jsonl", [assistant_msg(before_ts, "msg_v", entry=5_000_000)])
        self.transcript("nova.jsonl", [assistant_msg(self.t0, "msg_n", entry=1_000_000, render=0)])
        r = cost_report.measure(str(self.repo), now_ts=self.t0 + datetime.timedelta(minutes=5))
        self.assertEqual(r["models"]["claude-opus-5-5"]["input"], 1_000_000)
        self.assertEqual(r["sessions"], 1)

    def test_unknown_models_are_listed_and_left_out_of_the_total(self):
        self.transcript("s.jsonl", [assistant_msg(self.t0, "m1", model="claude-novo-9", entry=1_000_000)])
        r = cost_report.measure(str(self.repo), now_ts=self.t0 + datetime.timedelta(minutes=1))
        self.assertEqual(r["unpriced"], ["claude-novo-9"])
        self.assertEqual(r["usd"], 0)

    def test_the_ledger_events_in_the_window_are_counted(self):
        self.transcript("s.jsonl", [assistant_msg(self.t0, "m1")])
        ledger.log(str(self.repo), "tr", "blocked", "envio")
        ledger.log(str(self.repo), "tr", "signed", "quality")
        r = cost_report.measure(str(self.repo), now_ts=datetime.datetime.now(UTC) + datetime.timedelta(minutes=1))
        self.assertEqual(r["gates"], {"blocked": 1, "signed": 1})

    def test_the_cli_prints_the_report_and_json(self):
        self.transcript("s.jsonl", [assistant_msg(self.t0, "m1", entry=1_000_000, render=0)])
        env = dict(os.environ, HOME=str(self.home))
        out = subprocess.run(["node", str(ROOT / "bin/harness.js"), "cost", str(self.repo)],
                             capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Custo da entrega — branch feat", out.stdout)
        self.assertIn("claude-opus-5-5", out.stdout)
        data = json.loads(subprocess.run(["node", str(ROOT / "bin/harness.js"), "cost", str(self.repo), "--json"],
                                         capture_output=True, text=True, env=env).stdout)
        self.assertEqual(data["usd"], 4.0)

    def test_since_accepts_date_and_time_and_rejects_garbage(self):
        self.transcript("s.jsonl", [assistant_msg(self.t0 - datetime.timedelta(hours=1), "m1", entry=1_000_000, render=0)])
        since = (self.t0 - datetime.timedelta(hours=2)).astimezone().strftime("%Y-%m-%dT%H:%M")
        r = cost_report.measure(str(self.repo), since=since, now_ts=self.t0)
        self.assertEqual(r["usd"], 4.0)
        with self.assertRaises(SystemExit):
            cost_report.measure(str(self.repo), since="nada-disso")


if __name__ == "__main__":
    unittest.main()
