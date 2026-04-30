#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${PYTEST_BIN:-}" && -x "$ROOT_DIR/backend/.venv/bin/pytest" ]]; then
  PYTEST_BIN="$ROOT_DIR/backend/.venv/bin/pytest"
else
  PYTEST_BIN="${PYTEST_BIN:-pytest}"
fi

"$PYTEST_BIN" -q --cov=backend --cov-report=term-missing
