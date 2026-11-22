"""Só o plugin trilho escreve em `.claude/trilho.json`. O agente é negado nas três camadas:
pela ferramenta de edição, pelo terminal, e pelo sandbox (denyWrite)."""
import json
import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, _tmpdir, commit_all, make_repo, run_hook

PLUGIN = ROOT / "plugins/trilho"
GATE = PLUGIN / "scripts/gate.py"
STAMP = PLUGIN / "scripts/sign.py"


def with_registry(repo):
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude/trilho.json").write_text(json.dumps({"portoes": {}}))


def write_hook(repo, path, cwd=None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(cwd or repo), CLAUDE_PLUGIN_ROOT=str(PLUGIN))
    return subprocess.run([sys.executable, "-I", str(GATE)], env=env, capture_output=True, text=True,
                          input=json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write",
                                            "cwd": str(cwd or repo), "tool_input": {"file_path": str(path), "content": "x"}}))


def bash_hook(repo, command, cwd=None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(cwd or repo), CLAUDE_PLUGIN_ROOT=str(PLUGIN))
    return subprocess.run([sys.executable, "-I", str(GATE)], env=env, capture_output=True, text=True,
                          input=json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                            "cwd": str(cwd or repo), "tool_input": {"command": command}}))


class TestLock(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        (self.repo / "x.txt").write_text("x")
        commit_all(self.repo, "chore: scaffold")

    def test_the_edit_tool_cannot_write_the_registry(self):
        with_registry(self.repo)
        r = write_hook(self.repo, self.repo / ".claude/trilho.json")
        self.assertEqual(r.returncode, 2)
        for mark in ("trilho.json", "só o dono"):
            self.assertIn(mark, r.stderr, mark)

    def test_the_terminal_cannot_write_the_registry(self):
        with_registry(self.repo)
        p = ".claude/trilho.json"
        for command in (f'echo "{{}}" > {p}', f"cat > {p} <<EOF\\n{{}}\\nEOF",
                        f"sed -i '' 's/a/b/' {p}", f'tee {p} < /dev/null',
                        f'cp outro.json {p}', f'mv novo.json {p}'):
            r = bash_hook(self.repo, command)
            self.assertEqual(r.returncode, 2, command)
        self.assertEqual(bash_hook(self.repo, f"cat {p}").returncode, 0, "ler passa")

    def test_the_sandbox_lists_the_registry_in_denywrite(self):
        """Terceira camada: o install e o portoes --gravar põem o arquivo no denyWrite."""
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/settings.json").write_text('{"sandbox": {"enabled": true, "filesystem": {"denyWrite": []}}}')
        subprocess.run([sys.executable, "-I", str(PLUGIN / "scripts/portoes.py"), "--padrao", "--gravar",
                        "--projeto", str(self.repo)], capture_output=True, text=True, check=True)
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertIn(".claude/trilho.json", settings["sandbox"]["filesystem"]["denyWrite"])

    def test_without_registry_the_block_still_protects_the_file(self):
        # mesmo sem `portoes` no arquivo, o agente não pode criar o registro para enfiar um portão fraco
        (self.repo / ".claude").mkdir()
        r = write_hook(self.repo, self.repo / ".claude/trilho.json")
        self.assertEqual(r.returncode, 2, r.stderr)


if __name__ == "__main__":
    unittest.main()
