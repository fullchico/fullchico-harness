import json
import os
import subprocess
import sys
import unittest

from tests.helpers import HOOKS, ROOT, _tmpdir, commit_all, make_repo, sync

FORMS = [prefix + name for name in ("up", "down", "destroy") for prefix in (".harness/", "./.harness/")]
CLEAN = {"name": "p", "services": {"db": {"image": "postgres:16"}}}


def settings(repo):
    return json.loads((repo / ".claude/settings.json").read_text())


class TestEnvSettings(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        self.s = settings(self.repo)

    def test_only_exact_env_commands_leave_the_sandbox_and_only_destroy_asks(self):
        excluded = self.s["sandbox"]["excludedCommands"]
        for form in FORMS:
            self.assertIn(form, excluded)
            # Mínimo de interrupção: só o que apaga dados pergunta ao dono.
            asks = form.endswith("destroy")
            self.assertEqual(f"Bash({form})" in self.s["permissions"]["ask"], asks, form)
            self.assertEqual(f"Bash({form})" in self.s["permissions"]["allow"], not asks, form)
        # nada além dos scripts do harness sai do sandbox, e nenhum deles com argumento livre,
        # exceto o pr, os de skills e o logs, que recebem nomes simples como argumento e os conferem
        self.assertTrue(all(c.lstrip("./").startswith("harness/") for c in excluded), excluded)
        with_args = {f"{prefix}.harness/{name} *" for prefix in ("", "./")
                     for name in ("pr", "skills-search", "skills-show", "skills-add", "logs")}
        self.assertEqual({c for c in excluded if "*" in c}, with_args)

    def test_network(self):
        net = self.s["sandbox"]["network"]
        self.assertIs(net["allowLocalBinding"], True)
        self.assertIn("registry.npmjs.org", net["allowedDomains"])
        self.assertIn("github.com", net["deniedDomains"])

    def test_package_manager_caches_are_writable(self):
        for path in ("~/.npm", "~/Library/pnpm", "~/.local/share/pnpm", "~/.yarn", "~/.bun/install/cache"):
            self.assertIn(path, self.s["sandbox"]["filesystem"]["allowWrite"])

    def test_generated_integration_files_are_write_protected(self):
        for path in ("orca.yaml", ".conductor"):
            self.assertIn(path, self.s["sandbox"]["filesystem"]["denyWrite"])

    def test_fragment_adds_but_cannot_remove(self):
        (self.repo / "harness.d").mkdir()
        (self.repo / "harness.d/settings.json").write_text(json.dumps({
            "sandbox": {"network": {"allowedDomains": ["api.exemplo.com"], "allowLocalBinding": False},
                        "excludedCommands": []},
            "permissions": {"ask": []}}))
        self.assertEqual(sync(self.repo).returncode, 0)
        s = settings(self.repo)
        self.assertIn("api.exemplo.com", s["sandbox"]["network"]["allowedDomains"])
        self.assertIn("registry.npmjs.org", s["sandbox"]["network"]["allowedDomains"])
        self.assertIs(s["sandbox"]["network"]["allowLocalBinding"], True)
        self.assertIn("Bash(.harness/destroy)", s["permissions"]["ask"])
        self.assertIn(".harness/up", s["sandbox"]["excludedCommands"])


class TestAskWithSummary(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo("roseau")
        (self.repo / "harness.conf").write_text('PROJECT=meuapp\nSERVICES="web db"\nCOMPOSE_FILE=dc.yml\n')
        (self.repo / "dc.yml").write_text("services: {}\n")
        self.assertEqual(sync(self.repo).returncode, 0)
        commit_all(self.repo, "chore: adopt harness")
        tmp = _tmpdir()
        (tmp / "bin").mkdir()
        os.symlink(ROOT / "tests/fake_docker", tmp / "bin/docker")
        self.config = tmp / "config.json"
        self.config.write_text(json.dumps(CLEAN))
        self.path = f"{tmp / 'bin'}:{os.environ['PATH']}"

    def ask(self, command, **extra):
        env = dict(os.environ, PATH=self.path, FAKE_DOCKER_CONFIG=str(self.config), **extra)
        payload = {"tool_name": "Bash", "cwd": str(self.repo), "tool_input": {"command": command}}
        r = subprocess.run([sys.executable, str(HOOKS / "service_guard.py")], input=json.dumps(payload),
                           capture_output=True, text=True, env=env)
        return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else None)

    def test_up_and_down_do_not_interrupt_the_owner(self):
        for form in (".harness/up", "./.harness/up", "  .harness/up  ", ".harness/down"):
            self.assertEqual(self.ask(form), (0, None), form)

    def test_destroy_reason_names_the_project_and_says_data_is_deleted(self):
        _, out = self.ask(".harness/destroy")
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertIn("meuapp-roseau", reason)
        self.assertIn("apaga", reason.lower())

    def test_other_forms_get_no_special_treatment(self):
        for c in (".harness/validate --profile push", ".harness/prepare", "git status"):
            self.assertEqual(self.ask(c), (0, None), c)
        # Fora da forma exata o script cairia no sandbox: agora é negado, com o motivo.
        for c in ("bash .harness/up", ".harness/up --force", "cd x && .harness/up"):
            self.assertEqual(self.ask(c)[0], 2, c)

    def test_hook_skip_flags_still_denied(self):
        self.assertEqual(self.ask("git push --no-verify")[0], 2)


if __name__ == "__main__":
    unittest.main()
