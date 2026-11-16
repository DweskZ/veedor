#!/usr/bin/env bash
# Build a deployable release on the OWNER'S machine (never on the server).
#
#   deploy/scripts/build-release.sh --site-url https://veedor.example.org [options]
#
# Options
#   --site-url URL        Public origin baked into the web image (NEXT_PUBLIC_SITE_URL). Required.
#                         Use http://<elastic-ip> for the temporary no-domain mode.
#   --out DIR             Output directory (default: dist/release-<UTC stamp>)
#   --db-container NAME   Running PostgreSQL container to dump (default: veedor-db-1)
#   --platform P          Image platform (default: linux/arm64, the Graviton target)
#   --with-ask-model      Also ship data/models/fastembed (about 0.5 GB) for the optional ask route
#   --skip-images         Do not build or save images (data/dump only)
#
# Output (all inside --out): data.tar.gz (lake, marts, investigations, glossary), db.dump (pg_dump custom
# format, no reviews rows), images-api.tar.gz, images-web.tar.gz, deploy/ (compose, Caddyfile, scripts,
# env template), manifest.json and SHA256SUMS.
#
# Images are built here and shipped as tarballs, not built on the server: the API image build
# (uv sync with scipy/pyarrow/scikit-learn) and `next build` need several GB of RAM and many minutes,
# which a 2 GB t4g.small cannot do without swapping to a crawl or being OOM-killed. The owner's Apple
# silicon machine is arm64 like Graviton, so the build is native (no emulation).
#
# Refuses to continue if anything from data/raw or data/texts, or any file whose name is a known
# unmasked/personal table, would be shipped.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA="${VEEDOR_DATA_DIR:-$ROOT/data}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SITE_URL=""; OUT=""; DB_CONTAINER="veedor-db-1"; PLATFORM="linux/arm64"; ASK_MODEL=0; IMAGES=1

usage() { sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --site-url) SITE_URL="${2:?}"; shift 2 ;;
    --out) OUT="${2:?}"; shift 2 ;;
    --db-container) DB_CONTAINER="${2:?}"; shift 2 ;;
    --platform) PLATFORM="${2:?}"; shift 2 ;;
    --with-ask-model) ASK_MODEL=1; shift ;;
    --skip-images) IMAGES=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ -n "$SITE_URL" ]] || { echo "--site-url is required" >&2; exit 2; }
SITE_URL="${SITE_URL%/}"
OUT="${OUT:-$ROOT/dist/release-$STAMP}"
for tool in docker jq shasum tar gzip; do command -v "$tool" >/dev/null || { echo "missing tool: $tool" >&2; exit 1; }; done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT" "$WORK/data/lake" "$WORK/data/marts" "$WORK/data/investigations" "$WORK/data/glossary" "$WORK/data/models"

echo "== 1/6 data bundle (scripts/build_data_bundle.sh)"
if [[ -z "${PYTHON:-}" ]] && ! command -v uv >/dev/null && [[ -x "$ROOT/.venv/bin/python" ]]; then
  export PYTHON="$ROOT/.venv/bin/python"
fi
"$ROOT/scripts/build_data_bundle.sh" "$WORK/bundle" >/dev/null
BUNDLE="$(echo "$WORK"/bundle/veedor-data-*.tar.gz)"
tar -xzf "$BUNDLE" -C "$WORK/data"
rm -f "$WORK/data/manifest.json"; cp "$WORK"/bundle/veedor-data-*.manifest.json "$WORK/data/bundle-manifest.json"

echo "== 2/6 investigations, glossary, optional model"
# Investigation files are written mode 600 by the CLI; the API runs as uid 10001, so make them readable.
cp "$DATA"/investigations/*.json "$WORK/data/investigations/" 2>/dev/null || true
chmod 644 "$WORK"/data/investigations/*.json 2>/dev/null || true
cp "$ROOT/web/src/data/glossary.json" "$WORK/data/glossary/glossary.json"
if [[ $ASK_MODEL -eq 1 ]]; then
  [[ -d "$DATA/models/fastembed" ]] || { echo "data/models/fastembed not found" >&2; exit 1; }
  cp -R "$DATA/models/fastembed" "$WORK/data/models/fastembed"
fi
find "$WORK/data" -type d -exec chmod 755 {} + ; find "$WORK/data" -type f -exec chmod 644 {} +

echo "== 3/6 privacy gate"
ALLOWED_PARQUET="lake/processes lake/tenderers lake/awards lake/suppliers_sri lake/ghost_companies lake/companies_supercias lake/company_financials marts/process_signals marts/process_scores marts/supplier_profiles marts/process_quotes marts/process_quote_stats"
fail=0
while IFS= read -r f; do
  rel="${f#"$WORK"/data/}"
  case "$rel" in
    raw/*|texts/*|*/process_texts*|*person_name_tokens*|*.jsonl|*.jsonl.gz|*.zip|*.csv) echo "FORBIDDEN path in release: $rel" >&2; fail=1 ;;
    lake/*.parquet|marts/*.parquet)
      case " $ALLOWED_PARQUET " in *" ${rel%.parquet} "*) ;; *) echo "parquet not on the allow-list: $rel" >&2; fail=1 ;; esac ;;
  esac
done < <(find "$WORK/data" -type f | sort)
# Byte-identical copies of anything under data/raw or data/texts are also refused, whatever the name.
if [[ -d "$DATA/raw" || -d "$DATA/texts" ]]; then
  forbidden_hashes="$(find "$DATA/raw" "$DATA/texts" -type f -exec shasum -a 256 {} + 2>/dev/null | awk '{print $1}' | sort -u)"
  staged_hashes="$(find "$WORK/data" -type f -exec shasum -a 256 {} + | awk '{print $1}' | sort -u)"
  dup="$(comm -12 <(echo "$forbidden_hashes") <(echo "$staged_hashes") || true)"
  [[ -z "$dup" ]] || { echo "a staged file is byte-identical to a file in data/raw or data/texts" >&2; fail=1; }
fi
[[ $fail -eq 0 ]] || { echo "privacy gate FAILED: nothing was written to $OUT" >&2; exit 1; }
echo "ok: $(find "$WORK/data" -type f | wc -l | tr -d ' ') files, none from raw/ or texts/"

echo "== 4/6 data.tar.gz"
COPYFILE_DISABLE=1 tar -C "$WORK" -cf - data | gzip -1 > "$OUT/data.tar.gz"
# Re-check the archive itself, as the owner will upload exactly this file.
if tar -tzf "$OUT/data.tar.gz" | grep -Eq '(^|/)(raw|texts)/|process_texts|person_name_tokens'; then
  echo "forbidden entry found inside data.tar.gz" >&2; rm -f "$OUT/data.tar.gz"; exit 1
fi

echo "== 5/6 database dump from $DB_CONTAINER (process_vectors + schema; reviews rows excluded)"
docker exec "$DB_CONTAINER" pg_dump -U veedor -d veedor -Fc -Z 6 --no-owner --no-privileges \
  --exclude-table-data=reviews > "$OUT/db.dump"
[[ -s "$OUT/db.dump" ]] || { echo "empty dump" >&2; exit 1; }

if [[ $IMAGES -eq 1 ]]; then
  echo "== 6/6 images ($PLATFORM)"
  docker buildx build --platform "$PLATFORM" --load -t veedor-api:release "$ROOT"
  docker buildx build --platform "$PLATFORM" --load -t veedor-web:release \
    --build-arg NEXT_PUBLIC_API_URL=/api/v1 --build-arg "NEXT_PUBLIC_SITE_URL=$SITE_URL" "$ROOT/web"
  docker save veedor-api:release | gzip -6 > "$OUT/images-api.tar.gz"
  docker save veedor-web:release | gzip -6 > "$OUT/images-web.tar.gz"
  # Third-party images from compose.prod.yml (not the optional observability one), so the server never
  # depends on Docker Hub's anonymous pull limits at install time.
  BASE_IMAGES="$(grep -E '^ +image: (caddy|pgvector)' "$ROOT/deploy/compose.prod.yml" | awk '{print $2}')"
  for img in $BASE_IMAGES; do docker pull --platform "$PLATFORM" "$img" >/dev/null; done
  # shellcheck disable=SC2086
  docker save $BASE_IMAGES | gzip -6 > "$OUT/images-base.tar.gz"
else
  echo "== 6/6 images skipped"
fi

mkdir -p "$OUT/deploy"
cp "$ROOT"/deploy/{compose.prod.yml,compose.local.yml,Caddyfile,server.env.template} "$OUT/deploy/"
cp -R "$ROOT/deploy/scripts" "$OUT/deploy/scripts"
mkdir -p "$OUT/deploy/ops/observability/grafana"
cp -R "$ROOT/ops/observability/grafana/provisioning" "$ROOT/ops/observability/grafana/dashboards" "$OUT/deploy/ops/observability/grafana/"

# shellcheck disable=SC2094
( cd "$OUT" && find . -type f ! -name SHA256SUMS ! -name manifest.json -print0 | sort -z | xargs -0 shasum -a 256 > SHA256SUMS )
jq -n --arg stamp "$STAMP" --arg site "$SITE_URL" --arg platform "$PLATFORM" --argjson model "$ASK_MODEL" \
  --rawfile sums "$OUT/SHA256SUMS" '
  { stamp: $stamp, site_url: $site, platform: $platform, includes_ask_model: ($model == 1),
    files: ($sums | split("\n") | map(select(length > 0) | capture("^(?<sha256>[0-9a-f]+)  (?<file>.+)$"))) }' > "$OUT/manifest.json"
for f in data.tar.gz db.dump images-api.tar.gz images-web.tar.gz images-base.tar.gz; do
  [[ -f "$OUT/$f" ]] && jq --arg f "./$f" --argjson b "$(wc -c < "$OUT/$f" | tr -d ' ')" \
    '(.files[] | select(.file == $f)) += {bytes: $b}' "$OUT/manifest.json" > "$WORK/m.json" && mv "$WORK/m.json" "$OUT/manifest.json"
done
echo; echo "release: $OUT"
jq -r '.files[] | select(.bytes) | "\(.bytes)\t\(.sha256[0:16])\t\(.file)"' "$OUT/manifest.json" | awk -F'\t' '{printf "%14s  %s  %s\n",$1,$2,$3}'
echo "next: aws s3 sync \"$OUT\" s3://<release-bucket>/releases/$STAMP/   (docs/DEPLOYMENT_AWS.md, step 6)"
