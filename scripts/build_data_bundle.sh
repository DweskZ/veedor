#!/usr/bin/env bash
# Build the deployment data bundle: only the Parquet files the API and the dossier builder read
# (see veedor/infrastructure/lake/reader.py and evidence_reader.py), plus a manifest with
# file, bytes, sha256 and row count.
#
#   scripts/build_data_bundle.sh [OUT_DIR]      default OUT_DIR=dist
#
# Output: OUT_DIR/veedor-data-<UTC date>.tar.gz containing lake/*.parquet, marts/*.parquet and
# manifest.json; the manifest is also written next to the tarball. Raw files, build_summary.json,
# dossiers, traces and the unmasked data/texts/process_texts.parquet are deliberately excluded. Requires: uv (or PYTHON=<interpreter with pyarrow>).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="${VEEDOR_DATA_DIR:-$ROOT/data}"
OUT="${1:-$ROOT/dist}"
STAMP="$(date -u +%Y%m%d)"
LAKE_TABLES=(processes tenderers awards suppliers_sri ghost_companies companies_supercias company_financials)
# person_name_tokens.parquet is deliberately not shipped (docs/SECURITY.md, "Name vocabulary").
MART_TABLES=(process_signals process_scores supplier_profiles process_quotes process_quote_stats)

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/lake" "$STAGE/marts" "$OUT"

for t in "${LAKE_TABLES[@]}"; do
  [[ -f "$DATA/lake/$t.parquet" ]] || { echo "missing $DATA/lake/$t.parquet" >&2; exit 1; }
  ln "$DATA/lake/$t.parquet" "$STAGE/lake/$t.parquet" 2>/dev/null || cp "$DATA/lake/$t.parquet" "$STAGE/lake/"
done
for t in "${MART_TABLES[@]}"; do
  [[ -f "$DATA/marts/$t.parquet" ]] || { echo "missing $DATA/marts/$t.parquet" >&2; exit 1; }
  ln "$DATA/marts/$t.parquet" "$STAGE/marts/$t.parquet" 2>/dev/null || cp "$DATA/marts/$t.parquet" "$STAGE/marts/"
done

if [[ -n "${PYTHON:-}" ]]; then RUN=("$PYTHON"); else RUN=(uv run --project "$ROOT" python); fi
"${RUN[@]}" - "$STAGE" <<'PY'
import hashlib, json, sys
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

stage = Path(sys.argv[1])
files = []
for path in sorted(stage.glob("*/*.parquet")):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    files.append({
        "file": f"{path.parent.name}/{path.name}",
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "rows": pq.ParquetFile(path).metadata.num_rows,
    })
manifest = {
    "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    "total_bytes": sum(f["bytes"] for f in files),
    "files": files,
}
(stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(f"{'file':38} {'bytes':>12} {'rows':>12}  sha256")
for f in files:
    print(f"{f['file']:38} {f['bytes']:>12,} {f['rows']:>12,}  {f['sha256'][:16]}...")
print(f"{'TOTAL':38} {manifest['total_bytes']:>12,}")
PY

TARBALL="$OUT/veedor-data-$STAMP.tar.gz"
COPYFILE_DISABLE=1 tar -C "$STAGE" -cf - manifest.json lake marts | gzip -1 > "$TARBALL"
cp "$STAGE/manifest.json" "$OUT/veedor-data-$STAMP.manifest.json"
echo "tarball:  $TARBALL ($(wc -c < "$TARBALL" | tr -d ' ') bytes)"
echo "manifest: $OUT/veedor-data-$STAMP.manifest.json"
echo "restore:  tar -xzf $(basename "$TARBALL") -C <data dir>   # yields lake/, marts/, manifest.json"
