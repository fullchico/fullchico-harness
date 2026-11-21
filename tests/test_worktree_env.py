import os
import socket
import subprocess
import unittest

from tests.helpers import ROOT, commit_all, git, make_repo

SCRIPT = str(ROOT / "plugin/payload/worktree-env")
CONF = ('PROJECT=meuapp\nSERVICES="web api postgres"\n'
        "ENV_DATABASE_URL='postgresql://a:b@localhost:${POSTGRES_PORT}/app'\n"
        "ENV_APP_URL='http://localhost:${WEB_PORT}/${COMPOSE_PROJECT_NAME}'\n")


def conf(repo, text=CONF):
    (repo / "harness.conf").write_text(text)


def parse(text):
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line and not line.startswith("#"))


def env(repo):
    return parse((repo / ".env").read_text())


def run(repo, *args, **extra):
    environ = {k: v for k, v in os.environ.items() if k not in ("CONDUCTOR_PORT", "HARNESS_ENV")}
    return subprocess.run([SCRIPT, *args], cwd=repo, env=dict(environ, **extra), capture_output=True, text=True)


def worktree(repo, path, branch=None):
    args = ["worktree", "add", "-q", str(path)] + (["-b", branch] if branch else ["--detach"])
    git(repo, *args)
    return path


class TestWorktreeEnv(unittest.TestCase):
    def test_writes_block_and_derived_values(self):
        repo = make_repo("Meu App_2")
        conf(repo)
        r = run(repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        e = env(repo)
        base = int(e["WEB_PORT"])
        self.assertEqual((int(e["API_PORT"]), int(e["POSTGRES_PORT"])), (base + 1, base + 2))
        self.assertEqual(base % 10, 0)
        self.assertTrue(20000 <= base < 40000)
        self.assertEqual(e["COMPOSE_PROJECT_NAME"], "meuapp-meu-app-2")
        self.assertEqual(e["HARNESS_ENV_CONTEXT"], "meu-app-2")
        self.assertEqual(e["DATABASE_URL"], f"postgresql://a:b@localhost:{base + 2}/app")
        self.assertEqual(e["APP_URL"], f"http://localhost:{base}/meuapp-meu-app-2")

    def test_service_names_with_dash_become_valid_variables(self):
        repo = make_repo()
        conf(repo, 'PROJECT=x\nSERVICES="web-app redis"\n')
        run(repo)
        self.assertIn("WEB_APP_PORT", env(repo))

    def test_idempotent_and_preserves_other_keys(self):
        repo = make_repo()
        conf(repo)
        (repo / ".env").write_text("SECRET=abc=def\n# comentário\nWEB_PORT=1\n")
        run(repo)
        first = (repo / ".env").read_text()
        run(repo)
        self.assertEqual((repo / ".env").read_text(), first)
        self.assertEqual(env(repo)["SECRET"], "abc=def")
        self.assertIn("# comentário", first)
        self.assertNotEqual(env(repo)["WEB_PORT"], "1")
        self.assertEqual(first.count("WEB_PORT="), 1)

    def test_two_features_get_different_blocks_and_projects(self):
        repo = make_repo()
        conf(repo)
        commit_all(repo, "chore: conf")
        a = worktree(repo, repo.parent / "roseau-audience", "feat/audience")
        b = worktree(repo, repo.parent / "Fix Dev_Env", "fix/dev-env")
        run(a)
        run(b)
        self.assertNotEqual(env(a)["WEB_PORT"], env(b)["WEB_PORT"])
        self.assertEqual(env(a)["COMPOSE_PROJECT_NAME"], "meuapp-roseau-audience")
        self.assertEqual(env(b)["COMPOSE_PROJECT_NAME"], "meuapp-fix-dev-env")

    def test_agent_worktree_inside_a_feature_shares_its_environment(self):
        repo = make_repo()
        conf(repo)
        commit_all(repo, "chore: conf")
        feature = worktree(repo, repo.parent / "roseau-audience", "feat/audience")
        agent = worktree(repo, feature / ".claude/worktrees/agent-a1b2c3")
        run(feature)
        r = run(agent)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(env(agent)["WEB_PORT"], env(feature)["WEB_PORT"])
        self.assertEqual(env(agent)["COMPOSE_PROJECT_NAME"], "meuapp-roseau-audience")
        self.assertEqual(env(agent)["HARNESS_ENV_CONTEXT"], "roseau-audience")

    def test_agent_worktree_under_the_main_checkout_finds_its_feature(self):
        # É onde o Claude Code cria os worktrees de agente: sob o checkout principal,
        # mesmo quando a sessão está no worktree de uma feature.
        repo = make_repo()
        conf(repo)
        commit_all(repo, "chore: conf")
        other = worktree(repo, repo.parent / "roseau-other", "feat/other")
        feature = worktree(repo, repo.parent / "roseau-audience", "feat/audience")
        (feature / "a.txt").write_text("a\n")
        commit_all(feature, "feat: a")
        agent = repo / ".claude/worktrees/agent-a1b2c3"
        git(feature, "worktree", "add", "-q", "-b", "worktree-agent-a1b2c3", str(agent), "HEAD")
        (agent / "b.txt").write_text("b\n")
        commit_all(agent, "feat: b")
        (feature / "c.txt").write_text("c\n")
        commit_all(feature, "feat: c")  # a feature andou depois do despacho
        run(feature)
        run(other)
        r = run(agent)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(env(agent)["COMPOSE_PROJECT_NAME"], "meuapp-roseau-audience")
        self.assertEqual(env(agent)["WEB_PORT"], env(feature)["WEB_PORT"])

    def test_fresh_agent_worktree_prefers_the_feature_over_the_main_checkout(self):
        repo = make_repo()
        conf(repo)
        commit_all(repo, "chore: conf")
        feature = worktree(repo, repo.parent / "roseau-audience", "feat/audience")
        agent = repo / ".claude/worktrees/agent-zz"
        git(feature, "worktree", "add", "-q", "-b", "worktree-agent-zz", str(agent), "HEAD")
        run(feature)
        self.assertEqual(run(agent).returncode, 0)
        self.assertEqual(env(agent)["COMPOSE_PROJECT_NAME"], "meuapp-roseau-audience")

    def test_explicit_context_wins(self):
        repo = make_repo()
        conf(repo)
        run(repo, HARNESS_ENV="Demo 1")
        self.assertEqual(env(repo)["COMPOSE_PROJECT_NAME"], "meuapp-demo-1")

    def test_busy_port_moves_to_next_block(self):
        repo = make_repo()
        conf(repo)
        base = int(parse(run(repo, "--print").stdout)["WEB_PORT"])
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", base + 1))
            s.listen()
            r = run(repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(int(env(repo)["WEB_PORT"]), base + 10)
        self.assertIn(str(base + 1), r.stderr)

    def test_conductor_port_is_the_base(self):
        repo = make_repo()
        conf(repo)
        run(repo, CONDUCTOR_PORT="31000")
        self.assertEqual(env(repo)["WEB_PORT"], "31000")
        self.assertEqual(env(repo)["POSTGRES_PORT"], "31002")

    def test_print_does_not_write(self):
        repo = make_repo()
        conf(repo)
        out = run(repo, "--print").stdout
        self.assertIn("WEB_PORT=", out)
        self.assertIn("COMPOSE_PROJECT_NAME=meuapp-", out)
        self.assertFalse((repo / ".env").exists())

    def test_errors_leave_env_untouched(self):
        cases = [("SERVICES=web\n", {}), ("PROJECT=x\n", {}), ("", {}),
                 ('PROJECT=x\nSERVICES="a b c d e f g h i j k"\n', {}),
                 (CONF, {"CONDUCTOR_PORT": "abc"}), (CONF, {"CONDUCTOR_PORT": "70000"})]
        for text, extra in cases:
            repo = make_repo()
            conf(repo, text)
            (repo / ".env").write_text("SECRET=abc\n")
            r = run(repo, **extra)
            self.assertEqual(r.returncode, 1, (text, extra))
            self.assertEqual((repo / ".env").read_text(), "SECRET=abc\n")
            self.assertTrue(r.stderr.strip(), (text, extra))

    def test_starts_from_env_example(self):
        repo = make_repo()
        conf(repo)
        (repo / ".env.example").write_text("FOO=bar\n")
        run(repo)
        self.assertEqual(env(repo)["FOO"], "bar")

    def test_runs_from_a_subdirectory(self):
        repo = make_repo()
        conf(repo)
        (repo / "src").mkdir()
        r = subprocess.run([SCRIPT], cwd=repo / "src", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((repo / ".env").exists())


if __name__ == "__main__":
    unittest.main()
