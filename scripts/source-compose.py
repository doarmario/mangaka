"""Compile trusted local manifests into a restricted Compose overlay (JSON)."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_registry import load_packages


def compile_services(directory):
    packages, errors = load_packages(directory)
    if errors:
        raise ValueError('; '.join(f"{e['package']}: {e['message']}" for e in errors))
    return {'services': {
        f'source-{s.id}': {'image': s.image, 'restart': 'unless-stopped',
                         'security_opt': ['no-new-privileges:true'],
                         'cap_drop': ['ALL']}
        for s in packages if s.enabled and s.image
    }}


if __name__ == '__main__':
    try:
        print(json.dumps(compile_services(Path(__file__).resolve().parents[1] / 'sources'), sort_keys=True))
    except ValueError as exc:
        print(f'Source package error: {exc}', file=sys.stderr)
        sys.exit(1)
