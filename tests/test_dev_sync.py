"""O dev-sync leva o plugin local para a pasta que o projeto carrega, sem publicar."""
import json
import os
import subprocess
import unittest

from tests.helpers import ROOT, _tmpdir, make_repo


class DevSyncTest(unittest.TestCase):
    def test_copies_the_local_plugins_into_the_folders_the_project_loads(self):
        home, project = _tmpdir(), make_repo()
        cache = home / ".claude/plugins/cache/fullchico"
        (cache / "tr/2.0.0").mkdir(parents=True)
        (cache / "tr/2.0.0/velho.txt").write_text("versão instalada")
        (home / ".claude/plugins/installed_plugins.json").write_text(json.dumps({"plugins": {
            "tr@fullchico": [{"projectPath": str(project), "installPath": str(cache / "tr/2.0.0")},
                             {"projectPath": "/outro/projeto", "installPath": str(cache / "tr/1.0.0")}]}}))
        run = subprocess.run([str(ROOT / "tools/dev-sync"), str(project)], capture_output=True, text=True,
                             env=dict(os.environ, HOME=str(home)))
        self.assertEqual(run.returncode, 0, run.stderr)
        loaded = cache / "tr/2.0.0"
        self.assertTrue((loaded / "scripts/certs.py").exists(), "o código daqui está onde o projeto carrega")
        self.assertFalse((loaded / "velho.txt").exists(), "nada da versão antiga sobra")
        self.assertIn("commit", json.loads((loaded / ".dev-sync.json").read_text()))
        self.assertFalse((cache / "tr/1.0.0").exists(), "outro projeto não é tocado")


if __name__ == "__main__":
    unittest.main()
