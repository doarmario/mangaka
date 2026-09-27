"""Exercise the deployment script with real Git and a simulated Docker daemon."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AutoUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo = root / "checkout with spaces"
        remote = root / "remote.git"
        self.git("init", "--bare", str(remote), cwd=root)
        self.git("clone", str(remote), str(self.repo), cwd=root)
        self.git("config", "user.name", "Update test")
        self.git("config", "user.email", "test@example.invalid")
        (self.repo / "scripts").mkdir()
        shutil.copy(ROOT / "scripts/auto-update.sh", self.repo / "scripts")
        shutil.copy(ROOT / "scripts/deploy-update.sh", self.repo / "scripts")
        self.services = ["web", "updates-worker", "manga-novel", "qiscans", "demonicscans", "thunderscans", "mysql", "redis"]
        (self.repo / "services.txt").write_text("\n".join(self.services + ["init-db"]))
        (self.repo / ".gitignore").write_text(".env\n")
        (self.repo / ".env").touch()
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        self.git("push", "-u", "origin", "HEAD")
        self.calls = root / "calls.jsonl"
        binaries = root / "bin"
        binaries.mkdir()
        docker = binaries / "docker"
        docker.write_text("""#!/usr/bin/env python3
import json, os, sys, subprocess
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['CALL_LOG'], 'a') as f:
    f.write(json.dumps(args) + '\\n')
services = Path('services.txt').read_text().splitlines()
running = Path(os.environ['RUNNING_STATE'])
if args[-2:] == ['config', '--services']: print('\\n'.join(services))
if args[-3:] == ['ps', '--format', 'json']:
    if os.environ.get('PS_ERROR'): sys.exit(1)
    active = running.read_text().splitlines() if running.exists() else []
    rows = [{'Service': s, 'State': 'running', 'Health': 'unhealthy' if s == os.environ.get('UNHEALTHY_SERVICE') else 'healthy'} for s in active]
    print(json.dumps(rows) if os.environ.get('PS_ARRAY') else '\\n'.join(json.dumps(r) for r in rows))
if 'build' in args:
    assert subprocess.run(['flock', '-n', '.git/mangaka-update/lock', 'true']).returncode != 0
if '--wait-timeout' in args:
    running.write_text('\\n'.join(s for s in services if s != 'init-db'))
if 'mysqldump' in ' '.join(args): print('SQL_BACKUP')
if args[-2:] == ['db', 'upgrade'] and os.environ.get('FAIL_MIGRATION'): sys.exit(1)
""")
        docker.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{binaries}:{os.environ['PATH']}",
                        CALL_LOG=str(self.calls), RUNNING_STATE=str(root / "running"), GIT_TERMINAL_PROMPT="0")
        self.marker = self.repo / ".git/mangaka-update/deployed"

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.repo,
                              check=True, capture_output=True, text=True)

    def update(self, **environment):
        return subprocess.run(["bash", "scripts/auto-update.sh"], cwd=self.repo,
                              env=self.env | environment, capture_output=True, text=True)

    def test_deploy_then_skip_unchanged_commit(self):
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        compose_calls = [call for call in calls if call[0] == "compose"]
        for call in compose_calls:
            self.assertEqual(call[1:5], ["--project-directory", str(self.repo),
                                        "-f", str(self.repo / "compose.yaml")])
            self.assertNotIn("auto-updater", call)
            self.assertNotIn("--remove-orphans", call)
        commands = [call[5:] for call in compose_calls]
        self.assertIn(["build", *self.services], commands)
        self.assertIn(["up", "-d", "--wait", "--wait-timeout", "180", *self.services], commands)
        backup = list((self.marker.parent / "backups").glob("*.sql"))
        self.assertEqual(len(backup), 1)
        self.assertEqual(backup[0].read_text().strip(), "SQL_BACKUP")
        before = self.calls.read_text()
        self.assertEqual(self.update().returncode, 0)
        new_calls = [json.loads(line) for line in self.calls.read_text()[len(before):].splitlines()]
        self.assertTrue(any(call[-3:] == ["ps", "--format", "json"] for call in new_calls))
        self.assertFalse(any("build" in call or "stop" in call for call in new_calls))

    def test_dirty_checkout_does_not_touch_docker(self):
        (self.repo / "local-change").touch()
        self.assertNotEqual(self.update().returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_new_commit_uses_new_deployment_code_and_new_service(self):
        publisher = Path(self.temp.name) / "publisher"
        self.git("clone", str(Path(self.temp.name) / "remote.git"), str(publisher))
        helper = publisher / "scripts/deploy-update.sh"
        helper.write_text(helper.read_text().replace(
            "compose config --quiet", "echo 'New deployment code loaded'\ncompose config --quiet"))
        services = publisher / "services.txt"
        services.write_text(services.read_text() + "\nfuture-source\n")
        self.git("add", ".", cwd=publisher)
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-m", "Add a new source and deployment code", cwd=publisher)
        self.git("push", cwd=publisher)
        target = self.git("rev-parse", "HEAD", cwd=publisher).stdout.strip()
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("New deployment code loaded", result.stdout)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertTrue(any("build" in call and "future-source" in call for call in calls))
        self.assertTrue(any("--wait-timeout" in call and "future-source" in call for call in calls))
        self.assertEqual(self.marker.read_text().strip(), target)

    def test_missing_container_is_repaired_even_for_deployed_commit(self):
        self.assertEqual(self.update().returncode, 0)
        Path(self.env['RUNNING_STATE']).write_text("\n".join(
            service for service in self.services if service != 'thunderscans'))
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Reparando a implantação', result.stdout)
        self.assertIn('thunderscans', Path(self.env['RUNNING_STATE']).read_text())
        self.assertEqual(len(list((self.marker.parent / 'backups').glob('*.sql'))), 2)

    def test_failed_repair_does_not_keep_a_success_marker(self):
        self.assertEqual(self.update().returncode, 0)
        Path(self.env['RUNNING_STATE']).write_text('web\n')
        result = self.update(FAIL_MIGRATION='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.marker.exists())
        self.assertTrue(self.marker.with_name('deployed.previous').exists())
        self.assertEqual(self.update().returncode, 0)
        self.assertTrue(self.marker.exists())

    def test_unhealthy_container_does_not_mark_deployment_success(self):
        self.assertNotEqual(self.update(UNHEALTHY_SERVICE='thunderscans').returncode, 0)
        self.assertFalse(self.marker.exists())

    def test_compose_json_array_is_supported(self):
        self.assertEqual(self.update(PS_ARRAY='1').returncode, 0)
        result = self.update(PS_ARRAY='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Instalação já atualizada', result.stdout)

    def test_failed_state_query_does_not_restart_services(self):
        self.assertEqual(self.update().returncode, 0)
        before = self.calls.read_text()
        self.assertNotEqual(self.update(PS_ERROR='1').returncode, 0)
        self.assertNotIn('"stop"', self.calls.read_text()[len(before):])

    def test_deployment_helper_requires_the_update_lock(self):
        target = self.git('rev-parse', 'HEAD').stdout.strip()
        result = subprocess.run(['bash', 'scripts/deploy-update.sh', target],
                                cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('lock', result.stderr)
        self.assertFalse(self.calls.exists())

    def test_wrong_user_cannot_write_git_or_invoke_docker(self):
        fake_id = Path(self.env['PATH'].split(':')[0]) / 'id'
        fake_id.write_text('#!/bin/sh\necho 987654\n')
        fake_id.chmod(0o755)
        before = (self.repo / '.git/index').read_bytes()
        result = self.update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('dono do projeto', result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.marker.parent.exists())
        self.assertEqual((self.repo / '.git/index').read_bytes(), before)

    def test_unpushed_commit_does_not_touch_docker(self):
        self.git("commit", "--allow-empty", "-m", "local")
        self.assertNotEqual(self.update().returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_migration_failure_retries_without_success_marker(self):
        self.assertNotEqual(self.update(FAIL_MIGRATION="1").returncode, 0)
        self.assertFalse(self.marker.exists())
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.marker.exists())

    def test_invalid_poll_interval(self):
        for interval in ("0", "59", "abc", "1000000"):
            result = subprocess.run(["bash", str(ROOT / "integrations/updater/loop.sh")],
                                    env=self.env | {"AUTO_UPDATE_INTERVAL_SECONDS": interval},
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AUTO_UPDATE_INTERVAL_SECONDS", result.stderr)


if __name__ == "__main__":
    unittest.main()
