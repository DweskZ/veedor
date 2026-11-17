#!/usr/bin/env bash
# Update a running server from a release folder or from the release bucket (as root).
#
#   sudo server-update.sh [--with-data] /srv/veedor/release/<name>     a folder already on the server
#   sudo server-update.sh --release-id gh-<run>-<attempt>              download releases/<id>/ from
#                                                                      $VEEDOR_RELEASE_BUCKET, then update
#
# --release-id is what the GitHub deploy reaches through the custom Systems Manager document
# (infra/terraform/oidc.tf): the ONLY input that caller controls. Everything it can influence is
# validated here, strictly and independently of the document's own allowedPattern:
#   - the release id must match ^gh-[0-9]{1,20}-[0-9]{1,3}$
#   - the bucket (from the environment) must be a plain S3 bucket name
#   - a folder argument must be a direct child of $VEEDOR_HOME/release with a plain name (no "..",
#     no symlink out), and --with-data is refused together with --release-id
#   - any other option or argument is an error
#
# What is applied depends on what the release contains:
#   images-*.tar.gz  loaded, containers recreated
#   deploy/          compose file, Caddyfile and scripts refreshed
#   data.tar.gz      data swapped (only with --with-data; the dossier cache volume is then cleared)
#   db.dump          never restored here; use server-install.sh on an empty database
# A release produced by the GitHub workflow carries code and images only. Idempotent.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

WITH_DATA=0; SRC=""; RELEASE_ID=""
usage() { die "usage: server-update.sh [--with-data] <folder under \$VEEDOR_HOME/release> | --release-id gh-<run>-<attempt>"; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-data) WITH_DATA=1; shift ;;
    --release-id) [[ $# -ge 2 ]] || usage; RELEASE_ID="$2"; shift 2 ;;
    -*) usage ;;
    *) [[ -z "$SRC" ]] || usage; SRC="$1"; shift ;;
  esac
done
[[ -n "$SRC" || -n "$RELEASE_ID" ]] || usage
[[ -z "$SRC" || -z "$RELEASE_ID" ]] || usage
require_root
require_env_file

if [[ -n "$RELEASE_ID" ]]; then
  [[ $WITH_DATA -eq 0 ]] || die "--with-data cannot be combined with --release-id"
  [[ "$RELEASE_ID" =~ ^gh-[0-9]{1,20}-[0-9]{1,3}$ ]] || die "invalid release id"
  BUCKET="${VEEDOR_RELEASE_BUCKET:-}"
  [[ "$BUCKET" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]] || die "VEEDOR_RELEASE_BUCKET is not a valid bucket name"
  RELEASE="$VEEDOR_HOME/release/$RELEASE_ID"
  mkdir -p "$RELEASE"
  log "downloading s3://$BUCKET/releases/$RELEASE_ID/"
  aws s3 sync "s3://$BUCKET/releases/$RELEASE_ID/" "$RELEASE" --only-show-errors
else
  [[ "$(basename "$SRC")" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$ ]] || die "invalid release folder name"
  [[ -d "$SRC" ]] || die "$SRC is not a folder"
  ROOT_DIR="$(cd "$VEEDOR_HOME/release" && pwd -P)"
  RELEASE="$(cd "$SRC" && pwd -P)"
  [[ "$(dirname "$RELEASE")" == "$ROOT_DIR" ]] || die "release folder must be a direct child of $ROOT_DIR"
fi
[[ ! -d "$RELEASE" ]] || chmod 700 "$RELEASE"

verify_release "$RELEASE"
install_deploy_files "$RELEASE"
load_images "$RELEASE"
if [[ $WITH_DATA -eq 1 ]]; then
  [[ -f "$RELEASE/data.tar.gz" ]] || die "--with-data but no data.tar.gz in $RELEASE"
  swap_data "$RELEASE/data.tar.gz"
  dc rm -sf api >/dev/null 2>&1 || true
  docker volume rm "${VEEDOR_PROJECT}_dossiers" >/dev/null 2>&1 || true   # cached dossiers are per data build
fi

dc up -d --wait
wait_healthy

# Keep the last three release folders and drop dangling images.
# shellcheck disable=SC2012
(cd "$VEEDOR_HOME/release" 2>/dev/null && ls -1dt ./*/ 2>/dev/null | tail -n +4 | xargs -r rm -rf) || true
docker image prune -f >/dev/null
log "update complete"
dc ps
