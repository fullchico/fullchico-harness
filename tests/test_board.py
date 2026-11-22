"""O painel da entrega: uma página que o dono abre uma vez e acompanha, sem perguntar à sessão.

Visto em entregas reais: 44 minutos parada num pedido de permissão e 1 hora parada por queda de
rede, sem o dono saber. O `.harness/board` junta o que os trilhos já sabem numa página que se
atualiza sozinha, e o `activity.py` registra que agente começou e terminou.
"""
import datetime
import html.parser
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from tests.helpers import HOOKS, ROOT, commit_all, git, make_repo, run_hook, sync
import common

SPEC = "docs/specs/loja"
PAGE = ".harness-run/painel.html"
TICKETS = ((1, "cadastro", "done", "Cadastro de clientes"), (2, "pedidos", "claimed", "Pedidos <script>alert(1)</script>"),
           (3, "estoque", "claimed", "Estoque"), (4, "relatorio", "open", "Relatório de vendas"))
STANDARD = ('[ -f "$CLAUDE_PROJECT_DIR/.harness/hooks/activity.py" ] || exit 0; '
            'python3 -I "$CLAUDE_PROJECT_DIR/.harness/hooks/activity.py"')


def stamp(minutes_ago=0):
    at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes_ago)
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def tree(folder):
    return {os.path.relpath(os.path.join(base, name), folder)
            for base, dirs, names in os.walk(folder) for name in names + dirs if ".git" not in base.split(os.sep)}


class Tags(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.attrs, self.text, self.scripts, self._in = [], [], [], [], None

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs += [(tag, k, v) for k, v in attrs]
        self._in = tag

    def handle_endtag(self, tag):
        self._in = None

    def handle_data(self, data):
        (self.scripts if self._in == "script" else self.text).append(data)


class Base(unittest.TestCase):
    def setUp(self):
        self.addCleanup(os.environ.pop, "HARNESS_NOW", None)
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        commit_all(self.repo, "chore: adopt harness")
        self.state = common.state_dir(str(self.repo))

    def tickets(self, items=TICKETS):
        for number, name, status, title in items:
            path = self.repo / SPEC / "issues" / f"{number:02d}-{name}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {title}\n\nStatus: {status}\nBlocked by:\nOwns: src/{name}\n")
        (self.repo / SPEC / "spec.md").write_text("# Loja virtual\n\nspec\n")
        commit_all(self.repo, "docs: add spec")

    def board(self, *args, cwd=None):
        r = subprocess.run([str(self.repo / ".harness/board"), *args], cwd=cwd or self.repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        return r.stdout

    def page(self):
        self.board()
        return (self.repo / PAGE).read_text()

    def data(self):
        return json.loads(self.board("--json"))

    def append(self, name, record):
        os.makedirs(self.state, exist_ok=True)
        with open(os.path.join(self.state, name), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def activity(self, event, agent_id="a1", agent_type="harness:implementador", **extra):
        payload = dict({"hook_event_name": event, "agent_id": agent_id, "agent_type": agent_type,
                        "session_id": "s1", "cwd": str(self.repo)}, **extra)
        return run_hook("activity.py", payload)


class TestBoard(Base):
    def test_project_without_a_delivery_says_so(self):
        out = self.board()
        self.assertEqual(out.strip(), str(self.repo / PAGE))
        self.assertIn("Nenhuma entrega em andamento", (self.repo / PAGE).read_text())
        self.assertEqual(self.data()["state"], "none")
        self.assertIn("Nenhuma entrega em andamento", self.board("--text"))

    def test_outside_git_still_writes_a_page(self):
        with tempfile.TemporaryDirectory() as folder:
            r = subprocess.run([sys.executable, str(ROOT / "plugin/payload/board.py"), folder], capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stderr), (0, ""))
            with open(os.path.join(folder, PAGE), encoding="utf-8") as f:
                self.assertIn("Nenhuma entrega em andamento", f.read())

    def test_unreadable_ticket_is_reported_not_raised(self):
        self.tickets()
        (self.repo / SPEC / "issues/05-quebrado.md").write_text("# sem cabeçalho\n")
        self.assertIn("05-quebrado.md", self.page())

    def test_four_tickets_fall_in_three_columns_with_progress(self):
        self.tickets()
        page, data = self.page(), self.data()
        for needed in ("A fazer", "Em andamento", "Concluído", "Cadastro de clientes", "Estoque", "Relatório de vendas",
                       "1 de 4", "Loja virtual", "src/estoque"):
            self.assertIn(needed, page, needed)
        self.assertEqual((data["done"], data["total"], data["spec"], data["name"]), (1, 4, SPEC, "Loja virtual"))
        columns = {c: [t["number"] for t in data["tickets"] if t["column"] == c] for c in ("todo", "doing", "done")}
        self.assertEqual(columns, {"todo": [4], "doing": [2, 3], "done": [1]})
        doing = next(t for t in data["tickets"] if t["number"] == 3)
        self.assertEqual((doing["title"], doing["action"]), ("Estoque", "despachar"))
        self.assertTrue(doing["next"])
        text = self.board("--text")
        for needed in ("Loja virtual", "1 de 4", "Estoque"):
            self.assertIn(needed, text, needed)

    def test_fix_rounds_are_counted_from_the_findings(self):
        self.tickets()
        (self.repo / SPEC / "achados").mkdir()
        (self.repo / SPEC / "achados/02-rodada-1.md").write_text("achado\n")
        rounds = {t["number"]: t["rounds"] for t in self.data()["tickets"] if t["column"] == "doing"}
        self.assertEqual((rounds[2], rounds[3]), (1, 0))
        self.assertIn("1 rodada de correção", self.page())

    def test_all_done_is_concluded_and_newest_open_spec_wins(self):
        self.tickets(((1, "a", "done", "A"),))
        self.assertEqual(self.data()["state"], "done")
        self.assertIn("Concluída", self.page())
        path = self.repo / "docs/specs/outra/issues/01-b.md"
        path.parent.mkdir(parents=True)
        path.write_text("# B\n\nStatus: open\nBlocked by:\nOwns: src/b\n")
        commit_all(self.repo, "docs: add another spec")
        self.assertEqual(self.data()["spec"], "docs/specs/outra")

    def test_no_activity_beyond_the_limit_is_stalled(self):
        self.tickets()
        self.assertEqual(self.data()["state"], "working")
        os.environ["HARNESS_NOW"] = str(int(time.time()) + 45 * 60)
        data = self.data()
        self.assertEqual(data["state"], "stalled")
        self.assertRegex(data["headline"], r"Parada há 4[45] min")
        self.assertIn("Parada há 4", self.page())

    def test_recent_permission_request_waits_for_the_owner(self):
        self.tickets()
        self.append("permissions.jsonl", {"at": stamp(), "what": "permissão pedida", "session": "s1",
                                          "agent_type": "harness:implementador", "agent_id": "a9",
                                          "tool": "Bash", "summary": "git push origin main"})
        data = self.data()
        self.assertEqual(data["state"], "waiting_owner")
        page = self.page()
        self.assertIn("Esperando você", page)
        self.assertIn("git push origin main", page)

    def test_orchestrator_that_ended_stopped_waits_for_the_owner(self):
        self.tickets()
        self.activity("SubagentStart", "o1", "harness:orquestrador")
        self.activity("SubagentStop", "o1", "harness:orquestrador",
                      last_assistant_message="fiz o que deu.\nENTREGA: PARADA ticket 02 não fechou em 3 rodadas")
        data = self.data()
        self.assertEqual(data["state"], "waiting_owner")
        self.assertIn("ticket 02 não fechou em 3 rodadas", data["detail"])

    def test_timeline_mixes_denials_and_ticket_merges(self):
        self.tickets()
        (self.repo / "nota.md").write_text("x\n")
        commit_all(self.repo, "Merge ticket docs/specs/loja/issues/01-cadastro.md")
        self.append("log.jsonl", {"at": stamp(), "hook": "service_guard", "what": "negou", "detail": "git push direto não pode"})
        self.append("log.jsonl", {"at": stamp(), "hook": "gate_stamp", "what": "carimbou", "detail": "bugs abc"})
        texts = [e["text"] for e in self.data()["timeline"]]
        self.assertTrue(any("git push direto não pode" in t for t in texts), texts)
        merges = [e for e in self.data()["timeline"] if e["kind"] == "merge"]
        self.assertEqual(len(merges), 1)
        self.assertIn("01-cadastro", merges[0]["text"])
        page = self.page()
        self.assertIn("git push direto não pode", page)
        self.assertIn("Ticket integrado", page)

    def test_gates_show_what_is_approved_for_the_current_commit(self):
        self.tickets()
        head = git(self.repo, "rev-parse", "HEAD")
        path = common.approval_path(self.state, "bugs", head)
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"gate": "bugs", "sha": head, "status": "PASS", "by": "hook"}, f)
        gates = {g["gate"]: g["approved"] for g in self.data()["gates"]}
        self.assertEqual(gates, {"seguranca": False, "revisao": False, "bugs": True, "qualidade": False})
        with open(self.repo / "harness.conf", "a") as f:
            f.write("\nSCREENS_DIR=docs/telas\n")
        self.assertIn("visual", [g["gate"] for g in self.data()["gates"]])
        page = self.page()
        self.assertRegex(page, r"Caça a bugs[^<]*</span>\s*<span[^>]*>✓ aprovado")
        self.assertIn("faltando", page)

    def test_pendings_and_result_links(self):
        self.tickets()
        folder = common.pendings_dir(str(self.repo))
        os.makedirs(folder)
        with open(os.path.join(folder, "P1.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "P1", "text": "validar o CEP", "status": "open", "commit": "abc"}, f)
        (self.repo / ".env").write_text("WEB_PORT=1\n")
        (self.repo / "DESIGN.md").write_text("# Design\n")
        data = self.data()
        self.assertEqual((data["pendings"]["count"], data["pendings"]["texts"]), (1, ["validar o CEP"]))
        self.assertEqual((data["result"]["app"], data["result"]["app_up"], data["result"]["design"]),
                         ("http://localhost:1", False, "DESIGN.md"))
        self.assertNotIn("pr", [k for k, v in data["result"].items() if v])
        page = self.page()
        for needed in ("validar o CEP", "http://localhost:1", "não está respondendo", "DESIGN.md"):
            self.assertIn(needed, page, needed)

    def test_page_refreshes_itself_escapes_and_loads_nothing_from_the_network(self):
        self.tickets()
        page = self.page()
        parser = Tags()
        parser.feed(page)
        parser.close()
        self.assertIn(("meta", "http-equiv", "refresh"), parser.attrs)
        self.assertIn(("meta", "content", "5"), parser.attrs)
        self.assertIn(("html", "lang", "pt-BR"), parser.attrs)
        self.assertIn("Pedidos <script>alert(1)</script>", "".join(parser.text), "o título chega como texto")
        self.assertNotIn("alert(1)", "".join(parser.scripts))
        self.assertFalse({"link", "img", "iframe", "object", "embed"} & set(parser.tags))
        self.assertFalse([a for a in parser.attrs if a[1] == "src"])
        for forbidden in ("@import", "url(", "fetch(", "XMLHttpRequest"):
            self.assertNotIn(forbidden, page)
        for tag, key, value in parser.attrs:
            if key == "href":
                self.assertFalse(value.startswith("http") and "//localhost" not in value, value)

    def test_writes_only_the_page(self):
        self.tickets()
        before, state_before = tree(self.repo), tree(self.state) if os.path.isdir(self.state) else set()
        status = git(self.repo, "status", "--short")
        self.board()
        self.board("--json")
        self.board("--text")
        self.assertEqual(tree(self.repo) - before, {".harness-run", ".harness-run/.gitignore", PAGE})
        self.assertEqual((self.repo / ".harness-run/.gitignore").read_text(), "*\n")
        self.assertEqual(tree(self.state) if os.path.isdir(self.state) else set(), state_before)
        self.assertEqual(git(self.repo, "status", "--short"), status)
        self.assertFalse([p for p in tree(self.repo / ".harness") if "__pycache__" in p])

    def test_watch_regenerates_until_interrupted(self):
        self.tickets()
        p = subprocess.Popen([str(self.repo / ".harness/board"), "--watch", "1"], cwd=self.repo, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        try:
            first = p.stdout.readline()
            self.assertIn("1 de 4", first)
            self.assertTrue((self.repo / PAGE).exists())
            p.send_signal(signal.SIGINT)
            self.assertEqual(p.wait(timeout=10), 0)
            self.assertNotIn("Traceback", p.stderr.read())
        finally:
            p.kill()
            p.stdout.close()
            p.stderr.close()

    def test_usage_error_exits_2(self):
        r = subprocess.run([str(self.repo / ".harness/board"), "--outra"], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


class TestActivity(Base):
    def rows(self):
        with open(os.path.join(self.state, "activity.jsonl"), encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def test_agent_is_active_between_start_and_stop_and_the_page_is_regenerated(self):
        self.tickets()
        self.assertEqual(self.activity("SubagentStart"), (0, "", ""))
        self.assertIn("implementador", (self.repo / PAGE).read_text(), "o hook regenera o painel")
        (only,) = self.rows()
        self.assertEqual((only["event"], only["agent_type"], only["agent_id"], only["session_id"]),
                         ("start", "harness:implementador", "a1", "s1"))
        self.assertRegex(only["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.activity("SubagentStart", "a2", "harness:revisor-bugs")
        active = self.data()["agents"]
        self.assertEqual([(a["agent_id"], a["role"]) for a in active], [("a1", "implementador"), ("a2", "revisor de bugs")])
        self.assertEqual(self.activity("SubagentStop"), (0, "", ""))
        self.assertEqual([a["agent_id"] for a in self.data()["agents"]], ["a2"])
        page = (self.repo / PAGE).read_text()
        self.assertIn("revisor de bugs", page)
        kinds = [e["kind"] for e in self.data()["timeline"]]
        self.assertIn("start", kinds)
        self.assertIn("stop", kinds)

    def test_active_agent_is_tied_to_its_dispatched_ticket(self):
        self.tickets()
        (self.repo / "harness.conf").write_text("PROJECT=p\n")
        commit_all(self.repo, "chore: conf")
        rc, _, err = run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(self.repo), "agent_type": "harness:orquestrador",
                                                    "tool_input": {"subagent_type": "harness:implementador", "isolation": "worktree",
                                                                   "prompt": f"spec: {SPEC}/spec.md\nticket: {SPEC}/issues/03-estoque.md"}})
        self.assertEqual(rc, 0, err)
        self.activity("SubagentStart")
        (agent,) = self.data()["agents"]
        self.assertEqual(agent["ticket"], "03-estoque")
        card = next(t for t in self.data()["tickets"] if t["number"] == 3)
        self.assertEqual((card["who"], card["action"]), ("implementador", "esperar"))

    def test_start_older_than_three_hours_is_not_active(self):
        self.tickets()
        self.append("activity.jsonl", {"at": stamp(200), "event": "start", "agent_type": "harness:implementador", "agent_id": "velho"})
        self.assertEqual(self.data()["agents"], [])

    def test_never_blocks_never_prints(self):
        self.assertEqual(run_hook("activity.py", None, raw="isto não é json"), (0, "", ""))
        self.assertEqual(run_hook("activity.py", {"hook_event_name": "SubagentStop", "cwd": "/nao/existe"}), (0, "", ""))
        self.assertEqual(run_hook("activity.py", {"hook_event_name": "SubagentStop", "cwd": str(self.repo), "agent_id": {"x": 1},
                                                  "agent_type": 7, "last_assistant_message": ["x"]}), (0, "", ""))
        self.assertEqual(run_hook("activity.py", {"hook_event_name": "Stop", "cwd": str(self.repo)}), (0, "", ""))
        self.assertEqual(len(self.rows()), 1, "só os dois eventos de subagente são registrados")
        # hooks/__pycache__ é do próprio teste, que importa o common; o hook não pode deixar o dele ao lado do board.py
        self.assertFalse([p for p in tree(HOOKS.parent) if "__pycache__" in p and not p.startswith("hooks")])

    def test_settings_wire_the_hook_on_both_events_in_new_groups(self):
        hooks = json.loads((ROOT / "plugin/templates/settings.json").read_text())["hooks"]
        for event in ("SubagentStart", "SubagentStop"):
            own = [g for g in hooks[event] if any("activity.py" in h["command"] for h in g["hooks"])]
            self.assertEqual(len(own), 1, event)
            # No SubagentStop o grupo diz "*": outros testes leem o `matcher` de todos os grupos de lá.
            self.assertIn(own[0].get("matcher"), (None, "*"), "todo subagente")
            self.assertEqual([h["command"] for h in own[0]["hooks"]], [STANDARD])
            self.assertNotIn("onFailure", own[0]["hooks"][0])
            self.assertIs(hooks[event][-1], own[0], "grupo novo, no fim da lista")
        self.assertFalse(any("activity.py" in h["command"] for g in hooks["UserPromptSubmit"] for h in g["hooks"]))

    def test_docs_point_the_owner_to_the_board(self):
        skill = (ROOT / "plugin/skills/entregar/SKILL.md").read_text()
        self.assertIn(".harness/board", skill)
        self.assertLess(skill.index(".harness/board"), skill.index("```pedido harness:orquestrador"),
                        "o painel é rodado uma vez, antes do primeiro disparo")
        self.assertIn("| `.harness/board", (ROOT / "README.md").read_text())


class TestCost(Base):
    def test_a_real_sized_project_is_generated_fast(self):
        for i in range(800):
            path = self.repo / "src" / f"m{i % 20}" / f"f{i}.ts"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("export const x = 1\n")
        self.tickets(tuple((n, f"t{n}", "done" if n <= 8 else "claimed" if n <= 11 else "open", f"Ticket {n}")
                           for n in range(1, 16)))
        self.board()  # a primeira aquece o cache do sistema de arquivos
        best = min(self._timed() for _ in range(3))
        self.assertLess(best, 1.5, "medido: 0,26 s com 3 tickets em andamento; o limite tem folga para máquina ocupada")

    def _timed(self):
        start = time.monotonic()
        self.board()
        return time.monotonic() - start


if __name__ == "__main__":
    unittest.main()
