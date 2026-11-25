"""Só o plugin tr escreve em `.claude/harness.json`. O agente é negado nas três camadas:
pela ferramenta de edição, pelo terminal, e pelo sandbox (denyWrite)."""
import json
import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, _tmpdir, commit_all, make_repo, hook_verdict

PLUGIN = ROOT / "plugins/tr"
GATE = PLUGIN / "scripts/guard.py"
STAMP = PLUGIN / "scripts/sign.py"


def with_registry(repo):
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude/harness.json").write_text(json.dumps({"gates": {}}))


def write_hook(repo, path, cwd=None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(cwd or repo), CLAUDE_PLUGIN_ROOT=str(PLUGIN))
    return hook_verdict(subprocess.run([sys.executable, "-I", str(GATE)], env=env, capture_output=True, text=True,
                          input=json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write",
                                            "cwd": str(cwd or repo), "tool_input": {"file_path": str(path), "content": "x"}})))


def bash_hook(repo, command, cwd=None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(cwd or repo), CLAUDE_PLUGIN_ROOT=str(PLUGIN))
    return hook_verdict(subprocess.run([sys.executable, "-I", str(GATE)], env=env, capture_output=True, text=True,
                          input=json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                            "cwd": str(cwd or repo), "tool_input": {"command": command}})))


class TestLock(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        (self.repo / "x.txt").write_text("x")
        commit_all(self.repo, "chore: scaffold")

    def test_the_edit_tool_cannot_write_the_registry(self):
        with_registry(self.repo)
        r = write_hook(self.repo, self.repo / ".claude/harness.json")
        self.assertEqual(r.returncode, 2)
        for mark in ("harness.json", "só o dono"):
            self.assertIn(mark, r.stderr, mark)

    def test_the_terminal_cannot_write_the_registry(self):
        with_registry(self.repo)
        p = ".claude/harness.json"
        for command in (f'echo "{{}}" > {p}', f"cat > {p} <<EOF\\n{{}}\\nEOF",
                        f"sed -i '' 's/a/b/' {p}", f'tee {p} < /dev/null',
                        f'cp outro.json {p}', f'mv novo.json {p}'):
            r = bash_hook(self.repo, command)
            self.assertEqual(r.returncode, 2, command)
        self.assertEqual(bash_hook(self.repo, f"cat {p}").returncode, 0, "ler passa")

    def test_the_sandbox_lists_the_registry_in_denywrite(self):
        """Terceira camada: o install e o gates --write põem o arquivo no denyWrite."""
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/settings.json").write_text('{"sandbox": {"enabled": true, "filesystem": {"denyWrite": []}}}')
        subprocess.run([sys.executable, "-I", str(PLUGIN / "scripts/gates_cli.py"), "--default", "--write",
                        "--project", str(self.repo)], capture_output=True, text=True, check=True)
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertIn(".claude/harness.json", settings["sandbox"]["filesystem"]["denyWrite"])

    def test_without_registry_the_block_still_protects_the_file(self):
        # mesmo sem `gates` no arquivo, o agente não pode criar o registro para enfiar um portão fraco
        (self.repo / ".claude").mkdir()
        r = write_hook(self.repo, self.repo / ".claude/harness.json")
        self.assertEqual(r.returncode, 2, r.stderr)


if __name__ == "__main__":
    unittest.main()
