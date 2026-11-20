import re
import unittest

from tests.helpers import ROOT
import gate_stamp


def load(name):
    text = (ROOT / f"plugin/agents/{name}.md").read_text()
    head = text.split("---")[1]
    fm = dict(line.split(": ", 1) for line in head.strip().splitlines() if ": " in line)
    return fm, text


class TestAgents(unittest.TestCase):
    def test_frontmatter(self):
        for n in ("seguranca", "revisor"):
            fm, _ = load(n)
            self.assertEqual(fm["name"], n)
            self.assertEqual(fm["model"], "haiku" if fm["name"] == "implementador" else "sonnet")
            self.assertTrue(fm["description"])
            self.assertNotIn("Edit", fm["tools"])
            self.assertNotIn("Write", fm["tools"])

    def test_agents_teach_the_verdict_contract(self):
        for n in ("seguranca", "revisor"):
            _, text = load(n)
            for token in ("VEREDITO: APPROVED", "VEREDITO: REJECTED", "COMMIT:", "RESUMO:"):
                self.assertIn(token, text, n)

    def test_example_block_in_each_agent_parses(self):
        for n in ("seguranca", "revisor"):
            _, text = load(n)
            block = re.search(r"```\n(VEREDITO: APPROVED\nCOMMIT: [^\n]+\nRESUMO: [^\n]+)\n```", text)
            self.assertIsNotNone(block, n)
            filled = block.group(1).replace(re.search(r"COMMIT: ([^\n]+)", block.group(1)).group(1), "a" * 40)
            self.assertEqual(gate_stamp.parse_verdict("achados...\n" + filled)["verdict"], "APPROVED")

    def test_agents_say_they_only_get_pointers(self):
        for n in ("seguranca", "revisor"):
            _, text = load(n)
            self.assertIn("git diff", text)
            self.assertIn("diff:", text)
            self.assertIn("commit:", text)

    def test_revisor_checks_commit_type_and_glossary(self):
        _, text = load("revisor")
        self.assertIn("GLOSSARY.md", text)
        self.assertIn("tipo do commit", text)

    def test_setup_skill_is_user_invoked_and_calls_sync(self):
        text = (ROOT / "plugin/skills/setup/SKILL.md").read_text()
        self.assertIn("disable-model-invocation: true", text)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/bin/sync", text)
        self.assertIn("--scope project", text)


if __name__ == "__main__":
    unittest.main()
