import json
import os
import subprocess
import time
import unittest

from tests.helpers import ROOT, _tmpdir, commit_all, git, make_repo, sync
import common

CONF = ('PROJECT=meuapp\nSERVICES="web db"\nCOMPOSE_FILE=docker-compose.dev.yml\n'
        'AFTER_UP=\'echo "$WEB_PORT" > out-after.txt\'\nDEV_CMD="sleep 60"\n')
CLEAN = {"name": "p", "services": {"db": {"image": "postgres:16", "ports": [{"published": "25432", "target": 5432}]}}}


class EnvCase(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo("feature dir")
        self.assertEqual(sync(self.repo).returncode, 0)
        (self.repo / "harness.conf").write_text(CONF)
        (self.repo / "docker-compose.dev.yml").write_text("services: {}\n")
        commit_all(self.repo, "chore: adopt harness")
        tmp = _tmpdir()
        self.bin = tmp / "bin"
        self.bin.mkdir()
        os.symlink(ROOT / "tests/fake_docker", self.bin / "docker")
        self.log = tmp / "docker.log"
        self.config = tmp / "config.json"
        self.config.write_text(json.dumps(CLEAN))
        self.addCleanup(self.stop_dev, self.repo)

    def env(self, **extra):
        base = {k: v for k, v in os.environ.items() if k not in ("CONDUCTOR_PORT", "HARNESS_ENV")}
        base.update(PATH=f"{self.bin}:{os.environ['PATH']}", FAKE_DOCKER_LOG=str(self.log),
                    FAKE_DOCKER_CONFIG=str(self.config))
        base.update(extra)
        return base

    def run_script(self, name, *args, repo=None, **extra):
        repo = repo or self.repo
        return subprocess.run([str(repo / ".harness" / name), *args], cwd=repo, env=self.env(**extra),
                              capture_output=True, text=True)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def dotenv(self, repo=None):
        text = ((repo or self.repo) / ".env").read_text()
        return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)

    def stop_dev(self, repo):
        pid_file = repo / ".harness-run/dev.pid"
        if pid_file.exists():
            subprocess.run(["kill", pid_file.read_text().strip()], capture_output=True)

    def worktree(self, path, branch=None):
        args = ["worktree", "add", "-q", str(path)] + (["-b", branch] if branch else ["--detach"])
        git(self.repo, *args)
        self.addCleanup(self.stop_dev, path)
        return path


class TestUp(EnvCase):
    def test_up_runs_env_then_check_then_compose_up(self):
        r = self.run_script("up")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        config = next(i for i, c in enumerate(calls) if "config --format json" in c)
        up = next(i for i, c in enumerate(calls) if "up -d --wait" in c)
        self.assertLess(config, up)
        self.assertIn("-p meuapp-feature-dir", calls[up])
        self.assertIn("docker-compose.dev.yml", calls[up])
        self.assertEqual(self.dotenv()["COMPOSE_PROJECT_NAME"], "meuapp-feature-dir")

    def test_up_refuses_violating_compose(self):
        self.config.write_text(json.dumps({"services": {"db": {"image": "x", "privileged": True}}}))
        r = self.run_script("up")
        self.assertEqual(r.returncode, 1)
        self.assertIn("db", r.stderr)
        self.assertFalse(any("up -d" in c for c in self.calls()))

    def test_up_refuses_when_compose_config_fails(self):
        r = self.run_script("up", FAKE_DOCKER_RC="1")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(any("up -d" in c for c in self.calls()))

    def test_up_does_not_run_project_commands(self):
        (self.repo / "harness.conf").write_text(CONF.replace('DEV_CMD="sleep 60"', 'DEV_CMD="touch ran-dev"'))
        self.assertEqual(self.run_script("up").returncode, 0)
        self.assertFalse((self.repo / "out-after.txt").exists())
        self.assertFalse((self.repo / "ran-dev").exists())

    def test_up_mounts_the_rails_read_only_in_a_container_that_sees_the_project(self):
        app = {"image": "node:24", "volumes": [{"type": "bind", "source": str(self.repo), "target": "/work"}]}
        self.config.write_text(json.dumps({"name": "p", "services": {"app": app}}))
        self.assertEqual(self.run_script("up").returncode, 0)
        up = next(c for c in self.calls() if "up -d --wait" in c)
        override = up.split(" -f ")[2].split(" ")[0]
        self.assertFalse(override.startswith(str(self.repo)), "o agente não pode alcançar este arquivo")
        with open(override) as f:
            mounts = json.load(f)["services"]["app"]["volumes"]
        self.assertIn("/work/.harness", [m["target"] for m in mounts])

    def test_up_without_project_mount_uses_only_the_project_compose(self):
        self.assertEqual(self.run_script("up").returncode, 0)
        up = next(c for c in self.calls() if "up -d --wait" in c)
        self.assertEqual(up.count(" -f "), 1)

    def test_up_prints_summary(self):
        out = self.run_script("up").stdout
        self.assertIn("db", out)
        self.assertIn("postgres:16", out)

    def test_up_registers_owner_and_destroy_clears_it(self):
        feature = self.worktree(self.repo.parent / "roseau", "feat/x")
        self.assertEqual(self.run_script("up", repo=feature).returncode, 0)
        record = os.path.join(common.state_dir(str(feature)), "envs", "roseau.json")
        with open(record, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["worktree"], str(feature))
        self.assertEqual(str(data["base"]), self.dotenv(feature)["WEB_PORT"])
        self.assertEqual(self.run_script("destroy", repo=feature).returncode, 0)
        self.assertFalse(os.path.exists(record))

    def test_agent_worktree_does_not_recreate(self):
        feature = self.worktree(self.repo.parent / "roseau", "feat/x")
        self.assertEqual(self.run_script("up", repo=feature).returncode, 0)
        agent = self.worktree(feature / ".claude/worktrees/agent-a1")
        r = self.run_script("up", repo=agent, FAKE_DOCKER_RUNNING="1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(str(feature), r.stdout)
        self.assertEqual(sum("up -d" in c for c in self.calls()), 1)
        self.assertEqual(self.dotenv(agent)["WEB_PORT"], self.dotenv(feature)["WEB_PORT"])


class TestPrepareAndDev(EnvCase):
    def test_prepare_runs_after_up_with_env(self):
        self.run_script("up")
        r = self.run_script("prepare")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.repo / "out-after.txt").read_text().strip(), self.dotenv()["WEB_PORT"])

    def test_prepare_without_after_up_is_ok(self):
        (self.repo / "harness.conf").write_text('PROJECT=x\nSERVICES=web\nCOMPOSE_FILE=docker-compose.dev.yml\n')
        self.run_script("up")
        self.assertEqual(self.run_script("prepare").returncode, 0)

    def test_prepare_propagates_failure(self):
        (self.repo / "harness.conf").write_text(CONF.replace("AFTER_UP='echo \"$WEB_PORT\" > out-after.txt'", 'AFTER_UP="exit 7"'))
        self.run_script("up")
        self.assertEqual(self.run_script("prepare").returncode, 7)

    def test_dev_background_writes_pid_and_log_and_down_stops_it(self):
        self.run_script("up")
        r = self.run_script("dev", "--background")
        self.assertEqual(r.returncode, 0, r.stderr)
        pid = int((self.repo / ".harness-run/dev.pid").read_text())
        os.kill(pid, 0)
        self.assertTrue((self.repo / ".harness-run/dev.log").exists())
        self.assertEqual(self.run_script("down").returncode, 0)
        time.sleep(0.5)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertTrue(any(c.rstrip().endswith("stop") for c in self.calls()))

    def test_dev_refuses_second_instance(self):
        self.run_script("up")
        self.assertEqual(self.run_script("dev", "--background").returncode, 0)
        r = self.run_script("dev", "--background")
        self.assertEqual(r.returncode, 1)
        self.assertIn("já", r.stderr)

    def test_logs_shows_state_and_tail_of_the_environment(self):
        self.run_script("up")
        self.assertEqual(self.run_script("logs").returncode, 0)
        self.assertEqual(self.run_script("logs", "app").returncode, 0)
        calls = self.calls()
        self.assertTrue(any(c.endswith(" ps") for c in calls))
        self.assertTrue(any("logs --tail" in c and c.endswith(" app") for c in calls))
        r = self.run_script("logs", "--follow")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(any("--follow" in c for c in self.calls()))

    def test_logs_is_reachable_from_the_sandbox_by_everyone(self):
        s = json.loads((self.repo / ".claude/settings.json").read_text())
        for form in (".harness/logs", ".harness/logs *"):
            self.assertIn(form, s["sandbox"]["excludedCommands"])
            self.assertIn(f"Bash({form})", s["permissions"]["allow"])

    def test_dev_without_command_explains(self):
        (self.repo / "harness.conf").write_text('PROJECT=x\nSERVICES=web\nCOMPOSE_FILE=docker-compose.dev.yml\n')
        r = self.run_script("dev")
        self.assertEqual(r.returncode, 1)
        self.assertIn("DEV_CMD", r.stderr)

    def test_scripts_write_nothing_under_harness_dir(self):
        self.run_script("up")
        self.run_script("prepare")
        self.run_script("dev", "--background")
        self.run_script("down")
        status = git(self.repo, "status", "--short")
        self.assertNotIn(".harness/", status)
        self.assertNotIn(".harness-run", status)


class TestDestroy(EnvCase):
    def test_destroy_refuses_main_checkout(self):
        self.run_script("up")
        r = self.run_script("destroy")
        self.assertEqual(r.returncode, 1)
        self.assertIn("principal", r.stderr)
        self.assertFalse(any("down -v" in c for c in self.calls()))

    def test_destroy_refuses_context_equal_to_main(self):
        self.run_script("up")
        feature = self.worktree(self.repo.parent / "roseau", "feat/x")
        r = self.run_script("destroy", repo=feature, HARNESS_ENV="feature dir")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(any("down -v" in c for c in self.calls()))

    def test_destroy_removes_only_its_feature_project(self):
        feature = self.worktree(self.repo.parent / "roseau", "feat/x")
        self.run_script("up", repo=feature)
        r = self.run_script("destroy", repo=feature)
        self.assertEqual(r.returncode, 0, r.stderr)
        down = [c for c in self.calls() if "down -v --rmi local --remove-orphans" in c]
        self.assertEqual(len(down), 1)
        self.assertIn("-p meuapp-roseau", down[0])


class TestMissingPieces(EnvCase):
    def test_missing_compose_file_key_or_file_explains(self):
        (self.repo / "harness.conf").write_text('PROJECT=x\nSERVICES=web\n')
        r = self.run_script("up")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("COMPOSE_FILE", r.stderr)
        (self.repo / "harness.conf").write_text('PROJECT=x\nSERVICES=web\nCOMPOSE_FILE=nao-existe.yml\n')
        r = self.run_script("up")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nao-existe.yml", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_missing_docker_explains(self):
        r = subprocess.run([str(self.repo / ".harness/up")], cwd=self.repo,
                           env=dict(self.env(), PATH="/usr/bin:/bin"), capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("docker", r.stderr.lower())


if __name__ == "__main__":
    unittest.main()
