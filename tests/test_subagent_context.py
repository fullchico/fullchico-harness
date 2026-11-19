import json
import unittest

from tests.helpers import ROOT, make_repo, run_hook, sync

RULES = ROOT / "plugin/payload/subagent-rules.md"


def start(agent, **extra):
    payload = dict({"hook_event_name": "SubagentStart", "agent_type": agent, "agent_id": "a1"}, **extra)
    return run_hook("subagent_context.py", payload)


class TestSubagentContext(unittest.TestCase):
    def test_implementers_and_project_agents_get_the_rules(self):
        for agent in ("harness:implementador", "backend", "general-purpose", "Explore"):
            rc, out, _ = start(agent)
            self.assertEqual(rc, 0, agent)
            hook = json.loads(out)["hookSpecificOutput"]
            self.assertEqual(hook["hookEventName"], "SubagentStart")
            self.assertEqual(hook["additionalContext"], RULES.read_text().strip())

    def test_reviewers_get_nothing(self):
        for agent in ("harness:seguranca", "harness:revisor", "harness:revisor-spec"):
            self.assertEqual(start(agent)[:2], (0, ""), agent)

    def test_bad_input_is_silent(self):
        for raw in ("", "{nao json", "[]", '{"agent_type": 3}'):
            self.assertEqual(run_hook("subagent_context.py", None, raw=raw)[:2], (0, ""), raw)

    def test_rules_fit_and_name_the_boundaries(self):
        text = RULES.read_text()
        self.assertLess(len(text), 3000)
        for token in (".env", "tdd", "remoto", "ambiente", "commit", "spec"):
            self.assertIn(token, text)
        for forbidden in ("git push", "docker compose up", "--no-verify"):
            self.assertNotIn(forbidden, text)

    def test_settings_register_the_hook(self):
        repo = make_repo()
        sync(repo)
        settings = json.loads((repo / ".claude/settings.json").read_text())
        commands = [h["command"] for group in settings["hooks"]["SubagentStart"] for h in group["hooks"]]
        self.assertTrue(any("python3 -I " in c and ".harness/hooks/subagent_context.py" in c for c in commands))
        self.assertTrue((repo / ".harness/subagent-rules.md").exists())


if __name__ == "__main__":
    unittest.main()
