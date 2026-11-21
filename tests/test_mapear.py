import re
import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, make_repo, sync

sys.path.insert(0, str(ROOT / "plugin/payload"))
import memory  # noqa: E402

SKILL = ROOT / "plugin/skills/mapear/SKILL.md"


class TestMapear(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text()

    def test_skill_can_be_invoked_by_the_agent_and_uses_haiku(self):
        self.assertNotIn("disable-model-invocation: true", self.text)
        self.assertIn("haiku", self.text)

    def test_skill_uses_the_real_commands(self):
        for command in (".harness/memory check", ".harness/memory units", ".harness/memory record",
                        ".harness/memory anchor glossary", ".harness/memory anchor adr", ".harness-run/map/"):
            self.assertIn(command, self.text, command)
        for forbidden in ("git push", "git fetch", "--no-verify", "docker compose up"):
            self.assertNotIn(forbidden, self.text)

    def test_summary_example_is_accepted_by_record(self):
        example = re.search(r"```resumo\n(.*?)```", self.text, flags=re.S)
        self.assertIsNotNone(example)
        repo = make_repo()
        (repo / "apps/api").mkdir(parents=True)
        (repo / "apps/api/a.py").write_text("x\n")
        commit_all(repo, "feat: scaffold")
        memory.record(str(repo), "apps/api", example.group(1))
        first = memory.index(str(repo)).splitlines()[0]
        self.assertTrue(first.startswith("apps/api: "))
        self.assertGreater(len(first), len("apps/api: ") + 10)

    def test_subagents_are_told_about_the_map_and_rules_still_fit(self):
        rules = (ROOT / "plugin/payload/subagent-rules.md").read_text()
        self.assertIn(".harness/memory slice", rules)
        self.assertLess(len(rules), 3000)

    def test_delivery_checks_the_map_first(self):
        text = (ROOT / "plugin/skills/entregar/SKILL.md").read_text()
        self.assertIn(".harness/memory check", text)
        self.assertIn("mapear", text)

    def test_generated_agents_md_fits_and_conf_documents_the_keys(self):
        repo = make_repo()
        sync(repo)
        agents = (repo / "AGENTS.md").read_text()
        self.assertIn(".harness/memory", agents)
        self.assertLess(len(agents.encode("utf-8")), 8 * 1024)
        conf = (repo / "harness.conf").read_text()
        for key in ("# MAP_DEPTH=2", "# MAP_EXCLUDE=", "# ADR_REVIEW_COMMITS=20"):
            self.assertIn(key, conf)

    def test_memory_script_is_installed_and_runs_in_a_project(self):
        repo = make_repo()
        sync(repo)
        r = subprocess.run([str(repo / ".harness/memory"), "check"], cwd=repo, capture_output=True, text=True)
        self.assertIn("mapa:", r.stdout)


if __name__ == "__main__":
    unittest.main()
