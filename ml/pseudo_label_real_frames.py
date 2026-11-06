from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from ultralytics import YOLO


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Label real C270 frames with a pretrained YOLOv8n person-only teacher")
    parser.add_argument("--sessions-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--teacher", default="yolov8n.pt")
    parser.add_argument("--confidence", type=float, default=0.60)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.output.exists():
        raise SystemExit(f"Refusing to overwrite existing labeled dataset: {args.output}")
    sessions = sorted((args.sessions_root / "sessions").glob("*/capture_manifest.json"))
    if not sessions:
        raise SystemExit("No physical capture manifests were found")
    model = YOLO(args.teacher)
    dataset_records: list[dict] = []
    split_counts = {"train": 0, "val": 0, "calibration": 0}
    for manifest_path in sessions:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("source") != "physical_logitech_c270" or manifest.get("synthetic_data") is not False:
            raise SystemExit(f"Session is not a verified physical C270 capture: {manifest_path.parent}")
        split = manifest["split"]
        source_images = manifest_path.parent / "images"
        destination_images = args.output / "images" / split
        destination_labels = args.output / "labels" / split
        confidence_dir = args.output / "teacher_confidence" / split
        destination_images.mkdir(parents=True, exist_ok=True)
        destination_labels.mkdir(parents=True, exist_ok=True)
        confidence_dir.mkdir(parents=True, exist_ok=True)
        for source in sorted(path for path in source_images.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES):
            destination = destination_images / source.name
            shutil.copy2(source, destination)
            result = model.predict(str(source), classes=[0], conf=args.confidence, verbose=False)[0]
            height, width = result.orig_shape
            labels: list[str] = []
            confidences: list[dict] = []
            for box in result.boxes:
                x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
                centre_x, centre_y = ((x1 + x2) / 2 / width), ((y1 + y2) / 2 / height)
                box_width, box_height = (x2 - x1) / width, (y2 - y1) / height
                confidence = float(box.conf[0])
                labels.append(f"0 {centre_x:.8f} {centre_y:.8f} {box_width:.8f} {box_height:.8f}")
                confidences.append({"bbox_xyxy": [x1, y1, x2, y2], "confidence": confidence})
            (destination_labels / f"{source.stem}.txt").write_text("\n".join(labels), encoding="utf-8")
            (confidence_dir / f"{source.stem}.json").write_text(json.dumps(confidences, indent=2), encoding="utf-8")
            split_counts[split] += 1
            dataset_records.append({"session": manifest["session"], "split": split, "image": source.name, "people": len(labels)})

    dataset_yaml = (
        f"path: {args.output.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n  0: person\n"
    )
    (args.output / "dataset.yaml").write_text(dataset_yaml, encoding="utf-8")
    manifest = {
        "schema": 1,
        "teacher": args.teacher,
        "teacher_class": 0,
        "teacher_class_name": "person",
        "confidence_threshold": args.confidence,
        "source": "physical_logitech_c270",
        "synthetic_data": False,
        "manual_labels": False,
        "split_counts": split_counts,
        "records": dataset_records,
    }
    (args.output / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(split_counts, indent=2))


if __name__ == "__main__":
    main()
