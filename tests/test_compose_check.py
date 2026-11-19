import json
import os
import subprocess
import sys
import unittest

from tests.helpers import ROOT, make_repo

sys.path.insert(0, str(ROOT / "plugin/payload"))
import compose_check  # noqa: E402

SCRIPT = str(ROOT / "plugin/payload/compose_check.py")


def cfg(**service):
    return {"name": "p", "services": {"db": dict({"image": "postgres:16"}, **service)}}


def bind(src, dst="/data"):
    return {"volumes": [{"type": "bind", "source": src, "target": dst}]}


class TestComposeCheck(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        (self.root / "data").mkdir()

    def v(self, config):
        return compose_check.violations(config, str(self.root))

    def test_clean_configs_pass(self):
        self.assertEqual(self.v(cfg()), [])
        self.assertEqual(self.v(cfg(**bind(str(self.root / "data")))), [])
        self.assertEqual(self.v(cfg(**bind(str(self.root)))), [])
        self.assertEqual(self.v(cfg(volumes=[{"type": "volume", "source": "pgdata", "target": "/var/lib"}])), [])
        self.assertEqual(self.v(cfg(volumes=[{"type": "tmpfs", "target": "/tmp"}])), [])
        self.assertEqual(self.v(cfg(privileged=False, cap_add=[], devices=[], network_mode="bridge")), [])

    def test_bind_outside_the_project_is_a_violation(self):
        home = os.path.expanduser("~")
        for src in [home, os.path.join(home, ".claude"), "/var/run/docker.sock", "/",
                    str(self.root.parent), str(self.root / "data" / ".." / ".."),
                    str(self.root) + "-outro"]:
            out = self.v(cfg(**bind(src)))
            self.assertEqual(len(out), 1, src)
            self.assertIn("db", out[0])

    def test_symlink_inside_pointing_outside_is_a_violation(self):
        os.symlink(os.path.expanduser("~"), self.root / "link")
        self.assertEqual(len(self.v(cfg(**bind(str(self.root / "link"))))), 1)

    def test_git_dir_is_not_mountable(self):
        self.assertEqual(len(self.v(cfg(**bind(str(self.root / ".git"))))), 1)

    def test_host_access_flags_are_violations(self):
        for extra in [{"privileged": True}, {"pid": "host"}, {"ipc": "host"}, {"network_mode": "host"},
                      {"cap_add": ["SYS_ADMIN"]}, {"devices": [{"source": "/dev/sda", "target": "/dev/sda"}]}]:
            self.assertEqual(len(self.v(cfg(**extra))), 1, extra)

    def test_every_service_is_checked(self):
        c = cfg()
        c["services"]["evil"] = {"image": "x", "privileged": True}
        self.assertIn("evil", self.v(c)[0])

    def test_malformed_config_is_a_violation_not_a_pass(self):
        for bad in ({}, {"services": []}, {"services": {"db": "x"}}, {"services": {"db": {"volumes": "x"}}}):
            self.assertTrue(self.v(bad), bad)

    def test_summary_lists_images_ports_and_mounts(self):
        c = cfg(ports=[{"published": "25432", "target": 5432}], **bind(str(self.root / "data")))
        c["services"]["app"] = {"build": {"context": str(self.root)}}
        s = compose_check.summary(c, str(self.root))
        for token in ("db", "postgres:16", "25432", "data", "app", "build local"):
            self.assertIn(token, s)
        self.assertNotIn(str(self.root), s)

    def test_cli(self):
        def run(data, *args):
            return subprocess.run([sys.executable, SCRIPT, str(self.root), *args], input=data,
                                  capture_output=True, text=True)
        self.assertEqual(run(json.dumps(cfg())).returncode, 0)
        r = run(json.dumps(cfg(privileged=True)))
        self.assertEqual(r.returncode, 1)
        self.assertIn("db", r.stderr)
        self.assertEqual(run("{nao json").returncode, 1)
        self.assertEqual(run("").returncode, 1)
        self.assertIn("postgres:16", run(json.dumps(cfg()), "--summary").stdout)


if __name__ == "__main__":
    unittest.main()
