import { FormEvent, useEffect, useState } from "react";
import { Camera, Cpu, Save, Server, ShieldCheck, Zap } from "lucide-react";
import { request } from "../api";
import { SystemState } from "../types";

type SettingsData = {
  camera_index:number; camera_width:number; camera_height:number; detection_model:string;
  detection_confidence:number; inference_interval_ms:number; activation_delay_seconds:number;
  deactivation_delay_seconds:number; esp32_base_url:string; energy_tariff_per_kwh:number; mode:string;
};

export default function Settings({ state }: { state: SystemState }) {
  const [data, setData] = useState<SettingsData>();
  const [saved, setSaved] = useState(false);
  useEffect(() => { request<SettingsData>("/api/settings").then(setData); }, []);
  if (!data) return <div className="page"><div className="empty-state">Loading system settings…</div></div>;

  function patch(values: Partial<SettingsData>) {
    setData(current => ({ ...current!, ...values }));
    setSaved(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await request("/api/detection/settings", {
      method: "PUT",
      body: JSON.stringify({ confidence: data!.detection_confidence, inference_interval_ms: data!.inference_interval_ms }),
    });
    await request("/api/camera/select", {
      method: "POST",
      body: JSON.stringify({ index: data!.camera_index, width: data!.camera_width, height: data!.camera_height }),
    });
    await request("/api/settings", { method: "PUT", body: JSON.stringify(data) });
    setSaved(true);
  }

  return <form className="page" onSubmit={submit}>
    <header className="topbar">
      <div><p className="eyebrow">SYSTEM / CONFIGURATION</p><h1>Settings</h1></div>
      <button className="button primary"><Save size={17} />{saved ? "Saved" : "Save changes"}</button>
    </header>
    <div className="settings-grid">
      <section className="settings-section panel">
        <div className="settings-title"><Camera /><div><h2>Camera source</h2><p>Physical Logitech C270 capture</p></div></div>
        <label>Camera index<input type="number" min="0" max="20" value={data.camera_index} onChange={event => patch({ camera_index: +event.target.value })} /></label>
        <label>Resolution<select value={`${data.camera_width}x${data.camera_height}`} onChange={event => { const [width, height] = event.target.value.split("x").map(Number); patch({ camera_width: width, camera_height: height }); }}><option value="640x480">640 × 480</option><option value="1280x720">1280 × 720</option></select></label>
      </section>
      <section className="settings-section panel">
        <div className="settings-title"><Cpu /><div><h2>Edge person detection</h2><p>YOLOv8n teacher · Visualec-Pico INT8 runtime</p></div></div>
        <label>Model<input value={state.edge.model_version !== "unknown" ? state.edge.model_version : data.detection_model} disabled /></label>
        <label>Confidence · {Math.round(data.detection_confidence * 100)}%<input type="range" min=".1" max=".95" step=".05" value={data.detection_confidence} onChange={event => patch({ detection_confidence: +event.target.value })} /></label>
        <div className="inline-status"><span className={`status-dot ${state.edge.connected ? "online" : ""}`} />{state.edge.connected ? `${state.edge.inference_fps.toFixed(1)} FPS · ${state.edge.round_trip_ms.toFixed(0)} ms round trip` : "ESP-DL inference unavailable — no laptop fallback"}</div>
      </section>
      <section className="settings-section panel">
        <div className="settings-title"><ShieldCheck /><div><h2>Occupancy guards</h2><p>Executed once on the ESP32-S3</p></div></div>
        <label>Activation delay (s)<input type="number" min="0" value={data.activation_delay_seconds} onChange={event => patch({ activation_delay_seconds: +event.target.value })} /></label>
        <label>Deactivation delay (s)<input type="number" min="0" value={data.deactivation_delay_seconds} onChange={event => patch({ deactivation_delay_seconds: +event.target.value })} /></label>
      </section>
      <section className="settings-section panel">
        <div className="settings-title"><Server /><div><h2>Hardware gateway</h2><p>Authenticated WebSocket edge channel · HTTP rollback</p></div></div>
        <label>Rollback ESP32 URL<input value={data.esp32_base_url} onChange={event => patch({ esp32_base_url: event.target.value })} /></label>
        <div className="inline-status"><span className={`status-dot ${state.esp32.connected ? "online" : ""}`} />{state.esp32.connected ? `${state.edge.device_id} · firmware ${state.edge.firmware_version}` : "Physical device offline — inference and relay commands are blocked"}</div>
      </section>
      <section className="settings-section panel">
        <div className="settings-title"><Zap /><div><h2>Energy model</h2><p>Tariff and operating policy</p></div></div>
        <label>Tariff (₹ / kWh)<input type="number" min="0" step=".01" value={data.energy_tariff_per_kwh} onChange={event => patch({ energy_tariff_per_kwh: +event.target.value })} /></label>
        <label>Operating mode<select value={data.mode} onChange={event => patch({ mode: event.target.value })}><option value="automatic">Automatic</option><option value="hybrid">Hybrid</option><option value="manual">Manual</option></select></label>
      </section>
    </div>
  </form>;
}
