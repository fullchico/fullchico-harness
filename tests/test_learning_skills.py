import re
import sys
import unittest

from tests.helpers import ROOT, commit_all, make_repo, sync

sys.path.insert(0, str(ROOT / "plugin/payload"))
import memory  # noqa: E402

DREAM = ROOT / "plugin/skills/dream/SKILL.md"
APRENDER = ROOT / "plugin/skills/aprender/SKILL.md"


class TestLearningSkills(unittest.TestCase):
    def test_invocation(self):
        self.assertNotIn("disable-model-invocation: true", DREAM.read_text())
        self.assertIn("disable-model-invocation: true", APRENDER.read_text())

    def test_skills_use_the_real_commands(self):
        dream = DREAM.read_text()
        for command in (".harness/learn sessions", ".harness/learn digest", ".harness/learn mark",
                        ".harness/memory note add", ".harness/memory check", ".harness-run/dream/", "haiku"):
            self.assertIn(command, dream, command)
        aprender = APRENDER.read_text()
        for command in (".harness/fetch", ".harness/learn usage", "`mapear`", "`dream`", ".harness-run/propostas/"):
            self.assertIn(command, aprender, command)

    def test_skills_never_teach_a_denied_command_or_write_to_claude_home(self):
        for path in (DREAM, APRENDER):
            text = path.read_text()
            for forbidden in ("git push", "git fetch", "git pull", "gh pr", "gh issue", "--no-verify",
                              "docker compose up"):
                self.assertNotIn(forbidden, text, f"{path.name}: {forbidden}")
            for line in text.splitlines():
                if "~/.claude" in line:
                    self.assertRegex(line, r"só para leitura|não grav|nunca grav", line)

    def test_dream_treats_transcripts_as_data_and_requires_code_paths(self):
        text = DREAM.read_text()
        self.assertIn("dado", text)
        self.assertIn("caminho", text)
        self.assertIn("confira", text.lower())

    def test_note_example_is_accepted_by_note_add(self):
        example = re.search(r"```nota (\S+)\n(.*?)```", DREAM.read_text(), flags=re.S)
        self.assertIsNotNone(example)
        repo = make_repo()
        (repo / "apps/api").mkdir(parents=True)
        (repo / "apps/api/booking.py").write_text("x\n")
        commit_all(repo, "feat: scaffold")
        memory.note_add(str(repo), example.group(1), example.group(2), ["apps/api/booking.py"])
        self.assertTrue(memory.notes_index(str(repo)).startswith(example.group(1) + ": "))

    def test_delivery_points_to_learning_and_agents_md_fits(self):
        self.assertIn("/harness:aprender", (ROOT / "plugin/skills/entregar/SKILL.md").read_text())
        repo = make_repo()
        sync(repo)
        agents = (repo / "AGENTS.md").read_text()
        self.assertIn("/harness:aprender", agents)
        self.assertLess(len(agents.encode("utf-8")), 8 * 1024)
        self.assertTrue((repo / ".harness/learn").exists())


if __name__ == "__main__":
    unittest.main()
