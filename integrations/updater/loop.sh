#!/usr/bin/env bash
set -Eeuo pipefail
interval="${AUTO_UPDATE_INTERVAL_SECONDS:-300}"
if [[ ! "$interval" =~ ^[0-9]{1,6}$ ]] || (( 10#$interval < 60 )); then
    echo "AUTO_UPDATE_INTERVAL_SECONDS deve ser um inteiro entre 60 e 999999." >&2
    exit 1
fi
interval=$((10#$interval))
echo "Atualizador iniciado; verificação a cada ${interval}s."
while true; do
    # Pick up fixes to permission handling from the checkout, too. No Git or
    # Docker operations happen in the scheduler itself.
    if ! bash /workspace/integrations/updater/entrypoint.sh update-once; then
        echo "Falha no ciclo de atualização; nova tentativa em ${interval}s." >&2
    fi
    sleep "$interval" &
    wait $!
done
