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
        (self.repo / ".gitignore").write_text(".env\n")
        (self.repo / ".env").touch()
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        self.git("push", "-u", "origin", "HEAD")
        self.calls = root / "calls.jsonl"
        binaries = root / "bin"
        binaries.mkdir()
        docker = binaries / "docker"
        docker.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['CALL_LOG'], 'a') as f:\n"
            "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "if 'mysqldump' in ' '.join(sys.argv): print('SQL_BACKUP')\n"
            "if sys.argv[-2:] == ['db', 'upgrade'] and os.environ.get('FAIL_MIGRATION'):\n"
            "    sys.exit(1)\n"
        )
        docker.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{binaries}:{os.environ['PATH']}",
                        CALL_LOG=str(self.calls), GIT_TERMINAL_PROMPT="0")
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
        self.assertIn(["build", "web", "manga-novel", "qiscans", "demonicscans"], commands)
        self.assertEqual(commands[-1], ["up", "-d", "--wait", "--wait-timeout", "180",
                                        "web", "updates-worker", "manga-novel", "qiscans", "demonicscans"])
        backup = list((self.marker.parent / "backups").glob("*.sql"))
        self.assertEqual(len(backup), 1)
        self.assertEqual(backup[0].read_text().strip(), "SQL_BACKUP")
        before = self.calls.read_text()
        self.assertEqual(self.update().returncode, 0)
        self.assertEqual(self.calls.read_text(), before)

    def test_dirty_checkout_does_not_touch_docker(self):
        (self.repo / "local-change").touch()
        self.assertNotEqual(self.update().returncode, 0)
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
