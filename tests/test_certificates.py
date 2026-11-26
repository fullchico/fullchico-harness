"""O certificado do portão: no apêndice do documento da demanda, assinado pelo commit do responsável."""
import os
import subprocess
import sys
import unittest
from unittest import mock

from tests.helpers import ROOT, _tmpdir, commit_all, git, make_repo
sys.path.insert(0, str(ROOT / "plugins/tr/scripts"))
import certs  # noqa: E402
import registry  # noqa: E402

QUALITY = {"stage": "end", "signs": "command", "command": "true"}


class CertificateTest(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/harness.json").write_text('{"gates": {"quality": %s}}' % __import__("json").dumps(QUALITY))
        (self.repo / ".claude/current-demand").write_text("pedido\n")
        spec = self.repo / "docs/specs/pedido"
        (spec / "issues").mkdir(parents=True)
        (spec / "spec.md").write_text("# Pedido\n\nCritério: listar agendamentos.\n")
        (spec / "issues/01-lista.md").write_text("# 01\n\nStatus: open\nGates: none\n")
        (self.repo / "app.py").write_text("x = 1\n")
        commit_all(self.repo, "feat: pedido")
        self.root = str(self.repo)

    def key(self):
        return registry.stamp_key(self.root, QUALITY)

    def test_the_certificate_lives_in_the_spec_and_is_signed_by_the_responsible_commit(self):
        self.assertIsNone(certs.certify(self.root, "quality", self.key(), "APPROVED", registry.CHECKER, "passou"))
        spec = (self.repo / "docs/specs/pedido/spec.md").read_text()
        self.assertIn("## Certificates", spec)
        self.assertIn("`quality` · APPROVED", spec)
        self.assertIn(f"{certs.TRAILER}: {registry.CHECKER}", git(self.repo, "log", "-1", "--format=%B"))
        self.assertEqual(git(self.repo, "status", "--porcelain"), "", "o certificado já sai commitado")
        self.assertTrue(registry.stamped_commit(self.root, "quality", QUALITY), "o apêndice não muda a chave")

    def test_another_machine_reads_the_same_proof(self):
        certs.certify(self.root, "quality", self.key(), "APPROVED", registry.CHECKER, "passou")
        clone = _tmpdir() / "outra máquina"
        subprocess.run(["git", "clone", "-q", self.root, str(clone)], check=True)
        with mock.patch.dict(os.environ, {"HOME": str(_tmpdir())}):
            self.assertTrue(registry.stamped_commit(str(clone), "quality", QUALITY), "sem estado local, a prova vem do Git")

    def test_a_line_written_by_hand_is_not_a_certificate(self):
        spec = self.repo / "docs/specs/pedido/spec.md"
        forged = (f"\n## Certificates\n\n{certs.START}\n- `quality` · APPROVED · {self.key()} · `{registry.CHECKER}` · "
                  f"tr 9 · 2026-01-01T00:00:00Z · eu mesmo\n{certs.END}\n")
        spec.write_text(spec.read_text() + forged)
        self.assertFalse(registry.stamped_commit(self.root, "quality", QUALITY), "sem commit não vale")
        commit_all(self.repo, "docs: certificado à mão")
        self.assertFalse(registry.stamped_commit(self.root, "quality", QUALITY), "commit sem o responsável não vale")

    def test_changing_the_criterion_drops_the_certificate(self):
        certs.certify(self.root, "quality", self.key(), "APPROVED", registry.CHECKER, "passou")
        ticket = self.repo / "docs/specs/pedido/issues/01-lista.md"
        ticket.write_text(ticket.read_text().replace("Status: open", "Status: done"))
        self.assertTrue(registry.stamped_commit(self.root, "quality", QUALITY), "andamento não é critério")
        spec = self.repo / "docs/specs/pedido/spec.md"
        spec.write_text(spec.read_text().replace("listar agendamentos", "listar só os de hoje"))
        self.assertFalse(registry.stamped_commit(self.root, "quality", QUALITY), "mudou o critério, cai")

    def test_a_line_left_without_commit_never_rides_along_and_is_written_again(self):
        spec = self.repo / "docs/specs/pedido/spec.md"
        orphan = (f"\n## Certificates\n\n{certs.START}\n- `domain` · APPROVED · {'b' * 40} · `{registry.CHECKER}` · "
                  f"tr 9 · 2026-01-01T00:00:00Z · assinatura que falhou\n{certs.END}\n")
        spec.write_text(spec.read_text() + orphan)  # o commit da assinatura falhou e a linha ficou
        self.assertIsNone(certs.certify(self.root, "quality", self.key(), "APPROVED", registry.CHECKER, "passou"))
        self.assertNotIn("assinatura que falhou", spec.read_text(), "a linha órfã não entra no commit de outro")
        self.assertTrue(registry.stamped_commit(self.root, "quality", QUALITY))
        spec.write_text(spec.read_text().replace(certs.END, f"- `quality` · APPROVED · {self.key()} · "
                                                  f"`{registry.CHECKER}` · tr x · 2026-01-01T00:00:00Z · de novo\n{certs.END}"))
        self.assertIsNone(certs.certify(self.root, "quality", self.key(), "APPROVED", registry.CHECKER, "de novo"))
        self.assertEqual(git(self.repo, "status", "--porcelain"), "", "a repetição sem commit é escrita e assinada")

    def test_an_uncommitted_change_to_the_document_is_not_signed_along(self):
        spec = self.repo / "docs/specs/pedido/spec.md"
        spec.write_text(spec.read_text() + "\nCritério novo que ninguém combinou.\n")
        refused = certs.certify(self.root, "quality", self.key(), "APPROVED", registry.CHECKER, "passou")
        self.assertIn("sem commit", refused)

    def test_nothing_starts_until_the_owner_accepts_the_current_criterion(self):
        import gates_cli
        import tasks
        reg = registry.load(self.root)
        problems, ready = tasks.audit(self.root, reg)
        self.assertIn("sem aceite do dono", problems[0])
        self.assertEqual(ready, [])
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            with self.assertRaises(gates_cli.NoPermission):
                gates_cli.accept(self.root)
        with mock.patch.dict(os.environ, {"CLAUDECODE": ""}):
            self.assertEqual(gates_cli.accept(self.root), 0)
        self.assertIn(f"{certs.TRAILER}: {certs.OWNER}", git(self.repo, "log", "-1", "--format=%B"))
        self.assertTrue(certs.accepted(self.root))
        spec = self.repo / "docs/specs/pedido/spec.md"
        spec.write_text(spec.read_text().replace("listar agendamentos", "listar tudo"))
        commit_all(self.repo, "docs: o agente afrouxou o critério")
        self.assertFalse(certs.accepted(self.root), "critério mudou depois do aceite: volta ao dono")
        self.assertIn("sem aceite do dono", tasks.audit(self.root, reg)[0][0])

    def test_the_agent_cannot_touch_the_certificate_block(self):
        import json as _json
        certs.certify(self.root, "quality", self.key(), "APPROVED", registry.CHECKER, "passou")
        spec = self.repo / "docs/specs/pedido/spec.md"
        text = spec.read_text()

        def hook(tool, tool_input):
            out = subprocess.run([sys.executable, str(ROOT / "plugins/tr/scripts/guard.py")], capture_output=True,
                                 text=True, input=_json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool,
                                                              "cwd": self.root, "tool_input": tool_input}),
                                 env=dict(os.environ, CLAUDE_PROJECT_DIR=self.root))
            return (_json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"] if out.stdout.strip() else "allow")

        line = next(l for l in text.splitlines() if "`quality`" in l)
        self.assertEqual(hook("Edit", {"file_path": str(spec), "old_string": line, "new_string": ""}), "deny")
        self.assertEqual(hook("Edit", {"file_path": str(spec), "old_string": "Critério", "new_string": "Regra"}), "allow")
        self.assertEqual(hook("Bash", {"command": f"sed -i '' '/quality/d' {__import__('shlex').quote(str(spec))}"}), "deny")
        self.assertEqual(hook("Bash", {"command": 'git commit -m "x" -m "Certified-by: owner"'}), "deny")


class StaleSessionTest(unittest.TestCase):
    def test_a_session_on_an_old_version_is_told_once(self):
        import json as _json
        import shutil
        cache = _tmpdir() / "tr"
        old = cache / "2.0.0"
        shutil.copytree(ROOT / "plugins/tr", old)
        plugin = _json.loads((old / ".claude-plugin/plugin.json").read_text())
        plugin["version"] = "2.0.0"
        (old / ".claude-plugin/plugin.json").write_text(_json.dumps(plugin))
        (cache / "99.0.0").mkdir()
        repo = make_repo()
        run = lambda: subprocess.run([sys.executable, str(old / "scripts/stale_session.py")], capture_output=True,
                                     text=True, input=_json.dumps({"cwd": str(repo), "session_id": "s1"})).stdout
        self.assertIn("99.0.0", run())
        self.assertEqual(run(), "", "uma vez por sessão")


if __name__ == "__main__":
    unittest.main()
