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

export interface ChatPlan {
  steps: string[];
  rationale: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  /** Accumulated `<think>…</think>` content from the response stream.  Rendered
   *  in a separate collapsible card so the user can see the model's reasoning
   *  without it polluting the answer body. */
  thinking?: string;
  /** Plan event emitted by the LangGraph planner before tool execution. */
  plan?: ChatPlan;
}

export interface ToolCall {
  tool: string;
  input?: Record<string, unknown>;
  /** Tool result.  Sent as JSON over SSE — may arrive deserialised as
   *  object/array (most tools) or as a plain string (errors, weather, etc.).
   *  Consumers must handle both.  ToolCallCard normalises before render. */
  output?: unknown;
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

  viewMode: "skyChart" | "earthMap";
  setViewMode: (m: "skyChart" | "earthMap") => void;

  mountStatus: MountStatus | null;
  setMountStatus: (s: MountStatus) => void;

  messages: ChatMessage[];
  addMessage: (m: ChatMessage) => void;
  updateLastMessage: (patch: Partial<ChatMessage>) => void;
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

  // ── Code Inspector ────────────────────────────────────────────────────────
  /** Which tab is active in the ObjectView panel.  Lifted to the store so
   *  external triggers (e.g. clicking "OPEN IN EDITOR" on a tool card) can
   *  flip the tab from outside the ObjectView component. */
  objectViewTab: "object" | "camera" | "code";
  setObjectViewTab: (t: "object" | "camera" | "code") => void;

  /** Current source in the Code Inspector.  When non-empty AND
   *  `editorAttached` is true, every chat turn carries it as a system
   *  context so the model can see "the code the user has open". */
  editorCode: string;
  editorLanguage: "python" | "text";
  editorAttached: boolean;
  setEditorCode: (c: string) => void;
  setEditorAttached: (v: boolean) => void;
  /** One-shot helper used by ToolCallCard: load code into the editor,
   *  switch ObjectView to the Code tab, and mark it attached so the next
   *  user message includes it as context. */
  openCodeInEditor: (code: string) => void;

  // ── User profiles ────────────────────────────────────────────────────────
  /** Currently active user (mirrors backend `.active` file).  Null until
   *  `/api/users/current` has been fetched. */
  currentUser: string | null;
  /** All known user profiles fetched from `/api/users`. */
  knownUsers: string[];
  /** LLM-related preferences persisted with the user profile. */
  llmPrefs: { backend: string; model_hint: string; thinking: boolean; language: string };
  /** Voice-related preferences persisted with the user profile. */
  voicePrefs: { voice: string; speed: number; enabled: boolean };
  setLlmPrefs: (p: Partial<{ backend: string; model_hint: string; thinking: boolean; language: string }>) => void;
  setVoicePrefs: (p: Partial<{ voice: string; speed: number; enabled: boolean }>) => void;
  setCurrentUser: (u: string | null) => void;
  setKnownUsers: (u: string[]) => void;
  /** Replace the whole settings block from a fetched profile.  Called on
   *  mount and after switching users. */
  applyProfile: (p: {
    appearance?: { fontSize?: FontSize; themeAccent?: ThemeAccent };
    session?: { observer?: Observer };
    llm?: { backend?: string; model_hint?: string; thinking?: boolean; language?: string };
    voice?: { voice?: string; speed?: number; enabled?: boolean };
  }) => void;
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
  updateLastMessage: (patch) =>
    set((state) => {
      const msgs = [...state.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant") {
        msgs[msgs.length - 1] = { ...last, ...patch };
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

  objectViewTab: "object",
  setObjectViewTab: (t) => set({ objectViewTab: t }),

  editorCode: "",
  editorLanguage: "python",
  editorAttached: false,
  setEditorCode: (c) => set({ editorCode: c }),
  setEditorAttached: (v) => set({ editorAttached: v }),
  openCodeInEditor: (code) => set({
    editorCode: code,
    editorLanguage: "python",
    editorAttached: true,
    objectViewTab: "code",
  }),

  currentUser: null,
  knownUsers: [],
  llmPrefs: { backend: "ik_llama", model_hint: "4b", thinking: true, language: "es" },
  voicePrefs: { voice: "ef_dora", speed: 0.9, enabled: false },
  setLlmPrefs: (p) => set((s) => ({ llmPrefs: { ...s.llmPrefs, ...p } })),
  setVoicePrefs: (p) => set((s) => ({ voicePrefs: { ...s.voicePrefs, ...p } })),
  setCurrentUser: (u) => set({ currentUser: u }),
  setKnownUsers: (u) => set({ knownUsers: u }),
  applyProfile: (p) => set((s) => ({
    fontSize: (p.appearance?.fontSize as FontSize) ?? s.fontSize,
    themeAccent: (p.appearance?.themeAccent as ThemeAccent) ?? s.themeAccent,
    observer: p.session?.observer ?? s.observer,
    llmPrefs: { ...s.llmPrefs, ...(p.llm ?? {}) },
    voicePrefs: { ...s.voicePrefs, ...(p.voice ?? {}) },
  })),
}));
