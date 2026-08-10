import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Check, MousePointer2, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import { apiBase, request } from "../api";
import { ZoneConfig } from "../types";

const palette = ["#22d3ee", "#34d399", "#f59e0b", "#a78bfa", "#fb7185"];
const handles = ["n", "ne", "e", "se", "s", "sw", "w", "nw"] as const;
const minimumZoneSize = 0.04;

type ResizeHandle = (typeof handles)[number];
type Interaction = ResizeHandle | "move";
type Point = { x: number; y: number };
type Bounds = { left: number; top: number; right: number; bottom: number };
type DragState = {
  id: number;
  interaction: Interaction;
  pointerId: number;
  startX: number;
  startY: number;
  coordinates: Point[];
  bounds: Bounds;
};

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, value));
}

function getBounds(coordinates: Point[]): Bounds {
  const xs = coordinates.map(point => point.x);
  const ys = coordinates.map(point => point.y);
  return {
    left: Math.min(...xs),
    top: Math.min(...ys),
    right: Math.max(...xs),
    bottom: Math.max(...ys),
  };
}

function moveCoordinates(coordinates: Point[], bounds: Bounds, dx: number, dy: number) {
  const width = bounds.right - bounds.left;
  const height = bounds.bottom - bounds.top;
  const left = clamp(bounds.left + dx, 0, 1 - width);
  const top = clamp(bounds.top + dy, 0, 1 - height);
  const offsetX = left - bounds.left;
  const offsetY = top - bounds.top;
  return coordinates.map(point => ({ x: point.x + offsetX, y: point.y + offsetY }));
}

function resizeCoordinates(coordinates: Point[], bounds: Bounds, handle: ResizeHandle, dx: number, dy: number) {
  let { left, top, right, bottom } = bounds;
  if (handle.includes("w")) left = clamp(left + dx, 0, right - minimumZoneSize);
  if (handle.includes("e")) right = clamp(right + dx, left + minimumZoneSize, 1);
  if (handle.includes("n")) top = clamp(top + dy, 0, bottom - minimumZoneSize);
  if (handle.includes("s")) bottom = clamp(bottom + dy, top + minimumZoneSize, 1);

  const oldWidth = Math.max(bounds.right - bounds.left, Number.EPSILON);
  const oldHeight = Math.max(bounds.bottom - bounds.top, Number.EPSILON);
  const width = right - left;
  const height = bottom - top;
  return coordinates.map(point => ({
    x: left + ((point.x - bounds.left) / oldWidth) * width,
    y: top + ((point.y - bounds.top) / oldHeight) * height,
  }));
}

export default function ZoneEditor({ cameraConnected }: { cameraConnected: boolean }) {
  const [zones, setZones] = useState<ZoneConfig[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const drag = useRef<DragState | null>(null);

  useEffect(() => {
    request<ZoneConfig[]>("/api/zones")
      .then(value => {
        setZones(value);
        setSelected(value[0]?.id ?? null);
      })
      .catch(() => undefined);
  }, []);

  const active = useMemo(() => zones.find(zone => zone.id === selected), [zones, selected]);

  function startInteraction(event: PointerEvent<HTMLElement>, id: number, interaction: Interaction) {
    const zone = zones.find(item => item.id === id);
    if (!zone || !canvasRef.current) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    const coordinates = zone.coordinates.map(point => ({ ...point }));
    drag.current = {
      id,
      interaction,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      coordinates,
      bounds: getBounds(coordinates),
    };
    setSelected(id);
  }

  function continueInteraction(event: PointerEvent<HTMLElement>) {
    const current = drag.current;
    const canvas = canvasRef.current;
    if (!current || !canvas || current.pointerId !== event.pointerId) return;
    const dx = (event.clientX - current.startX) / canvas.clientWidth;
    const dy = (event.clientY - current.startY) / canvas.clientHeight;
    const coordinates = current.interaction === "move"
      ? moveCoordinates(current.coordinates, current.bounds, dx, dy)
      : resizeCoordinates(current.coordinates, current.bounds, current.interaction, dx, dy);
    setZones(value => value.map(zone => zone.id === current.id ? { ...zone, coordinates } : zone));
  }

  function endInteraction(event: PointerEvent<HTMLElement>) {
    if (drag.current?.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    drag.current = null;
  }

  function moveWithKeyboard(event: KeyboardEvent<HTMLElement>, zone: ZoneConfig) {
    const step = event.shiftKey ? 0.025 : 0.01;
    const movement: Record<string, Point> = {
      ArrowLeft: { x: -step, y: 0 },
      ArrowRight: { x: step, y: 0 },
      ArrowUp: { x: 0, y: -step },
      ArrowDown: { x: 0, y: step },
    };
    const delta = movement[event.key];
    if (!delta) return;
    event.preventDefault();
    setSelected(zone.id);
    setZones(value => value.map(item => item.id === zone.id
      ? { ...item, coordinates: moveCoordinates(item.coordinates, getBounds(item.coordinates), delta.x, delta.y) }
      : item));
  }

  async function save() {
    setSaving(true);
    try {
      for (const zone of zones) {
        await request(`/api/zones/${zone.id}`, { method: "PUT", body: JSON.stringify(zone) });
      }
    } finally {
      setSaving(false);
    }
  }

  async function reset() {
    if (!confirm("Restore the three default zones? Custom zones will be removed.")) return;
    const defaults = await request<ZoneConfig[]>("/api/zones/reset-default", { method: "POST" });
    setZones(defaults);
    setSelected(defaults[0]?.id ?? null);
  }

  function add() {
    const next = Math.max(0, ...zones.map(zone => zone.id)) + 1;
    const zone: ZoneConfig = {
      id: next,
      name: `Zone ${next}`,
      colour: palette[zones.length % palette.length],
      enabled: true,
      zone_type: "rectangle",
      coordinates: [{ x: .35, y: .3 }, { x: .65, y: .3 }, { x: .65, y: .75 }, { x: .35, y: .75 }],
      relay_ids: [],
      auto_control_enabled: true,
    };
    request<{ id: number }>("/api/zones", { method: "POST", body: JSON.stringify({ ...zone, id: undefined }) })
      .then(saved => {
        zone.id = saved.id;
        setZones(value => [...value, zone]);
        setSelected(zone.id);
      });
  }

  async function remove() {
    if (!active || !confirm(`Delete ${active.name}?`)) return;
    await request(`/api/zones/${active.id}`, { method: "DELETE" });
    setZones(value => value.filter(zone => zone.id !== active.id));
    setSelected(null);
  }

  function patch(values: Partial<ZoneConfig>) {
    setZones(value => value.map(zone => zone.id === selected ? { ...zone, ...values } : zone));
  }

  return <div className="page">
    <header className="topbar">
      <div><p className="eyebrow">SPATIAL INTELLIGENCE</p><h1>Zone studio</h1></div>
      <div className="top-actions">
        <button className="button ghost" onClick={reset}><RotateCcw size={17} />Reset</button>
        <button className="button primary" disabled={saving} onClick={save}><Save size={17} />{saving ? "Saving…" : "Save layout"}</button>
      </div>
    </header>
    <div className="editor-layout">
      <section className="editor-canvas panel">
        <div className="panel-heading">
          <div><MousePointer2 size={18} /><div><strong>Move and resize zones</strong><small>Drag inside to move · drag borders or corners to resize</small></div></div>
          <button className="icon-button" onClick={add} aria-label="Add zone"><Plus /></button>
        </div>
        <div className="canvas-feed" ref={canvasRef}>
          {cameraConnected
            ? <img src={`${apiBase}/api/camera/stream`} alt="Camera preview for zone editing" draggable={false} />
            : <div className="hardware-offline"><strong>Physical camera required</strong><span>Zone editing resumes when the live camera reconnects.</span></div>}
          {cameraConnected ? zones.map(zone => {
            const bounds = getBounds(zone.coordinates);
            const isSelected = selected === zone.id;
            return <div
              key={zone.id}
              role="button"
              tabIndex={0}
              aria-label={`Move ${zone.name}. Use arrow keys for precise positioning.`}
              aria-pressed={isSelected}
              className={`zone-shape ${isSelected ? "selected" : ""}`}
              onPointerDown={event => startInteraction(event, zone.id, "move")}
              onPointerMove={continueInteraction}
              onPointerUp={endInteraction}
              onPointerCancel={endInteraction}
              onKeyDown={event => moveWithKeyboard(event, zone)}
              style={{
                left: `${bounds.left * 100}%`,
                top: `${bounds.top * 100}%`,
                width: `${(bounds.right - bounds.left) * 100}%`,
                height: `${(bounds.bottom - bounds.top) * 100}%`,
                borderColor: zone.colour,
                background: `${zone.colour}22`,
              }}
            >
              <span className="zone-shape-label" style={{ background: zone.colour }}>{zone.name}</span>
              {handles.map(handle => <button
                key={handle}
                type="button"
                className="zone-resize-handle"
                data-handle={handle}
                aria-label={`Resize ${zone.name} from ${handle} border`}
                style={{ color: zone.colour }}
                onPointerDown={event => startInteraction(event, zone.id, handle)}
                onPointerMove={continueInteraction}
                onPointerUp={endInteraction}
                onPointerCancel={endInteraction}
              />)}
            </div>;
          }) : null}
        </div>
      </section>
      <aside className="inspector panel">
        <div className="panel-heading"><div><strong>Zone inspector</strong><small>{active ? `Editing zone ${active.id}` : "Select a zone"}</small></div></div>
        {active ? <div className="form-stack">
          <label>Name<input value={active.name} onChange={event => patch({ name: event.target.value })} /></label>
          <label>Geometry<select value={active.zone_type} onChange={event => patch({ zone_type: event.target.value as ZoneConfig["zone_type"] })}><option value="rectangle">Rectangle</option><option value="polygon">Polygon</option></select></label>
          <fieldset><legend>Accent colour</legend><div className="palette">{palette.map(colour => <button key={colour} aria-label={`Use ${colour}`} onClick={() => patch({ colour })} style={{ background: colour }}>{active.colour === colour && <Check />}</button>)}</div></fieldset>
          <label>Relay IDs<input value={active.relay_ids.join(", ")} onChange={event => patch({ relay_ids: event.target.value.split(",").map(Number).filter(Boolean) })} /></label>
          <label className="toggle-row"><span><strong>Automatic control</strong><small>Occupancy drives mapped relays</small></span><input type="checkbox" checked={active.auto_control_enabled} onChange={event => patch({ auto_control_enabled: event.target.checked })} /></label>
          <label className="toggle-row"><span><strong>Zone enabled</strong><small>Include in person assignment</small></span><input type="checkbox" checked={active.enabled} onChange={event => patch({ enabled: event.target.checked })} /></label>
          <button className="danger-text" onClick={remove}><Trash2 size={16} />Delete zone</button>
        </div> : <div className="empty-state">Select a zone on the preview to edit its settings.</div>}
      </aside>
    </div>
  </div>;
}
