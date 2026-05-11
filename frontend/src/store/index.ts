import { create } from "zustand";

export interface SkyObject {
  name: string;
  catalog_id?: string;
  object_type: string;
  ra_h?: number;
  dec_deg?: number;
  alt_deg?: number;
  az_deg?: number;
  magnitude?: number;
  angular_size_arcmin?: number;
  note?: string;
}

export interface MoonInfo {
  phase: number;
  illumination_pct: number;
  phase_name: string;
  alt_deg?: number;
  interference: boolean;
  interference_note: string;
}

export interface Observer {
  lat: number;
  lng: number;
  alt_m: number;
  name: string;
}

export interface MountStatus {
  ra_h: number;
  dec_deg: number;
  alt_deg: number;
  az_deg: number;
  tracking: boolean;
  tracking_rate?: string;
  target_name?: string;
  slewing: boolean;
  parked: boolean;
  log: string[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  sources?: WebSource[];
}

export interface ToolCall {
  tool: string;
  input?: Record<string, unknown>;
  output?: string;
}

export interface SelectedTarget {
  name: string;
  ra_h?: number;
  dec_deg?: number;
  lat?: number;
  lng?: number;
  norad_id?: number;
  type: "dso" | "planet" | "satellite";
}

/** Live selection snapshot from the embedded Stellarium engine.  Pushed to
 *  the parent via postMessage whenever the engine's selection changes (or
 *  every ~2 s while a selection is held, so Az/Alt track sky motion). */
export interface StelSelection {
  names: string[];
  ra_h: number;
  dec_deg: number;
  az_deg: number | null;
  alt_deg: number | null;
  vmag: number | null;
  /** AU for solar-system bodies, parsecs otherwise.  null if unknown. */
  distance: number | null;
  /** 0–1 illuminated fraction; null for non-Moon/planet objects. */
  phase: number | null;
  utc_mjd: number;
  visibility?: Array<{ rise: number; set: number }>;
}

export interface InfoCard {
  name: string;
  catalog_id?: string;
  object_type: string;
  magnitude?: number;
  angular_size_arcmin?: number;
  alt_deg?: number;
  az_deg?: number;
  note?: string;
  description?: string;
  image_url?: string;
}

export interface WebSource {
  title: string;
  url: string;
  snippet?: string;
}

export interface YouTubeVideo {
  video_id: string;
  title: string;
  embed_url: string;
  url: string;
}

export interface CustomWidget {
  id: string;
  name: string;
  description: string;
  created_at: number;
}

export type FontSize = "xs" | "sm" | "md" | "lg";
export type ThemeAccent = "red" | "blue" | "green";

interface AppState {
  fontSize: FontSize;
  setFontSize: (s: FontSize) => void;
  themeAccent: ThemeAccent;
  setThemeAccent: (a: ThemeAccent) => void;

  observer: Observer;
  setObserver: (o: Observer) => void;

  skyObjects: SkyObject[];
  setSkyObjects: (objs: SkyObject[]) => void;

  moonInfo: MoonInfo | null;
  setMoonInfo: (m: MoonInfo) => void;

  selectedTarget: SelectedTarget | null;
  setSelectedTarget: (t: SelectedTarget | null) => void;

  viewMode: "skyChart" | "earthMap" | "youtube";
  setViewMode: (m: "skyChart" | "earthMap" | "youtube") => void;

  mountStatus: MountStatus | null;
  setMountStatus: (s: MountStatus) => void;

  messages: ChatMessage[];
  addMessage: (m: ChatMessage) => void;
  updateLastMessage: (content: string, toolCalls?: ToolCall[], sources?: WebSource[]) => void;
  clearMessages: () => void;

  ollamaOnline: boolean;
  setOllamaOnline: (v: boolean) => void;

  satelliteCategories: Array<{ id: number; name: string }>;
  setSatelliteCategories: (cats: Array<{ id: number; name: string }>) => void;

  groundTrack: Array<{ lat: number; lng: number }>;
  setGroundTrack: (t: Array<{ lat: number; lng: number }>) => void;

  infoCard: InfoCard | null;
  setInfoCard: (c: InfoCard | null) => void;

  stelSelection: StelSelection | null;
  setStelSelection: (s: StelSelection | null) => void;

  youtubeVideo: YouTubeVideo | null;
  setYoutubeVideo: (v: YouTubeVideo | null) => void;

  customWidgets: CustomWidget[];
  setCustomWidgets: (w: CustomWidget[]) => void;
  addCustomWidget: (w: CustomWidget) => void;
  removeCustomWidget: (id: string) => void;

  pendingSources: WebSource[];
  setPendingSources: (s: WebSource[]) => void;
}

export const useAppStore = create<AppState>((set) => ({
  fontSize: "md",
  setFontSize: (s) => set({ fontSize: s }),
  themeAccent: "red",
  setThemeAccent: (a) => set({ themeAccent: a }),

  observer: { lat: 41.548, lng: 2.105, alt_m: 190, name: "Sabadell" },
  setObserver: (o) => set({ observer: o }),

  skyObjects: [],
  setSkyObjects: (objs) => set({ skyObjects: objs }),

  moonInfo: null,
  setMoonInfo: (m) => set({ moonInfo: m }),

  selectedTarget: null,
  setSelectedTarget: (t) => set((state) => ({
    selectedTarget: t,
    // Clear ground track when switching to a non-satellite target
    groundTrack: (t && t.type !== "satellite") ? [] : state.groundTrack,
  })),

  viewMode: "skyChart",
  setViewMode: (m) => set({ viewMode: m }),

  mountStatus: null,
  setMountStatus: (s) => set({ mountStatus: s }),

  messages: [],
  addMessage: (m) => set((state) => ({ messages: [...state.messages, m] })),
  clearMessages: () => set({ messages: [] }),
  updateLastMessage: (content, toolCalls, sources) =>
    set((state) => {
      const msgs = [...state.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant") {
        msgs[msgs.length - 1] = {
          ...last,
          content,
          toolCalls: toolCalls ?? last.toolCalls,
          sources: sources ?? last.sources,
        };
      }
      return { messages: msgs };
    }),

  ollamaOnline: false,
  setOllamaOnline: (v) => set({ ollamaOnline: v }),

  satelliteCategories: [],
  setSatelliteCategories: (cats) => set({ satelliteCategories: cats }),

  groundTrack: [],
  setGroundTrack: (t) => set({ groundTrack: t }),

  infoCard: null,
  setInfoCard: (c) => set({ infoCard: c }),

  stelSelection: null,
  setStelSelection: (s) => set({ stelSelection: s }),

  youtubeVideo: null,
  setYoutubeVideo: (v) => set({ youtubeVideo: v }),

  customWidgets: [],
  setCustomWidgets: (w) => set({ customWidgets: w }),
  addCustomWidget: (w) => set((s) => ({ customWidgets: [...s.customWidgets, w] })),
  removeCustomWidget: (id) => set((s) => ({ customWidgets: s.customWidgets.filter((w) => w.id !== id) })),

  pendingSources: [],
  setPendingSources: (s) => set({ pendingSources: s }),
}));
