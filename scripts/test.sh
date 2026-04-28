#!/usr/bin/env bash
set -euo pipefail

pytest -q --cov=backend --cov-report=term-missing
