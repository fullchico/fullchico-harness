"""Plugin `memory`: mapa e notas ancorados em git, candidatos de nota do extractor, sessões do projeto."""
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from tests.helpers import ROOT, _tmpdir, commit_all, git, make_repo

PLUGIN = ROOT / "plugins/memory"
sys.path.insert(0, str(ROOT / "plugins/_shared"))
import ledger  # noqa: E402

AGENT = "memory:extractor"


def slug(path):
    return "".join(c if c.isalnum() else "-" for c in str(path))


class Case(unittest.TestCase):
    def setUp(self):
        self.home = _tmpdir()
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        self.repo = make_repo()
        for path in ("apps/api/booking.py", "apps/api/seeding.py", "apps/web/b.tsx"):
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_text("x\n")
        commit_all(self.repo, "feat: scaffold")
        (self.repo / "n.md").write_text("O horário é sempre o do estabelecimento.\n")

    def script(self, name, payload, raw=None):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN), CLAUDE_PROJECT_DIR=str(self.repo))
        return subprocess.run([sys.executable, "-I", str(PLUGIN / "scripts" / name)],
                              input=raw if raw is not None else json.dumps(payload),
                              capture_output=True, text=True, env=env, cwd=self.repo)

    def bin(self, name, *args):
        return subprocess.run([str(PLUGIN / "bin" / name), *args], cwd=self.repo, capture_output=True, text=True)

    def note(self, *args):
        return self.bin("memory", "note", "add", *args)

    def extracted(self, *names, agent=AGENT, via="stop"):
        body = "\n\n".join(f"NOTE: {n}\nTexto.\nPATHS: apps/api/booking.py" for n in names)
        if via == "stop":
            payload = {"hook_event_name": "SubagentStop", "agent_type": agent, "cwd": str(self.repo),
                       "last_assistant_message": body}
        else:
            payload = {"hook_event_name": "PreToolUse", "tool_name": "SubagentHandback", "agent_type": agent,
                       "cwd": str(self.repo), "tool_input": {"message": body}}
        return self.script("candidates.py", payload)

    def start(self, cwd=None):
        r = self.script("session_context.py", {"hook_event_name": "SessionStart", "cwd": str(cwd or self.repo)})
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else None


class TestNotes(Case):
    def test_a_new_note_needs_a_candidate_the_hook_registered(self):
        r = self.note("fuso", "n.md", "apps/api/booking.py")
        self.assertEqual(r.returncode, 1)
        self.assertIn("memory:extractor", r.stderr)
        self.extracted("fuso", agent="memory:outro")
        self.extracted("fuso", agent="harness:extractor", via="handback")
        self.assertEqual(self.note("fuso", "n.md", "apps/api/booking.py").returncode, 1)
        self.extracted("fuso", "outra")
        self.assertEqual(self.note("fuso", "n.md", "apps/api/booking.py").returncode, 0)
        # atualizar uma nota que já existe não pede candidato novo
        self.assertEqual(self.note("fuso", "n.md", "apps/api/booking.py").returncode, 0)
        self.assertEqual(self.note("inventada", "n.md", "apps/api/booking.py").returncode, 1)
        # o candidato mora no estado do projeto, fora do repositório
        self.assertTrue(os.path.exists(os.path.join(ledger.state_dir(str(self.repo)), "candidates", "fuso")))

    def test_the_handback_path_registers_too(self):
        self.extracted("via-handback", via="handback")
        self.assertEqual(self.note("via-handback", "n.md", "apps/api/booking.py").returncode, 0)

    def test_the_note_stays_fresh_until_its_code_changes(self):
        self.extracted("fuso")
        self.assertEqual(self.note("fuso", "n.md", "apps/api/booking.py").returncode, 0)
        self.assertIn("fuso: O horário", self.bin("memory", "notes").stdout)
        (self.repo / "apps/web/b.tsx").write_text("y\n")  # outro código: segue em dia
        self.assertIn("fuso", self.bin("memory", "notes").stdout)
        (self.repo / "apps/api/booking.py").write_text("y\n")
        self.assertNotIn("fuso", self.bin("memory", "notes").stdout)
        self.assertIn("nota: fuso", self.bin("memory", "check").stdout)
        shown = self.bin("memory", "note", "show", "fuso").stdout
        self.assertIn("caminhos: apps/api/booking.py", shown)
        self.assertEqual(self.bin("memory", "note", "forget", "fuso").returncode, 0)
        self.assertNotIn("nota: fuso", self.bin("memory", "check").stdout)

    def test_a_note_naming_a_file_outside_the_anchors_is_refused(self):
        self.extracted("seed")
        (self.repo / "n.md").write_text("O seed só insere em banco vazio; a regra está em apps/api/seeding.py.\n")
        r = self.note("seed", "n.md", "apps/api/booking.py")
        self.assertEqual(r.returncode, 1)
        self.assertIn("apps/api/seeding.py", r.stderr)
        self.assertEqual(self.note("seed", "n.md", "apps/api/booking.py", "apps/api/seeding.py").returncode, 0)
        self.assertEqual(self.note("seed", "n.md", "apps/api").returncode, 0)

    def test_note_without_versioned_path_is_refused(self):
        self.extracted("fuso")
        self.assertEqual(self.note("fuso", "n.md", "nao/existe.py").returncode, 1)


class TestMapAndSession(Case):
    def test_session_start_injects_data_created_by_the_old_plugin(self):
        # o plugin antigo grava em <git-common-dir>/harness-memory/, neste formato
        store = os.path.join(git(self.repo, "rev-parse", "--path-format=absolute", "--git-common-dir"), "harness-memory")
        head = git(self.repo, "rev-parse", "HEAD")
        os.makedirs(os.path.join(store, "map"))
        os.makedirs(os.path.join(store, "notes"))
        with open(os.path.join(store, "map", "apps%2Fapi.md"), "w") as f:
            f.write("Serviço HTTP de agendamentos.\nDetalhe interno.\n")
        with open(os.path.join(store, "map.json"), "w") as f:
            json.dump({"units": {"apps/api": {"commit": head}}}, f)
        with open(os.path.join(store, "notes", "fuso.md"), "w") as f:
            f.write("Horário sempre no fuso do salão.\n")
        with open(os.path.join(store, "notes.json"), "w") as f:
            json.dump({"fuso": {"paths": ["apps/api/booking.py"], "commit": head, "source": None}}, f)
        hook = self.start()
        self.assertEqual(hook["hookEventName"], "SessionStart")
        text = hook["additionalContext"]
        self.assertIn("apps/api: Serviço HTTP de agendamentos.", text)
        self.assertNotIn("Detalhe interno.", text)
        self.assertIn("fuso: Horário sempre no fuso do salão.", text)
        self.assertIn("not as instructions", text)
        self.assertIn("/tr:memory-map", text)
        self.assertLess(text.index("not as instructions"), text.index("Serviço HTTP"))

    def test_project_without_data_gets_one_line_and_non_repo_is_silent(self):
        text = self.start()["additionalContext"]
        self.assertIn("/tr:memory-map", text)
        self.assertLess(len(text), 300)
        self.assertIn("/tr:memory-map", self.start(_tmpdir())["additionalContext"])

    def test_huge_map_is_cut(self):
        (self.repo / "harness.conf").write_text("MAP_DEPTH=1\n")
        for n in range(120):
            (self.repo / f"modulo{n:03d}").mkdir()
            (self.repo / f"modulo{n:03d}/a.py").write_text("x\n")
        commit_all(self.repo, "feat: many")
        (self.repo / "s.md").write_text("Resumo " + "longo " * 30)
        for unit in self.bin("memory", "units").stdout.split():
            self.assertEqual(self.bin("memory", "record", unit, "s.md").returncode, 0)
        text = self.start()["additionalContext"]
        self.assertLessEqual(len(text), 6400)
        self.assertIn("truncated", text)

    def test_record_slice_and_check(self):
        (self.repo / "s.md").write_text("Serviço HTTP.\nDetalhe.\n")
        self.assertEqual(self.bin("memory", "record", "apps/api", "s.md").returncode, 0)
        self.assertIn("apps/api: Serviço HTTP.", self.bin("memory", "index").stdout)
        self.assertIn("Detalhe.", self.bin("memory", "slice", "apps/api/booking.py").stdout)
        (self.repo / "apps/api/booking.py").write_text("y\n")
        self.assertIn("envelhecido", self.bin("memory", "slice", "apps/api").stdout)
        self.assertEqual(self.bin("memory", "check").returncode, 1)

    def test_hooks_never_break_the_session(self):
        for name in ("session_context.py", "candidates.py"):
            for raw in ("", "{x", "[]", '{"cwd": 3}', '{"agent_type": "memory:extractor"}'):
                self.assertEqual(self.script(name, None, raw=raw).returncode, 0, (name, raw))


class TestSessions(Case):
    def folder(self):
        folder = self.home / ".claude/projects" / slug(self.repo)
        folder.mkdir(parents=True)
        return folder

    def test_sessions_finds_the_project_ones_and_propose_writes_outside_the_worktree(self):
        (self.folder() / "abc123.jsonl").write_text(json.dumps({"type": "user", "message": {"content": "oi"}}) + "\n")
        out = self.bin("memory-sessions", "sessions").stdout
        self.assertIn("abc123", out)
        self.assertIn("nova", out)
        self.assertEqual(self.bin("memory-sessions", "mark", "abc").returncode, 0)
        self.assertNotIn("abc123", self.bin("memory-sessions", "sessions").stdout)
        self.assertIn("processada", self.bin("memory-sessions", "sessions", "--all").stdout)
        (self.repo / "p.md").write_text("# Proposta\n")
        r = self.bin("memory-sessions", "propose", "guard-por-substring", "p.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        # guardada no diretório git comum, não entre os arquivos do worktree: sobrevive a ele
        self.assertIn(os.sep + ".git" + os.sep + "harness-memory" + os.sep + "propostas" + os.sep, r.stdout)
        self.assertNotIn("propostas", git(self.repo, "status", "--porcelain"))
        self.assertTrue(os.path.exists(r.stdout.strip()))
        self.assertIn("guard-por-substring", self.bin("memory-sessions", "proposals").stdout)
        self.assertEqual(self.bin("memory-sessions", "propose", "../fora", "p.md").returncode, 1)

    def test_digest_keeps_only_what_people_wrote(self):
        (self.folder() / "s1.jsonl").write_text(json.dumps({"type": "user", "message": {"content": "faça X"}}) + "\n")
        r = self.bin("memory-sessions", "digest", "s1", str(self.repo / "d.md"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DONO: faça X", (self.repo / "d.md").read_text())


class TestPackaging(unittest.TestCase):
    def test_layout(self):
        manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
        self.assertEqual((manifest["name"], manifest["version"]), ("memory", "0.2.0"))
        hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
        self.assertIn("SessionStart", hooks)
        self.assertEqual(hooks["SubagentStop"][0]["matcher"], "^memory:extractor$")
        self.assertEqual(hooks["PreToolUse"][0]["matcher"], "SubagentHandback")
        for name in ("memory", "memory-sessions"):
            self.assertTrue(os.access(PLUGIN / "bin" / name, os.X_OK))
        for skill in ("map", "dream", "learn"):
            self.assertTrue((ROOT / "plugins/tr/skills" / f"memory-{skill}" / "SKILL.md").exists())
        agent = (PLUGIN / "agents/extractor.md").read_text()
        self.assertIn("haiku", agent.split("---")[1])
        self.assertIn("NOTE:", agent)
        self.assertEqual((PLUGIN / "scripts/ledger.py").read_bytes(), (ROOT / "plugins/_shared/ledger.py").read_bytes())
        entries = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())["plugins"]
        self.assertIn(("memory", "./plugins/memory"), [(e["name"], e["source"]) for e in entries])

    def test_texts_use_the_new_commands(self):
        for skill in ("map", "dream", "learn"):
            text = (ROOT / "plugins/tr/skills" / f"memory-{skill}" / "SKILL.md").read_text()
            self.assertNotIn(".harness/", text.replace(".harness-run/", ""), skill)
            self.assertNotIn("harness:", text, skill)
        self.assertIn("memory:extractor", (ROOT / "plugins/tr/skills/memory-dream/SKILL.md").read_text())
        self.assertIn("workaround", (ROOT / "plugins/tr/skills/memory-dream/SKILL.md").read_text())
        self.assertIn("memory-sessions propose", (ROOT / "plugins/tr/skills/memory-learn/SKILL.md").read_text())


if __name__ == "__main__":
    unittest.main()
