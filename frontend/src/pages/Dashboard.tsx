import { useState } from "react";
import { Activity, Camera, CameraOff, Clock3, Gauge, Leaf, Power, Radio, TriangleAlert, Users, Zap } from "lucide-react";
import { apiBase, request } from "../api";
import MetricCard from "../components/MetricCard";
import StatusPill from "../components/StatusPill";
import { SystemState, ZoneState } from "../types";

function formatDuration(seconds:number) { const m=Math.floor(seconds/60); return m ? `${m}m ${Math.floor(seconds%60)}s` : `${Math.floor(seconds)}s`; }

function ZoneCard({zone, state}:{zone:ZoneState;state:SystemState}) {
  const [busy,setBusy] = useState(false);
  const relay = state.relays.find(item=>zone.relay_ids.includes(item.id));
  async function setRelay(on:boolean) {
    if (!relay) return;
    setBusy(true);
    try { await request(`/api/relays/${relay.id}/override`, {method:"POST",body:JSON.stringify({state:on,duration_seconds:900})}); }
    finally { setBusy(false); }
  }
  return <article className={`zone-card ${zone.occupied?"occupied":""}`}>
    <div className="zone-head"><span className="zone-swatch" style={{background:zone.colour}}/><div><p>{zone.name}</p><strong>{zone.occupied?"Occupied":"Vacant"}</strong></div><span className="people-count"><Users size={15}/>{zone.people_count}</span></div>
    <div className="zone-stats"><span><Clock3 size={14}/> {formatDuration(zone.occupancy_duration_seconds)}</span><span><Radio size={14}/> {relay?`Relay ${relay.id}`:"Unmapped"}</span></div>
    <div className="appliance-row"><div><span className={`power-icon ${relay?.state==="on"?"on":""}`}><Power size={17}/></span><div><strong>Prototype load</strong><small>{state.esp32.connected?(relay?.state==="on"?"Powered":"Standby"):"Controller offline"}</small></div></div><div className="segmented"><button disabled={busy||!relay||!state.esp32.connected} className={relay?.state==="on"?"selected":""} onClick={()=>setRelay(true)}>On</button><button disabled={busy||!relay||!state.esp32.connected} className={relay?.state==="off"?"selected":""} onClick={()=>setRelay(false)}>Off</button></div></div>
  </article>;
}

export default function Dashboard({state,connected}:{state:SystemState;connected:boolean}) {
  const [emergencyBusy,setEmergencyBusy] = useState(false);
  async function emergency() {
    const message = state.emergency ? "Reset emergency mode and resume detection?" : "Emergency stop will turn every relay off and suspend detection. Continue?";
    if (!confirm(message)) return;
    setEmergencyBusy(true);
    try { await request(state.emergency?"/api/system/reset":"/api/system/emergency-stop",{method:"POST"}); } finally { setEmergencyBusy(false); }
  }
  const energy = state.energy;
  return <div className="page dashboard-page">
    <header className="topbar"><div><p className="eyebrow">ROOM CONTROL / LIVE</p><h1>Energy command center</h1></div><div className="top-actions"><StatusPill tone={state.mode==="automatic"?"good":"warn"}>{state.mode}</StatusPill><StatusPill tone={state.esp32.connected?"good":"danger"}>{state.esp32.connected?"ESP32 online":"ESP32 offline"}</StatusPill><button className={`emergency ${state.emergency?"active":""}`} disabled={emergencyBusy} onClick={emergency}><TriangleAlert size={18}/>{state.emergency?"Reset system":"Emergency stop"}</button></div></header>
    <section className="hero-grid">
      <article className="camera-panel panel">
        <div className="panel-heading"><div><span className={`live-dot ${state.camera.connected?"":"offline"}`}/><div><strong>Camera · Main room</strong><small>{state.camera.connected?"Real-time detection overlay active":"Waiting for a physical camera"}</small></div></div><div className="camera-badges"><span><Gauge size={14}/>{state.camera.fps.toFixed(1)} FPS</span><span><Users size={14}/>{state.detection.people_count} people</span></div></div>
        <div className="feed-wrap">{state.camera.connected?<img src={`${apiBase}/api/camera/stream`} alt="Live room camera with detection and zone overlays"/>:<div className="hardware-offline"><CameraOff/><strong>Camera unavailable</strong><span>{state.camera.error??"Connect a physical webcam to start real-time detection."}</span></div>}<div className="feed-status"><Camera size={14}/>{state.camera.health}</div></div>
      </article>
      <aside className="live-summary panel"><div className="pulse-orb"><Zap size={28}/><span/></div><p>Adaptive load</p><strong>{energy?.current_power_watts.toFixed(0) ?? "0"}<small> W</small></strong><span>Right now</span><div className="load-meter"><i style={{width:`${Math.min(100,(energy?.current_power_watts||0)/.27)}%`}}/></div><dl><div><dt>Occupied zones</dt><dd>{state.zones.filter(z=>z.occupied).length} / {state.zones.length}</dd></div><div><dt>Relays active</dt><dd>{state.relays.filter(r=>r.state==="on").length} / {state.relays.length}</dd></div><div><dt>Inference</dt><dd>{state.detection.inference_ms.toFixed(0)} ms</dd></div></dl><StatusPill tone={connected?"good":"danger"}>{connected?"Telemetry live":"Reconnecting"}</StatusPill></aside>
    </section>
    <section className="section-heading"><div><p className="eyebrow">OCCUPANCY GRID</p><h2>Zone activity</h2></div><span>Automation delay guards active</span></section>
    <section className="zone-grid">{state.zones.length?state.zones.map(zone=><ZoneCard key={zone.id} zone={zone} state={state}/>):[1,2,3].map(id=><div className="zone-card skeleton" key={id}/>)}</section>
    <section className="metrics-grid"><MetricCard label="Current draw" value={`${energy?.current_power_watts.toFixed(0)??0} W`} detail="Across active loads" icon={<Activity/>}/><MetricCard label="Energy saved" value={`${energy?.energy_saved_kwh.toFixed(3)??"0.000"} kWh`} detail="Versus all-on baseline" icon={<Leaf/>}/><MetricCard label="Cost avoided" value={`₹${energy?.cost_saved.toFixed(2)??"0.00"}`} detail="Current reporting period" icon={<Zap/>}/><MetricCard label="Activations" value={`${energy?.relay_activations??0}`} detail="Acknowledged relay starts" icon={<Radio/>}/></section>
  </div>;
}
