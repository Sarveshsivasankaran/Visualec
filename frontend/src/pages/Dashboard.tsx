import { useState } from "react";
import { Activity, Camera, CameraOff, Clock3, Cpu, Gauge, Leaf, Power, Radio, ShieldAlert, ShieldCheck, Timer, TriangleAlert, Users, Wifi, Zap } from "lucide-react";
import { apiBase, request } from "../api";
import MetricCard from "../components/MetricCard";
import StatusPill from "../components/StatusPill";
import { SystemState, ZoneState } from "../types";

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes}m ${Math.floor(seconds % 60)}s` : `${Math.floor(seconds)}s`;
}

function ZoneCard({ zone, state }: { zone: ZoneState; state: SystemState }) {
  const [busy, setBusy] = useState(false);
  const relay = state.relays.find(item => zone.relay_ids.includes(item.id));

  async function setRelay(on: boolean) {
    if (!relay) return;
    setBusy(true);
    try {
      await request(`/api/relays/${relay.id}/override`, {
        method: "POST",
        body: JSON.stringify({ state: on }),
      });
    } finally {
      setBusy(false);
    }
  }

  // 4-Tier State Priority Resolution:
  // Tier 1 (Highest): Emergency Stop - Latched into NVS, forces all relays OFF
  // Tier 2: Safe-OFF - Loss of link / Stale input safety timeout
  // Tier 3: Manual Override - Temporary dashboard toggle
  // Tier 4: Automatic Occupancy - ESP-DL bounding box & debounce
  let tierLabel = "Tier 4: Standby";
  let tierTone: "good" | "warn" | "danger" | "neutral" = "neutral";
  let stateDescription = "Standby · automatic debounce active";

  if (state.emergency) {
    tierLabel = "Tier 1: E-Stop";
    tierTone = "danger";
    stateDescription = "Circuits isolated · Emergency Stop latched in NVS";
  } else if (!state.esp32.connected) {
    tierLabel = "Tier 2: Safe-OFF";
    tierTone = "danger";
    stateDescription = "Controller offline · Relays de-energized on timeout";
  } else if (relay?.manual_override) {
    tierLabel = `Tier 3: Override (${Math.ceil(relay.manual_override_remaining_seconds ?? 0)}s)`;
    tierTone = "warn";
    stateDescription = `Manual override · Auto-revert in ${Math.ceil(relay.manual_override_remaining_seconds ?? 0)}s`;
  } else if (relay?.state === "on" || zone.occupied) {
    tierLabel = "Tier 4: Auto Active";
    tierTone = "good";
    stateDescription = "Powered · ESP-DL bounding-box confirmed";
  } else if (zone.raw_occupied) {
    tierLabel = "Tier 4: Debouncing";
    tierTone = "warn";
    stateDescription = "Temporal tracking · Awaiting activation debounce";
  }

  const isRelayOn = relay?.state === "on";
  const controlsDisabled = busy || !relay || !state.esp32.connected || state.emergency;

  return (
    <article className={`zone-card ${zone.occupied ? "occupied" : ""} ${state.emergency ? "emergency-locked" : ""}`}>
      <div className="zone-head">
        <span className="zone-swatch" style={{ background: zone.colour }} />
        <div>
          <p>{zone.name}</p>
          <strong>{zone.occupied ? "Occupied" : zone.raw_occupied ? "Confirming…" : "Vacant"}</strong>
        </div>
        <div className="zone-head-badges">
          <span className={`priority-tier-badge tone-${tierTone}`}>{tierLabel}</span>
          <span className="people-count" title={`${zone.people_count} person(s) detected`}>
            <Users size={14} />{zone.people_count}
          </span>
        </div>
      </div>

      <div className="zone-stats">
        <span><Clock3 size={14} /> {formatDuration(zone.occupancy_duration_seconds)}</span>
        <span><Radio size={14} /> {relay ? `Relay ${relay.id}` : "Unmapped"}</span>
        {relay?.rated_wattage ? <span><Zap size={14} /> {relay.rated_wattage}W rated</span> : null}
      </div>

      <div className="appliance-row">
        <div className="appliance-meta">
          <span className={`power-icon ${isRelayOn ? "on" : ""} ${state.emergency ? "danger" : ""}`}>
            <Power size={17} />
          </span>
          <div className="appliance-info">
            <div className="appliance-title">
              <strong>{relay ? relay.name : `${zone.name} Circuit`}</strong>
              {relay?.rated_wattage ? <span className="wattage-tag">{relay.rated_wattage}W</span> : null}
            </div>
            <small>{stateDescription}</small>
          </div>
        </div>

        <div className="segmented">
          <button
            disabled={controlsDisabled}
            className={isRelayOn ? "selected" : ""}
            onClick={() => setRelay(true)}
            title={state.emergency ? "Locked by Emergency Stop" : !state.esp32.connected ? "Locked: Controller offline" : "Force Relay ON"}
          >
            On
          </button>
          <button
            disabled={controlsDisabled}
            className={relay?.state === "off" ? "selected" : ""}
            onClick={() => setRelay(false)}
            title={state.emergency ? "Locked by Emergency Stop" : !state.esp32.connected ? "Locked: Controller offline" : "Force Relay OFF"}
          >
            Off
          </button>
        </div>
      </div>
    </article>
  );
}

export default function Dashboard({ state, connected }: { state: SystemState; connected: boolean }) {
  const [emergencyBusy, setEmergencyBusy] = useState(false);
  const energy = state.energy;

  async function emergency() {
    const message = state.emergency
      ? "Reset emergency mode and resume detection?"
      : "Emergency stop will turn every relay off and suspend detection. Continue?";
    if (!confirm(message)) return;
    setEmergencyBusy(true);
    try {
      await request(state.emergency ? "/api/system/reset" : "/api/system/emergency-stop", { method: "POST" });
    } finally {
      setEmergencyBusy(false);
    }
  }

  const roundTripSlaMet = state.edge.round_trip_ms <= 200;

  // Active priority status across system
  const systemPriority = state.emergency
    ? { tier: "Tier 1: Emergency Stop", desc: "NVS Latched · Circuits Isolated", tone: "danger" as const }
    : !state.esp32.connected
    ? { tier: "Tier 2: Safe-OFF Active", desc: "Link Lost · Automatic Relays De-energized", tone: "danger" as const }
    : state.relays.some(r => r.manual_override)
    ? { tier: "Tier 3: Manual Override", desc: "Dashboard Temporary Toggles Active", tone: "warn" as const }
    : { tier: "Tier 4: Automatic Occupancy", desc: "ESP-DL On-Device Bounding Box & Debounce", tone: "good" as const };

  return (
    <div className="page dashboard-page">
      <header className="topbar">
        <div>
          <p className="eyebrow">ROOM CONTROL / EDGE COMMAND</p>
          <h1>Energy command center</h1>
        </div>
        <div className="top-actions">
          <StatusPill tone={systemPriority.tone}>{systemPriority.tier}</StatusPill>
          <StatusPill tone={state.edge.connected ? "good" : "danger"}>
            {state.edge.connected ? "ESP-DL online" : "Edge offline"}
          </StatusPill>
          <button
            className={`emergency ${state.emergency ? "active" : ""}`}
            disabled={emergencyBusy}
            onClick={emergency}
          >
            <TriangleAlert size={18} />
            {state.emergency ? "Reset system" : "Emergency stop"}
          </button>
        </div>
      </header>

      {state.emergency ? (
        <aside className="safety-alert-banner tier-1" role="alert">
          <div className="safety-banner-icon"><TriangleAlert size={20} /></div>
          <div className="safety-banner-content">
            <strong>Tier 1 Safety Latched: Emergency Stop Active</strong>
            <p>Relay circuits are locked OFF in non-volatile storage (NVS). Automatic occupancy dispatch and manual toggles are suspended until explicit reset.</p>
          </div>
          <button className="button primary" disabled={emergencyBusy} onClick={emergency}>
            Reset System
          </button>
        </aside>
      ) : !state.esp32.connected ? (
        <aside className="safety-alert-banner tier-2" role="alert">
          <div className="safety-banner-icon"><ShieldAlert size={20} /></div>
          <div className="safety-banner-content">
            <strong>Tier 2 Safety Engaged: Safe-OFF Timeout</strong>
            <p>Controller link offline or telemetry stale. Relays are automatically de-energized to safeguard physical loads against stale inputs.</p>
          </div>
        </aside>
      ) : null}

      <section className="hero-grid">
        <article className="camera-panel panel">
          <div className="panel-heading">
            <div>
              <span className={`live-dot ${state.camera.connected ? "" : "offline"}`} />
              <div>
                <strong>Camera · Main room</strong>
                <small>{state.camera.connected ? "24 FPS temporal tracking · sparse ESP-DL correction" : "Waiting for physical camera"}</small>
              </div>
            </div>
            <div className="camera-badges">
              <span><Gauge size={14} />{state.camera.fps.toFixed(1)} FPS</span>
              <span><Users size={14} />{state.detection.people_count} people</span>
            </div>
          </div>
          <div className="feed-wrap">
            {state.camera.connected ? (
              <img src={`${apiBase}/api/camera/stream`} alt="Live room camera with detection and zone overlays" />
            ) : (
              <div className="hardware-offline">
                <CameraOff />
                <strong>Camera unavailable</strong>
                <span>{state.camera.error ?? "Connect the Logitech C270 to start real-time tracking."}</span>
              </div>
            )}
            <div className="feed-status"><Camera size={14} />{state.camera.health}</div>
          </div>
        </article>

        <aside className="live-summary panel">
          <div className="pulse-orb"><Zap size={28} /><span /></div>
          <p>Adaptive grid load</p>
          <strong>{energy?.current_power_watts.toFixed(0) ?? "0"}<small> W</small></strong>
          <span>Current draw</span>
          <div className="load-meter"><i style={{ width: `${Math.min(100, (energy?.current_power_watts || 0) / .27)}%` }} /></div>
          <dl>
            <div><dt>Occupied zones</dt><dd>{state.zones.filter(zone => zone.occupied).length} / {state.zones.length}</dd></div>
            <div><dt>Relays active</dt><dd>{state.relays.filter(relay => relay.state === "on").length} / {state.relays.length}</dd></div>
            <div><dt>Edge inference</dt><dd>{state.edge.inference_ms.toFixed(0)} ms</dd></div>
            <div><dt>Round trip SLA</dt><dd className={roundTripSlaMet ? "good-color" : "danger-color"}>{state.edge.round_trip_ms.toFixed(0)} ms {roundTripSlaMet ? "✓" : "⚠"}</dd></div>
            <div><dt>State priority</dt><dd className={systemPriority.tone === "good" ? "good-color" : systemPriority.tone === "warn" ? "" : "danger-color"}>{systemPriority.tier.split(":")[0]}</dd></div>
          </dl>
          <StatusPill tone={connected ? "good" : "danger"}>{connected ? "Telemetry live" : "Reconnecting"}</StatusPill>
        </aside>
      </section>

      <section className="section-heading">
        <div>
          <p className="eyebrow">OCCUPANCY GRID · 4-TIER PRIORITY DISPATCH</p>
          <h2>Zone activity & relay circuits</h2>
        </div>
        <div className="section-meta-tags">
          <span className="sla-tag"><Timer size={12} /> SLA: p95 ≤ 200 ms</span>
          <span className="timing-tag"><ShieldCheck size={12} /> ESP32 Monotonic Timing Guards</span>
        </div>
      </section>

      <section className="zone-grid">
        {state.zones.length
          ? state.zones.map(zone => <ZoneCard key={zone.id} zone={zone} state={state} />)
          : [1, 2, 3].map(id => <div className="zone-card skeleton" key={id} />)}
      </section>

      <section className="metrics-grid">
        <MetricCard
          label="Round trip latency"
          value={`${state.edge.round_trip_ms.toFixed(0)} ms`}
          detail={state.edge.connected ? (roundTripSlaMet ? "Passes ≤ 200 ms physical SLA gate" : "SLA gate breached (> 200 ms)") : "Awaiting edge frame"}
          icon={<Timer />}
          tone={state.edge.connected ? (roundTripSlaMet ? "good" : "warn") : "neutral"}
          badge={
            <StatusPill tone={state.edge.connected ? (roundTripSlaMet ? "good" : "danger") : "neutral"}>
              {roundTripSlaMet ? "≤200ms SLA" : "High latency"}
            </StatusPill>
          }
        />
        <MetricCard
          label="Edge detector"
          value={`${state.edge.inference_fps.toFixed(1)} FPS`}
          detail={state.edge.connected ? `${state.edge.inference_ms.toFixed(0)} ms on ESP32-S3 (ESP-DL INT8)` : "Physical edge offline"}
          icon={<Cpu />}
          tone={state.edge.connected ? "good" : "danger"}
          badge={<StatusPill tone={state.edge.connected ? "good" : "danger"}>{state.edge.connected ? "ESP-DL" : "Offline"}</StatusPill>}
        />
        <MetricCard
          label="Hardware pipeline"
          value="ROM CRC32"
          detail="~1.2 ms CRC + PSRAM ping-pong (0 malloc spinlock)"
          icon={<Gauge />}
          tone="good"
          badge={<StatusPill tone="good">Accelerated</StatusPill>}
        />
        <MetricCard
          label="Wi-Fi link & health"
          value={`${state.edge.wifi_rssi || 0} dBm`}
          detail={`${state.edge.dropped_keyframes} drops · ${state.edge.late_results} late · ${state.edge.protocol_errors} err`}
          icon={<Wifi />}
          tone={(state.edge.wifi_rssi || -100) > -75 ? "good" : "warn"}
        />
      </section>

      <section className="metrics-grid">
        <MetricCard
          label="Current draw"
          value={`${energy?.current_power_watts.toFixed(0) ?? 0} W`}
          detail="Across active relay loads"
          icon={<Activity />}
        />
        <MetricCard
          label="Energy avoided"
          value={`${energy?.energy_saved_kwh.toFixed(3) ?? "0.000"} kWh`}
          detail="Adaptive reduction vs all-on baseline"
          icon={<Leaf />}
          tone="good"
        />
        <MetricCard
          label="Cost avoided"
          value={`₹${energy?.cost_saved.toFixed(2) ?? "0.00"}`}
          detail="Current reporting period"
          icon={<Zap />}
          tone="good"
        />
        <MetricCard
          label="Relay activations"
          value={`${energy?.relay_activations ?? 0}`}
          detail="Acknowledged state transitions"
          icon={<Radio />}
        />
      </section>
    </div>
  );
}

