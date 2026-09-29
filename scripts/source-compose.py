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
    root = Path(__file__).resolve().parents[1]
    services = {}
    for source in packages:
        if not source.enabled or not source.image:
            continue
        service = {'image': source.image, 'restart': 'unless-stopped',
                   'security_opt': ['no-new-privileges:true'], 'cap_drop': ['ALL']}
        context = root / 'integrations' / source.id
        if (context / 'Dockerfile').is_file():
            service['build'] = f'./integrations/{source.id}'
        services[f'source-{source.id}'] = service
    return {'services': services}


if __name__ == '__main__':
    try:
        print(json.dumps(compile_services(Path(__file__).resolve().parents[1] / 'sources'), sort_keys=True))
    except ValueError as exc:
        print(f'Source package error: {exc}', file=sys.stderr)
        sys.exit(1)
