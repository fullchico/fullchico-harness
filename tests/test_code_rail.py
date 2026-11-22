"""Código do aplicativo só muda pelo fluxo.

No worktree da feature ninguém escreve código direto: quem escreve são os implementadores,
nos worktrees deles. A regra era texto no AGENTS.md, e uma sessão decidiu não segui-la. Agora
a escrita é negada no primeiro arquivo, e só o dono libera a edição direta, por sessão.
"""
import json
import unittest

from tests.helpers import ROOT, _tmpdir, commit_all, git, make_repo, run_hook, sync


def write(repo, path, session="s1", agent=None, cwd=None):
    payload = {"tool_name": "Write", "cwd": str(cwd or repo), "session_id": session,
               "tool_input": {"file_path": str(path), "content": "x\n"}}
    if agent:
        payload["agent_type"] = agent
    return run_hook("managed_guard.py", payload)


def bash(repo, command, session="s1", cwd=None):
    return run_hook("service_guard.py", {"tool_name": "Bash", "cwd": str(cwd or repo), "session_id": session,
                                         "tool_input": {"command": command}})


def say(repo, prompt, session="s1"):
    return run_hook("prompt_context.py", {"hook_event_name": "UserPromptSubmit", "cwd": str(repo),
                                          "session_id": session, "prompt": prompt})


class TestCodeRail(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        (self.repo / "apps/web").mkdir(parents=True)
        (self.repo / "apps/web/page.tsx").write_text("old\n")
        (self.repo / ".gitignore").write_text((self.repo / ".gitignore").read_text() + "\ndist/\n"
                                              if (self.repo / ".gitignore").exists() else "dist/\n")
        commit_all(self.repo, "chore: adopt harness")
        self.agent = self.repo / ".claude/worktrees/agent-a"
        git(self.repo, "worktree", "add", "-q", "-b", "worktree-agent-a", str(self.agent), "HEAD")

    def test_code_in_the_feature_worktree_is_denied_and_the_message_points_to_the_flow(self):
        for path in ("apps/web/page.tsx", "apps/web/new.tsx", "package.json", self.repo / "src/a.py"):
            rc, _, err = write(self.repo, path)
            self.assertEqual(rc, 2, path)
            self.assertIn("harness:entregar", err)
            self.assertIn("/harness:direto", err)
        # subagente no worktree da feature também não: revisor e orquestrador não escrevem código
        self.assertEqual(write(self.repo, "apps/web/page.tsx", agent="harness:orquestrador")[0], 2)

    def test_what_is_not_code_stays_free(self):
        for path in ("docs/specs/x/spec.md", "GLOSSARY.md", ".harness-run/pr-body.md", "apps/web/README.md",
                     "dist/out.js", _tmpdir() / "scratch.ts"):
            self.assertEqual(write(self.repo, path)[0], 0, path)

    def test_implementers_write_in_their_own_worktree(self):
        self.assertEqual(write(self.agent, "apps/web/page.tsx", agent="harness:implementador")[0], 0)
        self.assertEqual(write(self.repo, self.agent / "apps/web/page.tsx")[0], 0)

    def test_only_the_owner_opens_direct_editing_and_only_for_that_session(self):
        rc, out, _ = say(self.repo, "/harness:direto troca o texto do botão")
        self.assertEqual(rc, 0)
        self.assertIn("liber", out)
        self.assertEqual(write(self.repo, "apps/web/page.tsx")[0], 0)
        self.assertEqual(bash(self.repo, "sed -i '' s/old/new/ apps/web/page.tsx")[0], 0)
        self.assertEqual(write(self.repo, "apps/web/page.tsx", session="s2")[0], 2)
        # a liberação fica no estado do harness, que agente nenhum grava
        import common
        marker = common.direct_path(str(self.repo), "s9")
        self.assertEqual(write(self.repo, marker, session="s9")[0], 2)

    def test_every_request_is_reminded_of_the_flow(self):
        rc, out, _ = say(self.repo, "agora quero um design system inspirado no airbnb")
        self.assertEqual(rc, 0)
        self.assertIn("harness:entregar", out)
        self.assertIn("/harness:direto", out)
        self.assertEqual(write(self.repo, "apps/web/page.tsx")[0], 2, "pedido comum não libera nada")
        # a liberação é a mensagem que COMEÇA pelo comando: citado no meio, ou num texto colado, não abre
        for prompt in ("o que faz o /harness:direto?", "segue o log:\n/harness:direto troca tudo",
                       "harness:direto troca o texto", "  /harness:diretoria"):
            say(self.repo, prompt)
            self.assertEqual(write(self.repo, "apps/web/page.tsx")[0], 2, prompt)
        self.assertEqual(say(self.repo, "")[0], 0)
        self.assertEqual(run_hook("prompt_context.py", None, raw="{nao json")[0], 0, "nunca bloqueia o dono")

    def test_a_request_to_build_something_is_sent_straight_into_the_flow(self):
        # Quem decide que é pedido de implementação é o hook, pelo texto: o modelo recebe a ordem pronta.
        for prompt in ("agora quero definir interface, projeto ta muito simples", "implemente o cadastro de clientes",
                       "adiciona um filtro por data na agenda", "monte a tela de relatórios", "crie um tema escuro",
                       "Preciso que o barbeiro veja a comissão", "muda o botão de cancelar para vermelho",
                       "add a dark theme", "faz um dashboard"):
            out = say(self.repo, prompt, session="nova-" + str(abs(hash(prompt))))[1]  # a ordem vem uma vez por sessão
            self.assertIn("PRIMEIRA ação", out, prompt)
            self.assertIn("harness:entregar", out, prompt)
        for prompt in ("como estamos no andamento?", "qual a nota da entrega?", "explica esse erro", "status",
                       "o que é um implementador?"):
            out = say(self.repo, prompt)[1]
            self.assertNotIn("PRIMEIRA ação", out, prompt)
            self.assertIn("harness:entregar", out, prompt)

    def test_bash_cannot_write_code_around_the_edit_tool(self):
        for command in ("sed -i '' s/old/new/ apps/web/page.tsx", "cat > apps/web/new.tsx <<'EOF'\nexport {}\nEOF",
                        "echo x >> apps/web/page.tsx", "git mv apps/web/page.tsx apps/web/home.tsx",
                        "printf x | tee apps/web/page.tsx", "rm apps/web/page.tsx",
                        f'cd "{self.repo}" && perl -pi -e s/a/b/ apps/web/page.tsx',
                        "python3 - <<'PY' > apps/web/gen.ts\nprint(1)\nPY"):
            rc, _, err = bash(self.repo, command)
            self.assertEqual(rc, 2, command)
            self.assertIn("harness:entregar", err, command)

    def test_bash_that_does_not_write_code_passes(self):
        for command in ("pnpm test > .harness-run/out.log 2>&1", "pnpm lint 2>&1 | tail -5", "echo ok > /dev/null",
                        'git commit -q -m "fix: a > b"', "sed -n 1,3p apps/web/page.tsx", "rm -rf dist",
                        "grep -rn 'sed -i' docs", "git status --short", "cat apps/web/page.tsx",
                        "echo nota >> docs/notas.md", "pnpm build > $TMPDIR/build.log 2>&1",
                        "git show HEAD:apps/web/page.tsx > $SCRATCH/p.tsx; sed -n 1,5p $SCRATCH/p.tsx", f"sed -i '' s/a/b/ {self.agent}/apps/web/page.tsx"):
            self.assertEqual(bash(self.repo, command)[0], 0, command)
        self.assertEqual(bash(self.repo, "sed -i '' s/old/new/ apps/web/page.tsx", cwd=self.agent)[0], 0)

    def test_the_door_is_open_to_the_agent_and_the_shortcut_is_not(self):
        deliver = (ROOT / "plugin/skills/entregar/SKILL.md").read_text().split("---")[1]
        self.assertNotIn("disable-model-invocation", deliver, "o agente precisa conseguir entrar no trilho")
        direct = (ROOT / "plugin/skills/direto/SKILL.md").read_text().split("---")[1]
        self.assertIn("disable-model-invocation: true", direct, "só o dono libera a edição direta")
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        hooks = [h["command"] for group in settings["hooks"]["UserPromptSubmit"] for h in group["hooks"]]
        self.assertTrue(any("prompt_context.py" in c for c in hooks))
        agents = (ROOT / "plugin/templates/AGENTS.managed.md").read_text()
        self.assertIn("sem o comando, invoque a skill", agents)


if __name__ == "__main__":
    unittest.main()
