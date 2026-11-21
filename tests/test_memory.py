import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, git, make_repo, sync

sys.path.insert(0, str(ROOT / "plugin/payload"))
import memory  # noqa: E402
import common  # noqa: E402

SCRIPT = str(ROOT / "plugin/payload/memory")


def project(name="proj dir"):
    repo = make_repo(name)
    for path in ("apps/api/src/users/service.py", "apps/api/src/orders/service.py", "apps/web/page.tsx",
                 "packages/shared/types.ts", "docs/guia.md", ".github/ci.yml", "Makefile",
                 "apps/api/módulo com espaço/arquivo.py"):
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n")
    commit_all(repo, "feat: scaffold")
    return repo


def cli(repo, *args, stdin=None):
    return subprocess.run([SCRIPT, *args], cwd=repo, capture_output=True, text=True, input=stdin)


class TestUnits(unittest.TestCase):
    def test_units_respect_depth_and_exclusions(self):
        repo = project()
        self.assertEqual(memory.units(str(repo)), [".", "apps/api", "apps/web", "packages/shared"])

    def test_depth_and_exclusions_come_from_the_conf(self):
        repo = project()
        (repo / "harness.conf").write_text('MAP_DEPTH=1\nMAP_EXCLUDE="docs .github packages"\n')
        commit_all(repo, "chore: conf")
        self.assertEqual(memory.units(str(repo)), [".", "apps"])

    def test_empty_repo_has_only_the_root_unit(self):
        self.assertEqual(memory.units(str(make_repo())), ["."])


class TestRecordAndStatus(unittest.TestCase):
    def setUp(self):
        self.repo = project()
        self.root = str(self.repo)

    def test_record_then_fresh_then_stale(self):
        memory.record(self.root, "apps/api", "Serviço HTTP.\nDetalhe.")
        status = memory.status(self.root)
        self.assertEqual(status["fresh"], ["apps/api"])
        self.assertEqual(status["missing"], [".", "apps/web", "packages/shared"])
        (self.repo / "apps/api/src/users/service.py").write_text("mudou\n")
        self.assertEqual(memory.status(self.root)["stale"], ["apps/api"], "mudança sem commit já conta")
        commit_all(self.repo, "fix: users")
        self.assertEqual(memory.status(self.root)["stale"], ["apps/api"])
        memory.record(self.root, "apps/api", "Serviço HTTP, atualizado.")
        self.assertEqual(memory.status(self.root)["fresh"], ["apps/api"])

    def test_change_in_another_unit_does_not_age_this_one(self):
        memory.record(self.root, "apps/api", "Serviço HTTP.")
        (self.repo / "apps/web/page.tsx").write_text("mudou\n")
        commit_all(self.repo, "fix: web")
        self.assertEqual(memory.status(self.root)["fresh"], ["apps/api"])

    def test_removed_unit_is_orphan(self):
        memory.record(self.root, "apps/web", "Tela.")
        git(self.repo, "rm", "-rq", "apps/web")
        commit_all(self.repo, "refactor: drop web")
        status = memory.status(self.root)
        self.assertEqual(status["orphan"], ["apps/web"])
        self.assertNotIn("apps/web", status["stale"] + status["fresh"])

    def test_anchor_on_a_commit_that_no_longer_exists_is_stale(self):
        git(self.repo, "checkout", "-q", "-b", "tmp")
        (self.repo / "apps/api/novo.py").write_text("x\n")
        commit_all(self.repo, "feat: temp")
        memory.record(self.root, "apps/api", "Serviço HTTP.")
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "branch", "-q", "-D", "tmp")
        git(self.repo, "reflog", "expire", "--expire=now", "--all")
        git(self.repo, "gc", "-q", "--prune=now")
        self.assertEqual(memory.status(self.root)["stale"], ["apps/api"])

    def test_record_refuses_bad_input(self):
        for unit, text in (("apps/naoexiste", "x"), ("../fora", "x"), ("/etc", "x"), ("apps/api/src", "x"),
                           ("apps/api", ""), ("apps/api", "x" * 1501)):
            with self.assertRaises(ValueError, msg=unit):
                memory.record(self.root, unit, text)

    def test_slice_and_index(self):
        memory.record(self.root, "apps/api", "Serviço HTTP.\nUsa packages/shared.")
        memory.record(self.root, ".", "Raiz do monorepo.")
        text = memory.slice_for(self.root, ["apps/api/src/users/service.py", "Makefile"])
        self.assertIn("Serviço HTTP.", text)
        self.assertIn("Raiz do monorepo.", text)
        self.assertNotIn("apps/web", text)
        self.assertIn("sem resumo", memory.slice_for(self.root, ["apps/web/page.tsx"]))
        index = memory.index(self.root)
        self.assertIn("apps/api: Serviço HTTP.", index)
        self.assertNotIn("Usa packages/shared.", index)
        (self.repo / "apps/api/src/users/service.py").write_text("mudou\n")
        self.assertIn("envelhec", memory.slice_for(self.root, ["apps/api"]))

    def test_memory_is_shared_between_worktrees_and_invisible_to_git(self):
        memory.record(self.root, "apps/api", "Serviço HTTP.")
        wt = self.repo.parent / "wt two"
        git(self.repo, "worktree", "add", "-q", str(wt), "-b", "feat/x")
        self.assertEqual(memory.status(str(wt))["fresh"], ["apps/api"])
        self.assertEqual(git(self.repo, "status", "--short"), "")
        self.assertTrue(common.memory_dir(self.root).endswith("/.git/harness-memory"))


class TestCli(unittest.TestCase):
    def test_commands(self):
        repo = project()
        self.assertEqual(cli(repo, "units").stdout.split("\n")[:2], [".", "apps/api"])
        r = cli(repo, "check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("apps/api", r.stdout)
        (repo / "resumo.md").write_text("Serviço HTTP.\n")
        for unit in memory.units(str(repo)):
            self.assertEqual(cli(repo, "record", unit, "resumo.md").returncode, 0, unit)
        (repo / "resumo.md").unlink()
        r = cli(repo, "check")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("Serviço HTTP.", cli(repo, "show", "apps/api").stdout)
        self.assertIn("Serviço HTTP.", cli(repo, "slice", "apps/api/src").stdout)
        self.assertIn("apps/web: Serviço HTTP.", cli(repo, "index").stdout)
        self.assertEqual(cli(repo, "forget", "apps/web").returncode, 0)
        self.assertIn("apps/web", cli(repo, "check").stdout)
        self.assertEqual(cli(repo, "record", "apps/api", "/nao/existe").returncode, 1)
        self.assertEqual(cli(repo, "comando-inexistente").returncode, 2)
        self.assertEqual(cli(repo, "slice", "--", "-começa-com-hífen").returncode, 0)

    def test_runs_from_a_synced_project_and_a_subdirectory(self):
        repo = project()
        sync(repo)
        r = subprocess.run([str(repo / ".harness/memory"), "units"], cwd=repo / "apps", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("apps/api", r.stdout)


if __name__ == "__main__":
    unittest.main()
