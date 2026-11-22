import unittest

from tests.helpers import make_repo, run_hook
import managed_guard

DOC = "# Proj\n\nlivre antes\n\n<!-- harness:begin -->\nregra 1\n<!-- harness:end -->\n\nlivre depois\n"


class TestManagedGuard(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        (self.repo / "AGENTS.md").write_text(DOC)
        self.f = str(self.repo / "AGENTS.md")

    def edit(self, old, new, path=None, replace_all=False):
        return run_hook("managed_guard.py", {"tool_name": "Edit", "cwd": str(self.repo), "tool_input": {
            "file_path": path or self.f, "old_string": old, "new_string": new, "replace_all": replace_all}})[0]

    def write(self, content, path=None):
        return run_hook("managed_guard.py", {"tool_name": "Write", "cwd": str(self.repo),
                        "tool_input": {"file_path": path or self.f, "content": content}})[0]

    def test_project_region_is_free(self):
        self.assertEqual(self.edit("livre antes", "produto X"), 0)
        self.assertEqual(self.write(DOC.replace("livre depois", "onde olhar")), 0)

    def test_managed_region_is_denied(self):
        self.assertEqual(self.edit("regra 1", "regra 2"), 2)
        self.assertEqual(self.edit("<!-- harness:end -->", ""), 2)
        self.assertEqual(self.write("# Proj\nsem região\n"), 2)
        self.assertEqual(self.edit("r", "R", replace_all=True), 2)

    def test_relative_path_is_resolved_against_cwd(self):
        self.assertEqual(self.edit("regra 1", "regra 2", path="AGENTS.md"), 2)
        self.assertEqual(self.edit("regra 1", "regra 2", path="./docs/../AGENTS.md"), 2)

    def test_other_files_pass(self):
        # código do aplicativo tem regra própria (test_code_rail); aqui, o que não é gerenciado nem código
        self.assertEqual(self.edit("a", "b", path=str(self.repo / "docs/x.md")), 0)
        self.assertEqual(self.edit("a", "b", path=str(self.repo / "docs/AGENTS.md")), 0)

    def test_file_without_region_or_missing_passes(self):
        (self.repo / "AGENTS.md").write_text("# sem marcadores\n")
        self.assertEqual(self.write("# outro\n"), 0)
        (self.repo / "AGENTS.md").unlink()
        self.assertEqual(self.write(DOC), 0)

    def test_region(self):
        self.assertEqual(managed_guard.region(DOC), "<!-- harness:begin -->\nregra 1\n<!-- harness:end -->")
        self.assertIsNone(managed_guard.region("nada"))
        self.assertIsNone(managed_guard.region("<!-- harness:end -->x<!-- harness:begin -->"))

    def test_bad_input_denies(self):
        self.assertEqual(run_hook("managed_guard.py", None, raw="{")[0], 2)
        self.assertEqual(run_hook("managed_guard.py", {"tool_name": "Edit", "cwd": str(self.repo),
                                  "tool_input": {"file_path": self.f}})[0], 2)

    def test_other_tools_pass(self):
        self.assertEqual(run_hook("managed_guard.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}})[0], 0)


if __name__ == "__main__":
    unittest.main()
