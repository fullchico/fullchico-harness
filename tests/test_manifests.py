import json
import unittest

from tests.helpers import ROOT


class TestManifests(unittest.TestCase):
    def test_marketplace_points_to_plugin(self):
        m = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(m["name"], "fullchico")
        self.assertTrue(m["owner"]["name"])
        self.assertEqual(m["plugins"][0]["name"], "harness")
        self.assertEqual(m["plugins"][0]["source"], "./plugin")

    def test_plugin_manifest(self):
        p = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text())
        self.assertEqual(p["name"], "harness")
        self.assertRegex(p["version"], r"^\d+\.\d+\.\d+$")

    def test_map_has_spec_paths_and_only_agent_invocable_cycle_skills(self):
        m = json.loads((ROOT / "plugin/map.json").read_text())
        self.assertEqual(m["spec_glob"], "docs/specs/*/spec.md")
        self.assertEqual(m["tickets_glob"], "docs/specs/*/issues/*.md")
        cycle = {s["skill"] for s in m["steps"] if s["step"] != "avulsa-dono"}
        self.assertTrue({"grilling", "domain-modeling", "tdd", "pr"} <= cycle)
        self.assertFalse(cycle & {"to-spec", "to-tickets", "implement-spec", "grill-with-docs"})

    def test_no_personal_paths_in_plugin(self):
        for f in (ROOT / "plugin").rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                text = f.read_text(errors="ignore")
                self.assertNotIn("/Users/", text, f)


if __name__ == "__main__":
    unittest.main()
