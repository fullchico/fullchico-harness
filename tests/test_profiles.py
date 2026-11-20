"""Três perfis: fullstack TypeScript, stack livre e projeto existente.

O núcleo (processo, portões, posse) vale nos três. O que muda é quanto de arquitetura e de
stack o harness impõe.
"""
import os
import stat
import subprocess
import unittest

from tests.helpers import ROOT, _tmpdir, make_repo, sync

INSTALL = str(ROOT / "install")


def agents(repo):
    return (repo / "AGENTS.md").read_text()


class TestProfiles(unittest.TestCase):
    def test_default_is_the_standard_stack(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        text = agents(repo)
        self.assertIn("Feature-Sliced Design", text)
        self.assertIn("docs/agents/stack.md", text)
        self.assertTrue((repo / "docs/agents/stack.md").exists())
        self.assertNotIn("perfil:", text, "os marcadores de perfil não vazam para o arquivo gerado")

    def test_existing_project_keeps_its_own_architecture_and_language(self):
        repo = make_repo()
        (repo / "harness.conf").write_text("PROFILE=existente\n")
        self.assertEqual(sync(repo).returncode, 0)
        text = agents(repo)
        self.assertIn("código já usa", text)
        for imposed in ("Feature-Sliced Design", "Código em inglês", "docs/agents/stack.md", "hexagonal-architecture"):
            self.assertNotIn(imposed, text, imposed)
        self.assertFalse((repo / "docs/agents/stack.md").exists())
        for kept in ("Um dono por arquivo", "Portões de push", "DRY"):
            self.assertIn(kept, text, kept)

    def test_free_stack_keeps_the_concepts_without_the_stack(self):
        repo = make_repo()
        (repo / "harness.conf").write_text("PROFILE=livre\n")
        self.assertEqual(sync(repo).returncode, 0)
        text = agents(repo)
        for concept in ("use cases", "Código em inglês", "Contrato"):
            self.assertIn(concept, text, concept)
        for stack in ("Feature-Sliced Design", "docs/agents/stack.md"):
            self.assertNotIn(stack, text, stack)
        self.assertFalse((repo / "docs/agents/stack.md").exists())

    def test_changing_profile_removes_what_the_new_one_does_not_generate(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        self.assertTrue((repo / "docs/agents/stack.md").exists())
        (repo / "harness.conf").write_text("PROFILE=existente\n")
        self.assertEqual(sync(repo).returncode, 0)
        self.assertFalse((repo / "docs/agents/stack.md").exists())

    def test_unknown_profile_is_refused(self):
        repo = make_repo()
        (repo / "harness.conf").write_text("PROFILE=qualquer\n")
        r = sync(repo)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("PROFILE", r.stderr)

    def test_every_variant_fits_the_agents_size_limit(self):
        for profile in ("fullstack-typescript", "livre", "existente"):
            repo = make_repo()
            (repo / "harness.conf").write_text(f"PROFILE={profile}\n")
            self.assertEqual(sync(repo).returncode, 0)
            self.assertLess(len(agents(repo).encode("utf-8")), 8 * 1024, profile)


class TestInstallByProfile(unittest.TestCase):
    def run_install(self, repo, *args):
        tools = _tmpdir()
        for name, body in (("claude", 'echo "claude $*" >> "$LOG"\n'), ("npx", 'cat >/dev/null\necho "npx $*" >> "$LOG"\n')):
            script = tools / name
            script.write_text("#!/usr/bin/env bash\n" + body)
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
        log = tools / "log"
        env = dict(os.environ, PATH=f"{tools}:{os.environ['PATH']}", LOG=str(log))
        r = subprocess.run([INSTALL, str(repo), *args], env=env, capture_output=True, text=True, timeout=120)
        return r, (log.read_text() if log.exists() else "")

    def test_profile_is_recorded_and_chooses_the_skills(self):
        repo = make_repo()
        r, calls = self.run_install(repo, "--profile", "existente")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PROFILE=existente", (repo / "harness.conf").read_text())
        self.assertIn("-s clean-code-guard ", calls)
        self.assertIn("-s parallel-feature-development ", calls)
        for stack_skill in ("shadcn", "drizzle-orm-patterns", "feature-sliced-design", "hexagonal-architecture"):
            self.assertNotIn(f"-s {stack_skill} ", calls, stack_skill)

    def test_free_stack_gets_the_architecture_skills_only(self):
        repo = make_repo()
        r, calls = self.run_install(repo, "--profile", "livre")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("-s hexagonal-architecture ", calls)
        self.assertNotIn("-s shadcn ", calls)
        self.assertNotIn("-s feature-sliced-design ", calls)

    def test_unknown_profile_stops_the_install(self):
        r, _ = self.run_install(make_repo(), "--profile", "x")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
