from __future__ import annotations

import argparse
import json
from pathlib import Path


def iou(left: list[float], right: list[float]) -> float:
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def agreement_recall(frames: list[dict], candidate_key: str, threshold: float) -> float:
    teacher_total = 0
    matched_total = 0
    for frame in frames:
        teacher = frame.get("teacher", [])
        candidates = frame.get(candidate_key, [])
        teacher_total += len(teacher)
        unmatched = set(range(len(candidates)))
        for truth in teacher:
            matches = [(iou(truth["bbox"], candidates[index]["bbox"]), index) for index in unmatched]
            if matches:
                best_iou, best_index = max(matches)
                if best_iou >= threshold:
                    matched_total += 1
                    unmatched.remove(best_index)
    return matched_total / teacher_total if teacher_total else 1.0


def average_precision_50(frames: list[dict], candidate_key: str) -> float:
    truth_count = sum(len(frame.get("teacher", [])) for frame in frames)
    if truth_count == 0:
        return 1.0
    ranked: list[tuple[float, bool]] = []
    for frame in frames:
        truth = frame.get("teacher", [])
        used: set[int] = set()
        for prediction in sorted(frame.get(candidate_key, []), key=lambda item: item.get("confidence", 0), reverse=True):
            matches = [(iou(prediction["bbox"], box["bbox"]), index) for index, box in enumerate(truth) if index not in used]
            best_iou, best_index = max(matches, default=(0.0, -1))
            is_true = best_iou >= 0.5
            if is_true:
                used.add(best_index)
            ranked.append((float(prediction.get("confidence", 0)), is_true))
    ranked.sort(reverse=True)
    true_positives = 0
    false_positives = 0
    curve: list[tuple[float, float]] = []
    for _, is_true in ranked:
        true_positives += int(is_true)
        false_positives += int(not is_true)
        curve.append((true_positives / truth_count, true_positives / (true_positives + false_positives)))
    ap = 0.0
    for recall_level in [value / 100 for value in range(101)]:
        ap += max((precision for recall, precision in curve if recall >= recall_level), default=0.0)
    return ap / 101


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare teacher, float, INT8 host, and physical ESP predictions on held-out C270 frames")
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-esp", action="store_true", help="Require recorded physical ESP predictions for release validation")
    args = parser.parse_args()
    manifest = json.loads(args.dataset_manifest.read_text(encoding="utf-8"))
    if manifest.get("source") != "physical_logitech_c270" or manifest.get("synthetic_data") is not False:
        raise SystemExit("Evaluation requires a verified physical C270 manifest")
    payload = json.loads(args.predictions.read_text(encoding="utf-8"))
    if payload.get("source") not in {"physical_c270", "physical_c270_and_esp32s3"} or payload.get("synthetic_data") is not False:
        raise SystemExit("Predictions must preserve real C270 provenance")
    frames = payload.get("frames", [])
    if not frames:
        raise SystemExit("No held-out frames were supplied")
    float_recall = agreement_recall(frames, "float_student", 0.5)
    int8_recall = agreement_recall(frames, "int8_host", 0.5)
    has_esp = all("esp" in frame for frame in frames)
    if args.require_esp and (payload.get("source") != "physical_c270_and_esp32s3" or not has_esp):
        raise SystemExit("Release validation requires recorded physical ESP output for every frame")
    esp_recall = agreement_recall(frames, "esp", 0.5) if has_esp else None
    float_ap = average_precision_50(frames, "float_student")
    int8_ap = average_precision_50(frames, "int8_host")
    report = {
        "source": "held_out_physical_c270_and_recorded_esp_packets",
        "synthetic_data": False,
        "frames": len(frames),
        "student_teacher_recall_ratio": float_recall,
        "int8_teacher_recall_ratio": int8_recall,
        "floating_student_map50": float_ap,
        "int8_host_map50": int8_ap,
        "int8_map50_drop_points": max(0.0, (float_ap - int8_ap) * 100),
        "qat_required": (float_ap - int8_ap) * 100 > 3.0,
    }
    if esp_recall is not None:
        report["esp_teacher_recall_ratio"] = esp_recall
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["student_teacher_recall_ratio"] < 0.90:
        raise SystemExit("Floating student retains under 90% of teacher recall")
    if report["qat_required"]:
        raise SystemExit("PTQ lost more than three mAP50 points; run QAT using the same real frames before packaging")


if __name__ == "__main__":
    main()
