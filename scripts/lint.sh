#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_BIN="$ROOT_DIR/backend/.venv/bin"

RUFF_BIN="${RUFF_BIN:-ruff}"
BLACK_BIN="${BLACK_BIN:-black}"
MYPY_BIN="${MYPY_BIN:-mypy}"

if [[ -x "$VENV_BIN/ruff" ]]; then
  RUFF_BIN="$VENV_BIN/ruff"
fi
if [[ -x "$VENV_BIN/black" ]]; then
  BLACK_BIN="$VENV_BIN/black"
fi
if [[ -x "$VENV_BIN/mypy" ]]; then
  MYPY_BIN="$VENV_BIN/mypy"
fi

"$RUFF_BIN" check .
"$BLACK_BIN" --check .
"$MYPY_BIN" backend
