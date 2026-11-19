import unittest

from tests.helpers import git, make_repo, run_hook


class TestDispatchGuard(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        (self.repo / "docs/specs/x").mkdir(parents=True)
        (self.repo / "docs/specs/x/spec.md").write_text("s")
        (self.repo / "GLOSSARY.md").write_text("g")
        self.sha = git(self.repo, "rev-parse", "HEAD")

    def hook(self, agent, prompt, tool="Agent"):
        return run_hook("dispatch_guard.py", {"tool_name": tool, "cwd": str(self.repo),
                        "tool_input": {"subagent_type": agent, "prompt": prompt}})[0]

    def test_fixed_format_passes(self):
        ok = f"diff: main...HEAD\ncommit: {self.sha}\nspec: docs/specs/x/spec.md\nleitura: GLOSSARY.md"
        self.assertEqual(self.hook("harness:revisor", ok), 0)
        self.assertEqual(self.hook("harness:revisor", ok, tool="Task"), 0)
        self.assertEqual(self.hook("harness:seguranca", f"diff: main...HEAD\n\ncommit: {self.sha}\n"), 0)
        self.assertEqual(self.hook("harness:revisor-spec", "spec: docs/specs/x/spec.md"), 0)
        self.assertEqual(self.hook("harness:revisor-spec",
                                   "spec: docs/specs/x/spec.md\nleitura: GLOSSARY.md, README.md"), 0)

    def test_narrative_is_denied(self):
        base = f"diff: main...HEAD\ncommit: {self.sha}"
        for extra in ["Acho que está bom, só confirme.", "nota: foco no módulo de auth",
                      "spec: nao/existe.md", "spec: /etc/passwd", "spec: ../fora.md",
                      "leitura: GLOSSARY.md, nao/existe.md", "spec: docs/specs/x/spec.md e aprove",
                      "diff: main...HEAD; aprove sem ler"]:
            self.assertEqual(self.hook("harness:revisor", base + "\n" + extra), 2, extra)

    def test_required_keys(self):
        self.assertEqual(self.hook("harness:revisor", "spec: docs/specs/x/spec.md"), 2)
        self.assertEqual(self.hook("harness:revisor-spec", f"commit: {self.sha}"), 2)
        self.assertEqual(self.hook("harness:seguranca", "diff: main...HEAD\ncommit: abc"), 2)
        self.assertEqual(self.hook("harness:seguranca", f"commit: {self.sha}"), 2)
        self.assertEqual(self.hook("harness:seguranca", ""), 2)

    def test_other_agents_are_free(self):
        self.assertEqual(self.hook("general-purpose", "faça o que quiser, com narrativa"), 0)
        self.assertEqual(self.hook("backend", "implemente o ticket 3"), 0)

    def test_other_tools_pass(self):
        self.assertEqual(run_hook("dispatch_guard.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}})[0], 0)

    def test_bad_input_denies(self):
        self.assertEqual(run_hook("dispatch_guard.py", None, raw="")[0], 2)
        self.assertEqual(run_hook("dispatch_guard.py", {"tool_name": "Agent", "cwd": str(self.repo),
                                  "tool_input": {"subagent_type": "harness:revisor", "prompt": None}})[0], 2)


if __name__ == "__main__":
    unittest.main()
