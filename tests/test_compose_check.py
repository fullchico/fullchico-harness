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

    def test_named_volume_that_is_really_a_host_bind_is_a_violation(self):
        c = cfg(volumes=[{"type": "volume", "source": "hostroot", "target": "/outside"}])
        c["volumes"] = {"hostroot": {"name": "p_hostroot", "driver": "local",
                                     "driver_opts": {"type": "none", "o": "bind", "device": "/tmp"}}}
        out = self.v(c)
        self.assertEqual(len(out), 1, out)
        self.assertIn("hostroot", out[0])

    def test_plain_named_volume_passes_and_unusual_ones_do_not(self):
        c = cfg(volumes=[{"type": "volume", "source": "pgdata", "target": "/var/lib"}])
        c["volumes"] = {"pgdata": {"name": "p_pgdata"}}
        self.assertEqual(self.v(c), [])
        for odd in ({"driver": "nfs"}, {"external": True}, {"driver_opts": {"device": "/x"}}):
            c["volumes"] = {"pgdata": dict({"name": "p_pgdata"}, **odd)}
            self.assertEqual(len(self.v(c)), 1, odd)
        c["volumes"] = {}
        self.assertEqual(len(self.v(cfg(volumes=[{"type": "npipe", "source": "x", "target": "/y"}]))), 1)

    def test_secrets_and_configs_from_host_files_are_violations(self):
        for key in ("secrets", "configs"):
            inside = cfg(**{key: [{"source": "s"}]})
            inside[key] = {"s": {"file": str(self.root / "data" / "s.txt")}}
            self.assertEqual(self.v(inside), [], key)
            outside = cfg(**{key: [{"source": "s"}]})
            outside[key] = {"s": {"file": "/etc/passwd"}}
            self.assertEqual(len(self.v(outside)), 1, key)
            external = cfg()
            external[key] = {"s": {"external": True}}
            self.assertEqual(len(self.v(external)), 1, key)

    def test_build_context_outside_the_project_is_a_violation(self):
        self.assertEqual(self.v({"services": {"app": {"build": {"context": str(self.root)}}}}), [])
        self.assertEqual(self.v({"services": {"app": {"build": {
            "context": str(self.root), "dockerfile": "Dockerfile.dev"}}}}), [])
        for build in ({"context": "/tmp"}, {"context": str(self.root.parent)},
                      {"context": str(self.root), "dockerfile": "/tmp/Dockerfile"},
                      {"context": str(self.root), "additional_contexts": {"x": "/tmp"}},
                      {"context": str(self.root), "ssh": ["default"]},
                      {"context": str(self.root), "secrets": [{"source": "s"}]}):
            self.assertEqual(len(self.v({"services": {"app": {"build": build}}})), 1, build)

    def test_env_file_outside_the_project_is_a_violation(self):
        ok = cfg(env_file=[{"path": str(self.root / ".env")}])
        self.assertEqual(self.v(ok), [])
        self.assertEqual(len(self.v(cfg(env_file=[{"path": "/etc/environment"}]))), 1)
        self.assertEqual(len(self.v(cfg(env_file=["/etc/environment"]))), 1)

    def test_fields_outside_the_known_set_are_refused(self):
        for extra in ({"security_opt": ["seccomp:unconfined"]}, {"userns_mode": "host"},
                      {"cgroup_parent": "x"}, {"volumes_from": ["container:other"]},
                      {"network_mode": "container:other"}, {"campo_inventado": 1}):
            out = self.v(cfg(**extra))
            self.assertEqual(len(out), 1, extra)
            self.assertIn(next(iter(extra)), out[0])

    def test_common_dev_fields_pass(self):
        c = cfg(command=["postgres"], environment={"A": "b"}, healthcheck={"test": ["CMD", "true"]},
                depends_on={"x": {"condition": "service_started"}}, restart="unless-stopped",
                networks={"default": None}, ports=[{"published": "1", "target": 1}], user="1000",
                working_dir="/app", labels={"a": "b"}, ulimits={"nofile": 1024}, shm_size="1gb",
                extra_hosts=["host.docker.internal=host-gateway"], init=True, platform="linux/arm64",
                profiles=["dev"], stop_grace_period="5s", tmpfs=["/tmp"], logging={"driver": "json-file"},
                container_name="c", hostname="h", entrypoint=["x"], expose=["1"], tty=True, stdin_open=True,
                read_only=True, pull_policy="missing", mem_limit="1g", cpus=1, network_mode="bridge")
        self.assertEqual(self.v(c), [])

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

    def app(self, source, **volume):
        return cfg(volumes=[dict({"type": "bind", "source": str(source), "target": "/work"}, **volume)])

    def test_project_mount_gets_the_rails_read_only(self):
        (self.root / ".harness").mkdir()
        (self.root / "harness.conf").write_text("PROJECT=x\n")
        extra = compose_check.protection(self.app(self.root), str(self.root))["services"]["db"]["volumes"]
        targets = {v["target"]: v for v in extra}
        self.assertIn("/work/.harness", targets)
        self.assertIn("/work/harness.conf", targets)
        self.assertIn("/work/.git", targets)
        self.assertTrue(all(v["read_only"] and v["type"] == "bind" for v in extra))
        self.assertEqual(targets["/work/.harness"]["source"], os.path.realpath(self.root / ".harness"))
        self.assertNotIn("/work/CLAUDE.md", targets)  # não existe neste projeto: nada a montar

    def test_mounts_that_cannot_write_the_rails_need_no_protection(self):
        (self.root / ".harness").mkdir()
        self.assertEqual(compose_check.protection(self.app(self.root / "data"), str(self.root)), {})
        self.assertEqual(compose_check.protection(self.app(self.root, read_only=True), str(self.root)), {})
        self.assertEqual(compose_check.protection(cfg(), str(self.root)), {})

    def test_writable_mount_of_a_rail_is_a_violation(self):
        (self.root / ".harness" / "hooks").mkdir(parents=True)
        (self.root / ".claude").mkdir()
        for path in (".harness", ".harness/hooks", ".claude"):
            self.assertTrue(any("trilho" in x for x in self.v(self.app(self.root / path))), path)
        self.assertEqual(self.v(self.app(self.root / ".harness", read_only=True)), [])

    def test_cli_protect_prints_the_override(self):
        (self.root / ".harness").mkdir()
        r = subprocess.run([sys.executable, SCRIPT, str(self.root), "--protect"], input=json.dumps(self.app(self.root)),
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("/work/.harness", r.stdout)
        json.loads(r.stdout)

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
