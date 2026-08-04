import { CheckCircle2, CircleAlert, Clock } from "lucide-react";
import StatusPill from "../components/StatusPill";
import { LiveEvent } from "../types";

const failureStates = new Set(["critical", "error", "failed", "offline"]);

export default function Logs({events}:{events:LiveEvent[]}) {
  const rows = events.slice(0, 15);
  return <div className="page">
    <header className="topbar">
      <div><p className="eyebrow">AUDIT / LIVE TELEMETRY</p><h1>System event log</h1></div>
      <StatusPill tone="good">Live · {rows.length}/15</StatusPill>
    </header>
    <section className="panel logs-panel">
      <div className="log-header"><span>Event</span><span>Source</span><span>Status</span><span>Time</span></div>
      {rows.length ? rows.map(event => {
        const failed = failureStates.has(event.status);
        return <div className="log-row" key={event.id}>
          <div>{failed ? <CircleAlert className="danger-color"/> : <CheckCircle2 className="good-color"/>}<div><strong>{event.message}</strong><small>{event.type}</small></div></div>
          <span>{event.source}</span>
          <span className={failed ? "danger-color" : "good-color"}>{event.status}</span>
          <time><Clock size={14}/>{new Date(event.timestamp).toLocaleTimeString()}</time>
        </div>;
      }) : <div className="empty-state">Waiting for live camera, detection, occupancy, relay, and system events.</div>}
    </section>
  </div>;
}
