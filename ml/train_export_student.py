from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train and INT8-export Visualec-Pico from real YOLOv8n labels")
    parser.add_argument("--esp-detection", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--device", default="cpu")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.esp_detection.resolve()
    if not (root / "train.py").exists() or not (root / "deploy" / "quantize.py").exists():
        raise SystemExit("--esp-detection must point to an Espressif ESP-Detection checkout")
    manifest_path = args.dataset.parent / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("source") != "physical_logitech_c270" or manifest.get("synthetic_data") is not False:
        raise SystemExit("Training is restricted to the verified physical C270 dataset")
    if not args.calibration.exists() or not any(args.calibration.iterdir()):
        raise SystemExit("Real calibration frames are required")
    args.output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root))
    from train import Train
    from deploy.export import Export
    from deploy.quantize import quant_espdet

    results = Train(
        pretrained_path=None,
        dataset=str(args.dataset.resolve()),
        imgsz=[160, 288],
        rect=True,
        epochs=args.epochs,
        batch=32,
        device=args.device,
        mosaic=0.0,
        mixup=0.0,
        copy_paste=0.0,
        augment=False,
        hsv_h=0.0,
        hsv_s=0.0,
        hsv_v=0.0,
        degrees=0.0,
        translate=0.0,
        scale=0.0,
        shear=0.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.0,
        project=str(args.output.resolve()),
        name="student",
    )
    best = Path(results.save_dir) / "weights" / "best.pt"
    Export(str(best), [160, 288])
    onnx_path = best.with_suffix(".onnx")
    espdl_path = args.output / "visualec_pico.espdl"
    quant_espdet(
        onnx_path=str(onnx_path),
        target="esp32s3",
        num_of_bits=8,
        device=args.device,
        batchsz=32,
        imgsz=[160, 288],
        calib_dir=str(args.calibration.resolve()),
        espdl_model_path=str(espdl_path),
    )
    shutil.copy2(best, args.output / "visualec_pico.pt")
    shutil.copy2(onnx_path, args.output / "visualec_pico.onnx")
    run_manifest = {
        "source_manifest": str(manifest_path.resolve()),
        "input_shape": [1, 3, 160, 288],
        "classes": ["person"],
        "target": "esp32s3",
        "quantization": "ESP-PPQ INT8 PTQ",
        "synthetic_augmentation": False,
    }
    (args.output / "training_manifest.json").write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")
    print(f"Created {espdl_path}")


if __name__ == "__main__":
    main()
