export type Relay = { id: number; name: string; state: "on" | "off"; rated_wattage: number; manual_override?: boolean; manual_override_remaining_seconds?: number };
export type ZoneState = { id: number; name: string; colour: string; occupied: boolean; raw_occupied: boolean; people_count: number; occupancy_duration_seconds: number; relay_ids: number[]; auto_control_enabled: boolean };
export type ZoneConfig = { id: number; name: string; colour: string; enabled: boolean; zone_type: "rectangle" | "polygon"; coordinates: {x:number;y:number}[]; relay_ids: number[]; auto_control_enabled: boolean };
export type Energy = { current_power_watts: number; actual_energy_kwh: number; baseline_energy_kwh: number; energy_saved_kwh: number; cost_saved: number; relay_activations: number; zone_usage: {relay_id:number;name:string;runtime_seconds:number;energy_kwh:number}[] };
export type LiveEvent = { id:number; timestamp:string; type:string; message:string; source:string; status:string; details:Record<string,unknown> };
export type EdgeState = {
  connected:boolean; device_id:string; firmware_version:string; model_version:string; model_sha256:string;
  configuration_revision:number; inference_ms:number; inference_fps:number; round_trip_ms:number; motion_score:number;
  last_frame_id:number; completed_frames:number; dropped_keyframes:number; timed_out_frames:number; late_results:number;
  protocol_errors:number; free_heap_bytes:number; free_psram_bytes:number; wifi_rssi:number; last_acknowledgement:string;
};
export type SystemState = {
  timestamp: string; mode: string; emergency: boolean;
  camera: { connected: boolean; running: boolean; health: string; fps: number; error?: string };
  detection: { people_count: number; inference_ms: number; fps: number; model_loaded: boolean; error?: string };
  zones: ZoneState[]; relays: Relay[]; esp32: { connected: boolean }; edge: EdgeState; energy?: Energy;
  alerts: {timestamp:string;level:string;message:string}[];
  events: LiveEvent[];
};

export const emptyState: SystemState = {
  timestamp: new Date().toISOString(), mode: "connecting", emergency: false,
  camera: {connected:false,running:false,health:"connecting",fps:0},
  detection:{people_count:0,inference_ms:0,fps:0,model_loaded:false}, zones:[], relays:[], esp32:{connected:false},
  edge:{connected:false,device_id:"visualec-esp32-s3",firmware_version:"unknown",model_version:"unknown",model_sha256:"",configuration_revision:0,inference_ms:0,inference_fps:0,round_trip_ms:0,motion_score:0,last_frame_id:0,completed_frames:0,dropped_keyframes:0,timed_out_frames:0,late_results:0,protocol_errors:0,free_heap_bytes:0,free_psram_bytes:0,wifi_rssi:0,last_acknowledgement:""}, alerts:[], events:[]
};
