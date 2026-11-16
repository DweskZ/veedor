#!/usr/bin/env bash
# Shared helpers for the server scripts. Source it; do not run it.
#
# Environment overrides (the defaults are right for the Terraform-built server; the local proof sets
# them to run the very same scripts against a throw-away compose project):
#   VEEDOR_HOME           /srv/veedor              data, release and backup folders
#   VEEDOR_ENV_FILE       /etc/veedor/server.env   server env file (created from server.env.template)
#   VEEDOR_PROJECT        veedor                   compose project name
#   VEEDOR_COMPOSE_EXTRA  ""                       extra compose arguments, e.g. "-f compose.local.yml"
#   VEEDOR_BASE_URL       http://127.0.0.1         where the proxy answers on this host
#   VEEDOR_PROFILES       ""                       e.g. "--profile observability"
#   VEEDOR_NO_ROOT        unset                    set to 1 to skip the root check (local proof only)

VEEDOR_HOME="${VEEDOR_HOME:-/srv/veedor}"
VEEDOR_ENV_FILE="${VEEDOR_ENV_FILE:-/etc/veedor/server.env}"
VEEDOR_PROJECT="${VEEDOR_PROJECT:-veedor}"
VEEDOR_BASE_URL="${VEEDOR_BASE_URL:-http://127.0.0.1}"
DEPLOY_DIR="$VEEDOR_HOME/deploy"

die() { echo "error: $*" >&2; exit 1; }
log() { echo "[$(date -u +%H:%M:%S)] $*"; }

require_root() {
  [[ "${VEEDOR_NO_ROOT:-0}" == 1 || "$(id -u)" -eq 0 ]] || die "run with sudo"
}

require_env_file() {
  [[ -f "$VEEDOR_ENV_FILE" ]] || die "$VEEDOR_ENV_FILE not found: create it from deploy/server.env.template"
  # shellcheck disable=SC2015
  ! grep -q 'CHANGE_ME' "$VEEDOR_ENV_FILE" || die "$VEEDOR_ENV_FILE still contains CHANGE_ME placeholders"
}

# dc <compose args...>: the production compose project.
dc() {
  # VEEDOR_COMPOSE_EXTRA and VEEDOR_PROFILES are intentionally word-split.
  # shellcheck disable=SC2086
  docker compose -p "$VEEDOR_PROJECT" --env-file "$VEEDOR_ENV_FILE" ${VEEDOR_PROFILES:-} \
    -f "$DEPLOY_DIR/compose.prod.yml" ${VEEDOR_COMPOSE_EXTRA:-} "$@"
}

env_value() { grep -E "^$1=" "$VEEDOR_ENV_FILE" | tail -n 1 | cut -d= -f2-; }

verify_release() {
  local dir="$1"
  [[ -f "$dir/SHA256SUMS" ]] || die "$dir/SHA256SUMS missing"
  log "verifying checksums in $dir"
  # shasum on macOS, sha256sum on Linux.
  if command -v sha256sum >/dev/null; then (cd "$dir" && sha256sum --quiet -c SHA256SUMS)
  else (cd "$dir" && shasum -a 256 --quiet -c SHA256SUMS); fi
}

load_images() {
  local dir="$1" f
  for f in "$dir"/images-base.tar.gz "$dir"/images-api.tar.gz "$dir"/images-web.tar.gz; do
    [[ -f "$f" ]] || continue
    log "loading $(basename "$f")"
    gunzip -c "$f" | docker load
  done
}

# install_deploy_files <release dir>: refresh the stable deploy folder the compose project runs from.
install_deploy_files() {
  local dir="$1"
  [[ -d "$dir/deploy" ]] || die "$dir/deploy missing"
  mkdir -p "$DEPLOY_DIR"
  cp -R "$dir/deploy/." "$DEPLOY_DIR/"
}

# swap_data <data.tar.gz>: unpack into a new folder and swap it in. Keeps an ask-model cache the new
# release does not carry. The previous folder stays as data.previous until the next swap.
swap_data() {
  local tarball="$1" new="$VEEDOR_HOME/data.incoming"
  rm -rf "$new"; mkdir -p "$new"
  tar -xzf "$tarball" -C "$new" --strip-components=1
  [[ -d "$new/lake" && -d "$new/marts" ]] || die "data.tar.gz has no lake/ and marts/"
  if [[ -d "$VEEDOR_HOME/data" ]]; then
    if [[ -d "$VEEDOR_HOME/data/models/fastembed" && ! -d "$new/models/fastembed" ]]; then
      mkdir -p "$new/models"; mv "$VEEDOR_HOME/data/models/fastembed" "$new/models/fastembed"
    fi
    rm -rf "$VEEDOR_HOME/data.previous"; mv "$VEEDOR_HOME/data" "$VEEDOR_HOME/data.previous"
  fi
  mv "$new" "$VEEDOR_HOME/data"
}

wait_healthy() {
  local url="${VEEDOR_BASE_URL}/api/v1/health"
  for _ in $(seq 1 30); do
    if curl -fsS -m 5 -o /dev/null "$url"; then log "healthy: $url"; return 0; fi
    sleep 4
  done
  die "no healthy answer from $url after 120 s (docker compose -p $VEEDOR_PROJECT logs --tail=50)"
}
