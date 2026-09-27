"""Build an isolated private checkout and verify the real non-root HTTP service.

Usage: python3 tests/source_image_permissions.py thunderscans
Requires Docker; intentionally separate from the offline unit test suite.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def verify(source):
    image = f'mangaka-{source}-permissions-test'
    with tempfile.TemporaryDirectory(prefix=f'{source}-private-') as temporary:
        context = Path(temporary) / 'context'
        shutil.copytree(ROOT / 'integrations' / source, context, symlinks=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache', '*.egg-info'))
        for path in [context, *context.rglob('*')]:
            if not path.is_symlink():
                path.chmod(0o700 if path.is_dir() else 0o600)
        subprocess.run(['docker', 'build', '-t', image, str(context)], check=True)
        owner = subprocess.check_output(['docker', 'image', 'inspect', image,
                                         '--format', '{{.Config.User}}'], text=True).strip()
        assert owner == '65534:65534', f'Unexpected runtime user: {owner}'
        container = subprocess.check_output(['docker', 'run', '-d', image], text=True).strip()
        try:
            deadline = time.monotonic() + 70
            while time.monotonic() < deadline:
                state = json.loads(subprocess.check_output(
                    ['docker', 'inspect', container, '--format', '{{json .State}}'], text=True))
                if state.get('Health', {}).get('Status') == 'healthy':
                    print(f'{source}: private checkout builds and serves HTTP as non-root.', flush=True)
                    return
                if not state['Running'] or state.get('Health', {}).get('Status') == 'unhealthy':
                    break
                time.sleep(1)
            subprocess.run(['docker', 'logs', '--tail=40', container], check=False)
            raise RuntimeError(f'{source}: HTTP healthcheck did not succeed')
        finally:
            subprocess.run(['docker', 'rm', '-f', container], check=False, stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', choices=['qiscans', 'demonicscans', 'thunderscans'])
    verify(parser.parse_args().source)
