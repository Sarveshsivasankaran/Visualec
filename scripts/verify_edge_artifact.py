from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Deployment gate for a Visualec edge model release")
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--require-hardware", action="store_true")
    args = parser.parse_args()
    metadata_path = args.artifact_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("synthetic_data") is not False:
        raise SystemExit("Artifact provenance does not explicitly prohibit synthetic data")
    if metadata.get("input") != {"width": 288, "height": 160, "pixel_format": "RGB565LE"}:
        raise SystemExit("Artifact input contract does not match the firmware protocol")
    source_manifest_path = args.artifact_dir / metadata.get("training_source_manifest", "")
    if not source_manifest_path.is_file():
        raise SystemExit("Release does not include its training-source manifest")
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if source_manifest.get("source") != "physical_logitech_c270" or source_manifest.get("synthetic_data") is not False:
        raise SystemExit("Training-source manifest is not a verified physical C270 dataset")
    for name, expected in metadata["files"].items():
        path = args.artifact_dir / name
        if not path.exists() or path.stat().st_size != expected["bytes"] or digest(path) != expected["sha256"]:
            raise SystemExit(f"Artifact verification failed for {name}")
    quality = metadata["quality"]
    if quality["student_teacher_recall_ratio"] < 0.90 or quality["int8_teacher_recall_ratio"] < 0.90 or quality["int8_map50_drop_points"] > 3.0:
        raise SystemExit("Artifact quality gates are not satisfied")
    if args.require_hardware and (not metadata.get("hardware_validated") or quality.get("esp_teacher_recall_ratio", 0) < 0.90):
        raise SystemExit("Release deployment requires recorded physical ESP recall >=90%")
    print(f"Verified {len(metadata['files'])} files; model SHA-256 {metadata['files']['visualec_pico.espdl']['sha256']}")


if __name__ == "__main__":
    main()
