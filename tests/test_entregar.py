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
REFS = ("spec.md", "tickets.md", "despacho.md", "fechamento.md")
AGENTS = ("implementador", "revisor-spec")


def texts():
    files = [SKILL / "SKILL.md"] + [SKILL / "references" / r for r in REFS]
    files += [ROOT / f"plugin/agents/{a}.md" for a in AGENTS] + [ROOT / "plugin/payload/subagent-rules.md"]
    return {str(f.relative_to(ROOT)): f.read_text() for f in files}


def frontmatter(path):
    head = path.read_text().split("---")[1]
    return dict(line.split(": ", 1) for line in head.strip().splitlines() if ": " in line)


class TestEntregar(unittest.TestCase):
    def test_agents_frontmatter(self):
        impl = frontmatter(ROOT / "plugin/agents/implementador.md")
        self.assertEqual((impl["name"], impl["model"]), ("implementador", "sonnet"))
        rev = frontmatter(ROOT / "plugin/agents/revisor-spec.md")
        self.assertEqual((rev["name"], rev["model"]), ("revisor-spec", "inherit"))
        self.assertNotIn("Edit", rev["tools"])
        self.assertNotIn("Write", rev["tools"])

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
            (repo / path).write_text("x")
        base = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "-b", "feat/exemplo")
        sha = commit_all(repo, "docs: add spec")
        found = 0
        for name, text in texts().items():
            for agent, body in re.findall(r"```pedido (\S+)\n(.*?)```", text, flags=re.S):
                found += 1
                prompt = body.replace("HASH_DO_COMMIT", sha).replace("BASE", base)
                rc, _, err = run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(repo), "tool_input": {
                    "subagent_type": agent, "prompt": prompt}})
                self.assertEqual(rc, 0, f"{name} ({agent}): {err}")
        self.assertGreaterEqual(found, 5)

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
        text = (SKILL / "references/tickets.md").read_text()
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
                        ".harness/up", ".harness/prepare", ".harness/dev --background", "tickets_check.py",
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
