#!/usr/bin/env bash
# Back up the only state that cannot be rebuilt: the reviews table (reviews are disabled by default,
# so the dump is normally empty). Everything else (lake, marts, vectors, images) is reproducible from
# the release. Keeps the newest 14 dumps; optionally copies each to S3.
#
#   sudo server-backup.sh                       run by veedor-backup.timer every day at 03:30 UTC
#   BACKUP_S3_URI=s3://<bucket>/backups/ sudo -E server-backup.sh
#
# Restore one dump:  docker compose -p veedor ... exec -T db pg_restore -U veedor -d veedor --clean --if-exists < file
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_root
require_env_file
umask 077   # dumps are root-only

DEST="$VEEDOR_HOME/backups"; mkdir -p "$DEST"
FILE="$DEST/reviews-$(date -u +%Y%m%dT%H%M%SZ).dump"
dc exec -T db pg_dump -U veedor -d veedor -Fc -t reviews > "$FILE.partial"
mv "$FILE.partial" "$FILE"
log "wrote $FILE ($(wc -c < "$FILE" | tr -d ' ') bytes)"
# shellcheck disable=SC2012
ls -1t "$DEST"/reviews-*.dump | tail -n +15 | xargs -r rm -f
if [[ -n "${BACKUP_S3_URI:-}" ]]; then aws s3 cp "$FILE" "$BACKUP_S3_URI" --only-show-errors; log "copied to $BACKUP_S3_URI"; fi
