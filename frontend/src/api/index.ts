const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const API_BASE_URL = BASE;

export async function fetchJson(path: string) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function postJson(path: string, body: unknown) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function qs(params?: Record<string, unknown>) {
  if (!params) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null) p.set(k, String(v));
  }
  const s = p.toString();
  return s ? "?" + s : "";
}

interface ObsCoords { lat?: number; lng?: number; alt_m?: number; [key: string]: unknown }

export const api = {
  skyObjectsTonight: (coords?: ObsCoords, extra?: Record<string, unknown>) =>
    fetchJson(`/api/sky/objects-tonight${qs({ ...coords, ...extra })}`),

  objectPosition: (name: string, coords?: ObsCoords) =>
    fetchJson(`/api/sky/object/${encodeURIComponent(name)}${qs(coords)}`),

  objectTrack: (name: string, hours = 4, coords?: ObsCoords) =>
    fetchJson(`/api/sky/track/${encodeURIComponent(name)}${qs({ hours, ...coords })}`),

  moonInfo: (coords?: ObsCoords) =>
    fetchJson(`/api/sky/moon${qs(coords)}`),

  observer: () => fetchJson("/api/sky/observer"),

  satelliteCategories: () => fetchJson("/api/satellites/categories"),
  satellitesAbove:    (catId: number) => fetchJson(`/api/satellites/above/${catId}`),
  satellitePosition:  (noradId: number) => fetchJson(`/api/satellites/position/${noradId}`),
  satellitePasses:    (noradId: number, days = 1) => fetchJson(`/api/satellites/passes/${noradId}?days=${days}`),
  groundTrack:        (noradId: number) => fetchJson(`/api/satellites/track/${noradId}`),
  satelliteFootprint: (noradId: number) => fetchJson(`/api/satellites/footprint/${noradId}`),

  mountStatus: () => fetchJson("/api/mount/status"),
  mountSlew:   (body: unknown) => postJson("/api/mount/slew", body),
  mountStop:   () => postJson("/api/mount/stop", {}),
  mountPark:   () => postJson("/api/mount/park", {}),
  mountLog:    () => fetchJson("/api/mount/log"),

  // Catalog search (all DSOs + named stars)
  catalogSearch: (q: string, type = "all", limit = 50, offset = 0) =>
    fetchJson(`/api/sky/catalog${qs({ q, type, limit, offset })}`),

  // Stars for sky chart rendering
  starsTonight: (max_mag = 5.5, coords?: ObsCoords) =>
    fetchJson(`/api/sky/stars-tonight${qs({ max_mag, ...coords })}`),

  // Satellite catalog (full Celestrak)
  satelliteCatalog: (q: string, limit = 50, offset = 0, obj_type?: string) =>
    fetchJson(`/api/satellites/catalog${qs({ q, limit, offset, obj_type })}`),

  chatHealth: () => fetchJson("/api/chat/health"),
  weather:    (coords?: ObsCoords) => fetchJson(`/api/sky/weather${qs(coords)}`),

  // User profiles
  usersList:    () => fetchJson("/api/users"),
  userCurrent:  () => fetchJson("/api/users/current"),
  userCreate:   (username: string) => postJson("/api/users", { username }),
  userUpdate:   (username: string, settings: unknown) =>
    fetch(`${BASE}/api/users/${encodeURIComponent(username)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return r.json();
    }),
  userDelete:   (username: string) =>
    fetch(`${BASE}/api/users/${encodeURIComponent(username)}`, { method: "DELETE" })
      .then((r) => { if (!r.ok) throw new Error(`${r.status} ${r.statusText}`); return r.json(); }),
  userSetActive: (username: string) => postJson("/api/users/active", { username }),
};

export const CHAT_STREAM_URL = `${BASE}/api/chat/stream`;
