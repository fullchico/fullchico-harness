import unittest

from tests.helpers import make_repo, run_hook
import common


class TestServiceGuardGates(unittest.TestCase):
    def hook(self, repo, command):
        return run_hook("service_guard.py", {"tool_name": "Bash", "cwd": str(repo),
                                             "tool_input": {"command": command}})[0]

    def test_denies(self):
        repo = make_repo()
        state = common.state_dir(str(repo))
        for c in ['.harness/approve seguranca "ok"',
                  'bash .harness/approve revisao x',
                  'cd .harness && ./approve revisao x',
                  'cd .harness; approve revisao x',
                  f'echo x > "{state}/approvals/revisao/a.json"',
                  'ls .git/harness/approvals',
                  'python3 .harness/hooks/gate_stamp.py < p.json',
                  'git status && sh ./.harness/approve seguranca ok',
                  'git push --no-verify',
                  'git -c core.hooksPath=/dev/null push',
                  'git config core.hooksPath /tmp/x',
                  'HUSKY=0 git push']:
            self.assertEqual(self.hook(repo, c), 2, c)

    def test_allows(self):
        repo = make_repo()
        for c in ['git status', 'git push origin feat/x', 'echo "aspas abertas',
                  'python3 -m unittest', 'git commit -m "feat: add approval flow"',
                  '.harness/validate --profile push', 'ls -la && git log --oneline | head -5']:
            self.assertEqual(self.hook(repo, c), 0, c)

    def test_bad_input_denies(self):
        self.assertEqual(run_hook("service_guard.py", None, raw="{x")[0], 2)
        self.assertEqual(run_hook("service_guard.py", None, raw="")[0], 2)
        self.assertEqual(run_hook("service_guard.py", {"tool_name": "Bash", "tool_input": {}})[0], 2)
        self.assertEqual(run_hook("service_guard.py", {"tool_name": "Bash", "tool_input": {"command": 3}})[0], 2)

    def test_other_tools_pass(self):
        self.assertEqual(run_hook("service_guard.py", {"tool_name": "Read", "tool_input": {}})[0], 0)

    def test_denial_explains_itself(self):
        repo = make_repo()
        _, _, err = run_hook("service_guard.py", {"tool_name": "Bash", "cwd": str(repo),
                                                  "tool_input": {"command": ".harness/approve revisao x"}})
        self.assertIn("dono", err)


if __name__ == "__main__":
    unittest.main()
