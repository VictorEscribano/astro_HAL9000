import { useEffect, useRef, useState } from "react";
import { useAppStore, type StelSelection } from "../../store";
import PanelFrame from "../ui/PanelFrame";
import CodeInspector from "../CodeInspector/CodeInspector";

// Object image lookup — reliable public domain / NASA/ESA images
const OBJECT_IMAGES: Record<string, string> = {
  "M42":   "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f3/Orion_Nebula_-_Hubble_2006_mosaic_18000.jpg/400px-Orion_Nebula_-_Hubble_2006_mosaic_18000.jpg",
  "M31":   "https://upload.wikimedia.org/wikipedia/commons/thumb/9/98/Andromeda_Galaxy_%28with_h-alpha%29.jpg/400px-Andromeda_Galaxy_%28with_h-alpha%29.jpg",
  "M45":   "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Pleiades_large.jpg/400px-Pleiades_large.jpg",
  "M13":   "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/Messier_13_Hubble_WikiSky.jpg/400px-Messier_13_Hubble_WikiSky.jpg",
  "M51":   "https://upload.wikimedia.org/wikipedia/commons/thumb/d/db/Hs-2005-12-a-large_web.jpg/400px-Hs-2005-12-a-large_web.jpg",
  "M57":   "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d0/Ring_Nebula.jpg/400px-Ring_Nebula.jpg",
  "Jupiter": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2b/Jupiter_and_its_shrunken_Great_Red_Spot.jpg/400px-Jupiter_and_its_shrunken_Great_Red_Spot.jpg",
  "Saturn":  "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c7/Saturn_during_Equinox.jpg/400px-Saturn_during_Equinox.jpg",
  "Mars":    "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/OSIRIS_Mars_true_color.jpg/400px-OSIRIS_Mars_true_color.jpg",
  "Moon":    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e1/FullMoon2010.jpg/400px-FullMoon2010.jpg",
  "Venus":   "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Venus_from_Mariner_10.jpg/400px-Venus_from_Mariner_10.jpg",
  "ISS":     "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/ISS_2_with_Space_Shuttle_attached.jpg/400px-ISS_2_with_Space_Shuttle_attached.jpg",
};

function StarfieldPlaceholder({ name }: { name: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, c.width, c.height);
    for (let i = 0; i < 120; i++) {
      const x = Math.random() * c.width;
      const y = Math.random() * c.height;
      const r = Math.random() > 0.95 ? 1.5 : 0.7;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255,255,255,${0.3 + Math.random() * 0.7})`;
      ctx.fill();
    }
    const cx = c.width / 2;
    const cy = c.height / 2;
    const grd = ctx.createRadialGradient(cx, cy, 2, cx, cy, 40);
    grd.addColorStop(0, "rgba(255,255,255,0.9)");
    grd.addColorStop(0.3, "rgba(200,200,255,0.3)");
    grd.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grd;
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.fillStyle = "rgba(230,234,240,0.25)";
    ctx.font = "bold 11px 'IBM Plex Mono', monospace";
    ctx.textAlign = "center";
    ctx.fillText(name, cx, c.height - 10);
  }, [name]);
  return <canvas ref={ref} width={280} height={200} className="w-full h-full object-cover" />;
}

function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-baseline py-[2px] border-b border-white/[0.04]">
      <span className="text-[calc(8px*var(--fs))] font-mono text-dim tracking-wider uppercase">{label}</span>
      <span className="text-[calc(10px*var(--fs))] font-mono text-text/80 tabular-nums">{value}</span>
    </div>
  );
}

function raToHMS(ra_h?: number | null) {
  if (ra_h == null) return "—";
  const h = Math.floor(ra_h);
  const m = Math.floor((ra_h - h) * 60);
  const s = Math.floor(((ra_h - h) * 60 - m) * 60);
  return `${String(h).padStart(2,"0")}h ${String(m).padStart(2,"0")}m ${String(s).padStart(2,"0")}s`;
}

function decToDMS(dec?: number | null) {
  if (dec == null) return "—";
  const sign = dec >= 0 ? "+" : "−";
  const abs = Math.abs(dec);
  const d = Math.floor(abs);
  const m = Math.floor((abs - d) * 60);
  const s = Math.floor(((abs - d) * 60 - m) * 60);
  return `${sign}${String(d).padStart(2,"0")}° ${String(m).padStart(2,"0")}' ${String(s).padStart(2,"0")}"`;
}

/** MJD → wall-clock HH:MM in observer's local time. */
function mjdToLocalHM(mjd?: number): string {
  if (mjd == null) return "—";
  const ms = (mjd + 2400000.5 - 2440587.5) * 86400 * 1000;
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** Stellarium reports distance in AU for solar-system objects (typically ≤ 50)
 *  and parsecs otherwise.  Format with the right unit. */
function formatDistance(d?: number | null): string {
  if (d == null) return "—";
  if (d < 100) return `${d.toFixed(3)} AU`;
  // d in parsecs
  if (d < 1000) return `${d.toFixed(1)} pc`;
  if (d < 1e6) return `${(d / 1000).toFixed(2)} kpc`;
  return `${(d / 1e6).toFixed(2)} Mpc`;
}

/** Strip "NAME " prefix that Stellarium adds to common-name designations. */
function cleanName(s: string): string {
  return s.replace(/^NAME\s+/, "").replace(/^\*\s+/, "");
}

function pickPrimaryName(stel: StelSelection | null, fallback?: string): string {
  if (stel?.names?.length) return cleanName(stel.names[0]);
  return fallback ?? "—";
}

/** Pick the best image key from any of the engine's designations. */
function pickImage(stel: StelSelection | null, fallback?: string): string | undefined {
  const candidates: string[] = [];
  if (stel?.names) candidates.push(...stel.names.map(cleanName));
  if (fallback) candidates.push(fallback);
  for (const c of candidates) {
    if (OBJECT_IMAGES[c]) return OBJECT_IMAGES[c];
    // Try Messier/NGC normalised form
    const m = c.match(/^(M|NGC|IC)\s*0*(\d+)$/i);
    if (m) {
      const key = `${m[1].toUpperCase()}${m[2]}`;
      if (OBJECT_IMAGES[key]) return OBJECT_IMAGES[key];
    }
  }
  return undefined;
}

// ── Wikipedia description (CORS-friendly via origin=*) ────────────────────
function useWikipediaSummary(names: string[] | undefined): string | null {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    setText(null);
    if (!names || names.length === 0) return;
    const ctrl = new AbortController();
    const candidates = Array.from(new Set(names.map(cleanName))).slice(0, 4);
    (async () => {
      for (const title of candidates) {
        try {
          const url = `https://en.wikipedia.org/w/api.php?` + new URLSearchParams({
            action: "query", prop: "extracts", exintro: "1", explaintext: "1",
            redirects: "1", exchars: "500", format: "json", origin: "*", titles: title,
          });
          const r = await fetch(url, { signal: ctrl.signal });
          const j = await r.json();
          const pages = j?.query?.pages ?? {};
          const first = Object.values(pages)[0] as { extract?: string; missing?: boolean } | undefined;
          if (first && !first.missing && first.extract && first.extract.length > 30) {
            setText(first.extract);
            return;
          }
        } catch { /* ignore and try the next title */ }
      }
    })();
    return () => ctrl.abort();
  }, [names?.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps
  return text;
}

function visibilityFromAlt(alt: number | null | undefined): { label: string; color: string } {
  if (alt == null) return { label: "—", color: "text-dim" };
  if (alt > 30) return { label: "GOOD", color: "text-accent-red" };
  if (alt > 15) return { label: "FAIR", color: "text-yellow-400" };
  if (alt > 0)  return { label: "LOW",  color: "text-dim" };
  return { label: "BELOW HORIZON", color: "text-dim" };
}

// ── Camera control values (unchanged) ─────────────────────────────────────
const SHUTTER_SPEEDS = ["1/4000","1/2000","1/1000","1/500","1/250","1/125","1/60","1/30","1/15","1/8","1/4","1/2","1s","2s","5s","10s","30s","60s","120s","300s"];
const ISO_VALUES     = ["100","200","400","800","1600","3200","6400","12800","25600","51200"];
const APERTURES      = ["f/1.4","f/2","f/2.8","f/4","f/5.6","f/8","f/11","f/16"];
const WHITE_BALANCE  = ["Auto","Daylight","Cloudy","Shade","Tungsten","Flash","Manual"];
const DRIVE_MODES    = ["Single","Continuous","Silent","Interval","Bulb"];

function Knob({ label, values, current, onChange }: {
  label: string;
  values: string[];
  current: number;
  onChange: (i: number) => void;
}) {
  return (
    <div className="flex flex-col items-center gap-0.5">
      <span className="text-[calc(7px*var(--fs))] font-mono text-dim tracking-widest uppercase">{label}</span>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onChange(Math.max(0, current - 1))}
          className="w-4 h-4 text-[calc(9px*var(--fs))] text-dim hover:text-accent-red border border-white/[0.08] rounded
                     flex items-center justify-center transition-colors"
        >‹</button>
        <span className="text-[calc(10px*var(--fs))] font-mono text-text/90 tabular-nums w-14 text-center">
          {values[current]}
        </span>
        <button
          onClick={() => onChange(Math.min(values.length - 1, current + 1))}
          className="w-4 h-4 text-[calc(9px*var(--fs))] text-dim hover:text-accent-red border border-white/[0.08] rounded
                     flex items-center justify-center transition-colors"
        >›</button>
      </div>
    </div>
  );
}

function CameraPanel() {
  const [shutter, setShutter] = useState(18);
  const [iso, setIso]         = useState(3);
  const [aperture, setAp]     = useState(2);
  const [wb, setWb]           = useState(0);
  const [drive, setDrive]     = useState(0);
  const [interval, setInterval_] = useState(5);
  const [frames, setFrames]   = useState(10);
  const [capturing, setCapturing] = useState(false);
  const [frameCount, setFrameCount] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function startCapture() {
    setCapturing(true);
    setFrameCount(0);
    timerRef.current = setInterval(() => {
      setFrameCount((c) => {
        if (c + 1 >= frames) {
          clearInterval(timerRef.current!);
          setCapturing(false);
          return frames;
        }
        return c + 1;
      });
    }, interval * 1000);
  }

  function stopCapture() {
    if (timerRef.current) clearInterval(timerRef.current);
    setCapturing(false);
  }

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current); }, []);

  return (
    <div className="flex flex-col h-full p-2 overflow-y-auto">
      <div className="text-[calc(8px*var(--fs))] font-mono text-accent-red/70 tracking-[0.15em] uppercase mb-2 pb-1
                      border-b border-white/[0.06]">
        Fujifilm X-M5 · Camera Control
      </div>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <Knob label="Shutter" values={SHUTTER_SPEEDS} current={shutter} onChange={setShutter} />
        <Knob label="ISO" values={ISO_VALUES} current={iso} onChange={setIso} />
        <Knob label="Aperture" values={APERTURES} current={aperture} onChange={setAp} />
        <Knob label="White Balance" values={WHITE_BALANCE} current={wb} onChange={setWb} />
      </div>
      <div className="grid grid-cols-1 gap-3 mb-3">
        <Knob label="Drive Mode" values={DRIVE_MODES} current={drive} onChange={setDrive} />
      </div>
      <div className="border border-white/[0.06] rounded p-2 mb-3">
        <div className="text-[calc(7px*var(--fs))] font-mono text-dim tracking-widest uppercase mb-1.5">Interval Sequence</div>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <div>
            <div className="text-[calc(7px*var(--fs))] font-mono text-dim mb-0.5">INTERVAL (s)</div>
            <div className="flex items-center gap-1">
              <button onClick={() => setInterval_(Math.max(1, interval - 1))}
                className="w-4 h-4 text-[calc(9px*var(--fs))] text-dim hover:text-accent-red border border-white/[0.08] rounded flex items-center justify-center">‹</button>
              <span className="text-[calc(10px*var(--fs))] font-mono text-text/90 w-8 text-center">{interval}s</span>
              <button onClick={() => setInterval_(interval + 1)}
                className="w-4 h-4 text-[calc(9px*var(--fs))] text-dim hover:text-accent-red border border-white/[0.08] rounded flex items-center justify-center">›</button>
            </div>
          </div>
          <div>
            <div className="text-[calc(7px*var(--fs))] font-mono text-dim mb-0.5">FRAMES</div>
            <div className="flex items-center gap-1">
              <button onClick={() => setFrames(Math.max(1, frames - 1))}
                className="w-4 h-4 text-[calc(9px*var(--fs))] text-dim hover:text-accent-red border border-white/[0.08] rounded flex items-center justify-center">‹</button>
              <span className="text-[calc(10px*var(--fs))] font-mono text-text/90 w-8 text-center">{frames}</span>
              <button onClick={() => setFrames(frames + 1)}
                className="w-4 h-4 text-[calc(9px*var(--fs))] text-dim hover:text-accent-red border border-white/[0.08] rounded flex items-center justify-center">›</button>
            </div>
          </div>
        </div>
        {capturing && (
          <div className="mb-2">
            <div className="flex justify-between text-[calc(7px*var(--fs))] font-mono text-dim mb-0.5">
              <span>Frame {frameCount}/{frames}</span>
              <span className="text-accent-red animate-pulse">● CAPTURING</span>
            </div>
            <div className="h-1 bg-white/[0.06] rounded-full overflow-hidden">
              <div className="h-full bg-accent-red/60 rounded-full transition-all duration-500"
                style={{ width: `${(frameCount / frames) * 100}%` }} />
            </div>
          </div>
        )}
        <button
          onClick={capturing ? stopCapture : startCapture}
          className={`w-full py-1 text-[calc(9px*var(--fs))] font-mono tracking-widest rounded transition-colors border
            ${capturing
              ? "border-accent-red/50 bg-accent-red/15 text-accent-red hover:bg-accent-red/25"
              : "border-white/[0.12] bg-white/[0.04] text-text/70 hover:text-accent-red hover:border-accent-red/30"
            }`}
        >
          {capturing ? "STOP SEQUENCE" : "START SEQUENCE"}
        </button>
      </div>
      <div className="grid grid-cols-2 gap-1 text-center border border-white/[0.06] rounded p-2">
        {[
          { l: "SHUTTER", v: SHUTTER_SPEEDS[shutter] },
          { l: "ISO",     v: ISO_VALUES[iso] },
          { l: "APERTURE",v: APERTURES[aperture] },
          { l: "WB",      v: WHITE_BALANCE[wb] },
        ].map(({ l, v }) => (
          <div key={l}>
            <div className="text-[calc(7px*var(--fs))] font-mono text-dim tracking-widest">{l}</div>
            <div className="text-[calc(9px*var(--fs))] font-mono text-accent-red">{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Object view panel ─────────────────────────────────────────────────────
export default function ObjectView() {
  const { selectedTarget, stelSelection, objectViewTab, setObjectViewTab } = useAppStore();
  const activeTab = objectViewTab;
  const setActiveTab = setObjectViewTab;

  // Stellarium drives the data when something is selected; fall back to the
  // catalog-side selection (e.g. user clicked a target before $stel was ready).
  const hasSelection = !!stelSelection || !!selectedTarget;
  const primary = pickPrimaryName(stelSelection, selectedTarget?.name);
  const imgUrl  = pickImage(stelSelection, selectedTarget?.name);
  const wikiSummary = useWikipediaSummary(stelSelection?.names);
  const { label: visLabel, color: visColor } = visibilityFromAlt(stelSelection?.alt_deg);
  const rise = stelSelection?.visibility?.[0]?.rise;
  const set  = stelSelection?.visibility?.[0]?.set;

  return (
    <PanelFrame className="h-full flex flex-col" accent="red">
      <div className="flex shrink-0 border-b border-white/[0.06]">
        {(["object", "camera", "code"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 py-1.5 text-[calc(8px*var(--fs))] font-mono uppercase tracking-widest transition-colors
              ${activeTab === tab
                ? "text-accent-red border-b border-accent-red"
                : "text-dim hover:text-text"
              }`}
          >
            {tab === "object"
              ? "⊙ Object View"
              : tab === "camera"
              ? "⊡ Camera Control"
              : "⟨/⟩ Code Inspector"}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0 overflow-hidden">
        {activeTab === "code" ? (
          <CodeInspector />
        ) : activeTab === "camera" ? (
          <CameraPanel />
        ) : !hasSelection ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="text-4xl opacity-10 mb-2">◎</div>
              <p className="text-[calc(9px*var(--fs))] font-mono text-dim tracking-widest">NO TARGET SELECTED</p>
            </div>
          </div>
        ) : (
          <div className="flex flex-col h-full overflow-y-auto">
            {/* Top: image + headline data */}
            <div className="flex shrink-0">
              <div className="w-[42%] aspect-[7/5] shrink-0 relative overflow-hidden border-r border-b border-white/[0.06]">
                {imgUrl ? (
                  <img src={imgUrl} alt={primary} className="w-full h-full object-cover"
                    style={{ filter: "grayscale(60%) brightness(0.75) contrast(1.2)" }} />
                ) : (
                  <StarfieldPlaceholder name={primary} />
                )}
                <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                  <div className="relative w-12 h-12">
                    <span className="absolute left-0 right-0 top-1/2 h-px bg-accent-red/30" />
                    <span className="absolute top-0 bottom-0 left-1/2 w-px bg-accent-red/30" />
                    <span className="absolute inset-2 border border-accent-red/30 rounded-full" />
                  </div>
                </div>
              </div>

              <div className="flex-1 min-w-0 px-3 py-2 border-b border-white/[0.06]">
                <div className="text-[calc(8px*var(--fs))] font-mono text-dim tracking-widest uppercase mb-0.5">Target</div>
                <div className="text-[calc(18px*var(--fs))] font-mono font-bold text-text leading-none tracking-wide truncate">
                  {primary}
                </div>
                {stelSelection?.names && stelSelection.names.length > 1 && (
                  <div className="text-[calc(9px*var(--fs))] font-mono text-accent-red/70 tracking-wider mt-1 line-clamp-2">
                    {stelSelection.names.slice(1, 4).map(cleanName).join(" · ")}
                  </div>
                )}
                <div className="mt-2 flex items-center gap-3">
                  <div>
                    <div className="text-[calc(7px*var(--fs))] font-mono text-dim tracking-widest uppercase">Vis</div>
                    <div className={`text-[calc(10px*var(--fs))] font-mono font-bold tracking-widest ${visColor}`}
                      style={visLabel === "GOOD" ? { textShadow: "0 0 6px rgba(255,59,59,0.6)" } : undefined}>
                      {visLabel}
                    </div>
                  </div>
                  {stelSelection?.vmag != null && (
                    <div>
                      <div className="text-[calc(7px*var(--fs))] font-mono text-dim tracking-widest uppercase">MAG</div>
                      <div className="text-[calc(10px*var(--fs))] font-mono text-text/90 tabular-nums">
                        {stelSelection.vmag.toFixed(2)}
                      </div>
                    </div>
                  )}
                  {stelSelection?.phase != null && (
                    <div>
                      <div className="text-[calc(7px*var(--fs))] font-mono text-dim tracking-widest uppercase">Phase</div>
                      <div className="text-[calc(10px*var(--fs))] font-mono text-text/90 tabular-nums">
                        {(stelSelection.phase * 100).toFixed(0)}%
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Telemetry — RA/DEC, Az/Alt, distance, rise/set (live) */}
            <div className="px-3 py-2 grid grid-cols-2 gap-x-3">
              <div>
                <DataRow label="RA (J2000)"  value={raToHMS(stelSelection?.ra_h)} />
                <DataRow label="DEC (J2000)" value={decToDMS(stelSelection?.dec_deg)} />
                <DataRow label="Distance"    value={formatDistance(stelSelection?.distance)} />
              </div>
              <div>
                <DataRow label="Azimuth"  value={stelSelection?.az_deg  != null ? `${stelSelection.az_deg.toFixed(2)}°` : "—"} />
                <DataRow label="Altitude" value={stelSelection?.alt_deg != null ? `${stelSelection.alt_deg.toFixed(2)}°` : "—"} />
                <DataRow label="Rise / Set" value={rise != null && set != null ? `${mjdToLocalHM(rise)} → ${mjdToLocalHM(set)}` : "—"} />
              </div>
            </div>

            {/* Wikipedia description */}
            <div className="px-3 pt-1 pb-2 flex-1 min-h-0">
              <div className="text-[calc(7px*var(--fs))] font-mono text-accent-red/60 tracking-[0.15em] uppercase mb-1
                              border-b border-white/[0.06] pb-[2px]">
                Description
              </div>
              {wikiSummary ? (
                <p className="text-[calc(10px*var(--fs))] leading-relaxed text-text/75">
                  {wikiSummary}
                </p>
              ) : (
                <p className="text-[calc(9px*var(--fs))] font-mono text-dim italic">
                  {stelSelection ? "Loading description…" : "—"}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </PanelFrame>
  );
}
