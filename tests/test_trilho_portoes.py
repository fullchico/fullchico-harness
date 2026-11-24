"""Plugin `tr`: o registro de portões (`.claude/trilho.json`, chave `portoes`).

O harness força a ETAPA do fluxo, não a ferramenta. O `portao` verifica, o hook assina o carimbo
(fora do repositório) e o `gate.py` barra a escrita de código sem a etapa de início e o envio sem as de fim.
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
PROCESSO = {"momento": "inicio", "assina": "artefato", "artefato": "docs/specs/*/spec.md",
            "valida": "python3 tools/check-spec.py", "descricao": "spec da mudança, saída da entrevista"}
QUALIDADE = {"momento": "fim", "assina": "comando", "comando": "true"}
BUGS = {"momento": "fim", "assina": "agente", "agente": "tr:bugs-cacador"}


class Case(unittest.TestCase):
    def setUp(self):
        self.home = _tmpdir()
        patch = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)
        self.repo = make_repo()

    def registry(self, portoes, **extra):
        """Grava o registro e o validador na main e abre a branch de trabalho."""
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude/trilho.json").write_text(json.dumps({**extra, "portoes": portoes}))
        (self.repo / "tools").mkdir(exist_ok=True)
        (self.repo / "tools/check-spec.py").write_text(CHECK_SPEC)
        commit_all(self.repo, "chore: registro de portões")
        git(self.repo, "checkout", "-q", "-b", "feat")

    def script(self, name, payload, plugin=PLUGIN, raw=None):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin), CLAUDE_PROJECT_DIR=str(self.repo))
        return hook_verdict(subprocess.run([sys.executable, str(plugin / "scripts" / name)],
                                           input=raw if raw is not None else json.dumps(payload),
                                           capture_output=True, text=True, env=env, cwd=self.repo))

    def portao(self, *args):
        return subprocess.run([str(PLUGIN / "bin/portao"), *args], capture_output=True, text=True, cwd=self.repo)

    def post(self, command, stdout, agent_type="tr:qualidade-verificador"):
        """O `PostToolUse` do `portao`, por padrão dentro do verificador (o único que assina portão de fim)."""
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": str(self.repo),
                   "tool_input": {"command": command}, "tool_response": {"stdout": stdout}}
        if agent_type:
            payload["agent_type"] = agent_type
        return self.script("sign.py", payload)

    def pre(self, tool, **tool_input):
        return self.script("gate.py", {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(self.repo),
                                       "tool_input": tool_input})

    def bash(self, command):
        return self.pre("Bash", command=command)

    def write(self, path, tool="Write"):
        return self.pre(tool, file_path=str(self.repo / path))

    def sign_through_hook(self, name):
        """O caminho completo: `portao <nome>` e o hook lendo a saída."""
        out = self.portao(name)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return self.post(f"portao {name}", out.stdout)

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
        (self.repo / ".claude/trilho.json").write_text(text)
        return registry.load(str(self.repo))

    def test_without_registry_or_gates_there_is_nothing(self):
        self.assertIsNone(registry.load(str(self.repo)))
        self.assertIsNone(self.load('{"qualidade": {"comando": "x"}}'))

    def test_invalid_registries_give_a_clear_error(self):
        casos = {
            "não é json": "não pôde ser lido",
            json.dumps({"portoes": {"a": {"momento": "meio-invalido", "assina": "comando", "comando": "x"}}}): "`momento`",
            json.dumps({"portoes": {"a": {"momento": "fim", "assina": "magia"}}}): "`assina`",
            json.dumps({"portoes": {"a": {"momento": "fim", "assina": "comando"}}}): "campo `comando`",
            json.dumps({"portoes": {"a b": QUALIDADE}}): "o nome",
            json.dumps({"portoes": {}}): "ao menos um portão",
            json.dumps({"codigo": "apps", "portoes": {"a": QUALIDADE}}): "`codigo`",
        }
        for text, trecho in casos.items():
            with self.assertRaises(registry.RegistryError, msg=text) as cm:
                self.load(text)
            self.assertIn(trecho, str(cm.exception))

    def test_is_code_with_the_codigo_key_is_by_prefix(self):
        reg = self.load(json.dumps({"codigo": ["apps", "packages/x"], "portoes": {"q": QUALIDADE}}))
        r = str(self.repo)
        for path, esperado in (("apps/web/a.ts", True), ("packages/x/b.ts", True), ("packages/y/b.ts", False),
                               ("appsx/a.ts", False), ("docs/a.ts", False), ("/etc/passwd", False)):
            self.assertEqual(registry.is_code(r, path, reg), esperado, path)

    def test_is_code_without_the_codigo_key_excludes_docs_claude_md_and_ignored(self):
        reg = self.load(json.dumps({"portoes": {"q": QUALIDADE}}))
        (self.repo / ".gitignore").write_text("dist/\n")
        r = str(self.repo)
        for path, esperado in (("src/a.ts", True), ("a.py", True), (".gitignore", False),
                               ("docs/x.ts", False), (".claude/x.json", False),
                               ("NOTAS.md", False), ("src/leia.md", False), ("dist/a.js", False)):
            self.assertEqual(registry.is_code(r, path, reg), esperado, path)


class TestStartGateByArtifact(Case):
    def setUp(self):
        super().setUp()
        self.registry({"processo": PROCESSO}, codigo=["apps"])

    def test_without_a_changed_spec_it_fails(self):
        out = self.portao("processo")
        self.assertEqual(out.returncode, 1)
        self.assertEqual(out.stdout.strip().splitlines()[-1].split(" (")[0], "portao processo: FALHOU")

    def test_with_a_changed_spec_and_a_passing_validator_it_passes(self):
        self.add_spec()
        out = self.portao("processo")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(out.stdout.strip().splitlines()[-1], "portao processo: passou")

    def test_a_failing_validator_fails(self):
        self.add_spec("ruim\n")
        out = self.portao("processo")
        self.assertEqual(out.returncode, 1)
        self.assertIn("FALHOU (python3 tools/check-spec.py)", out.stdout)

    def test_an_uncommitted_spec_fails(self):
        self.add_spec()
        (self.repo / "docs/specs/a/spec.md").write_text("ok mudou\n")
        self.assertIn("portao processo: passou", self.portao("processo").stdout)

    def test_the_hook_signs_only_with_the_passed_line(self):
        self.add_spec()
        self.post("portao processo", "portao processo: FALHOU (x)\n")
        self.post("portao processo && echo oi", "portao processo: passou\n")
        self.post("echo portao processo: passou", "portao processo: passou\nmais\n")
        self.assertFalse(self.signed("processo"))
        self.post("portao processo", "portao processo: passou\n")
        self.assertTrue(self.signed("processo"))

    def test_planner_cannot_sign_its_own_start_gate(self):
        self.add_spec()
        self.post("portao processo", "portao processo: passou\n", agent_type=None)
        self.assertFalse(self.signed("processo"))
        self.sign_through_hook("processo")
        self.assertTrue(self.signed("processo"))

    def test_changing_the_spec_invalidates_the_stamp(self):
        self.add_spec()
        self.sign_through_hook("processo")
        self.assertTrue(self.signed("processo"))
        (self.repo / "docs/specs/a/spec.md").write_text("ok, revisada\n")
        commit_all(self.repo, "docs: revisa spec")
        self.assertFalse(self.signed("processo"))

    def test_code_writes_are_blocked_before_and_free_after(self):
        for tool in ("Write", "Edit", "MultiEdit"):
            r = self.write("apps/web/a.ts", tool)
            self.assertEqual(r.returncode, 2, tool)
            self.assertIn("processo", r.stderr)
            self.assertIn("spec da mudança", r.stderr)
            self.assertIn("/tr:qualidade-verificar", r.stderr)
        nb = self.pre("NotebookEdit", notebook_path=str(self.repo / "apps/n.ipynb"))
        self.assertEqual(nb.returncode, 2)
        self.add_spec()
        self.sign_through_hook("processo")
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
        self.assertEqual((line["plugin"], line["what"]), ("trilho", "barrou"))


class TestEndGateByCommand(Case):
    def setUp(self):
        super().setUp()
        self.registry({"qualidade": QUALIDADE})
        commit_file(self.repo, "a.py", "feat: a")

    def test_the_block_is_a_hook_decision_not_an_error(self):
        """Exit 2 faz o Claude Code mostrar o caminho do script antes da mensagem; o JSON `deny` não."""
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN), CLAUDE_PROJECT_DIR=str(self.repo))
        raw = subprocess.run([sys.executable, str(PLUGIN / "scripts/delivery_stop.py")], capture_output=True, text=True,
                             env=env, cwd=self.repo, input=json.dumps({
                                 "hook_event_name": "Stop", "cwd": str(self.repo),
                                 "last_assistant_message": "ENTREGA: concluída"}))
        self.assertEqual((raw.returncode, raw.stderr), (0, ""))
        out = json.loads(raw.stdout)
        self.assertEqual(out["decision"], "block")
        self.assertIn("qualidade", out["reason"])

    def test_only_the_verifier_signs_an_end_gate(self):
        out = self.portao("qualidade")
        r = self.post("portao qualidade", out.stdout, agent_type=None)
        self.assertIn("/tr:qualidade-verificar", json.loads(r.stdout)["systemMessage"])
        self.assertFalse(self.signed("qualidade"))
        self.post("portao qualidade", out.stdout, agent_type="general-purpose")
        self.assertFalse(self.signed("qualidade"))
        self.post("portao qualidade", out.stdout)
        self.assertTrue(self.signed("qualidade"))

    def test_a_signed_stamp_tells_the_owner(self):
        r = self.sign_through_hook("qualidade")
        self.assertEqual(json.loads(r.stdout)["systemMessage"][:30], "✓ trilho · qualidade carimbado")

    def test_signs_only_with_a_clean_tree(self):
        (self.repo / "sujo.py").write_text("x\n")
        r = self.post("portao qualidade", "portao qualidade: passou\n")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(self.signed("qualidade"))
        commit_all(self.repo, "feat: limpa")
        self.assertEqual(self.sign_through_hook("qualidade").returncode, 0)
        self.assertTrue(self.signed("qualidade"))

    def test_a_failing_command_does_not_sign(self):
        data = json.loads((self.repo / ".claude/trilho.json").read_text())
        data["portoes"]["qualidade"]["comando"] = "echo quebrou; false"
        (self.repo / ".claude/trilho.json").write_text(json.dumps(data))
        commit_all(self.repo, "chore: comando que falha")
        out = self.portao("qualidade")
        self.assertEqual(out.returncode, 1)
        self.assertIn("quebrou", out.stdout)
        self.assertIn("portao qualidade: FALHOU (echo quebrou; false)", out.stdout)

    def test_a_send_is_blocked_without_the_stamp_and_free_with_it(self):
        for cmd in ("git push", "git add . && git push origin x", "gh pr create --fill"):
            r = self.bash(cmd)
            self.assertEqual(r.returncode, 0, cmd)
        self.assertEqual(self.portao("entrega").returncode, 1)
        self.assertEqual(self.bash("git status").returncode, 0)
        self.sign_through_hook("qualidade")
        self.assertEqual(self.bash("git push origin x").returncode, 0)

    def test_a_new_commit_invalidates_the_stamp(self):
        self.sign_through_hook("qualidade")
        commit_file(self.repo, "b.py", "feat: b")
        self.assertEqual(self.portao("entrega").returncode, 1)

    def test_the_list_shows_state_and_what_to_do(self):
        out = self.portao().stdout
        self.assertIn("[falta] qualidade (fim, assina por comando)", out)
        self.assertIn("fazer: /tr:qualidade-verificar", out)
        self.sign_through_hook("qualidade")
        self.assertIn("[ok] qualidade", self.portao().stdout)


class TestEndGateByAgent(Case):
    def setUp(self):
        super().setUp()
        self.registry({"bugs": BUGS})
        self.head = commit_file(self.repo, "a.py", "feat: a")
        self.head = ledger.head(str(self.repo))

    def block(self, verdict="APPROVED", commit=None):
        return f"VEREDITO: {verdict}\nCOMMIT: {commit or self.head}\nRESUMO: conferi o diff\n"

    def stop(self, text, agent="tr:bugs-cacador"):
        return self.script("sign.py", {"hook_event_name": "SubagentStop", "agent_type": agent, "cwd": str(self.repo),
                                       "last_assistant_message": text})

    def handback(self, text, agent="tr:bugs-cacador"):
        return self.script("sign.py", {"hook_event_name": "PreToolUse", "tool_name": "SubagentHandback",
                                       "agent_type": agent, "cwd": str(self.repo), "tool_input": {"message": text}})

    def test_the_right_agent_signs_by_both_paths(self):
        for send in (self.stop, self.handback):
            self.assertFalse(self.signed("bugs"))
            self.assertEqual(send(self.block()).returncode, 0)
            self.assertTrue(self.signed("bugs"), send.__name__)
            ledger.forget(str(self.repo), "bugs", self.head)

    def test_review_model_uses_gate_override_before_role_default(self):
        path = self.repo / ".claude/trilho.json"
        data = json.loads(path.read_text())
        data["modelos"] = {"revisao": {"cli": "claude", "modelo": "haiku"},
                           "portoes": {"bugs": {"cli": "claude", "modelo": "sonnet"}}}
        path.write_text(json.dumps(data))
        out = self.pre("Agent", subagent_type="tr:bugs-cacador", prompt="Revise bugs")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)["hookSpecificOutput"]["updatedInput"]["model"], "sonnet")
        del data["modelos"]["portoes"]
        path.write_text(json.dumps(data))
        out = self.pre("Agent", subagent_type="tr:bugs-cacador", prompt="Revise bugs")
        self.assertEqual(json.loads(out.stdout)["hookSpecificOutput"]["updatedInput"]["model"], "haiku")

    def test_codex_model_gate_cannot_be_stamped_by_claude_agent(self):
        path = self.repo / ".claude/trilho.json"
        data = json.loads(path.read_text())
        data["modelos"] = {"portoes": {"bugs": {"cli": "codex", "modelo": "sol"}}}
        path.write_text(json.dumps(data))
        out = self.pre("Agent", subagent_type="tr:bugs-cacador", prompt="Revise bugs")
        self.assertEqual(out.returncode, 2)
        self.assertIn("modelos validar-portao bugs", out.stderr)

    def test_the_wrong_agent_or_commit_does_not_sign(self):
        self.stop(self.block(), agent="outro:agente")
        self.handback(self.block(), agent="general-purpose")
        self.stop(self.block(commit="f" * 40))
        self.assertFalse(self.signed("bugs"))

    def test_rejected_removes_it(self):
        self.stop(self.block())
        self.stop(self.block("REJECTED"))
        self.assertFalse(self.signed("bugs"))

    def test_portao_explains_that_only_the_agent_signs(self):
        out = self.portao("bugs")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("tr:bugs-cacador", out.stdout)
        self.assertNotIn("portao bugs: passou", out.stdout)

    def test_the_send_is_blocked_pointing_at_the_agent(self):
        r = self.bash("git push")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.portao("entrega").returncode, 1)
        self.stop(self.block())
        self.assertEqual(self.portao("entrega").returncode, 0)


class TestProtectionAndInit(Case):
    def test_the_agent_cannot_change_the_registry(self):
        self.registry({"qualidade": QUALIDADE})
        for path in (".claude/trilho.json", ".claude/settings.json"):
            for tool in ("Write", "Edit"):
                r = self.write(path, tool)
                self.assertEqual(r.returncode, 2, path)
                self.assertIn("fullchico-harness portoes" if path.endswith("trilho.json") else "configuração protegida",
                              r.stderr)
        self.assertEqual(self.bash("echo {} > .claude/trilho.json").returncode, 2)
        self.assertEqual(self.write(".claude/outra.json").returncode, 0)

    def test_without_a_registry_core_guardrails_still_apply(self):
        for r in (self.write("apps/a.ts"), self.bash("git push")):
            self.assertEqual((r.returncode, r.stderr), (0, ""))
        for path in (".claude/trilho.json", ".claude/settings.json", ".claude/settings.local.json", ".git/info/exclude"):
            self.assertEqual(self.write(path).returncode, 2, path)

    def test_an_invalid_registry_blocks_the_send_with_the_reason(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/trilho.json").write_text(json.dumps({"portoes": {"a": {"momento": "inválido"}}}))
        r = self.portao("entrega")
        self.assertEqual(r.returncode, 2)
        self.assertIn("`momento`", r.stdout)

    def test_it_never_breaks_on_garbage(self):
        for name in ("gate.py", "sign.py"):
            self.assertEqual(self.script(name, None, raw="não é json").returncode, 0)

    def test_the_ledger_copy_is_identical_to_the_source(self):
        self.assertEqual((PLUGIN / "scripts/ledger.py").read_bytes(), (ROOT / "plugins/_shared/ledger.py").read_bytes())

    def test_hooks_keep_the_pure_mode_and_add_the_new_ones(self):
        hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
        self.assertIn("SessionStart", hooks)
        self.assertEqual({g["matcher"] for g in hooks["PreToolUse"]},
                         {"Bash", "Edit|Write|MultiEdit|NotebookEdit", "Agent|Task", "SubagentHandback"})
        self.assertEqual(hooks["PostToolUse"][0]["matcher"], "Bash")
        self.assertNotIn("matcher", hooks["SubagentStop"][0])
        self.assertTrue(os.access(PLUGIN / "bin/portao", os.X_OK))
        for skill in ("portoes", "configurar", "processo-planejar", "qualidade-verificar", "bugs-cacar", "grill-me"):
            self.assertTrue((PLUGIN / f"skills/{skill}/SKILL.md").exists(), skill)
        self.assertIn("codex doctor --json", (PLUGIN / "skills/configurar/SKILL.md").read_text())
        self.assertIn("versão 1.3.1", (PLUGIN / "skills/grill-me/SKILL.md").read_text())
        self.assertNotIn("disable-model-invocation: true", (PLUGIN / "skills/grill-me/SKILL.md").read_text(),
                         "configurar e processo-planejar precisam chamar grill-me dentro do fluxo")
        self.assertTrue((PLUGIN / "THIRD_PARTY_NOTICES.md").exists())
        for agent in ("bugs-cacador", "qualidade-verificador", "orquestrador"):
            text = (PLUGIN / f"agents/{agent}.md").read_text()
            self.assertIn(f"name: {agent}\n", text)
            self.assertRegex(text, r"\nmodel: (haiku|sonnet)\n")


class TestLedgerCopies(unittest.TestCase):
    def test_each_plugin_copy_is_identical_to_the_shared_one(self):
        shared = (ROOT / "plugins/_shared/ledger.py").read_text()
        for copy in ROOT.glob("plugins/*/scripts/ledger.py"):
            self.assertEqual(copy.read_text(), shared, copy)


class TestPortoesCli(Case):
    def cli(self, *args):
        return subprocess.run(["node", str(ROOT / "bin/harness.js"), "portoes", *args], capture_output=True, text=True)

    def test_claude_shell_cannot_change_registry_without_sandbox(self):
        path = self.repo / ".claude/trilho.json"
        path.parent.mkdir()
        path.write_text(json.dumps({"portoes": {"qualidade": QUALIDADE}}))
        before = path.read_text()
        draft = self.home / "draft.json"
        draft.write_text(json.dumps({"spec": {"momento": "inicio", "assina": "artefato", "artefato": "docs/spec.md"}}))
        env = dict(os.environ, CLAUDECODE="1")
        for args in (("--padrao", "--gravar"), ("--registrar", str(draft)),
                     ("--definir", "qualidade", "true")):
            out = subprocess.run(["node", str(ROOT / "bin/harness.js"), "portoes", *args,
                                  "--projeto", str(self.repo)], capture_output=True, text=True, env=env)
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
        (r / ".claude/trilho.json").write_text(json.dumps({"qualidade": {"comando": "antigo"}}))
        return r

    def proposed(self, out):
        return json.loads(out[:out.index("\n\n")])

    def test_analyze_proposes_the_three_gates_and_the_code_folders(self):
        r = self.project()
        out = self.cli("--projeto", str(r))
        self.assertEqual(out.returncode, 0, out.stderr)
        reg = self.proposed(out.stdout)
        self.assertEqual(reg["codigo"], ["apps"])
        p = reg["portoes"]
        self.assertEqual(list(p), ["processo", "qualidade", "bugs"])
        self.assertEqual((p["processo"]["momento"], p["processo"]["assina"], p["processo"]["artefato"]),
                         ("inicio", "artefato", "docs/specs/*/spec.md"))
        self.assertIn("grill-me", p["processo"]["descricao"])
        self.assertEqual(p["qualidade"], {"momento": "fim", "assina": "comando", "comando": "pnpm lint && pnpm test"})
        self.assertEqual(p["bugs"], {"momento": "fim", "assina": "agente", "agente": "tr:bugs-cacador"})
        self.assertIn("- qualidade:", out.stdout)
        self.assertEqual(json.loads((r / ".claude/trilho.json").read_text()), {"qualidade": {"comando": "antigo"}})

    def test_openspec_is_a_command_gate_and_yarn_npm_come_from_the_lockfile(self):
        r = self.repo
        (r / "openspec").mkdir()
        (r / "package.json").write_text(json.dumps({"scripts": {"typecheck": "x", "test": "y"}}))
        reg = self.proposed(self.cli("--projeto", str(r)).stdout)
        self.assertEqual(reg["portoes"]["processo"]["comando"], "openspec validate --all")
        self.assertEqual(reg["portoes"]["qualidade"]["comando"], "npm run typecheck && npm test")
        (r / "yarn.lock").write_text("")
        reg = self.proposed(self.cli("--projeto", str(r)).stdout)
        self.assertEqual(reg["portoes"]["qualidade"]["comando"], "yarn typecheck && yarn test")

    def test_save_writes_preserving_keys_and_protects_the_file_in_the_sandbox(self):
        r = self.project()
        self.assertEqual(self.cli("--gravar", "--projeto", str(r)).returncode, 0)
        data = json.loads((r / ".claude/trilho.json").read_text())
        self.assertEqual(data["qualidade"], {"comando": "antigo"})
        self.assertEqual(list(data["portoes"]), ["processo", "qualidade", "bugs"])
        settings = json.loads((r / ".claude/settings.json").read_text())
        self.assertEqual(settings["sandbox"]["filesystem"]["denyWrite"], [".claude/trilho.json"])
        self.assertTrue(settings["enabledPlugins"]["bugs@fullchico"])
        self.cli("--gravar", "--projeto", str(r))
        self.assertEqual(json.loads((r / ".claude/settings.json").read_text())["sandbox"]["filesystem"]["denyWrite"],
                         [".claude/trilho.json"])

    def test_default_registry(self):
        # sem scripts no projeto, o comando de qualidade fica para o dono definir: nada de `npm test` às cegas
        out = self.cli("--padrao", "--projeto", str(self.repo))
        p = self.proposed(out.stdout)["portoes"]
        self.assertEqual((p["processo"]["artefato"], p["qualidade"]["comando"], p["bugs"]["agente"]),
                         ("docs/specs/*/spec.md", "@definir", "tr:bugs-cacador"))

    def test_default_registry_takes_the_quality_command_from_the_project(self):
        (self.repo / "package.json").write_text(json.dumps({"scripts": {"lint": "x", "typecheck": "y", "test": "z"}}))
        (self.repo / "pnpm-lock.yaml").write_text("")
        p = self.proposed(self.cli("--padrao", "--projeto", str(self.repo)).stdout)["portoes"]
        self.assertEqual(p["qualidade"]["comando"], "pnpm lint && pnpm typecheck && pnpm test")

    def test_usage_shows_registrar(self):
        out = self.cli("--nada")
        self.assertEqual(out.returncode, 2)
        self.assertIn("--registrar <esboço.json>", out.stderr)

    def test_registrar_adds_new_gates_and_keeps_the_existing_ones(self):
        self.registry({"qualidade": QUALIDADE})
        draft = self.home / "esboco.json"
        draft.write_text(json.dumps({"planejamento": {"momento": "inicio", "assina": "artefato",
                                                      "artefato": "docs/specs/*/spec.md"},
                                     "seo": {"momento": "fim", "assina": "comando", "comando": "pnpm gate:seo"},
                                     "qualidade": {"momento": "fim", "assina": "comando", "comando": "outro"}}))
        out = self.cli("--registrar", str(draft), "--projeto", str(self.repo))
        self.assertEqual(out.returncode, 0, out.stderr)
        gates = json.loads((self.repo / ".claude/trilho.json").read_text())["portoes"]
        self.assertEqual(gates["planejamento"]["momento"], "inicio")
        self.assertEqual(gates["seo"]["comando"], "pnpm gate:seo")
        self.assertEqual(gates["qualidade"]["comando"], "true", "o que já existe não muda")

    def test_without_permission_nothing_is_written_and_the_owner_is_told(self):
        # na sessão com sandbox o registro é protegido: o CLI para antes, sem deixar nada pela metade
        r = self.project()
        settings = r / ".claude/settings.json"
        before = settings.read_text()
        trilho = r / ".claude/trilho.json"
        trilho.chmod(0o444)
        self.addCleanup(trilho.chmod, 0o644)
        out = self.cli("--gravar", "--projeto", str(r))
        self.assertEqual(out.returncode, 1)
        self.assertIn("fora da sessão", out.stderr)
        self.assertIn("Nada foi gravado", out.stderr)
        self.assertEqual(settings.read_text(), before)
        self.assertEqual(json.loads(trilho.read_text()), {"qualidade": {"comando": "antigo"}})


class TestHeredoc(Case):
    """O corpo de um heredoc é texto do arquivo: não escreve em código nem envia."""

    def setUp(self):
        super().setUp()
        self.registry({"processo": PROCESSO, "qualidade": QUALIDADE}, codigo=["apps"])

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
        self.registry({"qualidade": QUALIDADE, "bugs": BUGS})
        self.stamped = commit_file(self.repo, "a.py", "feat: a")
        self.sign_through_hook("qualidade")
        self.stamped = ledger.head(str(self.repo))
        ledger.sign(str(self.repo), "bugs", self.stamped, "trilho", "t", "tr:bugs-cacador", "ok")

    def test_a_docs_commit_keeps_them_and_the_list_says_from_where(self):
        (self.repo / "docs").mkdir(exist_ok=True)
        (self.repo / "docs/relatorio.md").write_text("x\n")
        commit_all(self.repo, "docs: relatório")
        (self.repo / "NOTAS.md").write_text("y\n")
        commit_all(self.repo, "docs: notas")
        self.assertTrue(self.signed("qualidade"))
        self.assertTrue(self.signed("bugs"))
        self.assertEqual(self.bash("git push").returncode, 0)
        out = self.portao().stdout
        self.assertIn("Todos os portões carimbados", out)
        self.assertIn("Todos os portões carimbados", out)

    def test_any_other_change_after_the_stamp_drops_them(self):
        (self.repo / "docs").mkdir(exist_ok=True)
        (self.repo / "docs/relatorio.md").write_text("x\n")
        commit_all(self.repo, "docs: relatório")
        commit_file(self.repo, "e2e.spec.ts", "test: muda a checagem")
        (self.repo / "docs/mais.md").write_text("z\n")
        commit_all(self.repo, "docs: mais")
        self.assertFalse(self.signed("qualidade"))
        self.assertEqual(self.portao("entrega").returncode, 1)

    def test_a_change_to_the_registry_drops_them(self):
        data = json.loads((self.repo / ".claude/trilho.json").read_text())
        data["portoes"]["qualidade"]["comando"] = "echo outro"
        (self.repo / ".claude/trilho.json").write_text(json.dumps(data))
        commit_all(self.repo, "chore: troca o comando")
        self.assertFalse(self.signed("qualidade"))


