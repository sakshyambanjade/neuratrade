"""
Experiment start metadata for reproducible paper-trading runs.
"""

from __future__ import annotations

import json
import platform
import subprocess
import time
from pathlib import Path
from typing import Any


def collect_runtime_metadata(config: dict[str, Any], *, artifact_dir: str | Path) -> dict[str, Any]:
    return {
        "execution_mode": "paper_trading",
        "started_at": int(time.time()),
        "config": config,
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "cpu": _command(["sysctl", "-n", "machdep.cpu.brand_string"]),
            "ram_bytes": _command(["sysctl", "-n", "hw.memsize"]),
            "gpu": _command(["sh", "-c", "system_profiler SPDisplaysDataType | grep 'Chipset Model' | head -1"]),
        },
        "ollama": {
            "version": _command(["ollama", "--version"]),
            "models": _command(["ollama", "list"]),
        },
        "artifact_dir": str(Path(artifact_dir)),
    }


def write_experiment_start(config: dict[str, Any], *, artifact_dir: str | Path) -> Path:
    artifact_path = Path(artifact_dir)
    artifact_path.mkdir(parents=True, exist_ok=True)
    output = artifact_path / "experiment_start.json"
    output.write_text(
        json.dumps(collect_runtime_metadata(config, artifact_dir=artifact_path), indent=2), encoding="utf-8"
    )
    return output


def _command(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (result.stdout or result.stderr).strip()
