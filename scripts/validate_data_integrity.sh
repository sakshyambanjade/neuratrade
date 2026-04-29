#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${1:-$ROOT_DIR/data}"
MANIFEST_PATH="${2:-$DATA_DIR/manifest.sha256}"

if [[ ! -d "$DATA_DIR" ]]; then
  echo "Data directory not found: $DATA_DIR" >&2
  exit 1
fi

mkdir -p "$(dirname "$MANIFEST_PATH")"

hash_file() {
  local file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file"
  else
    shasum -a 256 "$file"
  fi
}

tmp_manifest="$(mktemp)"
trap 'rm -f "$tmp_manifest"' EXIT

while IFS= read -r -d '' file; do
  relative_path="${file#$ROOT_DIR/}"
  digest="$(hash_file "$file" | awk '{print $1}')"
  printf '%s  %s\n' "$digest" "$relative_path" >> "$tmp_manifest"
done < <(
  find "$DATA_DIR" -type f \
    ! -name "$(basename "$MANIFEST_PATH")" \
    ! -name ".DS_Store" \
    -print0 | sort -z
)

mv "$tmp_manifest" "$MANIFEST_PATH"
echo "Wrote SHA-256 manifest to $MANIFEST_PATH"
