import json

from experiments.metadata import write_experiment_start


def test_write_experiment_start_labels_paper_trading(tmp_path):
    output = write_experiment_start({"model_name": "mock", "dry_run": True}, artifact_dir=tmp_path)
    data = json.loads(output.read_text(encoding="utf-8"))

    assert data["execution_mode"] == "paper_trading"
    assert data["config"]["dry_run"] is True
    assert output.name == "experiment_start.json"
