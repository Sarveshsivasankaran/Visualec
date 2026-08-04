const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
export const apiBase = API;

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {headers:{"Content-Type":"application/json", ...init?.headers}, ...init});
  if (!response.ok) throw new Error((await response.json().catch(()=>null))?.detail || `Request failed (${response.status})`);
  return response.status === 204 ? (undefined as T) : response.json();
}
