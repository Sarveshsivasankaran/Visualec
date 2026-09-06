from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify and package a deployable Visualec-Pico artifact")
    parser.add_argument("--espdl", type=Path, required=True)
    parser.add_argument("--onnx", type=Path, required=True)
    parser.add_argument("--quality", type=Path, required=True)
    parser.add_argument("--training-manifest", type=Path, required=True)
    parser.add_argument("--version", default=None, help="Release version; defaults to a UTC timestamp")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    quality = json.loads(args.quality.read_text(encoding="utf-8"))
    training_manifest = json.loads(args.training_manifest.read_text(encoding="utf-8"))
    if training_manifest.get("source") != "physical_logitech_c270" or training_manifest.get("synthetic_data") is not False:
        raise SystemExit("Training manifest must describe verified physical Logitech C270 frames")
    recall_ratio = float(quality.get("student_teacher_recall_ratio", 0))
    int8_recall_ratio = float(quality.get("int8_teacher_recall_ratio", 0))
    int8_drop = float(quality.get("int8_map50_drop_points", 999))
    if recall_ratio < 0.90:
        raise SystemExit(f"Student retains only {recall_ratio:.1%} of teacher recall; required >=90%")
    if int8_recall_ratio < 0.90:
        raise SystemExit("INT8 host output must retain at least 90% of teacher recall")
    if int8_drop > 3.0:
        raise SystemExit(f"INT8 mAP50 drop is {int8_drop:.2f} points; required <=3")
    if args.espdl.stat().st_size > 1_000_000:
        raise SystemExit("ESP-DL artifact exceeds the 1 MB deployment budget")

    args.output.mkdir(parents=True, exist_ok=True)
    model_target = args.output / "visualec_pico.espdl"
    onnx_target = args.output / "visualec_pico.onnx"
    quality_target = args.output / "quality.json"
    source_target = args.output / "training_source_manifest.json"
    shutil.copy2(args.espdl, model_target)
    shutil.copy2(args.onnx, onnx_target)
    shutil.copy2(args.quality, quality_target)
    shutil.copy2(args.training_manifest, source_target)

    artifact_version = args.version or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = {
        "schema": 1,
        "model": "visualec-pico-person-int8",
        "artifact_version": artifact_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": {"width": 288, "height": 160, "pixel_format": "RGB565LE"},
        "classes": ["person"],
        "confidence_threshold": 0.45,
        "quantization": "ESP-PPQ INT8 PTQ",
        "target": "esp32s3",
        "files": {
            target.name: {"bytes": target.stat().st_size, "sha256": sha256(target)}
            for target in (model_target, onnx_target, quality_target, source_target)
        },
        "quality": quality,
        "hardware_validated": float(quality.get("esp_teacher_recall_ratio", 0)) >= 0.90,
        "tools": {
            "ultralytics": package_version("ultralytics"),
            "esp-ppq": package_version("esp-ppq"),
            "onnx": package_version("onnx"),
        },
        "training_source_manifest": source_target.name,
        "synthetic_data": False,
    }
    (args.output / "metadata.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
