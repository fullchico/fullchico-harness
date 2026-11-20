"""Buscar skills para a stack do projeto: procurar, ler, e só instalar com o sim do dono."""
import json
import os
import stat
import subprocess
import sys
import unittest

from tests.helpers import ROOT, _tmpdir, make_repo, run_hook, sync

sys.path.insert(0, str(ROOT / "plugin/payload"))
import skills_remote  # noqa: E402


class TestPureParts(unittest.TestCase):
    def test_search_results_are_reduced_to_what_matters(self):
        raw = json.dumps({"skills": [{"skillId": "zod", "source": "anivar/zod-skill", "installs": 1237, "x": "y"},
                                     {"name": "outro", "topSource": "a/b", "installs": 5}, {"skillId": "ruim"}]})
        self.assertEqual(skills_remote.parse_search(raw),
                         [{"skill": "zod", "repo": "anivar/zod-skill", "installs": 1237},
                          {"skill": "outro", "repo": "a/b", "installs": 5}])
        self.assertEqual(skills_remote.parse_search("não é json"), [])

    def test_skill_folder_is_found_in_the_repository_tree(self):
        tree = ["README.md", "skills/zod/SKILL.md", "skills/zod/references/a.md", "plugins/x/skills/zod-extra/SKILL.md", "SKILL.md"]
        self.assertEqual(skills_remote.skill_folder(tree, "zod"), "skills/zod")
        self.assertEqual(skills_remote.skill_folder(tree, "zod-extra"), "plugins/x/skills/zod-extra")
        self.assertEqual(skills_remote.skill_folder(["SKILL.md", "a.md"], "qualquer"), "")
        self.assertIsNone(skills_remote.skill_folder(tree, "nao-existe"))

    def test_only_plain_names_reach_the_network(self):
        for good in ("nestjs", "react-hook-form", "next.js", "c++"[:1]):
            self.assertTrue(skills_remote.valid_term(good), good)
        for bad in ("", "a b", "a;b", "$(x)", "x" * 41, "../x", "a/b"):
            self.assertFalse(skills_remote.valid_term(bad), bad)
        self.assertTrue(skills_remote.valid_repo("vercel-labs/agent-skills"))
        for bad in ("vercel-labs", "a/b/c", "a/..", "a/b;rm", "https://x/y"):
            self.assertFalse(skills_remote.valid_repo(bad), bad)


class TestCommands(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)

    def test_settings_search_freely_and_ask_before_installing(self):
        s = json.loads((self.repo / ".claude/settings.json").read_text())
        for name in ("skills-search", "skills-show", "skills-add"):
            self.assertIn(f".harness/{name} *", s["sandbox"]["excludedCommands"])
        for name in ("skills-search", "skills-show"):
            self.assertIn(f"Bash(.harness/{name} *)", s["permissions"]["allow"])
        self.assertIn("Bash(.harness/skills-add *)", s["permissions"]["ask"])
        self.assertNotIn("Bash(.harness/skills-add *)", s["permissions"]["allow"])

    def test_guard_accepts_the_plain_forms_only(self):
        bash = lambda c: run_hook("service_guard.py", {"tool_name": "Bash", "cwd": str(self.repo), "tool_input": {"command": c}})[0]
        for ok in (".harness/skills-search nestjs", ".harness/skills-show anivar/zod-skill zod",
                   ".harness/skills-add anivar/zod-skill zod"):
            self.assertEqual(bash(ok), 0, ok)
        for bad in (".harness/skills-search nestjs | head", "x && .harness/skills-add a/b c", ".harness/skills-search $(cat .env)"):
            self.assertEqual(bash(bad), 2, bad)

    def test_bad_arguments_never_leave_the_machine(self):
        for args in (["skills-search", "a b"], ["skills-search"], ["skills-show", "semrepo", "x"], ["skills-add", "a/b", "x;y"]):
            r = subprocess.run([str(self.repo / ".harness" / args[0]), *args[1:]], cwd=self.repo, capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, args)

    def test_add_installs_into_the_project_with_the_skills_cli(self):
        tools = _tmpdir()
        npx = tools / "npx"
        npx.write_text('#!/usr/bin/env bash\necho "$PWD|$*" >> "$LOG"\n')
        npx.chmod(npx.stat().st_mode | stat.S_IXUSR)
        log = tools / "log"
        r = subprocess.run([str(self.repo / ".harness/skills-add"), "anivar/zod-skill", "zod"], cwd=self.repo,
                           capture_output=True, text=True, env=dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}", LOG=str(log)))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("skills add anivar/zod-skill -s zod -a claude-code -y --copy", log.read_text())
        self.assertTrue(log.read_text().startswith(str(self.repo.resolve())))

    def test_skill_is_owner_invoked_and_asks_before_installing(self):
        text = (ROOT / "plugin/skills/buscar-skills/SKILL.md").read_text()
        self.assertIn("disable-model-invocation: true", text)
        for needed in (".harness/skills-search", ".harness/skills-show", ".harness/skills-add", "pergunte", "dado"):
            self.assertIn(needed, text, needed)


if __name__ == "__main__":
    unittest.main()
