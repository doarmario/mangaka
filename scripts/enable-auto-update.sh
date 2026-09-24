#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$ROOT_DIR" == *$'\n'* ]]; then
    echo "Caminho da instalação não pode conter quebra de linha." >&2
    exit 1
fi
docker info >/dev/null
docker compose version >/dev/null
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"
# Escape systemd quoted strings and specifiers, including paths with spaces.
UNIT_ROOT="${ROOT_DIR//\\/\\\\}"
UNIT_ROOT="${UNIT_ROOT//\"/\\\"}"
UNIT_ROOT="${UNIT_ROOT//%/%%}"
cat > "$UNIT_DIR/mangaka-update.service" <<EOF
[Unit]
Description=Atualização automática do Mangaka

[Service]
Type=oneshot
WorkingDirectory="$UNIT_ROOT"
ExecStart=/bin/bash "$UNIT_ROOT/scripts/auto-update.sh"
Environment=GIT_TERMINAL_PROMPT=0
TimeoutStartSec=30min
UMask=0077
EOF
cat > "$UNIT_DIR/mangaka-update.timer" <<'EOF'
[Unit]
Description=Verificar atualizações do Mangaka a cada cinco minutos

[Timer]
OnStartupSec=2min
OnUnitInactiveSec=5min

[Install]
WantedBy=timers.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now mangaka-update.timer
echo "Agendamento ativado. Logs: journalctl --user -u mangaka-update.service"
