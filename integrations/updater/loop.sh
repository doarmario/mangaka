#!/usr/bin/env bash
set -Eeuo pipefail
interval="${AUTO_UPDATE_INTERVAL_SECONDS:-300}"
if [[ ! "$interval" =~ ^[0-9]{1,6}$ ]] || (( 10#$interval < 60 )); then
    echo "AUTO_UPDATE_INTERVAL_SECONDS deve ser um inteiro entre 60 e 999999." >&2
    exit 1
fi
interval=$((10#$interval))
# The host checkout may be owned by a different UID (including Docker Desktop).
git config --global --add safe.directory /workspace
echo "Atualizador iniciado; verificação a cada ${interval}s."
while true; do
    if ! bash /workspace/scripts/auto-update.sh; then
        echo "Falha no ciclo de atualização; nova tentativa em ${interval}s." >&2
    fi
    sleep "$interval" &
    wait $!
done
