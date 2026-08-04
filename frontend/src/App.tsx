import { lazy, Suspense, useState } from "react";
import { Activity, BarChart3, LayoutDashboard, Map, Settings as SettingsIcon, ScrollText, Zap } from "lucide-react";
import Dashboard from "./pages/Dashboard";
import { useVisualecSocket } from "./hooks/useVisualecSocket";

const ZoneEditor = lazy(() => import("./pages/ZoneEditor"));
const Analytics = lazy(() => import("./pages/Analytics"));
const Logs = lazy(() => import("./pages/Logs"));
const Settings = lazy(() => import("./pages/Settings"));

const pages = [
  {id:"dashboard",label:"Live control",icon:LayoutDashboard}, {id:"zones",label:"Zone studio",icon:Map},
  {id:"analytics",label:"Energy analytics",icon:BarChart3}, {id:"logs",label:"Event log",icon:ScrollText},
  {id:"settings",label:"Settings",icon:SettingsIcon},
] as const;

export default function App() {
  const [page, setPage] = useState<(typeof pages)[number]["id"]>("dashboard");
  const {state, connected} = useVisualecSocket();
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span><Zap size={21} fill="currentColor" /></span><div><strong>visualec</strong><small>adaptive grid</small></div></div>
      <nav aria-label="Primary navigation">{pages.map(item => <button key={item.id} className={page===item.id?"active":""} onClick={()=>setPage(item.id)}><item.icon size={19}/><span>{item.label}</span></button>)}</nav>
      <div className="sidebar-foot"><Activity size={17}/><div><strong>{connected?"Live telemetry":"Reconnecting"}</strong><span>{connected?"WebSocket secure":"Backend unavailable"}</span></div></div>
    </aside>
    <main>
      {page === "dashboard" && <Dashboard state={state} connected={connected}/>} 
      <Suspense fallback={<div className="page"><div className="empty-state">Loading workspace…</div></div>}>
        {page === "zones" ? <ZoneEditor cameraConnected={state.camera.connected} /> : null}
        {page === "analytics" ? <Analytics energy={state.energy}/> : null}
        {page === "logs" ? <Logs events={state.events ?? []}/> : null}
        {page === "settings" ? <Settings state={state}/> : null}
      </Suspense>
    </main>
  </div>;
}
