"""
Markdown report generation for NeuraTradeBench experiments.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


def generate_markdown_report(experiment_id: int, output_md: str | Path) -> None:
    output_md = Path(output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    artifact_dir = output_md.parent

    comparison_csv = _first_existing(
        artifact_dir / "model_comparison.csv",
        artifact_dir / "comparison.csv",
        artifact_dir / "ablation_results.csv",
    )
    ablation_csv = _first_existing(artifact_dir / "ablation_results.csv")
    summary_json = _first_existing(artifact_dir / "ablation_summary.json")
    config_json = _first_existing(artifact_dir / "experiment_config.json", artifact_dir / "config.json")

    lines = [
        f"# NeuraTradeBench Experiment {experiment_id}",
        "",
        "## Experiment Config",
        _json_block(config_json) if config_json else "No config artifact was found.",
        "",
        "## Model Leaderboard",
        (
            _table_from_csv(
                comparison_csv,
                preferred=["rank", "model", "return", "sharpe", "max_drawdown", "win_rate", "profit_factor"],
            )
            if comparison_csv
            else "No model comparison CSV was found."
        ),
        "",
        "## Ablation Table",
        (
            _table_from_csv(
                ablation_csv,
                preferred=[
                    "variant",
                    "cumulative_return",
                    "sharpe",
                    "max_drawdown",
                    "win_rate",
                    "profit_factor",
                    "avg_slippage_bps",
                    "avg_latency_ms",
                    "trade_count",
                ],
            )
            if ablation_csv
            else "No ablation CSV was found."
        ),
        "",
        "## Key Metrics",
        _key_metrics(summary_json),
        "",
        "## Charts",
        *_chart_links(artifact_dir),
        "",
        "## Limitations",
        "- Results are paper-trading simulations and do not include real exchange order placement.",
        "- Synthetic or short live windows may not capture regime changes, liquidity shocks, or exchange outages.",
        "- Local LLM outputs can vary across model versions, prompts, sampling settings, and hardware latency.",
        "",
        "## Reproducibility",
        "- Preserve CSV artifacts, generated charts, model names, prompts, and random seeds for each run.",
        "- Re-run tests with `pytest -q` before publishing tables.",
        "- Use the same price series across compared models and ablation variants.",
        "",
    ]
    output_md.write_text("\n".join(lines), encoding="utf-8")


def _first_existing(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _json_block(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return f"Config artifact `{path.name}` was not valid JSON."
    return f"```json\n{json.dumps(data, indent=2, sort_keys=True)}\n```"


def _table_from_csv(path: Path, *, preferred: list[str]) -> str:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    columns = [column for column in preferred if column in fieldnames] or fieldnames
    if not columns:
        return f"`{path.name}` has no columns."
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    if not rows:
        return "\n".join([header, divider])
    body = ["| " + " | ".join(str(row.get(column, "")) for column in columns) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def _key_metrics(summary_json: Path | None) -> str:
    if summary_json is None:
        return "No summary JSON was found."
    try:
        data = json.loads(summary_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return f"`{summary_json.name}` was not valid JSON."
    return "\n".join(f"- `{key}`: `{value}`" for key, value in sorted(data.items()))


def _chart_links(artifact_dir: Path) -> list[str]:
    pngs = sorted(artifact_dir.glob("*.png"))
    if not pngs:
        return ["No PNG charts were found."]
    return [f"- [{path.name}]({path.name})" for path in pngs]
