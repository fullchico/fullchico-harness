"""A skill de entrega é texto seguido por um modelo. Estes testes conferem que o que
ela manda escrever e rodar é aceito pelos guards e pelo validador do harness."""
import re
import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, git, make_repo, run_hook, sync

sys.path.insert(0, str(ROOT / "plugin/payload"))
import tickets_check  # noqa: E402

SKILL = ROOT / "plugin/skills/entregar"
REFS = ("spec.md",)
# O que o orquestrador segue vai para o projeto, em .harness/entrega/: é lido por um
# subagente, que não enxerga os arquivos da skill.
RUN = ROOT / "plugin/payload/entrega"
RUN_DOCS = ("tickets.md", "despacho.md", "fechamento.md")
AGENTS = ("implementador", "revisor-spec", "orquestrador")


def texts():
    files = [SKILL / "SKILL.md"] + [SKILL / "references" / r for r in REFS] + [RUN / r for r in RUN_DOCS]
    files += [ROOT / f"plugin/agents/{a}.md" for a in AGENTS] + [ROOT / "plugin/payload/subagent-rules.md"]
    return {str(f.relative_to(ROOT)): f.read_text() for f in files}


def frontmatter(path):
    head = path.read_text().split("---")[1]
    return dict(line.split(": ", 1) for line in head.strip().splitlines() if ": " in line)


class TestEntregar(unittest.TestCase):
    def test_agents_frontmatter(self):
        impl = frontmatter(ROOT / "plugin/agents/implementador.md")
        self.assertEqual((impl["name"], impl["model"]), ("implementador", "haiku"))
        rev = frontmatter(ROOT / "plugin/agents/revisor-spec.md")
        self.assertEqual((rev["name"], rev["model"]), ("revisor-spec", "inherit"))
        self.assertNotIn("Edit", rev["tools"])
        self.assertNotIn("Write", rev["tools"])

    def test_design_runs_on_the_session_model_and_execution_on_sonnet(self):
        orq = frontmatter(ROOT / "plugin/agents/orquestrador.md")
        self.assertEqual((orq["name"], orq["model"]), ("orquestrador", "sonnet"))
        for tool in ("Agent", "Bash", "Edit", "Write", "Read"):
            self.assertIn(tool, orq["tools"])
        skill = (SKILL / "SKILL.md").read_text()
        self.assertIn("`harness:orquestrador`", skill)
        body = (ROOT / "plugin/agents/orquestrador.md").read_text()
        for doc in RUN_DOCS:
            self.assertTrue((RUN / doc).exists(), doc)
            self.assertIn(f".harness/entrega/{doc}", body)
        for doc in ("tickets.md", "despacho.md"):
            self.assertNotIn(doc, skill, "a sessão de desenho não carrega o texto da execução")

    def test_orchestrator_request_is_pointer_only(self):
        repo = make_repo()
        (repo / "docs/specs/x").mkdir(parents=True)
        (repo / "docs/specs/x/spec.md").write_text("x")
        (repo / "harness.conf").write_text("PROJECT=p\n")
        commit_all(repo, "docs: add spec")
        ask = lambda prompt: run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(repo), "tool_input": {
            "subagent_type": "harness:orquestrador", "prompt": prompt}})[0]
        self.assertEqual(ask("spec: docs/specs/x/spec.md"), 0)
        self.assertEqual(ask("spec: docs/specs/x/spec.md\nCapriche, o dono tem pressa."), 2)
        self.assertEqual(ask("spec: docs/specs/x/spec.md\nticket: docs/specs/x/spec.md"), 2)
        self.assertEqual(ask("faça a entrega"), 2)

    def test_run_docs_reach_the_project(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        for doc in RUN_DOCS:
            self.assertTrue((repo / ".harness/entrega" / doc).exists(), doc)

    def test_skill_is_user_invoked_and_has_the_two_stops(self):
        text = (SKILL / "SKILL.md").read_text()
        self.assertIn("disable-model-invocation: true", text)
        self.assertEqual(len(re.findall(r"\*\*PARADA", text)), 2)
        self.assertIn("aprov", text)
        self.assertIn("3 rodadas", text)

    def test_every_reference_exists_and_is_linked(self):
        text = (SKILL / "SKILL.md").read_text()
        for ref in REFS:
            self.assertTrue((SKILL / "references" / ref).exists(), ref)
            self.assertIn(f"references/{ref}", text)

    def test_request_examples_pass_the_guard(self):
        repo = make_repo()
        for path in ("docs/specs/exemplo/spec.md", "docs/specs/exemplo/issues/01-nome.md",
                     "docs/specs/exemplo/achados/01-rodada-1.md", "GLOSSARY.md", "docs/adr/0001-exemplo.md"):
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / path).write_text("# t\n\nStatus: claimed\nBlocked by:\nOwns: src/t\n" if "issues" in path else "x")
        (repo / "harness.conf").write_text("PROJECT=p\n")
        base = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "-b", "feat/exemplo")
        sha = commit_all(repo, "docs: add spec")
        found = 0
        for name, text in texts().items():
            for agent, body in re.findall(r"```pedido (\S+)\n(.*?)```", text, flags=re.S):
                found += 1
                prompt = body.replace("HASH_DO_COMMIT", sha).replace("BASE", base)
                payload = {"tool_name": "Agent", "cwd": str(repo), "tool_input": {"subagent_type": agent, "prompt": prompt}}
                if agent == "harness:implementador":
                    payload["agent_type"] = "harness:orquestrador"
                    payload["tool_input"]["run_in_background"] = False
                    payload["tool_input"]["isolation"] = "worktree"
                rc, _, err = run_hook("dispatch_guard.py", payload)
                self.assertEqual(rc, 0, f"{name} ({agent}): {err}")
        self.assertGreaterEqual(found, 6)

    def test_skill_never_teaches_a_denied_command(self):
        for name, text in texts().items():
            for forbidden in ("git push", "git fetch", "git pull", "gh pr", "--no-verify", "docker compose up",
                              "git send-pack"):
                self.assertNotIn(forbidden, text, name)

    def test_skill_uses_only_agent_invocable_skills(self):
        joined = "\n".join(texts().values())
        for skill in ("grilling", "domain-modeling", "tdd", "diagnosing-bugs"):
            self.assertIn(f"`{skill}`", joined)
        for reserved in ("to-spec", "to-tickets", "implement-spec", "grill-with-docs", "grill-me"):
            self.assertNotIn(reserved, joined)

    def test_ticket_example_passes_tickets_check(self):
        text = (RUN / "tickets.md").read_text()
        examples = re.findall(r"```ticket (\S+)\n(.*?)```", text, flags=re.S)
        self.assertGreaterEqual(len(examples), 2)
        repo = make_repo()
        issues = repo / "docs/specs/exemplo/issues"
        issues.mkdir(parents=True)
        for name, body in examples:
            (issues / name).write_text(body)
        tickets = tickets_check.load(str(issues))
        self.assertEqual(tickets_check.problems(tickets), [])
        self.assertTrue(tickets_check.frontier(tickets))

    def test_skill_runs_the_harness_commands(self):
        joined = "\n".join(texts().values())
        for command in (".harness/fetch", ".harness/push", ".harness/pr create", ".harness/validate --profile merge",
                        ".harness/up", ".harness/prepare", ".harness/integrate", "tickets_check.py",
                        "--frontier", 'isolation'):
            self.assertIn(command, joined, command)

    def test_agents_md_still_fits_and_names_the_command(self):
        repo = make_repo()
        sync(repo)
        text = (repo / "AGENTS.md").read_text()
        self.assertIn("/harness:entregar", text)
        self.assertLess(len(text.encode("utf-8")), 8 * 1024)

    def test_conf_template_documents_max_parallel(self):
        self.assertIn("# MAX_PARALLEL=3", (ROOT / "plugin/templates/harness.conf").read_text())


if __name__ == "__main__":
    unittest.main()
