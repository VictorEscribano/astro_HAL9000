import { useEffect, useState, useRef, lazy, Suspense, useCallback } from "react";
import { useAppStore } from "./store";
import { api } from "./api";
import StellariumView from "./components/SkyChart/StellariumView";
import StatusBar from "./components/StatusBar/StatusBar";
import AIOrb from "./components/AIOrb/AIOrb";
import Chat from "./components/Chat/Chat";
import ObjectView from "./components/ObjectView/ObjectView";
import ObjectSelector from "./components/ObjectSelector/ObjectSelector";
import BottomBar from "./components/BottomBar/BottomBar";
import PanelFrame from "./components/ui/PanelFrame";

const EarthMap = lazy(() => import("./components/Map/EarthMap"));

// Split constraints (percentages)
const COL_MIN = 30; const COL_MAX = 80;
const ROW_MIN = 28; const ROW_MAX = 78;
const ORB_MIN = 16; const ORB_MAX = 52;

type DragKind = "col" | "row" | "orb";


/** Thin interactive bar — drag to resize adjacent panels. */
function SplitHandle({
  direction, position, onStart,
}: { direction: "col" | "row"; position: string; onStart: (e: React.MouseEvent) => void }) {
  const isCol = direction === "col";
  return (
    <div
      onMouseDown={onStart}
      style={{
        position: "absolute",
        zIndex: 9999,
        cursor: isCol ? "col-resize" : "row-resize",
        ...(isCol
          ? { top: 0, bottom: 0, left: position, width: "8px", transform: "translateX(-50%)" }
          : { left: 0, right: 0, top: position, height: "8px", transform: "translateY(-50%)" }),
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      {/* Visual grip dot */}
      <div style={{
        background: "rgba(255,255,255,0.12)",
        borderRadius: "4px",
        ...(isCol ? { width: "3px", height: "36px" } : { height: "3px", width: "36px" }),
      }} />
    </div>
  );
}

export default function App() {
  const {
    setSkyObjects, setMoonInfo, setOllamaOnline, setSatelliteCategories,
    viewMode, setViewMode, observer, setObserver,
  } = useAppStore();


  // Panel split state — percentages
  const [colSplit, setColSplit] = useState(64);
  const [rowSplit, setRowSplit] = useState(58);
  const [orbSplit, setOrbSplit] = useState(30);

  const gridRef  = useRef<HTMLDivElement>(null);
  const aiRowRef = useRef<HTMLDivElement>(null);
  const dragRef  = useRef<DragKind | null>(null);

  const startDrag = useCallback((kind: DragKind, e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = kind;
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const kind = dragRef.current;
      if (!kind) return;
      if (kind === "col" && gridRef.current) {
        const r = gridRef.current.getBoundingClientRect();
        const pct = ((e.clientX - r.left) / r.width) * 100;
        setColSplit(Math.max(COL_MIN, Math.min(COL_MAX, Math.round(pct))));
      } else if (kind === "row" && gridRef.current) {
        const r = gridRef.current.getBoundingClientRect();
        const pct = ((e.clientY - r.top) / r.height) * 100;
        setRowSplit(Math.max(ROW_MIN, Math.min(ROW_MAX, Math.round(pct))));
      } else if (kind === "orb" && aiRowRef.current) {
        const r = aiRowRef.current.getBoundingClientRect();
        const pct = ((e.clientX - r.left) / r.width) * 100;
        setOrbSplit(Math.max(ORB_MIN, Math.min(ORB_MAX, Math.round(pct))));
      }
    };
    const onUp = () => { dragRef.current = null; };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
  }, []);

  // GPS at startup
  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => setObserver({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        alt_m: pos.coords.altitude ?? observer.alt_m,
        name: observer.name,
      }),
      () => {},
      { timeout: 8000, enableHighAccuracy: false },
    );
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Bootstrap
  useEffect(() => {
    const coords = { lat: observer.lat, lng: observer.lng, alt_m: observer.alt_m };
    api.skyObjectsTonight(coords).then(setSkyObjects).catch(() => {});
    api.moonInfo(coords).then(setMoonInfo).catch(() => {});
    api.satelliteCategories().then(setSatelliteCategories).catch(() => {});
    api.chatHealth().then((h: { ok: boolean }) => setOllamaOnline(h.ok)).catch(() => setOllamaOnline(false));
    const id = setInterval(() => api.skyObjectsTonight(coords).then(setSkyObjects).catch(() => {}), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [observer.lat, observer.lng]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load the active user's persisted profile once on mount — overrides the
  // store defaults (font size, accent, observer, llm/voice prefs) with
  // whatever the user saved last time.
  useEffect(() => {
    (async () => {
      try {
        const list = await api.usersList();
        useAppStore.getState().setKnownUsers(list.users ?? []);
        useAppStore.getState().setCurrentUser(list.active ?? null);
        const profile = await api.userCurrent();
        useAppStore.getState().applyProfile(profile);
      } catch { /* backend may not be ready on first paint — silent retry-free */ }
    })();
  }, []);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-bg text-text">
      <StatusBar />

      {/*
        2×2 resizable grid.
        All direct children MUST have minHeight:0 + overflow:hidden to prevent
        the grid rows from expanding beyond their fr allocation (CSS Grid auto-min).
      */}
      <div
        ref={gridRef}
        className="flex-1 min-h-0 relative"
        style={{
          display: "grid",
          gridTemplateColumns: `${colSplit}fr ${100 - colSplit}fr`,
          gridTemplateRows:    `${rowSplit}fr ${100 - rowSplit}fr`,
          gap: "1px",
          background: "rgba(255,255,255,0.03)",
        }}
      >
        {/* ── Cell 1: SKY / EARTH viewport ──────────────────────────────── */}
        <div style={{ minHeight: 0, minWidth: 0, overflow: "hidden", position: "relative" }}>
          <PanelFrame accent="red" className="w-full h-full relative overflow-hidden">
            {/* SKY / EARTH toggle */}
            <div className="absolute top-3 left-10 flex gap-px" style={{ zIndex: 9999 }}>
              {(["skyChart", "earthMap"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setViewMode(m)}
                  className={`px-3 py-1 text-[calc(9px*var(--fs))] font-mono uppercase tracking-widest transition-colors rounded-sm
                    ${viewMode === m
                      ? "bg-accent-red text-bg font-bold"
                      : "bg-panel/90 text-dim hover:text-text border border-white/[0.08]"
                    }`}
                >
                  {m === "skyChart" ? "SKY" : "EARTH"}
                </button>
              ))}
            </div>

            <div className="w-full h-full">
              {viewMode === "skyChart" ? (
                <StellariumView />
              ) : (
                <Suspense fallback={
                  <div className="flex items-center justify-center h-full text-dim text-[calc(10px*var(--fs))] font-mono">
                    LOADING MAP…
                  </div>
                }>
                  <EarthMap />
                </Suspense>
              )}
            </div>
          </PanelFrame>
        </div>

        {/* ── Cell 2: Object view ───────────────────────────────────────── */}
        <div style={{ minHeight: 0, minWidth: 0, overflow: "hidden" }}>
          <ObjectView />
        </div>

        {/* ── Cell 3: AI Orb + Chat (internally split) ─────────────────── */}
        <div
          ref={aiRowRef}
          style={{
            minHeight: 0, minWidth: 0, overflow: "hidden",
            display: "flex", gap: "1px", position: "relative",
          }}
        >
          {/* AI Orb — width is orbSplit% of this cell */}
          <div style={{ width: `${orbSplit}%`, minWidth: "120px", flexShrink: 0, overflow: "hidden" }}>
            <PanelFrame accent="red" className="h-full">
              <AIOrb />
            </PanelFrame>
          </div>

          {/* Orb ↔ Chat drag handle */}
          <div
            onMouseDown={(e) => startDrag("orb", e)}
            style={{
              position: "absolute", top: 0, bottom: 0,
              left: `${orbSplit}%`, width: "8px", transform: "translateX(-50%)",
              cursor: "col-resize", zIndex: 1000,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            <div style={{ width: "3px", height: "28px", background: "rgba(255,255,255,0.12)", borderRadius: "2px" }} />
          </div>

          {/* AI Chat */}
          <div style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
            <Chat />
          </div>
        </div>

        {/* ── Cell 4: Object selector ───────────────────────────────────── */}
        <div style={{ minHeight: 0, minWidth: 0, overflow: "hidden" }}>
          <ObjectSelector />
        </div>

        {/* ── Column split handle ───────────────────────────────────────── */}
        <SplitHandle
          direction="col"
          position={`${colSplit}%`}
          onStart={(e) => startDrag("col", e)}
        />

        {/* ── Row split handle ──────────────────────────────────────────── */}
        <SplitHandle
          direction="row"
          position={`${rowSplit}%`}
          onStart={(e) => startDrag("row", e)}
        />
      </div>

      <BottomBar />
    </div>
  );
}
