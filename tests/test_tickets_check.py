import subprocess
import sys
import unittest

from tests.helpers import ROOT, commit_all, make_repo, sync

sys.path.insert(0, str(ROOT / "plugin/payload"))
import tickets_check  # noqa: E402

SCRIPT = str(ROOT / "plugin/payload/tickets_check.py")


def spec(repo, tickets, slug="x", header=None):
    """tickets: {"01-a": ("open", "")}. Grava docs/specs/<slug>/issues/*.md e devolve a pasta da spec."""
    folder = repo / "docs/specs" / slug
    (folder / "issues").mkdir(parents=True, exist_ok=True)
    (folder / "spec.md").write_text("# spec\n")
    for name, (status, blocked) in tickets.items():
        text = header(status, blocked) if header else f"# {name}\n\nStatus: {status}\nBlocked by: {blocked}\nOwns: src/{name}\n\ncorpo\n"
        (folder / "issues" / f"{name}.md").write_text(text)
    return folder


def load(folder):
    return tickets_check.load(str(folder / "issues"))


class TestTicketsCheck(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo()

    def test_valid_graph_and_frontier(self):
        folder = spec(self.repo, {"01-a": ("done", ""), "02-b": ("open", "01"),
                                  "03-c": ("open", "02"), "04-d": ("open", "")})
        tickets = load(folder)
        self.assertEqual(tickets_check.problems(tickets), [])
        self.assertEqual(tickets_check.frontier(tickets), [2, 4])
        self.assertEqual(tickets[3]["blocked_by"], [2])

    def test_claimed_and_done_are_not_in_the_frontier(self):
        folder = spec(self.repo, {"01-a": ("claimed", ""), "02-b": ("done", ""), "03-c": ("open", "01")})
        self.assertEqual(tickets_check.frontier(load(folder)), [])

    def test_missing_reference_self_reference_and_cycle(self):
        for tickets, tokens in (({"01-a": ("open", "07")}, ("01", "07")),
                                ({"01-a": ("open", "01")}, ("01",)),
                                ({"01-a": ("open", "03"), "02-b": ("open", "01"), "03-c": ("open", "02")},
                                 ("01", "02", "03"))):
            repo = make_repo()
            found = tickets_check.problems(load(spec(repo, tickets)))
            self.assertEqual(len(found), 1, found)
            for token in tokens:
                self.assertIn(token, found[0])

    def test_duplicate_number_bad_name_or_bad_status(self):
        for tickets in ({"01-a": ("open", ""), "01-b": ("open", "")}, {"1-a": ("open", "")},
                        {"01-a": ("started", "")}, {"sem-numero": ("open", "")}):
            repo = make_repo()
            with self.assertRaises(ValueError) as ctx:
                load(spec(repo, tickets))
            self.assertIn(".md", str(ctx.exception))

    def test_missing_status_or_blocked_by_line(self):
        for header in (lambda s, b: "# t\n\nStatus: open\n\ncorpo\n", lambda s, b: "# t\n\nBlocked by:\n\ncorpo\n"):
            repo = make_repo()
            with self.assertRaises(ValueError):
                load(spec(repo, {"01-a": ("open", "")}, header=header))

    def test_blocked_by_parsing(self):
        folder = spec(self.repo, {"01-a": ("done", ""), "02-b": ("done", ""), "03-c": ("open", "01, 02"),
                                  "04-d": ("open", "1,3")})
        tickets = load(folder)
        self.assertEqual(tickets[3]["blocked_by"], [1, 2])
        self.assertEqual(tickets[4]["blocked_by"], [1, 3])
        with self.assertRaises(ValueError):
            load(spec(make_repo(), {"01-a": ("open", "nenhum")}))

    def test_header_lines_only_count_in_the_first_ten(self):
        late = lambda s, b: "# t\n" + "linha\n" * 20 + "Status: done\nBlocked by:\n"
        with self.assertRaises(ValueError):
            load(spec(self.repo, {"01-a": ("open", "")}, header=late))

    def test_cli(self):
        run = lambda folder, *a: subprocess.run([sys.executable, "-I", SCRIPT, str(folder), *a],
                                                capture_output=True, text=True)
        folder = spec(self.repo, {"01-a": ("done", ""), "02-b": ("open", "01"), "03-c": ("open", "")})
        r = run(folder)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "ok: 3 tickets"))
        self.assertEqual(run(folder, "--frontier").stdout.splitlines(),
                         [str(folder / "issues/02-b.md"), str(folder / "issues/03-c.md")])
        cyclic = spec(make_repo(), {"01-a": ("open", "02"), "02-b": ("open", "01")})
        r = run(cyclic)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ciclo", r.stderr)
        self.assertEqual(run(cyclic, "--frontier").returncode, 1)
        empty = self.repo / "docs/specs/vazia"
        empty.mkdir(parents=True)
        self.assertEqual(run(empty).stdout.strip(), "ok: 0 tickets")
        broken = spec(make_repo(), {"01-a": ("started", "")})
        self.assertEqual(run(broken).returncode, 1)

    def test_validate_rejects_a_broken_graph(self):
        self.assertEqual(sync(self.repo).returncode, 0)
        validate = lambda: subprocess.run([str(self.repo / ".harness/validate"), "--profile", "push"],
                                          cwd=self.repo, capture_output=True, text=True)
        spec(self.repo, {"01-a": ("open", "")})
        self.assertEqual(validate().returncode, 0, validate().stderr)
        spec(self.repo, {"01-a": ("open", "02"), "02-b": ("open", "01")}, slug="y")
        r = validate()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("docs/specs/y", r.stderr)


if __name__ == "__main__":
    unittest.main()
