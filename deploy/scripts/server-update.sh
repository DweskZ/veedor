#!/usr/bin/env bash
# Update a running server from a release folder or an S3 prefix (as root; also what the GitHub
# workflow runs through Systems Manager Run Command).
#
#   sudo server-update.sh /srv/veedor/release/<stamp>
#   sudo server-update.sh s3://<bucket>/releases/<name>/        (downloaded first; needs the instance role)
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

WITH_DATA=0; SRC=""
for a in "$@"; do
  case "$a" in
    --with-data) WITH_DATA=1 ;;
    *) SRC="$a" ;;
  esac
done
[[ -n "$SRC" ]] || die "usage: server-update.sh [--with-data] <release dir | s3://bucket/prefix/>"
require_root
require_env_file

if [[ "$SRC" == s3://* ]]; then
  name="$(basename "${SRC%/}")"
  RELEASE="$VEEDOR_HOME/release/$name"
  mkdir -p "$RELEASE"
  log "downloading $SRC"
  aws s3 sync "$SRC" "$RELEASE" --only-show-errors
else
  RELEASE="$(cd "$SRC" && pwd)"
fi

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
