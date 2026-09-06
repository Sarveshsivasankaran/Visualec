from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def main() -> None:
    parser = argparse.ArgumentParser(description="Record physical Visualec edge measurements")
    parser.add_argument("--backend", default="http://localhost:8000")
    parser.add_argument("--duration-seconds", type=float, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    samples: list[dict] = []
    started = time.monotonic()
    while time.monotonic() - started < args.duration_seconds:
        with urlopen(f"{args.backend.rstrip('/')}/api/system/status", timeout=3) as response:
            payload = json.load(response)
        if not payload["camera"]["connected"] or not payload["edge"]["connected"]:
            raise SystemExit("Physical camera and ESP32-S3 must both remain connected for a valid benchmark")
        samples.append({
            "camera_fps": payload["camera"]["fps"],
            "inference_fps": payload["edge"]["inference_fps"],
            "inference_ms": payload["edge"]["inference_ms"],
            "round_trip_ms": payload["edge"]["round_trip_ms"],
            "dropped_keyframes": payload["edge"]["dropped_keyframes"],
        })
        time.sleep(1)
    report = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "source": "physical_c270_and_esp32s3",
        "synthetic_data": False,
        "samples": len(samples),
        "camera_fps_median": statistics.median(item["camera_fps"] for item in samples),
        "inference_fps_median": statistics.median(item["inference_fps"] for item in samples),
        "inference_ms_median": statistics.median(item["inference_ms"] for item in samples),
        "round_trip_ms_p95": percentile([item["round_trip_ms"] for item in samples], .95),
        "dropped_keyframes_final": samples[-1]["dropped_keyframes"],
    }
    report["gates"] = {
        "camera_at_least_24_fps": report["camera_fps_median"] >= 24,
        "edge_at_least_7_fps": report["inference_fps_median"] >= 7,
        "inference_at_most_140_ms": report["inference_ms_median"] <= 140,
        "round_trip_p95_at_most_200_ms": report["round_trip_ms_p95"] <= 200,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not all(report["gates"].values()):
        raise SystemExit("One or more physical performance gates failed")


if __name__ == "__main__":
    main()
