"""Ambiente de verdade: duas features lado a lado, com Docker real."""
import json
import os
import socket
import subprocess
import unittest

from tests.helpers import commit_all, git, make_repo, sync

IMAGE = "redis:7-alpine"
COMPOSE = """services:
  cache:
    image: redis:7-alpine
    ports:
      - "127.0.0.1:${CACHE_PORT}:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 1s
      timeout: 2s
      retries: 20
"""


def docker_ready() -> bool:
    try:
        ok = subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
        return ok and subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True,
                                     timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ping(port) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), 3) as s:
            s.sendall(b"PING\r\n")
            return s.recv(16).startswith(b"+PONG")
    except OSError:
        return False


@unittest.skipUnless(docker_ready(), f"Docker indisponível ou imagem {IMAGE} ausente")
class TestTwoFeaturesWithRealDocker(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo("principal")
        self.assertEqual(sync(self.repo).returncode, 0)
        (self.repo / "harness.conf").write_text('PROJECT=harnesstest\nSERVICES="cache"\nCOMPOSE_FILE=dc.yml\n')
        (self.repo / "dc.yml").write_text(COMPOSE)
        commit_all(self.repo, "chore: adopt harness")
        self.a = self.worktree(self.repo.parent / "feat-a", "feat/a")
        self.b = self.worktree(self.repo.parent / "feat-b", "feat/b")
        self.agent = self.worktree(self.a / ".claude/worktrees/agent-x")
        self.env = {k: v for k, v in os.environ.items() if k not in ("CONDUCTOR_PORT", "HARNESS_ENV")}
        self.addCleanup(self.cleanup)

    def worktree(self, path, branch=None):
        args = ["worktree", "add", "-q", str(path)] + (["-b", branch] if branch else ["--detach"])
        git(self.repo, *args)
        return path

    def cleanup(self):
        for name in ("harnesstest-feat-a", "harnesstest-feat-b", "harnesstest-principal"):
            subprocess.run(["docker", "compose", "-p", name, "down", "-v", "--remove-orphans"],
                           capture_output=True, timeout=120)

    def run_script(self, repo, name, *args):
        return subprocess.run([str(repo / ".harness" / name), *args], cwd=repo, env=self.env,
                              capture_output=True, text=True, timeout=300)

    def port(self, repo):
        text = (repo / ".env").read_text()
        return dict(l.split("=", 1) for l in text.splitlines() if "=" in l)["CACHE_PORT"]

    def containers(self, project):
        out = subprocess.run(["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={project}"],
                             capture_output=True, text=True).stdout.split()
        return out

    def test_two_features_and_an_agent_worktree(self):
        for feature in (self.a, self.b):
            r = self.run_script(feature, "up")
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertNotEqual(self.port(self.a), self.port(self.b))
        self.assertTrue(ping(self.port(self.a)))
        self.assertTrue(ping(self.port(self.b)))

        # o worktree de agente dentro de A usa o ambiente de A e não sobe nada
        self.assertEqual(self.run_script(self.agent, "worktree-env").returncode, 0)
        self.assertEqual(self.port(self.agent), self.port(self.a))
        r = self.run_script(self.agent, "up")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(str(self.a), r.stdout)
        self.assertEqual(len(self.containers("harnesstest-feat-a")), 1)

        # remover B não toca em A
        r = self.run_script(self.b, "destroy")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.containers("harnesstest-feat-b"), [])
        self.assertTrue(ping(self.port(self.a)))

        # o checkout principal não é removido por aqui
        self.assertEqual(self.run_script(self.repo, "destroy").returncode, 1)

        # parar mantém o contêiner, parado
        self.assertEqual(self.run_script(self.a, "down").returncode, 0)
        self.assertFalse(ping(self.port(self.a)))

    def test_compose_that_mounts_the_home_dir_is_refused_by_the_real_docker_config(self):
        (self.a / "dc.yml").write_text(COMPOSE + "    volumes:\n      - ${HOME}/.claude:/escape\n")
        r = self.run_script(self.a, "up")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fora do projeto", r.stderr)
        self.assertEqual(self.containers("harnesstest-feat-a"), [])

    def test_escapes_found_in_review_are_refused_with_the_real_docker_config(self):
        escapes = {
            "volume nomeado que é bind": "    volumes:\n      - hostroot:/outside\nvolumes:\n  hostroot:\n"
                                          "    driver: local\n    driver_opts:\n      type: none\n"
                                          "      o: bind\n      device: /tmp\n",
            "secret de arquivo da máquina": "    secrets:\n      - s\nsecrets:\n  s:\n    file: /etc/hosts\n",
            "build fora do projeto": "    build:\n      context: /tmp\n",
            "security_opt": "    security_opt:\n      - seccomp:unconfined\n",
        }
        for label, extra in escapes.items():
            (self.a / "dc.yml").write_text(COMPOSE + extra)
            r = self.run_script(self.a, "up")
            self.assertEqual(r.returncode, 1, label + ": " + r.stderr + r.stdout)
            self.assertIn("ambiente recusado", r.stderr, label)
            self.assertEqual(self.containers("harnesstest-feat-a"), [], label)


if __name__ == "__main__":
    unittest.main()
