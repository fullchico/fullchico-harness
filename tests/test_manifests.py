import json
import unittest

from tests.helpers import ROOT


class TestManifests(unittest.TestCase):
    def test_marketplace_lists_each_plugin_folder(self):
        m = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(m["name"], "fullchico")
        self.assertTrue(m["owner"]["name"])
        for entry in m["plugins"]:
            manifest = json.loads((ROOT / entry["source"] / ".claude-plugin/plugin.json").read_text())
            self.assertEqual(manifest["name"], entry["name"])
            self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")

    def test_no_personal_paths_in_plugins(self):
        for f in (ROOT / "plugins").rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                self.assertNotIn("/Users/", f.read_text(errors="ignore"), f)


if __name__ == "__main__":
    unittest.main()
