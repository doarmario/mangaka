#!/usr/bin/env bash
# Run from a dedicated, clean installation checkout.
set -Eeuo pipefail
umask 077
# Parse the controller before Git can replace this file on disk.
main() {
    ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    cd "$ROOT_DIR"
    if [[ "$(id -u)" != "$(stat -c '%u' "$ROOT_DIR")" ]]; then
        # Older updater images run this checkout script directly as root forever.
        # Load the current entrypoint BEFORE any Git writes so those installations
        # can repair ownership and adopt the host UID without rebuilding by hand.
        if [[ "$(id -u)" == 0 && "$ROOT_DIR" == /workspace &&
              -f /opt/mangaka-update-loop.sh ]]; then
            echo "Migrando atualizador antigo para o usuário dono do projeto..."
            exec env MANGAKA_INSTALL_ROOT="$ROOT_DIR" /bin/bash \
                "$ROOT_DIR/integrations/updater/entrypoint.sh" update-once
        fi
        echo "Atualização bloqueada: execute como o dono do projeto. No Docker, use /opt/mangaka-entrypoint.sh update-once." >&2
        exit 1
    fi
    STATE_DIR="$(git rev-parse --absolute-git-dir)/mangaka-update"
    mkdir -p "$STATE_DIR"
    exec 9>"$STATE_DIR/lock"
    flock -n 9 || exit 0
    trap 'echo "Atualização falhou. Consulte os logs antes de reiniciar os serviços; nenhum rollback de banco foi executado." >&2' ERR

    if [[ -n "$(git status --porcelain)" ]]; then
        echo "Atualização bloqueada: existem alterações locais. Faça commit ou use uma instalação separada." >&2
        exit 1
    fi
    [[ -f .env ]] || { echo "Execute a instalação primeiro (.env ausente)." >&2; exit 1; }
    BRANCH="$(git symbolic-ref --short HEAD)"
    REMOTE="$(git config --get "branch.$BRANCH.remote")"
    [[ "$REMOTE" != . ]] || { echo "Configure um remoto para esta branch." >&2; exit 1; }
    git fetch --prune "$REMOTE"
    TARGET="$(git rev-parse '@{upstream}')"
    git merge-base --is-ancestor HEAD "$TARGET" || {
        echo "Atualização bloqueada: histórico local diverge do remoto." >&2; exit 1;
    }
    git merge --ff-only "$TARGET"
    # Read deployment commands from the newly checked-out revision, not Bash's
    # buffered copy of the old script. The inherited FD keeps the same lock held.
    bash "$ROOT_DIR/scripts/deploy-update.sh" "$TARGET"
}
main "$@"; exit
