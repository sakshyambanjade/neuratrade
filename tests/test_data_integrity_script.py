import hashlib
import subprocess


def test_validate_data_integrity_writes_sha256_manifest(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    source_file = data_dir / "sample.csv"
    source_file.write_text("ts,close\n1,100\n", encoding="utf-8")
    manifest = data_dir / "manifest.sha256"

    subprocess.run(
        ["scripts/validate_data_integrity.sh", str(data_dir), str(manifest)],
        check=True,
        capture_output=True,
        text=True,
    )

    expected_digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
    manifest_text = manifest.read_text(encoding="utf-8")

    assert expected_digest in manifest_text
    assert str(source_file) in manifest_text
