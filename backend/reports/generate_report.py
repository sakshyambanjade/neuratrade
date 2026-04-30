"""
Markdown report generation for NeuraTradeBench experiments.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

INTEGER_COLUMNS = {"rank", "fills", "rejected", "risk_blocked", "trade_count", "n"}


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
    statistics_json = _first_existing(artifact_dir / "model_comparison_statistics.json")
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
                preferred=[
                    "rank",
                    "model",
                    "return",
                    "sharpe",
                    "sortino",
                    "calmar",
                    "max_drawdown",
                    "win_rate",
                    "profit_factor",
                    "avg_latency_ms",
                ],
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
                    "sortino",
                    "calmar",
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
        "## Statistical Validation",
        _statistical_summary(statistics_json),
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
    body = ["| " + " | ".join(_format_cell(column, row.get(column, "")) for column in columns) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def _key_metrics(summary_json: Path | None) -> str:
    if summary_json is None:
        return "No summary JSON was found."
    try:
        data = json.loads(summary_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return f"`{summary_json.name}` was not valid JSON."
    return "\n".join(f"- `{key}`: `{value}`" for key, value in sorted(data.items()))


def _statistical_summary(statistics_json: Path | None) -> str:
    if statistics_json is None:
        return "No model comparison statistics JSON was found."
    try:
        data = json.loads(statistics_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return f"`{statistics_json.name}` was not valid JSON."

    sections = []
    intervals = data.get("bootstrap_intervals", {})
    if intervals:
        rows = []
        for model, metrics in sorted(intervals.items()):
            return_ci = metrics.get("return", [0.0, 0.0])
            sharpe_ci = metrics.get("sharpe", [0.0, 0.0])
            win_rate_ci = metrics.get("win_rate", [0.0, 0.0])
            rows.append(
                "| "
                + " | ".join(
                    [
                        str(model),
                        _interval(return_ci),
                        _interval(sharpe_ci),
                        _interval(win_rate_ci),
                    ]
                )
                + " |"
            )
        sections.append(
            "\n".join(
                [
                    "Bootstrap 95% confidence intervals:",
                    "",
                    "| Model | Return CI | Sharpe CI | Win Rate CI |",
                    "| --- | --- | --- | --- |",
                    *rows,
                ]
            )
        )

    tests = data.get("pairwise_tests", [])
    if tests:
        rows = []
        for test in tests[:20]:
            rows.append(
                "| "
                + " | ".join(
                    [
                        str(test.get("left", "")),
                        str(test.get("right", "")),
                        str(test.get("test_name", "")),
                        _format_cell("p_value", test.get("p_value", "")),
                        _format_cell("corrected_p_value", test.get("corrected_p_value", "")),
                        _format_cell("effect_size", test.get("effect_size", "")),
                        _format_cell("n", test.get("n", "")),
                    ]
                )
                + " |"
            )
        sections.append(
            "\n".join(
                [
                    "Pairwise tests on matched period returns:",
                    "",
                    "| Left | Right | Test | p | p corrected | Effect | n |",
                    "| --- | --- | --- | ---: | ---: | ---: | ---: |",
                    *rows,
                ]
            )
        )

    return "\n\n".join(sections) if sections else f"`{statistics_json.name}` contained no statistical results."


def _chart_links(artifact_dir: Path) -> list[str]:
    pngs = sorted(artifact_dir.glob("*.png"))
    if not pngs:
        return ["No PNG charts were found."]
    return [f"- [{path.name}]({path.name})" for path in pngs]


def _interval(values: object) -> str:
    if not isinstance(values, (list, tuple)) or len(values) < 2:
        return "[0.0000, 0.0000]"
    return f"[{_format_cell('', values[0])}, {_format_cell('', values[1])}]"


def _format_cell(column: str, value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    try:
        number = float(text)
    except (TypeError, ValueError):
        return text
    if not math.isfinite(number):
        return text
    if column in INTEGER_COLUMNS:
        return str(int(number))
    return f"{number:.4f}"
