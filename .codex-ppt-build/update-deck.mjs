import fs from "node:fs/promises";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const input = "../PPT'S/Visualec_MAST_ESP32S3_Architecture.pptx";
const output = "../PPT'S/Visualec_MAST_ESP32S3_Architecture_Implemented.pptx";
const outDir = "rendered";
await fs.mkdir(outDir, { recursive: true });

const deck = await PresentationFile.importPptx(await FileBlob.load(input));
const edits = {
  "sh/7qp4be9c": "Implemented hybrid edge path: C270 capture and tracking at 24 FPS, motion-selected keyframes, ESP32-S3 INT8 inference, and device-owned relay safety.",
  "sh/65g3298r": "Architecture: hybrid edge authority",
  "sh/ts7md4r2": "Target: classroom zone power control",
  "sh/sryl4zqx": "Board: ESP32-S3 N16R8",
  "sh/fu94fe98": "C270 + laptop\n24 FPS capture",
  "sh/wn6dc7eh": "ESP32 detector\n7–9 FPS target",
  "sh/ul4vaxgb": "Laptop tracking\n24 FPS output",
  "sh/4r6dg7et": "ESP32 relays\ndevice timers",

  "sh/ozy1ofad": "Stock YOLOv8n is the offline teacher; 24 FPS system response does not require 24 neural inferences/sec.",
  "sh/b29kza94": "YOLOv8n teacher\n~3.2M params\n80 COCO classes",
  "sh/x4r21kru": "Not deployed\nstock 320×320 is\ntoo slow on S3",
  "sh/r65knqtk": "Deploy student:\n1 person class\n160×288 INT8",
  "sh/q5wjelsz": "ESP32-S3 at 240 MHz needs a small one-class topology. Espressif’s pedestrian detector is ~130 ms end-to-end; stock compact COCO YOLO is measured in seconds.",
  "sh/ove9o7yd": "Design rule: detector results correct a 24 FPS temporal service",
  "sh/9wnqhczy": "C270 capture, optical flow, tracks, and zones update each real frame. Edge inference runs only on the newest motion-selected keyframe.",
  "sh/mtwrmxg7": "Sources: Espressif pedestrian_detect and coco_detect hardware benchmarks; ESP-DL.",

  "sh/d0jax03i": "Camera-to-laptop capture, sparse device inference, laptop tracking, and ESP-owned relay authority.",
  "sh/n6ls3alk": "Logitech C270\n1280×720 @ 24",
  "sh/n2l4fq98": "Laptop\nmotion score",
  "sh/m1c3mlsn": "RGB565\nnewest keyframe",
  "sh/943mhgre": "ESP32-S3\nPico INT8",
  "sh/83ulovat": "Laptop\ntracks + zones",
  "sh/v6l4jq94": "ESP32\ntimers + GPIO",
  "sh/x8nml0ra": "Run the C270/tracker/zone path at 24 FPS. Send one motion-selected keyframe at a time to the ESP; discard stale frames and late results by frame_id.",
  "sh/w7ulsvqp": "C  C  E  T  T  E  T  T  E",
  "sh/ja54na9g": "C = camera frame, E = edge correction, T = tracking-only update. Raw occupancy returns to the ESP as heartbeats and transitions.",

  "sh/0ba143al": "YOLOv8n labels real C270 sessions offline; a one-class ESPDet-Pico-derived student is deployed.",
  "sh/rm1k7yt4": "YOLOv8n Teacher\noffline PC/GPU only\nperson pseudo-labels",
  "sh/doj29oba": "Automatic distillation\nboxes + confidence\nobjectness",
  "sh/3ihk3et8": "Visualec-Pico\n1 class: person\n≤0.4M params",
  "sh/kbm987y5": "L = box + confidence + objectness distillation; PTQ first, QAT only if INT8 loses over 3 points",
  "sh/i94r6xgz": "Every training, calibration, and validation image must trace to a physical C270 session. Synthetic augmentation and generated detections are disabled.",

  "sh/cf2tcr61": "ESPDet-Pico-derived depthwise blocks, rectangular input, and a one-class anchor-free head.",
  "sh/w32dkbuh": "Input\n160×288",
  "sh/j6dwfqds": "The rectangular input preserves classroom geometry while depthwise-separable blocks reduce compute. ESP-DL’s static planner controls deployment memory.",
  "sh/tcfel0vu": "Input\n160×288",
  "sh/hgrmpwj2": "Params\n≤0.4M",
  "sh/gfi5grih": "Precision\nINT8 PTQ",
  "sh/fe94nm1w": "Classes\n1 person",
  "sh/ud0ne10b": "Graph\nESP-DL ops",
  "sh/pkr6tgjy": "Artifact\n≤1 MB",

  "sh/yhg7epsj": "Hybrid runtime pipeline",
  "sh/zi98nu94": "Capture and tracking stay on the laptop; inference and relay authority stay on the ESP32-S3.",
  "sh/87ipkzal": "Laptop\nC270 + motion\ntracking + zones",
  "sh/98rqt4r6": "WebSocket\none frame in flight",
  "sh/ml07i9sv": "ESP32-S3\nESP-DL inference\nrelay control",
  "sh/pc76hkr2": "Newest keyframe wins; networking never blocks relay timing",
  "sh/w32twb6l": "Internal SRAM: relay state + hot operator workspace\n8 MB OPI PSRAM: frame and model buffers\n16 MB flash: OTA slots + ≥2 MB model partition",
  "sh/u1kbu1ov": "Real frames → ONNX opset 13 → ESP-PPQ INT8 PTQ → verified .espdl\nFlash-map parameters; use ESP-DL static planning and dual-core kernels.",
  "sh/5svutgni": "Sources: ESP-DL memory planner/quantization docs; ESP-Detection deployment; esp32-ai artifact gates.",

  "sh/dcbud0ra": "The laptop selects keyframes from real motion; the ESP processes only one outstanding frame.",
  "sh/ydkbm5sv": "Frame difference\nfrom real C270",
  "sh/kzmdova1": "Motion score\nchanged pixels / total",
  "sh/eh0ba1sr": "Send cadence\nadjusted dynamically",
  "sh/baxkjqlk": "send newest keyframe",
  "sh/a9ojq5kz": "up to 8 edge FPS",
  "sh/cbq1sv25": "send newest keyframe",
  "sh/n6x0fqlo": "up to 4 edge FPS",
  "sh/p8fih03e": "mandatory refresh ≤1 s",
  "sh/o761ov2t": "1 edge FPS",
  "sh/f2d0b6lc": "Result: 24 Hz camera/tracking/zone output with no frame backlog or laptop inference fallback",

  "sh/g72x4zyd": "The laptop computes raw zone occupancy; the ESP32 applies delays once and owns the effective relay state.",
  "sh/ri9g7uhw": "ESP result\nframe-linked boxes",
  "sh/tkby9kzm": "Temporal service\nflow + IoU/Kalman",
  "sh/je9g3ahk": "Polygon lookup\nnormalized zones",
  "sh/o7ydoret": "ESP heartbeat\nraw occupancy",
  "sh/lgbepgvm": "Tracks expire after 750 ms without valid flow or detector confirmation. Control priority: emergency → stale-link safe-off → manual override → automatic occupancy.",

  "sh/0b65obm9": "Software foundation is implemented; real-data training and physical acceptance remain gated work.",
  "sh/mdonql4z": "Capture real data",
  "sh/9gzml0nq": "C270 sessions; split by recording",
  "sh/bih4na5w": "Run teacher",
  "sh/ah8nu54b": "YOLOv8n person-only pseudo-labels",
  "sh/p0ji9kf2": "Distill student",
  "sh/2xsjepgb": "Visualec-Pico ≤0.4M params",
  "sh/cnu1kzyd": "PTQ INT8 first",
  "sh/do3id4fy": "QAT only if loss exceeds 3 points",
  "sh/bml0buxs": "Verify artifact",
  "sh/0ru1ozyp": "ONNX 13 → ESP-PPQ → .espdl + SHA-256",
  "sh/98ji147e": "Flash + measure",
  "sh/87a18zqt": "physical N16R8, C270, relay loads",
  "sh/76h0zup8": "Acceptance evidence rule",
  "sh/ml8j6p8n": "Only real camera frames and recorded ESP packets count. No estimates, simulations, generated detections, or silent fallback.",

  "sh/cbu58j2h": "Implemented modules separate host vision, device inference, protocol, and safety-critical control.",
  "sh/zelojyl8": "edge_inference_service.py\nkeyframe queue, results, metrics",
  "sh/ydcnatkn": "edge_protocol.py\nVEC1 header, RGB565, CRC32",
  "sh/l036l83y": "main.cpp\nWi-Fi, WebSocket, ESP-DL tasks",
  "sh/kzu5c32t": "visualec_pico_detect.cpp\ncustom .espdl wrapper",
  "sh/725onyl4": "relay_controller.cpp\ndelays, overrides, safe-off",
  "sh/m1cnetkj": "package/deploy scripts\nmanifest, hash, benchmark gates",
  "sh/s7yt4b21": "FreeRTOS relay control has higher priority than inference. GPIO acknowledgements are queued only after state is applied; network I/O runs outside the timing loop.",

  "sh/xcryxg7y": "Acceptance gates and current evidence",
  "sh/wbih4b6d": "Targets are explicit; hardware values remain unreported until measured on the physical system.",
  "sh/98rytw72": "Current evidence",
  "sh/72t03qp0": "≥24 Hz",
  "sh/61kzalof": "hardware run pending",
  "sh/9gza9sze": "≥7 FPS high motion",
  "sh/mdobedg3": "hardware run pending",
  "sh/0b6tc3yx": "≥24 Hz",
  "sh/1cfa58zi": "software path implemented",
  "sh/zaxs3yhc": "≤300 ms after delay",
  "sh/cn6t83y1": "HIL relay test pending",
  "sh/tsnip0ny": "0 in 60 min",
  "sh/87ehgv6d": "occupied soak pending",
  "sh/65wzelo7": "≤1 MB",
  "sh/l43ilgn2": "packaging gate enforced",
  "sh/k3uhcb6h": "Measured software: 22 backend tests pass; frontend production build passes. Physical camera/ESP/relay measurements: pending.",

  "sh/0f2lgnmp": "Implemented software architecture for Visualec on ESP32-S3 N16R8.",
  "sh/ra943il8": "Selected: hybrid edge authority",
  "sh/q903ad4n": "C270 → laptop motion/keyframes → Visualec-Pico INT8 on ESP32 → laptop tracking/zones → raw occupancy → ESP32 timers, overrides, emergency, and relay GPIO.",
  "sh/dcbm583y": "Implementation status",
  "sh/sb2lcnmd": "Host protocol, tracking, dashboard status, real-data ML tooling, artifact gates, and ESP-IDF firmware are implemented. Model training, firmware compilation, and measured hardware acceptance require the physical toolchain/devices.",
  "sh/b6d4f2lc": "Sources: ESP-DL; ESP-Detection; Espressif pedestrian/coco benchmarks; esp32-ai commit 97018d5.",
};

for (const [id, value] of Object.entries(edits)) {
  const target = deck.resolve(id);
  target.text = value;
}

const notes = [
  ["https://github.com/slvDev/esp32-ai/tree/97018d5", "https://github.com/espressif/esp-dl", "https://github.com/espressif/esp-detection"],
  ["https://www.espressif.com/en/products/socs/esp32-s3", "https://github.com/espressif/esp-dl/tree/master/models/pedestrian_detect", "https://github.com/espressif/esp-dl/tree/master/models/coco_detect"],
  ["https://github.com/espressif/esp-dl", "https://github.com/espressif/esp-detection"],
  ["https://docs.ultralytics.com/models/yolov8/", "https://github.com/espressif/esp-detection"],
  ["https://github.com/espressif/esp-detection/blob/master/cfg/models/espdet_pico.yaml", "https://github.com/espressif/esp-dl"],
  ["https://github.com/espressif/esp-dl", "https://github.com/espressif/esp-detection", "https://github.com/slvDev/esp32-ai/tree/97018d5"],
  ["https://github.com/espressif/esp-dl/tree/master/models/pedestrian_detect"],
  ["https://github.com/espressif/esp-detection", "https://github.com/espressif/esp-dl"],
  ["https://github.com/espressif/esp-detection", "https://github.com/slvDev/esp32-ai/tree/97018d5"],
  ["https://github.com/espressif/esp-dl", "https://github.com/espressif/esp-detection"],
  ["https://github.com/espressif/esp-dl/tree/master/models/pedestrian_detect", "https://github.com/espressif/esp-dl/tree/master/models/coco_detect"],
  ["https://github.com/espressif/esp-dl", "https://github.com/espressif/esp-detection", "https://github.com/slvDev/esp32-ai/tree/97018d5"],
];
for (let index = 0; index < deck.slides.items.length; index += 1) {
  const slide = deck.slides.getItem(index);
  slide.speakerNotes.textFrame.setText(`[Sources]\n${notes[index].map((url) => `- ${url}`).join("\n")}\n[/Sources]`);
  slide.speakerNotes.setVisible(true);
  const png = await deck.export({ slide, format: "png", scale: 1 });
  await fs.writeFile(`${outDir}/slide-${String(index + 1).padStart(2, "0")}.png`, new Uint8Array(await png.arrayBuffer()));
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(`${outDir}/slide-${String(index + 1).padStart(2, "0")}.layout.json`, await layout.text());
}
const montage = await deck.export({ format: "webp", montage: true, scale: 1 });
await fs.writeFile(`${outDir}/montage.webp`, new Uint8Array(await montage.arrayBuffer()));
const after = await deck.inspect({ kind: "slide,textbox,notes", maxChars: 120000 });
await fs.writeFile(`${outDir}/after-inspect.ndjson`, after.ndjson);
const pptx = await PresentationFile.exportPptx(deck);
await pptx.save(output);
console.log(`saved ${output}`);
