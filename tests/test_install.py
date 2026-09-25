"""Installer orchestration tests: local Git repository and simulated Docker."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo = root / "checkout with spaces"
        self.api = root / "api"
        self.repo.mkdir()
        self.api.mkdir()
        self.calls = root / "calls"
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=str(root / "gitconfig"),
                        MANGAKA_INSTALL_ROOT=str(self.repo), MANGAKA_INSTALL_API=str(self.api),
                        HOSTNAME="installer-test", CALL_LOG=str(self.calls))
        subprocess.run(["git", "init", str(self.repo)], check=True, capture_output=True)
        shutil.copy(ROOT / ".env.example", self.repo)
        upstream = root / "upstream"
        subprocess.run(["git", "init", str(upstream)], check=True, capture_output=True)
        (upstream / "package.json").write_text('{"name":"fixture"}')
        subprocess.run(["git", "-C", str(upstream), "add", "."], check=True)
        subprocess.run(["git", "-C", str(upstream), "-c", "user.name=Test", "-c",
                        "user.email=test@example.invalid", "commit", "-m", "fixture"],
                       check=True, capture_output=True)
        subprocess.run(["git", "config", "--global", f"url.{upstream.as_uri()}.insteadOf",
                        "https://github.com/Raby012/-manga-novel-api.git"],
                       env=self.env, check=True)
        binaries = root / "bin"
        binaries.mkdir()
        fake = binaries / "docker"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "args = sys.argv[1:]\n"
            "with open(os.environ['CALL_LOG'], 'a') as f:\n"
            "    f.write(json.dumps({'args': args, 'host': os.getenv('MANGAKA_HOST_WORKSPACE'),\n"
            "                        'api': os.getenv('MANGAKA_HOST_UPSTREAM')}) + '\\n')\n"
            "if args[0] == 'inspect':\n"
            "    print(json.dumps([{'Destination': x, 'Source': '/host' + x}\n"
            "                      for x in ['/workspace', '/upstream', '/var/run/docker.sock']]))\n"
            "elif args[-3:] == ['config', '--format', 'json']:\n"
            "    print(json.dumps({'services': {'web': {'ports': [{'published': '5000'}]}}}))\n"
            "if args[-2:] == ['db', 'upgrade'] and os.getenv('FAIL_MIGRATION'): sys.exit(1)\n"
        )
        fake.chmod(0o755)
        self.env['PATH'] = f"{binaries}:{os.environ['PATH']}"

    def install(self, **env):
        return subprocess.run(["bash", str(ROOT / "integrations/updater/install.sh")],
                              env=self.env | env, capture_output=True, text=True)

    def test_fresh_install_and_repeat_preserve_credentials(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        config = (self.repo / ".env").read_text()
        self.assertNotIn("=troque-", config)
        self.assertIn("MANGA_NOVEL_SOURCE_DIR=./.local/manga-novel-api", config)
        self.assertEqual((self.repo / ".env").stat().st_mode & 0o777, 0o600)
        self.assertTrue((self.api / "package.json").is_file())
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertTrue(any(c['args'][-5:] == ['build', 'web', 'manga-novel', 'qiscans', 'demonicscans'] for c in calls))
        self.assertTrue(any(c['args'][-5:] == ['web', 'updates-worker', 'manga-novel', 'qiscans', 'demonicscans'] for c in calls))
        updater = next(c for c in calls if c['args'][-1] == 'auto-updater')
        self.assertEqual(updater['host'], '/host/workspace')
        self.assertEqual(updater['api'], '/host/upstream')
        self.assertIn('http://localhost:5000', result.stdout)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / ".env").read_text(), config)

    def test_existing_api_files_are_not_overwritten(self):
        (self.api / "custom.txt").write_text("keep")
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.api / "custom.txt").read_text(), "keep")
        self.assertNotIn('"build"', self.calls.read_text())

    def test_example_passwords_are_rejected_without_replacing_env(self):
        shutil.copy(self.repo / ".env.example", self.repo / ".env")
        before = (self.repo / ".env").read_bytes()
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual((self.repo / ".env").read_bytes(), before)

    def test_migration_failure_does_not_start_updater(self):
        self.assertNotEqual(self.install(FAIL_MIGRATION="1").returncode, 0)
        self.assertNotIn('"auto-updater"', self.calls.read_text())

    def test_wrong_user_cannot_create_configuration(self):
        fake_id = Path(self.env['PATH'].split(':')[0]) / 'id'
        fake_id.write_text('#!/bin/sh\necho 987654\n')
        fake_id.chmod(0o755)
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('dono dos arquivos', result.stderr)
        self.assertFalse((self.repo / '.env').exists())
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
