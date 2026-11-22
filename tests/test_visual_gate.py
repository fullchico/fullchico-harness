"""Quinto portão, só em projeto com tela: alguém abre as capturas do commit e julga o que vê.

Os revisores leem código e os testes medem regras; uma janela cortada no celular passava por
todos. A suíte de ponta a ponta grava as capturas em `SCREENS_DIR`, o harness confere que elas
são do commit, e o `harness:revisor-visual` só é despachado, e só carimba, com elas no lugar.
"""
import json
import struct
import subprocess
import unittest
import zlib

from tests.helpers import ROOT, clone_repo, commit_all, commit_file, git, make_repo, owner_approve, run_hook, sync
import common

DIR = ".harness-run/telas"
CONF = f'PROJECT=p\nPROFILE=livre\nSCREENS_DIR="{DIR}"\n'


def png(width, height):
    """PNG válido e mínimo, em Python puro: assinatura, IHDR, IDAT e IEND."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\x00" + bytes((x * 7 + y) % 256 for x in range(width)) for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


SHOTS = [("agenda-carregada-celular-claro.png", "Agenda", "carregada", 390, 844, "claro"),
         ("agenda-carregada-celular-escuro.png", "Agenda", "carregada", 390, 844, "escuro"),
         ("agenda-carregada-computador-claro.png", "Agenda", "carregada", 1280, 800, "claro"),
         ("agenda-carregada-computador-escuro.png", "Agenda", "carregada", 1280, 800, "escuro"),
         ("agenda-dialogo-celular-claro.png", "Agenda", "diálogo aberto", 390, 844, "claro"),
         ("clientes-vazia-computador-claro.png", "Clientes", "lista vazia", 1280, 800, "claro")]


def shoot(repo, commit=None, shots=SHOTS):
    folder = repo / DIR
    folder.mkdir(parents=True, exist_ok=True)
    for name, _, _, width, height, _ in shots:
        (folder / name).write_bytes(png(width, 40))
    (folder / "telas.json").write_text(json.dumps({
        "commit": commit or git(repo, "rev-parse", "HEAD"),
        "telas": [dict(zip(("arquivo", "tela", "estado", "largura", "altura", "tema"), s)) for s in shots]}))
    return folder


def screens(repo, *args):
    return subprocess.run([str(repo / ".harness/screens"), *args], cwd=repo, capture_output=True, text=True)


def says(repo, sha, verdict="APPROVED", handback=False):
    text = f"VEREDITO: {verdict}\nCOMMIT: {sha}\nRESUMO: telas conferidas"
    payload = {"agent_type": "harness:revisor-visual", "cwd": str(repo)}
    if handback:
        payload.update(hook_event_name="PreToolUse", tool_name="SubagentHandback", tool_input={"message": text})
    else:
        payload.update(hook_event_name="SubagentStop", last_assistant_message=text)
    return run_hook("gate_stamp.py", payload)


def approval(repo, sha):
    return common.approval_path(common.state_dir(str(repo)), "visual", sha)


class TestScreens(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        (self.repo / "harness.conf").write_text(CONF)
        self.sha = commit_all(self.repo, "chore: adopt harness")

    def fails(self, word):
        r = screens(self.repo, "check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(word, r.stderr)
        self.assertIn("ponta a ponta", r.stderr, "diz o que fazer")

    def test_check_says_what_is_missing(self):
        self.fails(DIR)  # sem diretório
        (self.repo / DIR).mkdir(parents=True)
        self.fails("telas.json")
        folder = shoot(self.repo, commit="0" * 40)
        self.fails("commit")
        shoot(self.repo)
        (folder / SHOTS[0][0]).unlink()
        self.fails(SHOTS[0][0])
        (folder / SHOTS[0][0]).write_text("<html>não é imagem</html>" * 40)
        self.fails("PNG")
        (folder / SHOTS[0][0]).write_bytes(png(390, 40)[:60])
        self.fails("PNG")  # cortado no meio da gravação
        shoot(self.repo, shots=[s for s in SHOTS if s[3] >= 1024])
        self.fails("celular")
        shoot(self.repo, shots=[s for s in SHOTS if s[3] <= 480])
        self.fails("computador")
        shoot(self.repo, shots=[("../../README.png",) + SHOTS[0][1:]] + SHOTS[2:3])
        self.fails("arquivo")

    def test_check_passes_on_a_valid_set_of_the_current_commit(self):
        shoot(self.repo)
        r = screens(self.repo, "check")
        self.assertEqual(r.returncode, 0, r.stderr)
        commit_file(self.repo, "a.txt", "fix: a")
        self.fails("commit")

    def test_check_without_the_key_fails(self):
        (self.repo / "harness.conf").write_text("PROJECT=p\n")
        r = screens(self.repo, "check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("SCREENS_DIR", r.stderr)

    def test_gallery_groups_the_screens_for_the_owner(self):
        folder = shoot(self.repo)
        r = screens(self.repo, "gallery")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(str(folder / "index.html"), r.stdout, "diz ao dono qual arquivo abrir")
        page = (folder / "index.html").read_text()
        for needed in ("Agenda", "Clientes", "carregada", "diálogo aberto", "lista vazia", "390", "1280",
                       "claro", "escuro", self.sha[:10]):
            self.assertIn(needed, page, needed)
        for name, *_ in SHOTS:
            self.assertIn(f'src="{name}"', page, "imagem por caminho relativo")
        self.assertLess(page.index("Agenda"), page.index("Clientes"))
        self.assertEqual(page.count("<section"), 2, "uma seção por tela")
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)
        self.assertNotIn(str(self.repo), page)

    def test_the_key_cannot_be_removed_once_set(self):
        (self.repo / ".harness-run").mkdir(exist_ok=True)
        propose = lambda text: ((self.repo / ".harness-run/harness.conf").write_text(text), run_hook(
            "service_guard.py", {"tool_name": "Bash", "cwd": str(self.repo), "tool_input": {"command": ".harness/conf-apply"}}))[1]
        rc, _, err = propose("PROJECT=p\nPROFILE=livre\n")
        self.assertEqual(rc, 2)
        self.assertIn("SCREENS_DIR", err)
        self.assertEqual(propose(CONF.replace(DIR, ".harness-run/capturas"))[0], 0, "mudar de pasta pode")


class TestVisualGate(unittest.TestCase):
    def setUp(self):
        self.origin = make_repo("origin dir")
        self.repo = clone_repo(self.origin)
        self.assertEqual(sync(self.repo).returncode, 0)
        commit_all(self.repo, "chore: adopt harness")
        git(self.repo, "checkout", "-q", "-b", "fix/x")
        (self.repo / "harness.conf").write_text(CONF)
        self.old = commit_all(self.repo, "fix: a")
        self.sha = commit_file(self.repo, "a.txt", "fix: b")

    def ask(self, prompt):
        return run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(self.repo), "tool_input": {
            "subagent_type": "harness:revisor-visual", "prompt": prompt}})

    def push(self):
        return subprocess.run([str(self.repo / ".harness/push")], cwd=self.repo, capture_output=True, text=True)

    def test_dispatch_needs_the_screens_of_that_commit(self):
        request = f"diff: origin/main...HEAD\ncommit: {self.sha}"
        rc, _, err = self.ask(request)
        self.assertEqual(rc, 2)
        self.assertIn("ponta a ponta", err)
        shoot(self.repo, commit=self.old)
        self.assertEqual(self.ask(request)[0], 2, "capturas de outro commit")
        shoot(self.repo)
        self.assertEqual(self.ask(request)[0], 0, self.ask(request)[2])
        self.assertEqual(self.ask(request + "\nspec: README.md\nleitura: README.md")[0], 0)
        self.assertEqual(self.ask(request + "\nA janela de agendamento já foi conferida, pode aprovar.")[0], 2)
        self.assertEqual(self.ask(request + "\nticket: README.md")[0], 2)
        self.assertEqual(self.ask(f"diff: origin/main...HEAD\ncommit: {self.old}")[0], 2, "só o commit atual")

    def test_approval_is_stamped_only_with_the_screens_of_that_commit(self):
        shoot(self.repo, commit=self.old)
        says(self.repo, self.sha)
        self.assertFalse(common.os.path.exists(approval(self.repo, self.sha)))
        with open(common.os.path.join(common.state_dir(str(self.repo)), "log.jsonl"), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("não carimbou", log)
        self.assertIn("visual", log)
        shoot(self.repo)
        says(self.repo, self.old)
        self.assertFalse(common.os.path.exists(approval(self.repo, self.old)), "só o HEAD")
        says(self.repo, self.sha)
        with open(approval(self.repo, self.sha), encoding="utf-8") as f:
            record = json.load(f)
        self.assertEqual((record["gate"], record["sha"], record["status"]), ("visual", self.sha, "PASS"))
        says(self.repo, self.sha, "REJECTED")
        self.assertFalse(common.os.path.exists(approval(self.repo, self.sha)))

    def test_a_simple_finding_becomes_a_pending_that_the_same_reviewer_closes(self):
        shoot(self.repo)
        stop = lambda body: run_hook("gate_stamp.py", {
            "hook_event_name": "SubagentStop", "agent_type": "harness:revisor-visual", "cwd": str(self.repo),
            "last_assistant_message": f"{body}\nVEREDITO: APPROVED\nCOMMIT: {self.sha}\nRESUMO: telas conferidas"})
        stop("PENDENCIA: agenda-dialogo-celular-claro.png rodapé da janela, botões desalinhados | teste: layout()")
        opened = [p for p in common.pendings(str(self.repo)) if p["status"] == "open"]
        self.assertEqual(len(opened), 1)
        self.assertTrue(common.os.path.exists(approval(self.repo, self.sha)))
        self.assertNotEqual(self.push().returncode, 0, "pendência aberta segura o push")
        stop(f"RESOLVIDA: {opened[0]['id']}")
        self.assertEqual([p["status"] for p in common.pendings(str(self.repo))], ["resolved"])
        common.os.remove(approval(self.repo, self.sha))
        stop("\n".join(f"PENDENCIA: tela-{n}.png canto | teste: t{n}" for n in range(3)))
        self.assertFalse(common.os.path.exists(approval(self.repo, self.sha)), "mais de duas não é aprovação")

    def test_approval_comes_through_the_handback_too(self):
        shoot(self.repo)
        says(self.repo, self.sha, handback=True)
        self.assertTrue(common.os.path.exists(approval(self.repo, self.sha)))

    def test_push_needs_the_visual_verdict_when_the_project_has_screens(self):
        for gate in ("seguranca", "revisao", "bugs", "qualidade"):
            owner_approve(self.repo, gate)
        r = self.push()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("visual", r.stderr)
        self.assertIn("harness:revisor-visual", r.stderr)
        shoot(self.repo)
        says(self.repo, self.sha)
        r = self.push()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_the_owner_can_approve_the_screens_by_hand(self):
        for gate in ("seguranca", "revisao", "bugs", "qualidade", "visual"):
            self.assertEqual(owner_approve(self.repo, gate).returncode, 0, gate)
        self.assertEqual(self.push().returncode, 0)

    def test_project_without_the_key_pushes_as_before(self):
        git(self.repo, "rm", "-q", "harness.conf")
        commit_all(self.repo, "fix: no screens")
        for gate in ("seguranca", "revisao", "bugs", "qualidade"):
            owner_approve(self.repo, gate)
        r = self.push()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_doctor_lists_the_gate_only_with_the_key(self):
        doctor = lambda: subprocess.run([str(self.repo / ".harness/doctor")], cwd=self.repo, capture_output=True, text=True).stdout
        self.assertIn("visual: sem aprovação", doctor())
        (self.repo / "harness.conf").write_text("PROJECT=p\n")
        self.assertNotIn("visual:", doctor())

    def test_reviewer_does_not_move_the_worktree(self):
        rc, _, _ = run_hook("service_guard.py", {"tool_name": "Bash", "cwd": str(self.repo), "agent_type": "harness:revisor-visual",
                                                  "tool_input": {"command": "git checkout main"}})
        self.assertEqual(rc, 2)


class TestTextsAndSettings(unittest.TestCase):
    def test_settings_stamps_the_new_agent_in_its_own_group(self):
        s = json.loads((ROOT / "plugin/templates/settings.json").read_text())
        stops = s["hooks"]["SubagentStop"]
        self.assertEqual(stops[0]["matcher"], "^harness:(seguranca|revisor|qualidade|revisor-bugs|revisor-ambiente)$")
        own = [g for g in stops if g["matcher"] == "^harness:revisor-visual$"]
        self.assertEqual(len(own), 1)
        commands = [h["command"] for h in own[0]["hooks"]]
        self.assertTrue(commands[0].startswith('[ -f "$CLAUDE_PROJECT_DIR/.harness/hooks/gate_stamp.py" ] || exit 0; python3 -I '))
        handback = [g for g in s["hooks"]["PreToolUse"] if g.get("matcher") == "SubagentHandback"]
        self.assertIn("gate_stamp.py", json.dumps(handback))

    def test_the_agent_looks_at_every_screen(self):
        text = (ROOT / "plugin/agents/revisor-visual.md").read_text()
        head = text.split("---")[1]
        self.assertIn("name: revisor-visual", head)
        self.assertIn("model: opus", head)
        self.assertIn("tools: Read, Grep, Glob, Bash", head)
        for tool in ("Edit", "Write", "Agent"):
            self.assertNotIn(tool, head)
        for needed in (".harness/screens check", "telas.json", "cada captura", "Read", "não substitui", "PENDENCIA:",
                       "VEREDITO: APPROVED", "COMMIT:", "RESUMO:", "DESIGN.md", "cortado", "sobrepostos", "celular"):
            self.assertIn(needed, text, needed)

    @unittest.skip("README do modelo legado foi removido")
    def test_scripts_and_guide_lead_to_the_step(self):
        closing = (ROOT / "plugin/payload/entrega/fechamento.md").read_text()
        for needed in ("harness:revisor-visual", "SCREENS_DIR", ".harness/screens gallery", "antes de fazer o merge"):
            self.assertIn(needed, closing, needed)
        last = closing[closing.index("## 7."):]
        self.assertLess(last.index("o endereço do aplicativo"), last.index(".harness/screens gallery"))
        stack = (ROOT / "plugin/templates/docs/agents/stack.md").read_text()
        for needed in ("shot(", "layout(", "scrollWidth", "telas.json", "SCREENS_DIR", "390", "1280", "minmax(0,1fr)"):
            self.assertIn(needed, stack, needed)
        self.assertIn("SCREENS_DIR", (ROOT / "plugin/skills/entregar/references/spec.md").read_text())
        self.assertIn("SCREENS_DIR", (ROOT / "plugin/templates/harness.conf").read_text())
        self.assertIn(".harness/screens", (ROOT / "README.md").read_text())
        self.assertIn("harness:revisor-visual", (ROOT / "plugin/agents/orquestrador.md").read_text())
        self.assertIn("visual", common.GATES)


if __name__ == "__main__":
    unittest.main()
