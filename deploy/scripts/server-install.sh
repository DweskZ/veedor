#!/usr/bin/env bash
# First installation on the server (run through Session Manager, as root).
#
#   sudo /srv/veedor/release/<stamp>/deploy/scripts/server-install.sh /srv/veedor/release/<stamp>
#
# Does, in order: verifies checksums, loads the images, unpacks the data, starts PostgreSQL, restores
# the database dump (only when process_vectors does not exist yet), starts the whole stack, waits for
# health and prints the URL. Safe to run again: images are reloaded, data is swapped atomically, the
# database is restored only if it is still empty, containers are only recreated when something changed.
#
# Needs /etc/veedor/server.env (from deploy/server.env.template) without CHANGE_ME placeholders.
# Environment overrides: see lib.sh.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

RELEASE="${1:?usage: server-install.sh <release dir>}"
RELEASE="$(cd "$RELEASE" && pwd)"
require_root
require_env_file
START=$SECONDS

verify_release "$RELEASE"
mkdir -p "$VEEDOR_HOME"/{release,backups}
install_deploy_files "$RELEASE"
load_images "$RELEASE"

if [[ -f "$RELEASE/data.tar.gz" ]]; then
  log "unpacking data"
  swap_data "$RELEASE/data.tar.gz"
else
  [[ -d "$VEEDOR_HOME/data/lake" ]] || die "no data.tar.gz in the release and no data on this host"
fi
mkdir -p "$VEEDOR_HOME/data/models"

log "starting PostgreSQL"
dc up -d --wait db

# The HNSW index is the last object a restore creates: if it exists the restore completed.
restored="$(dc exec -T db psql -U veedor -d veedor -Atc "select to_regclass('public.ix_process_vectors_embedding_hnsw') is not null")"
if [[ "$restored" == "t" ]]; then
  log "vector index already present: skipping the database restore"
elif [[ -f "$RELEASE/db.dump" ]]; then
  log "restoring db.dump (the HNSW index is rebuilt: several minutes on a small instance)"
  # An interrupted earlier restore leaves a partial schema: start from an empty one.
  dc exec -T db psql -U veedor -d veedor -qc "drop schema public cascade; create schema public"
  # No parallel index workers: they need a large /dev/shm segment that a container does not have.
  dc exec -T -e PGOPTIONS="-c maintenance_work_mem=${PG_RESTORE_WORK_MEM:-384MB} -c max_parallel_maintenance_workers=0" db \
    pg_restore -U veedor -d veedor --no-owner --exit-on-error < "$RELEASE/db.dump"
  log "restore finished"
else
  die "database is empty and the release has no db.dump"
fi

log "starting the stack"
dc up -d --wait
wait_healthy

# Daily backup of the only mutable state (reviews). Skipped when systemd is not available (local proof).
if [[ "${VEEDOR_NO_ROOT:-0}" != 1 && -d /etc/systemd/system ]]; then
  cat > /etc/systemd/system/veedor-backup.service <<UNIT
[Unit]
Description=Veedor reviews backup
[Service]
Type=oneshot
ExecStart=$DEPLOY_DIR/scripts/server-backup.sh
UNIT
  cat > /etc/systemd/system/veedor-backup.timer <<'UNIT'
[Unit]
Description=Daily Veedor reviews backup
[Timer]
OnCalendar=*-*-* 03:30:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
UNIT
  systemctl daemon-reload && systemctl enable --now veedor-backup.timer >/dev/null
fi

log "done in $((SECONDS - START)) s: $(env_value PUBLIC_ORIGIN)"
dc ps
