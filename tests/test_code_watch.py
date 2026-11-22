"""Código do aplicativo só muda pelo fluxo: conferido depois do comando, pelo que mudou.

Ler o comando antes de ele rodar não é barreira: `python3 -c`, variável, `find -delete`, laço
e `git reset --hard` passam. Aqui o par PreToolUse → comando de verdade → PostToolUse é simulado,
e o que vale é o que apareceu alterado no repositório.
"""
import json
import os
import pathlib
import subprocess
import time
import unittest

from tests.helpers import ROOT, bug_review_passes, commit_all, git, make_repo, run_hook, sync
import common


def payload(repo, command, tid, session, cwd):
    data = {"tool_name": "Bash", "cwd": str(cwd or repo), "session_id": session, "tool_input": {"command": command}}
    if tid:
        data["tool_use_id"] = tid
    return data


def pre(repo, command, tid="t1", session="s1", cwd=None):
    return run_hook("service_guard.py", payload(repo, command, tid, session, cwd))


def post(repo, command, tid="t1", session="s1", cwd=None):
    return run_hook("code_watch.py", {"hook_event_name": "PostToolUse", **payload(repo, command, tid, session, cwd)})


def say(repo, prompt, session="s1"):
    return run_hook("prompt_context.py", {"hook_event_name": "UserPromptSubmit", "cwd": str(repo),
                                          "session_id": session, "prompt": prompt})


class TestCodeWatch(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()
        self.assertEqual(sync(self.repo).returncode, 0)
        (self.repo / "apps/web").mkdir(parents=True)
        (self.repo / "apps/web/page.tsx").write_text("old\n")
        (self.repo / "apps/web/other.tsx").write_text("old\n")
        with open(self.repo / ".gitignore", "a") as f:
            f.write("\ndist/\n")
        self.base = commit_all(self.repo, "chore: adopt harness")
        # outra branch, com um commit que muda código
        git(self.repo, "checkout", "-q", "-b", "impl")
        (self.repo / "apps/web/page.tsx").write_text("from impl\n")
        commit_all(self.repo, "feat: page")
        git(self.repo, "checkout", "-q", "main")
        self.agent = self.repo / ".claude/worktrees/agent-a"
        git(self.repo, "worktree", "add", "-q", "-b", "worktree-agent-a", str(self.agent), "HEAD")
        self.state = common.state_dir(str(self.repo))

    def ran(self, command, cwd=None, **kw):
        """O comando passa pelo guard, roda de verdade, e a conferência diz o que achou."""
        rc, _, err = pre(self.repo, command, cwd=cwd, **kw)
        self.assertEqual(rc, 0, f"{command}: {err}")
        subprocess.run(["bash", "-c", command], cwd=str(cwd or self.repo), capture_output=True, text=True)
        return post(self.repo, command, cwd=cwd, **kw)

    def assertCaught(self, command, path, **kw):
        rc, _, err = self.ran(command, **kw)
        self.assertEqual(rc, 2, command)
        self.assertIn(path, err, command)
        self.assertIn("harness:entregar", err)
        self.assertIn("/harness:direto", err)
        return err

    def test_writes_the_command_reader_cannot_see_are_caught(self):
        for command, path in (
                ("""python3 -c "open('apps/web/page.tsx','w').write('x')" """, "apps/web/page.tsx"),
                ("F=apps/web/page.tsx; echo y > $F", "apps/web/page.tsx"),
                ("find apps/web -name page.tsx -delete", "apps/web/page.tsx"),
                ("for f in apps/web/*.tsx; do echo z >> $f; done", "apps/web/other.tsx")):
            err = self.assertCaught(command, path)
            self.assertIn("git restore --staged --worktree --", err)
            git(self.repo, "checkout", "-q", "--", ".")

    def test_a_new_untracked_file_is_caught_and_the_undo_removes_it(self):
        err = self.assertCaught("""python3 -c "open('apps/web/new.tsx','w').write('x')" """, "apps/web/new.tsx")
        self.assertIn("git clean -f -- apps/web/new.tsx", err)

    def test_a_dirty_file_changed_again_is_caught(self):
        (self.repo / "apps/web/page.tsx").write_text("dirty before\n")
        self.assertEqual(self.ran("git status --short")[0], 0, "o que já estava sujo não é deste comando")
        self.assertCaught("F=apps/web/page.tsx; echo again >> $F", "apps/web/page.tsx", tid="t2")

    def test_a_commit_that_is_not_a_merge_and_touches_code_is_caught(self):
        (self.repo / "apps/web/page.tsx").write_text("dirty before\n")
        err = self.assertCaught("git commit -q -am 'fix: page'", "apps/web/page.tsx")
        self.assertIn(f"git reset --soft {self.base}", err)

    def test_bringing_the_default_branch_from_the_remote_is_not_writing_code(self):
        # O passo 0 da entrega: `git merge origin/<padrão>`, que avança sem commit de merge.
        git(self.repo, "checkout", "-q", "-b", "upstream")
        (self.repo / "apps/web/page.tsx").write_text("do remoto\n")
        tip = commit_all(self.repo, "feat: from the remote")
        git(self.repo, "checkout", "-q", "-")
        git(self.repo, "update-ref", "refs/remotes/origin/main", tip)
        git(self.repo, "branch", "-D", "upstream")
        self.assertEqual(pre(self.repo, "git merge origin/main")[0], 0)
        git(self.repo, "merge", "-q", "--ff-only", "origin/main")
        self.assertEqual(post(self.repo, "git merge origin/main")[0], 0)

    def test_reset_to_another_branch_that_changes_code_is_caught(self):
        self.assertCaught("git reset -q --hard impl", "apps/web/page.tsx")

    def test_reading_and_writing_what_is_not_code_is_not_accused(self):
        for command in ("cat apps/web/page.tsx", "git log --oneline | head -3",
                        "mkdir -p docs dist .harness-run; F=docs/n.ts; echo x > $F",
                        "mkdir -p dist; F=dist/out.js; echo x > $F",
                        "F=.harness-run/out.ts; echo x > $F",
                        "F=apps/web/NOTES.md; echo x > $F",
                        "git add -A docs; git commit -q -m 'docs: notes' -- docs"):
            rc, _, err = self.ran(command)
            self.assertEqual(rc, 0, f"{command}: {err}")

    def test_the_agent_worktree_is_where_code_is_written(self):
        write = "F=apps/web/page.tsx; echo x > $F; git commit -q -am 'feat: x'"
        self.assertEqual(self.ran(write, cwd=self.agent)[0], 0)
        self.assertEqual(self.ran(f"F='{self.agent}/apps/web/other.tsx'; echo x > \"$F\"")[0], 0)

    def test_the_owner_opened_direct_editing(self):
        say(self.repo, "/harness:direto troca o texto")
        self.assertEqual(self.ran("F=apps/web/page.tsx; echo x > $F")[0], 0)
        # outra sessão no mesmo worktree, rodando enquanto a sessão liberada escreve, não é acusada
        self.assertEqual(pre(self.repo, "git status", tid="t2", session="s2")[0], 0)
        self.assertEqual(self.ran("F=apps/web/other.tsx; echo x > $F")[0], 0)
        self.assertEqual(post(self.repo, "git status", tid="t2", session="s2")[0], 0)
        # e, sozinha, continua conferida
        self.assertEqual(self.ran("F=apps/web/third.tsx; echo x > $F", tid="t3", session="s2")[0], 2)

    def test_a_merge_commit_is_the_flow_and_is_not_accused(self):
        rc, _, err = self.ran("git merge --no-ff -q impl -m 'Merge ticket 01'")
        self.assertEqual(rc, 0, err)
        self.assertEqual((self.repo / "apps/web/page.tsx").read_text(), "from impl\n")

    def test_nothing_is_accused_while_integrate_runs(self):
        integrate = ".harness/integrate docs/specs/x/issues/01.md impl"
        self.assertEqual(pre(self.repo, integrate, tid="i1")[0], 0)
        # um revisor roda um comando enquanto o integrate mexe nos arquivos
        self.assertEqual(self.ran("F=apps/web/page.tsx; echo merging > $F", tid="r1")[0], 0)
        # o próprio integrate deixou algo sujo (instalação de dependência, junção desfeita)
        (self.repo / "apps/web/other.tsx").write_text("left by integrate\n")
        self.assertEqual(pre(self.repo, "git status", tid="r2")[0], 0)
        self.assertEqual(post(self.repo, integrate, tid="i1")[0], 0)
        self.assertEqual(post(self.repo, "git status", tid="r2")[0], 0, "o integrate terminou dentro da janela")
        # terminado o integrate, volta a conferir
        self.assertEqual(self.ran("F=apps/web/third.tsx; echo x > $F", tid="r3")[0], 2)
        # a forma tem de ser a exata: embutir o nome num comando não abre a janela
        self.assertEqual(self.ran(f"echo {integrate}; F=apps/web/fourth.tsx; echo x > $F", tid="r4")[0], 2)

    def test_an_integrate_marker_left_behind_expires(self):
        marker = os.path.join(self.state, "writers", "integrate")
        os.makedirs(os.path.dirname(marker))
        with open(marker, "w") as f:
            f.write("running\n")
        self.assertEqual(self.ran("F=apps/web/page.tsx; echo x > $F")[0], 0)
        old = time.time() - 3600
        os.utime(marker, (old, old))
        self.assertEqual(self.ran("F=apps/web/other.tsx; echo x > $F", tid="t2")[0], 2)

    def test_simultaneous_calls_do_not_mix(self):
        command = "F=apps/web/page.tsx; echo x > $F"
        self.assertEqual(pre(self.repo, command, tid="a")[0], 0)
        subprocess.run(["bash", "-c", command], cwd=str(self.repo))
        self.assertEqual(pre(self.repo, "git status", tid="b")[0], 0)
        self.assertEqual(post(self.repo, "git status", tid="b")[0], 0, "começou depois da escrita: não é dela")
        self.assertEqual(post(self.repo, command, tid="a")[0], 2)

    def test_without_a_tool_use_id_the_session_and_the_command_are_the_key(self):
        self.assertEqual(self.ran("F=apps/web/page.tsx; echo x > $F", tid=None)[0], 2)

    def test_the_baseline_is_removed_and_exact_harness_scripts_have_none(self):
        folder = os.path.join(self.state, "watch")
        self.assertEqual(pre(self.repo, "git status")[0], 0)
        self.assertEqual(len(os.listdir(folder)), 1)
        self.assertEqual(post(self.repo, "git status")[0], 0)
        self.assertEqual(os.listdir(folder), [])
        self.assertEqual(self.ran("F=apps/web/page.tsx; echo x > $F")[0], 2)
        self.assertEqual(os.listdir(folder), [], "também some depois de acusar")
        self.assertEqual(pre(self.repo, ".harness/ports-free")[0], 0)
        self.assertEqual(os.listdir(folder), [])
        log = pathlib.Path(self.state, "log.jsonl").read_text(encoding="utf-8")
        self.assertIn("code_watch", log)
        self.assertIn("apps/web/page.tsx", log)

    def test_an_internal_error_never_blocks(self):
        self.assertEqual(pre(self.repo, "git status")[0], 0)
        folder = os.path.join(self.state, "watch")
        name = os.listdir(folder)[0]
        with open(os.path.join(folder, name), "w") as f:
            f.write("{not json")
        (self.repo / "apps/web/page.tsx").write_text("x\n")
        self.assertEqual(post(self.repo, "git status")[0], 0)
        self.assertEqual(os.listdir(folder), [])
        self.assertIn("erro", pathlib.Path(self.state, "log.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(run_hook("code_watch.py", None, raw="{nao json")[0], 0)
        self.assertEqual(post(self.repo, "git status", tid="never-started")[0], 0)

    def test_the_baseline_is_cheap(self):
        for i in range(800):
            (self.repo / "apps/web" / f"f{i}.ts").write_text("x\n")
        commit_all(self.repo, "chore: many files")
        for i in range(20):
            (self.repo / "apps/web" / f"f{i}.ts").write_text("y\n")
        import code_watch
        start = time.time()
        code_watch.snapshot(str(self.repo))
        self.assertLess(time.time() - start, 0.5)

    def test_settings_wire_the_watch_and_every_writing_tool(self):
        settings = json.loads((ROOT / "plugin/templates/settings.json").read_text())
        # comando que sai com erro também grava: a conferência roda nos dois desfechos
        for event in ("PostToolUse", "PostToolUseFailure"):
            group = next(g for g in settings["hooks"][event] if g["matcher"] == "Bash")
            self.assertEqual(group["hooks"][0]["command"],
                             '[ -f "$CLAUDE_PROJECT_DIR/.harness/hooks/code_watch.py" ] || exit 0; '
                             'python3 -I "$CLAUDE_PROJECT_DIR/.harness/hooks/code_watch.py"', event)
        writing = next(g for g in settings["hooks"]["PreToolUse"] if "managed_guard" in g["hooks"][0]["command"])
        self.assertEqual(set(writing["matcher"].split("|")), {"Edit", "Write", "MultiEdit", "NotebookEdit"})
        self.assertEqual(writing["hooks"][0]["onFailure"], "block")
        self.assertTrue((self.repo / ".harness/hooks/code_watch.py").exists())

    def test_every_writing_tool_is_denied_on_app_code(self):
        def write(tool, key, path):
            return run_hook("managed_guard.py", {"tool_name": tool, "cwd": str(self.repo), "session_id": "s1",
                                                 "tool_input": {key: str(path), "content": "x\n", "new_source": "x"}})
        for tool, key in (("Write", "file_path"), ("NotebookEdit", "notebook_path"), ("NotebookEdit", "file_path"),
                          ("MultiEdit", "file_path")):
            rc, _, err = write(tool, key, "apps/web/analysis.ipynb")
            self.assertEqual(rc, 2, (tool, key))
            self.assertIn("harness:entregar", err)
            self.assertEqual(write(tool, key, self.agent / "apps/web/analysis.ipynb")[0], 0, (tool, key))
            self.assertEqual(write(tool, key, ".git/config")[0], 2, (tool, key))
        self.assertEqual(write("NotebookEdit", "notebook_path", "docs/n.md")[0], 0)
        self.assertEqual(write("NotebookEdit", "other", "x")[0], 2, "sem caminho, negado")
        self.assertEqual(write("NotebookEdit", "notebook_path", "AGENTS.md")[0], 2, "a região gerenciada só por Edit e Write")


class TestIntegrateMarksItself(unittest.TestCase):
    def test_integrate_leaves_its_marker_in_the_state(self):
        repo = make_repo()
        self.assertEqual(sync(repo).returncode, 0)
        ticket = repo / "docs/specs/x/issues/01-agenda.md"
        ticket.parent.mkdir(parents=True)
        ticket.write_text("# a\n\nStatus: claimed\nBlocked by:\nOwns: src/agenda\n")
        commit_all(repo, "chore: adopt harness")
        git(repo, "checkout", "-q", "-b", "feat/x")
        agent = repo / ".claude/worktrees/agent-a"
        git(repo, "worktree", "add", "-q", "-b", "worktree-agent-a", str(agent), "HEAD")
        (agent / "src/agenda").mkdir(parents=True)
        (agent / "src/agenda/a.py").write_text("x\n")
        path = agent / "docs/specs/x/issues/01-agenda.md"
        path.write_text(path.read_text().replace("claimed", "done"))
        commit_all(agent, "feat: agenda")
        bug_review_passes(repo, "worktree-agent-a")
        command = ".harness/integrate docs/specs/x/issues/01-agenda.md worktree-agent-a"
        self.assertEqual(pre(repo, "git status", tid="r1")[0], 0)
        r = subprocess.run(command.split(), cwd=repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        marker = os.path.join(common.state_dir(str(repo)), "writers", "integrate")
        self.assertEqual(pathlib.Path(marker).read_text().strip(), "done")
        (repo / "src/agenda/a.py").write_text("left dirty\n")
        self.assertEqual(post(repo, "git status", tid="r1")[0], 0, "o integrate rodou dentro da janela")


if __name__ == "__main__":
    unittest.main()
