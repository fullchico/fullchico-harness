"""`fullchico-harness custo`: quanto a entrega da branch custou, lido das transcrições e do livro.

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
import custo  # noqa: E402
import ledger  # noqa: E402

UTC = datetime.timezone.utc


def iso(dt):
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def assistente(t, mid, model="claude-opus-5-5", entrada=1000, escrita=0, leitura=0, saida=100):
    return {"type": "assistant", "timestamp": iso(t), "message": {
        "id": mid, "model": model, "usage": {"input_tokens": entrada, "cache_creation_input_tokens": escrita,
                                             "cache_read_input_tokens": leitura, "output_tokens": saida}}}


class TestCusto(unittest.TestCase):
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
            assistente(self.t0 + m, "msg_a", entrada=1_000_000, saida=0),
            assistente(self.t0 + m, "msg_a", entrada=1_000_000, saida=0),  # o mesmo id em outra linha
            assistente(self.t0 + 22 * m, "msg_b", entrada=0, saida=1_000_000),  # depois de 21 min parado
        ])
        self.transcript("s1/subagents/agent-x.jsonl", [
            assistente(self.t0 + 23 * m, "msg_c", model="claude-sonnet-5-5", entrada=1_000_000, saida=0)])
        agora = self.t0 + 30 * m
        r = custo.medir(str(self.repo), agora=agora)
        opus = r["modelos"]["claude-opus-5-5"]
        self.assertEqual((opus["entrada"], opus["saida"], opus["mensagens"]), (1_000_000, 1_000_000, 2))
        self.assertAlmostEqual(opus["usd"], 4.00 + 20.00)
        self.assertEqual(r["usd_por_papel"], {"principal": 24.0, "subagentes": 2.0})
        self.assertEqual(r["usd"], 26.0)
        self.assertEqual(r["sessoes"], 1)
        self.assertEqual(r["parede_min"], 23)
        self.assertEqual(r["ativo_min"], 2)
        self.assertEqual([p["minutos"] for p in r["paradas"]], [21])

    def test_a_session_that_did_not_touch_the_branch_is_left_out(self):
        antes = self.t0 - datetime.timedelta(days=2)
        self.transcript("velha.jsonl", [assistente(antes, "msg_v", entrada=5_000_000)])
        self.transcript("nova.jsonl", [assistente(self.t0, "msg_n", entrada=1_000_000, saida=0)])
        r = custo.medir(str(self.repo), agora=self.t0 + datetime.timedelta(minutes=5))
        self.assertEqual(r["modelos"]["claude-opus-5-5"]["entrada"], 1_000_000)
        self.assertEqual(r["sessoes"], 1)

    def test_unknown_models_are_listed_and_left_out_of_the_total(self):
        self.transcript("s.jsonl", [assistente(self.t0, "m1", model="claude-novo-9", entrada=1_000_000)])
        r = custo.medir(str(self.repo), agora=self.t0 + datetime.timedelta(minutes=1))
        self.assertEqual(r["sem_preco"], ["claude-novo-9"])
        self.assertEqual(r["usd"], 0)

    def test_the_ledger_events_in_the_window_are_counted(self):
        self.transcript("s.jsonl", [assistente(self.t0, "m1")])
        ledger.log(str(self.repo), "trilho", "barrou", "envio")
        ledger.log(str(self.repo), "trilho", "assinou", "qualidade")
        r = custo.medir(str(self.repo), agora=datetime.datetime.now(UTC) + datetime.timedelta(minutes=1))
        self.assertEqual(r["portoes"], {"barrou": 1, "assinou": 1})

    def test_the_cli_prints_the_report_and_json(self):
        self.transcript("s.jsonl", [assistente(self.t0, "m1", entrada=1_000_000, saida=0)])
        env = dict(os.environ, HOME=str(self.home))
        out = subprocess.run(["node", str(ROOT / "bin/harness.js"), "custo", str(self.repo)],
                             capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Custo da entrega — branch feat", out.stdout)
        self.assertIn("claude-opus-5-5", out.stdout)
        data = json.loads(subprocess.run(["node", str(ROOT / "bin/harness.js"), "custo", str(self.repo), "--json"],
                                         capture_output=True, text=True, env=env).stdout)
        self.assertEqual(data["usd"], 4.0)

    def test_desde_accepts_date_and_time_and_rejects_garbage(self):
        self.transcript("s.jsonl", [assistente(self.t0 - datetime.timedelta(hours=1), "m1", entrada=1_000_000, saida=0)])
        desde = (self.t0 - datetime.timedelta(hours=2)).astimezone().strftime("%Y-%m-%dT%H:%M")
        r = custo.medir(str(self.repo), desde=desde, agora=self.t0)
        self.assertEqual(r["usd"], 4.0)
        with self.assertRaises(SystemExit):
            custo.medir(str(self.repo), desde="nada-disso")


if __name__ == "__main__":
    unittest.main()
