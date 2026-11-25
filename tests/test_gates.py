"""Plugin `tr`: o registro de portões (`.claude/harness.json`, chave `gates`).

O harness força a ETAPA do fluxo, não a ferramenta. O `gate` verifica, o hook assina o carimbo
(fora do repositório) e o `guard.py` barra a escrita de código sem a etapa de início e o envio sem as de fim.
"""
import json
import pathlib
import os
import subprocess
import sys
import unittest
from unittest import mock

from tests.helpers import ROOT, _tmpdir, commit_all, commit_file, git, make_repo, hook_verdict

PLUGIN = ROOT / "plugins/tr"
sys.path.insert(0, str(PLUGIN / "scripts"))
import ledger  # noqa: E402
import registry  # noqa: E402

CHECK_SPEC = "import sys\nsys.exit(0 if all('ok' in open(f).read() for f in sys.argv[1:]) else 1)\n"
PROCESS = {"stage": "start", "signs": "artifact", "artifact": "docs/specs/*/spec.md",
            "check": "python3 tools/check-spec.py", "description": "spec da mudança, saída da entrevista"}
QUALITY = {"stage": "end", "signs": "command", "command": "true"}
BUGS = {"stage": "end", "signs": "agent", "agent": "tr:bug-hunter"}


class Case(unittest.TestCase):
    def setUp(self):
        self.home = _tmpdir()
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        self.repo = make_repo()

    def registry(self, gates, **extra):
        """Grava o registro e o validador na main e abre a branch de trabalho."""
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/harness.json").write_text(json.dumps({**extra, "gates": gates}))
        (self.repo / "tools").mkdir(exist_ok=True)
        (self.repo / "tools/check-spec.py").write_text(CHECK_SPEC)
        commit_all(self.repo, "chore: registro de portões")
        git(self.repo, "checkout", "-q", "-b", "feat")

    def script(self, name, payload, plugin=PLUGIN, raw=None):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin), CLAUDE_PROJECT_DIR=str(self.repo))
        return hook_verdict(subprocess.run([sys.executable, str(plugin / "scripts" / name)],
                                           input=raw if raw is not None else json.dumps(payload),
                                           capture_output=True, text=True, env=env, cwd=self.repo))

    def gate(self, *args):
        return subprocess.run([str(PLUGIN / "bin/gate"), *args], capture_output=True, text=True, cwd=self.repo)

    def post(self, command, stdout, agent_type="tr:quality-checker"):
        """O `PostToolUse` do `gate`, por padrão dentro do verificador (o único que assina portão de fim)."""
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": str(self.repo),
                   "tool_input": {"command": command}, "tool_response": {"stdout": stdout}}
        if agent_type:
            payload["agent_type"] = agent_type
        return self.script("sign.py", payload)

    def pre(self, tool, **tool_input):
        return self.script("guard.py", {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(self.repo),
                                       "tool_input": tool_input})

    def bash(self, command):
        return self.pre("Bash", command=command)

    def write(self, path, tool="Write"):
        return self.pre(tool, file_path=str(self.repo / path))

    def sign_through_hook(self, name):
        """O caminho completo: `gate <name>` e o hook lendo a saída."""
        out = self.gate(name)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return self.post(f"gate {name}", out.stdout)

    def signed(self, name):
        reg = registry.load(str(self.repo))
        return registry.satisfied(str(self.repo), name, reg)

    def add_spec(self, text="ok\n", name="a"):
        (self.repo / f"docs/specs/{name}").mkdir(parents=True, exist_ok=True)
        (self.repo / f"docs/specs/{name}/spec.md").write_text(text)
        return commit_all(self.repo, f"docs: spec {name}")


class TestRegistry(Case):
    def load(self, text):
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/harness.json").write_text(text)
        return registry.load(str(self.repo))

    def test_without_registry_or_gates_there_is_nothing(self):
        self.assertIsNone(registry.load(str(self.repo)))
        self.assertIsNone(self.load('{"quality": {"command": "x"}}'))

    def test_invalid_registries_give_a_clear_error(self):
        cases = {
            "não é json": "não pôde ser lido",
            json.dumps({"gates": {"a": {"stage": "meio-invalido", "signs": "command", "command": "x"}}}): "`stage`",
            json.dumps({"gates": {"a": {"stage": "end", "signs": "magia"}}}): "`signs`",
            json.dumps({"gates": {"a": {"stage": "end", "signs": "command"}}}): "campo `command`",
            json.dumps({"gates": {"a b": QUALITY}}): "o nome",
            json.dumps({"gates": {}}): "ao menos um portão",
            json.dumps({"code": "apps", "gates": {"a": QUALITY}}): "`code`",
        }
        for text, excerpt in cases.items():
            with self.assertRaises(registry.RegistryError, msg=text) as cm:
                self.load(text)
            self.assertIn(excerpt, str(cm.exception))

    def test_is_code_with_the_codigo_key_is_by_prefix(self):
        reg = self.load(json.dumps({"code": ["apps", "packages/x"], "gates": {"q": QUALITY}}))
        r = str(self.repo)
        for path, expected_value in (("apps/web/a.ts", True), ("packages/x/b.ts", True), ("packages/y/b.ts", False),
                               ("appsx/a.ts", False), ("docs/a.ts", False), ("/etc/passwd", False)):
            self.assertEqual(registry.is_code(r, path, reg), expected_value, path)

    def test_is_code_without_the_codigo_key_excludes_docs_claude_md_and_ignored(self):
        reg = self.load(json.dumps({"gates": {"q": QUALITY}}))
        (self.repo / ".gitignore").write_text("dist/\n")
        r = str(self.repo)
        for path, expected_value in (("src/a.ts", True), ("a.py", True), (".gitignore", False),
                               ("docs/x.ts", False), (".claude/x.json", False),
                               ("NOTAS.md", False), ("src/leia.md", False), ("dist/a.js", False)):
            self.assertEqual(registry.is_code(r, path, reg), expected_value, path)


class TestStartGateByArtifact(Case):
    def setUp(self):
        super().setUp()
        self.registry({"process": PROCESS}, code=["apps"])

    def test_without_a_changed_spec_it_fails(self):
        out = self.gate("process")
        self.assertEqual(out.returncode, 1)
        self.assertEqual(out.stdout.strip().splitlines()[-1].split(" (")[0], "gate process: FALHOU")

    def test_with_a_changed_spec_and_a_passing_validator_it_passes(self):
        self.add_spec()
        out = self.gate("process")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(out.stdout.strip().splitlines()[-1], "gate process: passou")

    def test_a_failing_validator_fails(self):
        self.add_spec("ruim\n")
        out = self.gate("process")
        self.assertEqual(out.returncode, 1)
        self.assertIn("FALHOU (python3 tools/check-spec.py)", out.stdout)

    def test_an_uncommitted_spec_fails(self):
        self.add_spec()
        (self.repo / "docs/specs/a/spec.md").write_text("ok mudou\n")
        self.assertIn("gate process: passou", self.gate("process").stdout)

    def test_the_hook_signs_only_with_the_passed_line(self):
        self.add_spec()
        self.post("gate process", "gate process: FALHOU (x)\n")
        self.post("gate process && echo oi", "gate process: passou\n")
        self.post("echo gate process: passou", "gate process: passou\nmais\n")
        self.assertFalse(self.signed("process"))
        self.post("gate process", "gate process: passou\n")
        self.assertTrue(self.signed("process"))

    def test_planner_cannot_sign_its_own_start_gate(self):
        self.add_spec()
        self.post("gate process", "gate process: passou\n", agent_type=None)
        self.assertFalse(self.signed("process"))
        self.sign_through_hook("process")
        self.assertTrue(self.signed("process"))

    def test_changing_the_spec_invalidates_the_stamp(self):
        self.add_spec()
        self.sign_through_hook("process")
        self.assertTrue(self.signed("process"))
        (self.repo / "docs/specs/a/spec.md").write_text("ok, revisada\n")
        commit_all(self.repo, "docs: revisa spec")
        self.assertFalse(self.signed("process"))

    def test_code_writes_are_blocked_before_and_free_after(self):
        for tool in ("Write", "Edit", "MultiEdit"):
            r = self.write("apps/web/a.ts", tool)
            self.assertEqual(r.returncode, 2, tool)
            self.assertIn("process", r.stderr)
            self.assertIn("spec da mudança", r.stderr)
            self.assertIn("/tr:quality-check", r.stderr)
        nb = self.pre("NotebookEdit", notebook_path=str(self.repo / "apps/n.ipynb"))
        self.assertEqual(nb.returncode, 2)
        self.add_spec()
        self.sign_through_hook("process")
        self.assertEqual(self.write("apps/web/a.ts").returncode, 0)

    def test_writes_in_docs_and_outside_code_are_never_blocked(self):
        for path in ("docs/specs/a/spec.md", "docs/x.md", "README.md", "tools/x.py"):
            self.assertEqual(self.write(path).returncode, 0, path)
        self.assertEqual(self.pre("Read", file_path=str(self.repo / "apps/a.ts")).returncode, 0)

    def test_terminal_writes_to_code_are_warned_early(self):
        for cmd in ("echo x > apps/a.ts", "echo x >> apps/a.ts", "echo x >apps/a.ts", "sed -i 's/a/b/' apps/a.ts",
                    "sed -i.bak -e 's/a/b/' apps/a.ts", "echo x | tee apps/a.ts", "cp /tmp/x apps/a.ts",
                    "mv x apps/b.ts", "cd apps && echo 1 > a.ts; true"):
            self.assertEqual(self.bash(cmd).returncode, 2 if "cd apps" not in cmd else 0, cmd)
        for cmd in ("echo x > docs/a.md", "sed 's/a/b/' apps/a.ts", "cat apps/a.ts", "ls apps 2>&1", "git status",
                    "echo x > /dev/null", "cp apps/a.ts /tmp/x"):
            self.assertEqual(self.bash(cmd).returncode, 0, cmd)

    def test_the_block_is_logged(self):
        self.write("apps/a.ts")
        with open(f"{ledger.state_dir(str(self.repo))}/log.jsonl") as f:
            line = json.loads(f.read().splitlines()[-1])
        self.assertEqual((line["plugin"], line["what"]), ("tr", "blocked"))


class TestEndGateByCommand(Case):
    def setUp(self):
        super().setUp()
        self.registry({"quality": QUALITY})
        commit_file(self.repo, "a.py", "feat: a")

    def test_the_block_is_a_hook_decision_not_an_error(self):
        """Exit 2 faz o Claude Code mostrar o caminho do script antes da mensagem; o JSON `deny` não."""
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN), CLAUDE_PROJECT_DIR=str(self.repo))
        raw = subprocess.run([sys.executable, str(PLUGIN / "scripts/delivery_stop.py")], capture_output=True, text=True,
                             env=env, cwd=self.repo, input=json.dumps({
                                 "hook_event_name": "Stop", "cwd": str(self.repo),
                                 "last_assistant_message": "DELIVERY: done"}))
        self.assertEqual((raw.returncode, raw.stderr), (0, ""))
        out = json.loads(raw.stdout)
        self.assertEqual(out["decision"], "block")
        self.assertIn("quality", out["reason"])

    def test_only_the_verifier_signs_an_end_gate(self):
        out = self.gate("quality")
        r = self.post("gate quality", out.stdout, agent_type=None)
        self.assertIn("/tr:quality-check", json.loads(r.stdout)["systemMessage"])
        self.assertFalse(self.signed("quality"))
        self.post("gate quality", out.stdout, agent_type="general-purpose")
        self.assertFalse(self.signed("quality"))
        self.post("gate quality", out.stdout)
        self.assertTrue(self.signed("quality"))

    def test_a_signed_stamp_tells_the_owner(self):
        r = self.sign_through_hook("quality")
        self.assertEqual(json.loads(r.stdout)["systemMessage"][:28], "✓ trilho · quality carimbado")

    def test_signs_only_with_a_clean_tree(self):
        (self.repo / "sujo.py").write_text("x\n")
        r = self.post("gate quality", "gate quality: passou\n")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(self.signed("quality"))
        commit_all(self.repo, "feat: limpa")
        self.assertEqual(self.sign_through_hook("quality").returncode, 0)
        self.assertTrue(self.signed("quality"))

    def test_a_failing_command_does_not_sign(self):
        data = json.loads((self.repo / ".claude/harness.json").read_text())
        data["gates"]["quality"]["command"] = "echo quebrou; false"
        (self.repo / ".claude/harness.json").write_text(json.dumps(data))
        commit_all(self.repo, "chore: comando que falha")
        out = self.gate("quality")
        self.assertEqual(out.returncode, 1)
        self.assertIn("quebrou", out.stdout)
        self.assertIn("gate quality: FALHOU (echo quebrou; false)", out.stdout)

    def test_a_send_is_blocked_without_the_stamp_and_free_with_it(self):
        for cmd in ("git push", "git add . && git push origin x", "gh pr create --fill"):
            r = self.bash(cmd)
            self.assertEqual(r.returncode, 0, cmd)
        self.assertEqual(self.gate("delivery").returncode, 1)
        self.assertEqual(self.bash("git status").returncode, 0)
        self.sign_through_hook("quality")
        self.assertEqual(self.bash("git push origin x").returncode, 0)

    def test_a_new_commit_invalidates_the_stamp(self):
        self.sign_through_hook("quality")
        commit_file(self.repo, "b.py", "feat: b")
        self.assertEqual(self.gate("delivery").returncode, 1)

    def test_the_list_shows_state_and_what_to_do(self):
        out = self.gate().stdout
        self.assertIn("[falta] quality (fim, assina por command)", out)
        self.assertIn("fazer: /tr:quality-check", out)
        self.sign_through_hook("quality")
        self.assertIn("[ok] quality", self.gate().stdout)


class TestEndGateByAgent(Case):
    def setUp(self):
        super().setUp()
        self.registry({"bugs": BUGS})
        self.head = commit_file(self.repo, "a.py", "feat: a")
        self.head = ledger.head(str(self.repo))

    def block(self, verdict="APPROVED", commit=None):
        return f"VERDICT: {verdict}\nCOMMIT: {commit or self.head}\nSUMMARY: conferi o diff\n"

    def stop(self, text, agent="tr:bug-hunter"):
        return self.script("sign.py", {"hook_event_name": "SubagentStop", "agent_type": agent, "cwd": str(self.repo),
                                       "last_assistant_message": text})

    def handback(self, text, agent="tr:bug-hunter"):
        return self.script("sign.py", {"hook_event_name": "PreToolUse", "tool_name": "SubagentHandback",
                                       "agent_type": agent, "cwd": str(self.repo), "tool_input": {"message": text}})

    def test_the_right_agent_signs_by_both_paths(self):
        for send in (self.stop, self.handback):
            self.assertFalse(self.signed("bugs"))
            self.assertEqual(send(self.block()).returncode, 0)
            self.assertTrue(self.signed("bugs"), send.__name__)
            ledger.forget(str(self.repo), "bugs", self.head)

    def test_review_model_uses_gate_override_before_role_default(self):
        path = self.repo / ".claude/harness.json"
        data = json.loads(path.read_text())
        data["models"] = {"review": {"cli": "claude", "model": "haiku"},
                           "gates": {"bugs": {"cli": "claude", "model": "sonnet"}}}
        path.write_text(json.dumps(data))
        out = self.pre("Agent", subagent_type="tr:bug-hunter", prompt="Revise bugs")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)["hookSpecificOutput"]["updatedInput"]["model"], "sonnet")
        del data["models"]["gates"]
        path.write_text(json.dumps(data))
        out = self.pre("Agent", subagent_type="tr:bug-hunter", prompt="Revise bugs")
        self.assertEqual(json.loads(out.stdout)["hookSpecificOutput"]["updatedInput"]["model"], "haiku")

    def test_codex_model_gate_cannot_be_stamped_by_claude_agent(self):
        path = self.repo / ".claude/harness.json"
        data = json.loads(path.read_text())
        data["models"] = {"gates": {"bugs": {"cli": "codex", "model": "sol"}}}
        path.write_text(json.dumps(data))
        out = self.pre("Agent", subagent_type="tr:bug-hunter", prompt="Revise bugs")
        self.assertEqual(out.returncode, 2)
        self.assertIn("models validate-gate bugs", out.stderr)

    def test_the_wrong_agent_or_commit_does_not_sign(self):
        self.stop(self.block(), agent="outro:agente")
        self.handback(self.block(), agent="general-purpose")
        self.stop(self.block(commit="f" * 40))
        self.assertFalse(self.signed("bugs"))

    def test_rejected_removes_it(self):
        self.stop(self.block())
        self.stop(self.block("REJECTED"))
        self.assertFalse(self.signed("bugs"))

    def test_gate_explains_that_only_the_agent_signs(self):
        out = self.gate("bugs")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("tr:bug-hunter", out.stdout)
        self.assertNotIn("gate bugs: passou", out.stdout)

    def test_the_send_is_blocked_pointing_at_the_agent(self):
        r = self.bash("git push")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.gate("delivery").returncode, 1)
        self.stop(self.block())
        self.assertEqual(self.gate("delivery").returncode, 0)


class TestProtectionAndInit(Case):
    def test_the_agent_cannot_change_the_registry(self):
        self.registry({"quality": QUALITY})
        for path in (".claude/harness.json", ".claude/settings.json"):
            for tool in ("Write", "Edit"):
                r = self.write(path, tool)
                self.assertEqual(r.returncode, 2, path)
                self.assertIn("npx @fullchico/harness gates" if path.endswith("harness.json") else "configuração protegida",
                              r.stderr)
        self.assertEqual(self.bash("echo {} > .claude/harness.json").returncode, 2)
        self.assertEqual(self.write(".claude/outra.json").returncode, 0)

    def test_without_a_registry_code_waits_for_the_gates_and_core_guardrails_apply(self):
        blocked = self.write("apps/a.ts")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("/tr:configure", blocked.stderr + blocked.stdout)
        for r in (self.write("docs/notas.md"), self.bash("git push")):
            self.assertEqual((r.returncode, r.stderr), (0, ""))
        for path in (".claude/harness.json", ".claude/settings.json", ".claude/settings.local.json", ".git/info/exclude"):
            self.assertEqual(self.write(path).returncode, 2, path)

    def test_an_invalid_registry_blocks_the_send_with_the_reason(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/harness.json").write_text(json.dumps({"gates": {"a": {"stage": "inválido"}}}))
        r = self.gate("delivery")
        self.assertEqual(r.returncode, 2)
        self.assertIn("`stage`", r.stdout)

    def test_it_never_breaks_on_garbage(self):
        self.assertEqual(self.script("guard.py", None, raw="não é json").returncode, 1)
        self.assertEqual(self.script("sign.py", None, raw="não é json").returncode, 0)

    def test_invalid_registry_blocks_writes_until_owner_fixes_it(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/harness.json").write_text('{"gates":{"a":{"stage":"inválido"}}}')
        result = self.write("apps/a.ts")
        self.assertEqual(result.returncode, 2)
        self.assertIn("trilho indisponível", result.stderr)

    def test_the_ledger_copy_is_identical_to_the_source(self):
        self.assertEqual((PLUGIN / "scripts/ledger.py").read_bytes(), (ROOT / "plugins/_shared/ledger.py").read_bytes())

    def test_hooks_register_the_expected_events(self):
        hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
        self.assertIn("SessionStart", hooks)
        self.assertEqual({g["matcher"] for g in hooks["PreToolUse"]},
                         {"Bash", "Edit|Write|MultiEdit|NotebookEdit", "Agent|Task", "SubagentHandback"})
        self.assertTrue(all(h.get("onFailure") == "block" for group in hooks["PreToolUse"][:3]
                            for h in group["hooks"]))
        self.assertEqual(hooks["PostToolUse"][0]["matcher"], "Bash")
        self.assertNotIn("matcher", hooks["SubagentStop"][0])
        self.assertTrue(os.access(PLUGIN / "bin/gate", os.X_OK))
        for skill in ("gates", "configure", "process-plan", "quality-check", "bugs-hunt", "grill-me", "skills-discover"):
            self.assertTrue((PLUGIN / f"skills/{skill}/SKILL.md").exists(), skill)
        self.assertIn("codex doctor --json", (PLUGIN / "skills/configure/SKILL.md").read_text())
        self.assertIn("version 1.3.1", (PLUGIN / "skills/grill-me/SKILL.md").read_text())
        self.assertNotIn("disable-model-invocation: true", (PLUGIN / "skills/grill-me/SKILL.md").read_text(),
                         "configurar e process-plan precisam chamar grill-me dentro do fluxo")
        self.assertTrue((PLUGIN / "THIRD_PARTY_NOTICES.md").exists())
        for agent in ("bug-hunter", "quality-checker", "orchestrator"):
            text = (PLUGIN / f"agents/{agent}.md").read_text()
            self.assertIn(f"name: {agent}\n", text)
            self.assertRegex(text, r"\nmodel: (haiku|sonnet)\n")


class TestLedgerCopies(unittest.TestCase):
    def test_each_plugin_copy_is_identical_to_the_shared_one(self):
        shared = (ROOT / "plugins/_shared/ledger.py").read_text()
        for copy in ROOT.glob("plugins/*/scripts/ledger.py"):
            self.assertEqual(copy.read_text(), shared, copy)


class TestGatesCli(Case):
    def cli(self, *args):
        return subprocess.run(["node", str(ROOT / "bin/harness.js"), "gates", *args], capture_output=True, text=True)

    def test_claude_shell_cannot_change_registry_without_sandbox(self):
        path = self.repo / ".claude/harness.json"
        path.parent.mkdir()
        path.write_text(json.dumps({"gates": {"quality": QUALITY}}))
        before = path.read_text()
        draft = self.home / "draft.json"
        draft.write_text(json.dumps({"spec": {"stage": "start", "signs": "artifact", "artifact": "docs/spec.md"}}))
        env = dict(os.environ, CLAUDECODE="1")
        for args in (("--default", "--write"), ("--register", str(draft)),
                     ("--set", "quality", "true")):
            out = subprocess.run(["node", str(ROOT / "bin/harness.js"), "gates", *args,
                                  "--project", str(self.repo)], capture_output=True, text=True, env=env)
            self.assertEqual(out.returncode, 1, out.stderr)
            self.assertIn("Sem permissão", out.stderr)
            self.assertEqual(path.read_text(), before)

    def project(self):
        r = self.repo
        (r / "docs/specs").mkdir(parents=True)
        (r / "apps").mkdir()
        (r / "package.json").write_text(json.dumps({"scripts": {"lint": "x", "test": "y", "build": "z"}}))
        (r / "pnpm-lock.yaml").write_text("")
        (r / ".claude").mkdir()
        (r / ".claude/settings.json").write_text(json.dumps({
            "enabledPlugins": {"bugs@fullchico": True, "mattpocock-skills@mattpocock": True},
            "sandbox": {"enabled": True}}))
        (r / ".claude/harness.json").write_text(json.dumps({"quality": {"command": "antigo"}}))
        return r

    def proposed(self, out):
        return json.loads(out[:out.index("\n\n")])

    def test_analyze_proposes_the_default_gates_and_the_code_folders(self):
        r = self.project()
        out = self.cli("--project", str(r))
        self.assertEqual(out.returncode, 0, out.stderr)
        reg = self.proposed(out.stdout)
        self.assertEqual(reg["code"], ["apps"])
        p = reg["gates"]
        self.assertEqual(list(p), ["process", "quality", "bugs", "scope"])
        self.assertEqual((p["process"]["stage"], p["process"]["signs"], p["process"]["artifact"]),
                         ("start", "artifact", "docs/specs/*/spec.md"))
        self.assertIn("grill-me", p["process"]["description"])
        self.assertEqual(p["quality"], {"stage": "end", "signs": "command", "command": "pnpm lint && pnpm test"})
        self.assertEqual(p["bugs"], {"stage": "end", "signs": "agent", "agent": "tr:bug-hunter"})
        self.assertIn("- quality:", out.stdout)
        self.assertEqual(json.loads((r / ".claude/harness.json").read_text()), {"quality": {"command": "antigo"}})

    def test_openspec_is_a_command_gate_and_yarn_npm_come_from_the_lockfile(self):
        r = self.repo
        (r / "openspec").mkdir()
        (r / "package.json").write_text(json.dumps({"scripts": {"typecheck": "x", "test": "y"}}))
        reg = self.proposed(self.cli("--project", str(r)).stdout)
        self.assertEqual(reg["gates"]["process"]["command"], "openspec validate --all")
        self.assertEqual(reg["gates"]["quality"]["command"], "npm run typecheck && npm test")
        (r / "yarn.lock").write_text("")
        reg = self.proposed(self.cli("--project", str(r)).stdout)
        self.assertEqual(reg["gates"]["quality"]["command"], "yarn typecheck && yarn test")

    def test_save_writes_preserving_keys_and_protects_the_file_in_the_sandbox(self):
        r = self.project()
        self.assertEqual(self.cli("--write", "--project", str(r)).returncode, 0)
        data = json.loads((r / ".claude/harness.json").read_text())
        self.assertEqual(data["quality"], {"command": "antigo"})
        self.assertEqual(list(data["gates"]), ["process", "quality", "bugs", "scope"])
        settings = json.loads((r / ".claude/settings.json").read_text())
        self.assertEqual(settings["sandbox"]["filesystem"]["denyWrite"], [".claude/harness.json"])
        self.assertTrue(settings["enabledPlugins"]["bugs@fullchico"])
        self.cli("--write", "--project", str(r))
        self.assertEqual(json.loads((r / ".claude/settings.json").read_text())["sandbox"]["filesystem"]["denyWrite"],
                         [".claude/harness.json"])

    def test_default_registry(self):
        # sem scripts no projeto, o comando de quality fica para o dono definir: nada de `npm test` às cegas
        out = self.cli("--default", "--project", str(self.repo))
        p = self.proposed(out.stdout)["gates"]
        self.assertEqual((p["process"]["artifact"], p["quality"]["command"], p["bugs"]["agent"]),
                         ("docs/specs/*/spec.md", "@define", "tr:bug-hunter"))

    def test_default_registry_takes_the_quality_command_from_the_project(self):
        (self.repo / "package.json").write_text(json.dumps({"scripts": {"lint": "x", "typecheck": "y", "test": "z"}}))
        (self.repo / "pnpm-lock.yaml").write_text("")
        p = self.proposed(self.cli("--default", "--project", str(self.repo)).stdout)["gates"]
        self.assertEqual(p["quality"]["command"], "pnpm lint && pnpm typecheck && pnpm test")

    def test_usage_shows_register(self):
        out = self.cli("--nada")
        self.assertEqual(out.returncode, 2)
        self.assertIn("--register <esboço.json>", out.stderr)

    def test_register_adds_new_gates_and_keeps_the_existing_ones(self):
        self.registry({"quality": QUALITY})
        draft = self.home / "esboco.json"
        draft.write_text(json.dumps({"planning": {"stage": "start", "signs": "artifact",
                                                      "artifact": "docs/specs/*/spec.md"},
                                     "seo": {"stage": "end", "signs": "command", "command": "pnpm gate:seo"},
                                     "quality": {"stage": "end", "signs": "command", "command": "outro"}}))
        out = self.cli("--register", str(draft), "--project", str(self.repo))
        self.assertEqual(out.returncode, 0, out.stderr)
        gates = json.loads((self.repo / ".claude/harness.json").read_text())["gates"]
        self.assertEqual(gates["planning"]["stage"], "start")
        self.assertEqual(gates["seo"]["command"], "pnpm gate:seo")
        self.assertEqual(gates["quality"]["command"], "true", "o que já existe não muda")

    def test_without_permission_nothing_is_written_and_the_owner_is_told(self):
        # na sessão com sandbox o registro é protegido: o CLI para antes, sem deixar nada pela metade
        r = self.project()
        settings = r / ".claude/settings.json"
        before = settings.read_text()
        registry_data = r / ".claude/harness.json"
        registry_data.chmod(0o444)
        self.addCleanup(registry_data.chmod, 0o644)
        out = self.cli("--write", "--project", str(r))
        self.assertEqual(out.returncode, 1)
        self.assertIn("fora da sessão", out.stderr)
        self.assertIn("Nada foi gravado", out.stderr)
        self.assertEqual(settings.read_text(), before)
        self.assertEqual(json.loads(registry_data.read_text()), {"quality": {"command": "antigo"}})


class TestHeredoc(Case):
    """O corpo de um heredoc é texto do arquivo: não escreve em código nem envia."""

    def setUp(self):
        super().setUp()
        self.registry({"process": PROCESS, "quality": QUALITY}, code=["apps"])

    def test_a_doc_that_quotes_a_write_to_code_is_not_blocked(self):
        cmd = "cat > docs/nota.md <<'EOF'\nrode: echo x > apps/a.ts\ne depois: git push\nEOF\n"
        self.assertEqual(self.bash(cmd).returncode, 0)

    def test_the_real_target_of_a_heredoc_still_counts(self):
        r = self.bash("cat > apps/a.ts <<EOF\nexport const a = 1\nEOF\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("apps/a.ts", r.stderr)

    def test_a_send_after_the_heredoc_still_counts(self):
        self.assertEqual(self.bash("cat > docs/n.md <<EOF\nx\nEOF\ngit push").returncode, 0)


class TestDocOnlyCommitsKeepTheEndStamps(Case):
    """Commit só de documentação depois do carimbo não refaz a rodada de portões de fim."""

    def setUp(self):
        super().setUp()
        self.registry({"quality": QUALITY, "bugs": BUGS})
        self.stamped = commit_file(self.repo, "a.py", "feat: a")
        self.sign_through_hook("quality")
        self.stamped = ledger.head(str(self.repo))
        ledger.sign(str(self.repo), "bugs", self.stamped, "tr", "t", "tr:bug-hunter", "ok")

    def test_a_docs_commit_keeps_them_and_the_list_says_from_where(self):
        (self.repo / "docs").mkdir(exist_ok=True)
        (self.repo / "docs/report.md").write_text("x\n")
        commit_all(self.repo, "docs: relatório")
        (self.repo / "NOTAS.md").write_text("y\n")
        commit_all(self.repo, "docs: notas")
        self.assertTrue(self.signed("quality"))
        self.assertTrue(self.signed("bugs"))
        self.assertEqual(self.bash("git push").returncode, 0)
        out = self.gate().stdout
        self.assertIn("Todos os portões carimbados", out)
        self.assertIn("Todos os portões carimbados", out)

    def test_any_other_change_after_the_stamp_drops_them(self):
        (self.repo / "docs").mkdir(exist_ok=True)
        (self.repo / "docs/report.md").write_text("x\n")
        commit_all(self.repo, "docs: relatório")
        commit_file(self.repo, "e2e.spec.ts", "test: muda a checagem")
        (self.repo / "docs/mais.md").write_text("z\n")
        commit_all(self.repo, "docs: mais")
        self.assertFalse(self.signed("quality"))
        self.assertEqual(self.gate("delivery").returncode, 1)

    def test_a_change_to_the_registry_drops_them(self):
        data = json.loads((self.repo / ".claude/harness.json").read_text())
        data["gates"]["quality"]["command"] = "echo outro"
        (self.repo / ".claude/harness.json").write_text(json.dumps(data))
        commit_all(self.repo, "chore: troca o comando")
        self.assertFalse(self.signed("quality"))


