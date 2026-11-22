"""O dream rodou de verdade e pulou o que era só texto: quem fez a entrega escolheu as notas.

Três notas saíram registrando contornos do ambiente, e as propostas da retrospectiva sumiram
com o worktree. Aqui o que dava para virar máquina virou.
"""
import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, make_repo, run_hook, sync

sys.path.insert(0, str(ROOT / "plugin/payload"))
import learn  # noqa: E402
import memory  # noqa: E402


def extracted(repo, *names, agent="harness:extrator"):
    """O extrator terminou propondo estas notas."""
    body = "\n\n".join(f"NOTA: {n}\nTexto.\nCAMINHOS: a.py" for n in names)
    return run_hook("gate_stamp.py", {"hook_event_name": "SubagentStop", "agent_type": agent, "cwd": str(repo),
                                      "last_assistant_message": body})


class TestDreamRails(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        for path in ("apps/api/booking.py", "apps/api/seeding.py"):
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_text("x\n")
        commit_all(self.repo, "feat: scaffold")
        (self.repo / "n.md").write_text("O horário é sempre o do estabelecimento.\n")

    def note(self, *args):
        return subprocess.run([str(self.repo / ".harness/memory"), "note", "add", *args], cwd=self.repo,
                              capture_output=True, text=True)

    def test_a_new_note_is_born_only_from_what_the_extractor_proposed(self):
        r = self.note("fuso", "n.md", "apps/api/booking.py")
        self.assertEqual(r.returncode, 1)
        self.assertIn("harness:extrator", r.stderr)
        extracted(self.repo, "fuso", agent="harness:revisor")  # outro agente não propõe nota
        self.assertEqual(self.note("fuso", "n.md", "apps/api/booking.py").returncode, 1)
        extracted(self.repo, "fuso", "outra")
        self.assertEqual(self.note("fuso", "n.md", "apps/api/booking.py").returncode, 0, r.stderr)
        # atualizar ou reancorar uma nota que já existe não pede candidato novo
        self.assertEqual(self.note("fuso", "n.md", "apps/api/booking.py").returncode, 0)
        self.assertEqual(self.note("inventada", "n.md", "apps/api/booking.py").returncode, 1)

    def test_the_extractor_gets_only_the_digest(self):
        ask = lambda prompt: run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(self.repo), "tool_input": {
            "subagent_type": "harness:extrator", "prompt": prompt}})[0]
        self.assertEqual(ask("resumo: .harness-run/dream/abc.md"), 0)
        self.assertEqual(ask("resumo: .harness-run/dream/abc.md\nJá sei que a nota boa é a do seed."), 2)
        self.assertEqual(ask("spec: docs/x.md"), 2)

    def test_the_anchor_covers_every_file_the_note_names(self):
        extracted(self.repo, "seed")
        (self.repo / "n.md").write_text("O seed só insere em banco vazio; a regra está em apps/api/seeding.py.\n")
        r = self.note("seed", "n.md", "apps/api/booking.py")
        self.assertEqual(r.returncode, 1)
        self.assertIn("apps/api/seeding.py", r.stderr)
        self.assertEqual(self.note("seed", "n.md", "apps/api/booking.py", "apps/api/seeding.py").returncode, 0)
        self.assertEqual(self.note("seed", "n.md", "apps/api").returncode, 0, "pasta ancorada cobre o que está nela")

    def test_proposals_survive_the_worktree(self):
        learn_cmd = lambda *a: subprocess.run([str(self.repo / ".harness/learn"), *a], cwd=self.repo,
                                             capture_output=True, text=True)
        (self.repo / "p.md").write_text("# Guard nega por substring\n\nEvidência...\n")
        r = learn_cmd("propose", "guard-por-substring", "p.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        stored = r.stdout.strip()
        self.assertFalse(stored.startswith(str(self.repo) + os.sep + ".harness-run"), "fora do worktree")
        self.assertTrue(os.path.exists(stored))
        self.assertIn("guard-por-substring", learn_cmd("proposals").stdout)
        self.assertEqual(learn_cmd("propose", "../fora", "p.md").returncode, 1)

    def test_a_session_that_kept_growing_after_being_marked_comes_back(self):
        import tempfile, json, pathlib
        home = pathlib.Path(tempfile.mkdtemp())
        folder = home / ".claude/projects" / learn._slug(str(self.repo))
        folder.mkdir(parents=True)
        path = folder / "s1.jsonl"
        path.write_text(json.dumps({"type": "user"}) + "\n")
        learn.mark(str(self.repo), ["s1"], home=str(home))
        self.assertTrue(learn.sessions(str(self.repo), str(home))[0]["processed"])
        with open(path, "a") as f:
            f.write("x" * 70000)
        self.assertFalse(learn.sessions(str(self.repo), str(home))[0]["processed"], "o que veio depois nunca era lido")

    def test_texts_point_to_the_rails(self):
        dream = (ROOT / "plugin/skills/dream/SKILL.md").read_text()
        self.assertIn("harness:extrator", dream)
        self.assertIn("contorno", dream)
        extractor = (ROOT / "plugin/agents/extrator.md").read_text()
        self.assertIn("haiku", extractor.split("---")[1])
        self.assertIn("NOTA:", extractor)
        self.assertIn("contorno", extractor)
        learn_skill = (ROOT / "plugin/skills/aprender/SKILL.md").read_text()
        self.assertIn(".harness/learn propose", learn_skill)
        self.assertLess(learn_skill.index("## 2. Retrospectiva"), learn_skill.index("Medir"), "mede-se por último")
        session = (ROOT / "plugin/payload/hooks/session_context.py").read_text()
        self.assertIn("harness:dream", session)


if __name__ == "__main__":
    unittest.main()
