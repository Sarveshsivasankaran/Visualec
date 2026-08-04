export type Relay = { id: number; name: string; state: "on" | "off"; rated_wattage: number; manual_override?: boolean };
export type ZoneState = { id: number; name: string; colour: string; occupied: boolean; people_count: number; occupancy_duration_seconds: number; relay_ids: number[]; auto_control_enabled: boolean };
export type ZoneConfig = { id: number; name: string; colour: string; enabled: boolean; zone_type: "rectangle" | "polygon"; coordinates: {x:number;y:number}[]; relay_ids: number[]; auto_control_enabled: boolean };
export type Energy = { current_power_watts: number; actual_energy_kwh: number; baseline_energy_kwh: number; energy_saved_kwh: number; cost_saved: number; relay_activations: number; zone_usage: {relay_id:number;name:string;runtime_seconds:number;energy_kwh:number}[] };
export type LiveEvent = { id:number; timestamp:string; type:string; message:string; source:string; status:string; details:Record<string,unknown> };
export type SystemState = {
  timestamp: string; mode: string; emergency: boolean;
  camera: { connected: boolean; running: boolean; health: string; fps: number; error?: string };
  detection: { people_count: number; inference_ms: number; fps: number; model_loaded: boolean; error?: string };
  zones: ZoneState[]; relays: Relay[]; esp32: { connected: boolean }; energy?: Energy;
  alerts: {timestamp:string;level:string;message:string}[];
  events: LiveEvent[];
};

export const emptyState: SystemState = {
  timestamp: new Date().toISOString(), mode: "connecting", emergency: false,
  camera: {connected:false,running:false,health:"connecting",fps:0},
  detection:{people_count:0,inference_ms:0,fps:0,model_loaded:false}, zones:[], relays:[], esp32:{connected:false}, alerts:[], events:[]
};
