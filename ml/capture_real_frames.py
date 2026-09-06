from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture motion-selected frames from a physical Logitech C270")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--split", choices=("train", "val", "calibration"), required=True)
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--duration-seconds", type=float, required=True)
    parser.add_argument("--minimum-interval", type=float, default=0.25)
    parser.add_argument("--maximum-interval", type=float, default=2.0)
    parser.add_argument("--motion-threshold", type=float, default=0.015)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session_dir = args.output / "sessions" / args.session
    images_dir = session_dir / "images"
    if session_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing capture session: {session_dir}")
    images_dir.mkdir(parents=True)
    camera = cv2.VideoCapture(args.camera_index, cv2.CAP_DSHOW)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    camera.set(cv2.CAP_PROP_FPS, 24)
    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not camera.isOpened():
        raise SystemExit("Physical camera could not be opened; no replacement frames will be generated")

    started = time.monotonic()
    last_saved = -args.maximum_interval
    previous_gray = None
    records: list[dict] = []
    captured = 0
    try:
        while time.monotonic() - started < args.duration_seconds:
            ok, frame = camera.read()
            if not ok:
                raise RuntimeError("Physical camera stopped returning frames")
            captured += 1
            gray = cv2.cvtColor(cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            motion = 1.0
            if previous_gray is not None:
                delta = cv2.absdiff(gray, previous_gray)
                motion = float((delta >= 20).sum() / delta.size)
            previous_gray = gray
            elapsed = time.monotonic() - started
            since_save = elapsed - last_saved
            should_save = since_save >= args.maximum_interval or (
                since_save >= args.minimum_interval and motion >= args.motion_threshold
            )
            if not should_save:
                continue
            filename = f"{args.session}_{len(records):06d}.jpg"
            path = images_dir / filename
            if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 94]):
                raise RuntimeError(f"Failed to write captured frame {path}")
            records.append({"file": filename, "elapsed_seconds": round(elapsed, 3), "motion_score": round(motion, 5)})
            last_saved = elapsed
    finally:
        camera.release()

    manifest = {
        "schema": 1,
        "source": "physical_logitech_c270",
        "synthetic_data": False,
        "session": args.session,
        "split": args.split,
        "camera_index": args.camera_index,
        "requested_resolution": [1280, 720],
        "requested_fps": 24,
        "captured_frames": captured,
        "saved_frames": len(records),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "frames": records,
    }
    (session_dir / "capture_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved {len(records)} real frames to {session_dir}")


if __name__ == "__main__":
    main()
