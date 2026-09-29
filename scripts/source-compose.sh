# Sourced by the installer and deployment controller after acquiring their lock.
# Resolve bind paths on the daemon host, including Docker Desktop installations.
if [[ "$ROOT_DIR" == /workspace && -z "${MANGAKA_HOST_WORKSPACE:-}" ]]; then
    mounts="$(docker inspect "$HOSTNAME" --format '{{json .Mounts}}')"
    export MANGAKA_HOST_WORKSPACE="$(jq -er '.[] | select(.Destination == "/workspace") | .Source' <<< "$mounts")"
fi
source_state="$(git rev-parse --absolute-git-dir)/mangaka-update"
mkdir -p "$source_state"
source_overlay="$source_state/sources.compose.json"
if command -v python3 >/dev/null; then
    python3 "$ROOT_DIR/scripts/source-compose.py" > "$source_overlay.pending"
else
    # Existing updater images predate Python. Use the already installed app
    # image with the new compiler mounted read-only; never install host packages.
    docker run --rm --network none --user "$(id -u):$(id -g)" \
        --mount "type=bind,src=${MANGAKA_HOST_WORKSPACE:-$ROOT_DIR},dst=/workspace,readonly" \
        --workdir /workspace mangaka-local python scripts/source-compose.py > "$source_overlay.pending"
fi
mv "$source_overlay.pending" "$source_overlay"
source_fingerprint="$(sha256sum "$source_overlay" | cut -d ' ' -f1)"
# Remember attempted services as well as successful ones. A failed first start
# must still be cleaned up if the operator subsequently removes that package.
source_managed="$source_state/sources-managed.compose.json"
if [[ -f "$source_managed" ]]; then
    jq -s '{services: (.[0].services + .[1].services)}' \
        "$source_managed" "$source_overlay" > "$source_managed.pending"
    mv "$source_managed.pending" "$source_managed"
else
    cp "$source_overlay" "$source_managed"
fi
source_compose_args=()
if [[ "$(jq '.services | length' "$source_overlay")" != 0 ]]; then
    source_compose_args=(-f "$source_overlay")
fi

finish_source_deployment() {
    # Stop only services previously managed by source packages. Keep their
    # containers and data; no --remove-orphans or volume removal is used.
    local previous="$source_managed"
    local retired=() service
    if [[ -f "$previous" ]]; then
        while IFS= read -r service; do
            [[ -n "$service" ]] && retired+=("$service")
        done < <(jq -r --slurpfile current "$source_overlay" \
            '.services | keys[] | select(. as $name | $current[0].services | has($name) | not)' "$previous")
        if ((${#retired[@]})); then
            docker compose --project-directory "$ROOT_DIR" -f "$ROOT_DIR/compose.yaml" \
                -f "$previous" stop "${retired[@]}"
        fi
    fi
    cp "$source_overlay" "$previous"
}
