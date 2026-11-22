"""O `.harness/doctor` diz se os trilhos estão de pé, e o `notify.py` registra pedido de permissão parado."""
import datetime
import json
import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, git, make_repo, run_hook, sync

sys.path.insert(0, str(ROOT / "plugin/payload/hooks"))
import common  # noqa: E402

STANDARD = ('[ -f "$CLAUDE_PROJECT_DIR/.harness/hooks/notify.py" ] || exit 0; '
            'python3 -I "$CLAUDE_PROJECT_DIR/.harness/hooks/notify.py"')


def stamp(minutes_ago=0):
    at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes_ago)
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


class Base(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        commit_all(self.repo, "chore: adopt harness")
        self.state = common.state_dir(str(self.repo))

    def doctor(self, *args):
        r = subprocess.run([str(self.repo / ".harness/doctor"), *args], cwd=self.repo, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def log(self):
        with open(os.path.join(self.state, "log.jsonl"), encoding="utf-8") as f:
            return f.read()

    def append(self, name, record):
        os.makedirs(self.state, exist_ok=True)
        with open(os.path.join(self.state, name), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


class TestDoctor(Base):
    def test_a_freshly_synced_project_is_healthy_and_lists_its_hooks(self):
        rc, out = self.doctor()
        self.assertEqual(rc, 0, out)
        for hook in ("service_guard.py", "dispatch_guard.py", "managed_guard.py", "gate_stamp.py", "notify.py"):
            self.assertRegex(out, rf"✓ {hook}: presente e compila")
        self.assertIn("v0.1.0", out)
        self.assertNotIn("\n  ✗", out)

    def test_a_missing_hook_fails_and_is_named(self):
        (self.repo / ".harness/hooks/gate_stamp.py").unlink()
        rc, out = self.doctor()
        self.assertEqual(rc, 1, out)
        self.assertRegex(out, r"✗ gate_stamp\.py: .*não existe")

    def test_a_hook_that_does_not_compile_fails_and_is_named(self):
        (self.repo / ".harness/hooks/managed_guard.py").write_text("def (:\n")
        rc, out = self.doctor()
        self.assertEqual(rc, 1, out)
        self.assertRegex(out, r"✗ managed_guard\.py: não compila")

    def test_a_hook_file_nobody_calls_is_reported(self):
        (self.repo / ".harness/hooks/solto.py").write_text("x = 1\n")
        rc, out = self.doctor()
        self.assertEqual(rc, 1, out)
        self.assertRegex(out, r"✗ solto\.py: .*não está ligado")

    def test_a_guard_without_on_failure_block_is_reported(self):
        path = self.repo / ".claude/settings.json"
        settings = json.loads(path.read_text())
        guard = next(h for g in settings["hooks"]["PreToolUse"] for h in g["hooks"] if "service_guard" in h["command"])
        del guard["onFailure"]
        path.write_text(json.dumps(settings, indent=2))
        rc, out = self.doctor()
        self.assertEqual(rc, 1, out)
        self.assertRegex(out, r"✗ service_guard\.py.*onFailure")

    def test_denials_are_counted_by_hook_and_unstamped_verdicts_show_the_reason(self):
        for reason in ("push sem portão", "flag proibida"):
            common.log(str(self.repo), "service_guard", "negou", reason)
        common.log(str(self.repo), "managed_guard", "negou", "arquivo gerenciado")
        common.log(str(self.repo), "gate_stamp", "não carimbou", "seguranca: resposta sem VEREDITO")
        common.log(str(self.repo), "gate_stamp", "erro", "KeyError: x")
        self.append("log.jsonl", {"at": stamp(48 * 60), "hook": "dispatch_guard", "what": "negou", "detail": "velha"})
        rc, out = self.doctor()
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"service_guard: 2\b")
        self.assertRegex(out, r"managed_guard: 1\b")
        self.assertIn("flag proibida", out)
        self.assertIn("seguranca: resposta sem VEREDITO", out)
        self.assertIn("KeyError: x", out)
        self.assertNotIn("dispatch_guard: 1", out)
        self.assertRegex(self.doctor("--hours", "72")[1], r"dispatch_guard: 1\b")

    def test_a_silent_rail_with_recent_commits_is_a_warning_not_a_failure(self):
        rc, out = self.doctor()
        self.assertEqual(rc, 0, out)
        self.assertIn("trilho mudo", out)
        common.log(str(self.repo), "service_guard", "negou", "x")
        self.assertNotIn("trilho mudo", self.doctor()[1])

    def test_gates_at_head_and_approvals_of_commits_that_are_gone(self):
        head = git(self.repo, "rev-parse", "HEAD")
        gone = "0123456789abcdef0123456789abcdef01234567"
        for sha, folder in ((head, "approvals/seguranca"), (gone, "approvals/revisao"), (gone, "requests/bugs")):
            os.makedirs(os.path.join(self.state, folder), exist_ok=True)
            with open(os.path.join(self.state, folder, sha + ".json"), "w") as f:
                json.dump({"status": "PASS", "by": "owner"}, f)
        rc, out = self.doctor()
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"✓ seguranca")
        self.assertRegex(out, r"- revisao: sem aprovação")
        self.assertRegex(out, r"2 registro\(s\) de commit que não existe mais")
        self.assertIn("doctor --prune", out)
        self.assertTrue(os.path.exists(os.path.join(self.state, "approvals/revisao", gone + ".json")), "sem --prune, só lê")
        rc, out = self.doctor("--prune")
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(os.path.join(self.state, "approvals/revisao", gone + ".json")))
        self.assertFalse(os.path.exists(os.path.join(self.state, "requests/bugs", gone + ".json")))
        self.assertTrue(os.path.exists(os.path.join(self.state, "approvals/seguranca", head + ".json")))

    def test_json_carries_the_same_verdict(self):
        rc, out = self.doctor("--json")
        report = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertIs(report["ok"], True)
        self.assertTrue(any("service_guard.py" in i["text"] for s in report["sections"] for i in s["items"]))

    def test_it_writes_nothing_in_the_repository(self):
        before = git(self.repo, "status", "--porcelain", "--ignored")
        self.doctor()
        self.doctor("--json")
        self.assertEqual(git(self.repo, "status", "--porcelain", "--ignored"), before)
        self.assertEqual([str(p) for p in self.repo.rglob("__pycache__")], [])
        self.assertFalse((self.repo / ".harness-run").exists())


class TestNotify(Base):
    def request(self, command="git push origin main", **extra):
        return run_hook("notify.py", {"hook_event_name": "PermissionRequest", "session_id": "s1", "cwd": str(self.repo),
                                      "tool_name": "Bash", "tool_input": {"command": command}, **extra})

    def records(self):
        with open(os.path.join(self.state, "permissions.jsonl"), encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def waiting(self):
        return (self.repo / ".harness-run/aguardando-dono.txt").read_text().splitlines()

    def test_a_permission_request_is_recorded_and_left_where_the_orchestrator_reads(self):
        rc, out, _ = self.request(agent_type="harness:implementador", agent_id="a1")
        self.assertEqual((rc, out), (0, ""), "não decide nada: o pedido segue para o dono")
        record = self.records()[-1]
        self.assertEqual((record["tool"], record["session"], record["agent_type"], record["agent_id"]),
                         ("Bash", "s1", "harness:implementador", "a1"))
        self.assertEqual(record["summary"], "git push origin main")
        self.assertIn("Bash", self.waiting()[-1])
        self.assertIn("git push origin main", self.waiting()[-1])
        self.assertEqual((self.repo / ".harness-run/.gitignore").read_text().strip(), "*")
        self.assertIn("permissão pedida", self.log())

    def test_a_prompt_that_kept_waiting_is_recorded_too(self):
        rc, out, _ = run_hook("notify.py", {"hook_event_name": "Notification", "notification_type": "permission_prompt",
                                            "session_id": "s1", "cwd": str(self.repo),
                                            "message": "Claude needs your permission to use Bash"})
        self.assertEqual((rc, out), (0, ""))
        self.assertEqual(self.records()[-1]["what"], "permissão esperando")
        self.assertIn("needs your permission", self.waiting()[-1])
        self.assertIn("permissão esperando", self.log())

    def test_other_notifications_are_ignored(self):
        run_hook("notify.py", {"hook_event_name": "Notification", "notification_type": "idle_prompt",
                               "session_id": "s1", "cwd": str(self.repo), "message": "x"})
        self.assertFalse(os.path.exists(os.path.join(self.state, "permissions.jsonl")))

    def test_long_commands_are_cut_and_secrets_and_contents_stay_out(self):
        self.request("curl -H 'Authorization: Bearer abc123segredo' https://x.test " + "a" * 900 + " FIM")
        summary = self.records()[-1]["summary"]
        self.assertLessEqual(len(summary), 201)
        self.assertNotIn("FIM", summary)
        self.assertNotIn("abc123segredo", summary)
        self.request("API_TOKEN=xyz987 ./deploy")
        self.assertNotIn("xyz987", self.records()[-1]["summary"])
        run_hook("notify.py", {"hook_event_name": "PermissionRequest", "session_id": "s1", "cwd": str(self.repo),
                               "tool_name": "Write", "tool_input": {"file_path": "src/a.ts", "content": "CONTEUDO"}})
        self.assertEqual(self.records()[-1]["summary"], "src/a.ts")
        everything = "\n".join(self.waiting()) + self.log()
        for leaked in ("abc123segredo", "xyz987", "CONTEUDO"):
            self.assertNotIn(leaked, everything)

    def test_a_bad_payload_never_fails(self):
        for raw in ("isto não é json", "[]", "{}", json.dumps({"hook_event_name": "PermissionRequest", "cwd": "/nao/existe"}),
                    json.dumps({"hook_event_name": "PermissionRequest", "cwd": str(self.repo), "tool_name": 3,
                                "tool_input": "texto", "session_id": None})):
            rc, out, _ = run_hook("notify.py", None, raw=raw)
            self.assertEqual((rc, out), (0, ""), raw)

    def test_doctor_shows_the_request_with_its_age_and_does_not_call_it_open(self):
        self.request()
        self.append("permissions.jsonl", {"at": stamp(30), "what": "permissão esperando", "session": "s2",
                                          "agent_type": "harness:implementador", "tool": None, "summary": "pedido antigo"})
        self.append("permissions.jsonl", {"at": stamp(300), "what": "permissão pedida", "session": "s3",
                                          "tool": "Bash", "summary": "fora da janela"})
        rc, out = self.doctor()
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"visto há [01] min.*Bash: git push origin main")
        self.assertRegex(out, r"visto há 3[01] min.*pedido antigo")
        self.assertNotIn("fora da janela", out)
        self.assertIn("não há como saber se já foi respondido", out)

    def test_the_template_wires_both_events_in_the_standard_form(self):
        hooks = json.loads((ROOT / "plugin/templates/settings.json").read_text())["hooks"]
        prompt = [g for g in hooks["Notification"] if g.get("matcher") == "permission_prompt"]
        self.assertEqual([h["command"] for g in prompt for h in g["hooks"]], [STANDARD])
        self.assertEqual([h["command"] for g in hooks["PermissionRequest"] for h in g["hooks"]], [STANDARD])
        # falha do hook não pode virar negação do pedido
        for group in prompt + hooks["PermissionRequest"]:
            for hook in group["hooks"]:
                self.assertNotIn("onFailure", hook)


if __name__ == "__main__":
    unittest.main()
