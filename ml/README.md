# Visualec real-frame model pipeline

This pipeline never creates synthetic images or simulated detections. Every training, calibration, and validation frame must originate from the physical Logitech C270. Pretrained YOLOv8n is used only as a person-class teacher; the ESP32-S3 deploys the one-class ESPDet-Pico-derived student.

## 1. Capture separate real sessions

Record train, validation, and calibration sessions at different times or viewpoints so adjacent frames never leak between splits.

```powershell
python ml\capture_real_frames.py --output ml\data\c270 --session classroom_train_01 --split train --duration-seconds 900
python ml\capture_real_frames.py --output ml\data\c270 --session classroom_val_01 --split val --duration-seconds 300
python ml\capture_real_frames.py --output ml\data\c270 --session classroom_calib_01 --split calibration --duration-seconds 180
```

## 2. Generate person-only teacher labels

```powershell
python ml\pseudo_label_real_frames.py --sessions-root ml\data\c270 --output ml\data\visualec_person --teacher yolov8n.pt --confidence 0.60
```

The script writes YOLO labels plus teacher confidence sidecars and refuses any session without a physical-capture manifest.

## 3. Train and export the student

Clone Espressif ESP-Detection separately, then run:

```powershell
python ml\train_export_student.py --esp-detection D:\src\esp-detection --dataset ml\data\visualec_person\dataset.yaml --calibration ml\data\visualec_person\images\calibration --output ml\artifacts\visualec-pico
```

Training uses 160×288 rectangular inputs with mosaic, mixup, copy-paste, geometric, and color synthesis disabled. Export is ONNX opset 13 followed by ESP-PPQ INT8 PTQ for `esp32s3`.

## 4. Record quality and package

Export teacher, floating-student, INT8-host, and physical-ESP predictions for the same held-out real frames into one recorded `predictions.json`, then calculate the quality gate. If PTQ loses more than three mAP50 points, the evaluator stops and QAT must be run using those same real frames before packaging.

```powershell
python ml\evaluate_real_pipeline.py --dataset-manifest ml\data\visualec_person\dataset_manifest.json --predictions ml\artifacts\visualec-pico\predictions.json --output ml\artifacts\visualec-pico\quality.json
```

Then package and verify:

```powershell
python ml\package_model.py --espdl ml\artifacts\visualec-pico\visualec_pico.espdl --onnx ml\artifacts\visualec-pico\best.onnx --quality ml\artifacts\visualec-pico\quality.json --training-manifest ml\data\visualec_person\dataset_manifest.json --version v1 --output ml\artifacts\release
powershell -ExecutionPolicy Bypass -File scripts\deploy_edge.ps1 -Port COM5 -ArtifactDir ml\artifacts\release
```

Deployment is blocked unless the student retains at least 90% of teacher recall, INT8 loses no more than three mAP50 points, the artifact is at most 1 MB, and every hash matches.

For the first laboratory candidate, use `scripts\flash_edge_candidate.ps1`; it applies the real-data, hash, size, host-quality, and build gates but does not pretend hardware results already exist. Record ESP predictions, rerun the evaluator with `--require-esp`, repackage the identical model, then use `deploy_edge.ps1`. Release deployment requires physical ESP recall evidence.
