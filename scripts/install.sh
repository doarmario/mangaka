#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec docker compose --project-directory "$ROOT_DIR" -f "$ROOT_DIR/compose.install.yaml" run --build --rm installer
