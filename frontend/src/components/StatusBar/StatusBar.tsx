import { useEffect, useState } from "react";
import { useAppStore } from "../../store";
import SettingsPanel from "../Settings/SettingsPanel";

function utcNow() {
  return new Date().toISOString().replace("T", " ").slice(0, 19);
}

interface Pill { label: string; value: string; ok: boolean }

export default function StatusBar() {
  const { ollamaOnline, observer, mountStatus, fontSize, themeAccent } = useAppStore();
  const [utc, setUtc] = useState(utcNow());
  const [uptime, setUptime] = useState(0);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    const id = setInterval(() => {
      setUtc(utcNow());
      setUptime((u) => u + 1);
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // Apply global font scale.  Every text-[Npx] class in the codebase reads
  // calc(N*var(--fs)) so this rescales the whole UI uniformly.
  useEffect(() => {
    const map = { xs: 1.0, sm: 1.2, md: 1.45, lg: 1.75 };
    document.documentElement.style.setProperty("--fs", String(map[fontSize] ?? 1));
  }, [fontSize]);

  // Apply theme accent globally — Tailwind's accent-red token is wired to
  // rgb(var(--accent-red-rgb) / <alpha-value>), so swapping this RGB triple
  // recolours every accent-red, accent-red/30, etc. in the UI.
  useEffect(() => {
    const map = { red: "255 59 59", blue: "59 167 255", green: "52 211 153" };
    document.documentElement.style.setProperty("--accent-red-rgb", map[themeAccent] ?? map.red);
  }, [themeAccent]);

  const uptimeStr = [
    String(Math.floor(uptime / 3600)).padStart(2, "0"),
    String(Math.floor((uptime % 3600) / 60)).padStart(2, "0"),
    String(uptime % 60).padStart(2, "0"),
  ].join(":");

  const pills: Pill[] = [
    { label: "SYSTEM STATUS", value: "ONLINE",          ok: true },
    { label: "EPHEMERIS",     value: "SKYFIELD ACTIVE",  ok: true },
    { label: "MOUNT",         value: mountStatus ? (mountStatus.parked ? "PARKED" : "READY") : "OFFLINE", ok: !!mountStatus },
    { label: "AI CORE",       value: ollamaOnline ? "ACTIVE" : "OFFLINE", ok: ollamaOnline },
  ];

  return (
    <>
      <div className="flex items-center gap-0 px-4 h-10 bg-panel border-b border-white/[0.06] shrink-0 select-none">
        {/* Logo */}
        <div className="flex items-center gap-2 mr-8">
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
            <polygon points="10,2 18,17 2,17" stroke="#FF3B3B" strokeWidth="1.5" fill="none" />
            <circle cx="10" cy="11" r="2" fill="#FF3B3B" />
          </svg>
          <div>
            <div className="text-[calc(11px*var(--fs))] font-mono font-semibold tracking-[0.15em] text-text uppercase leading-none">
              AstroAgent
            </div>
            <div className="text-[calc(8px*var(--fs))] font-mono text-dim tracking-widest leading-none mt-px">
              AI ASSISTANT FOR ASTRONOMY
            </div>
          </div>
        </div>

        {/* Status pills */}
        <div className="flex items-center gap-5 flex-1">
          {pills.map(({ label, value, ok }) => (
            <div key={label} className="flex flex-col">
              <span className="text-[calc(8px*var(--fs))] font-mono text-dim tracking-widest uppercase">{label}</span>
              <span
                className={`text-[calc(10px*var(--fs))] font-mono font-medium tracking-wider uppercase leading-none
                  ${ok ? "text-accent-red" : "text-dim"}`}
                style={ok ? { textShadow: "0 0 8px rgba(255,59,59,0.5)" } : undefined}
              >
                {value}
              </span>
            </div>
          ))}
        </div>

        {/* Time + Location */}
        <div className="flex items-center gap-6">
          <div className="flex flex-col items-end">
            <span className="text-[calc(8px*var(--fs))] font-mono text-dim tracking-widest">TIME (UTC)</span>
            <span className="text-[calc(10px*var(--fs))] font-mono text-text tracking-wider">{utc}</span>
          </div>
          <div className="flex flex-col items-end">
            <span className="text-[calc(8px*var(--fs))] font-mono text-dim tracking-widest">LOCATION</span>
            <span className="text-[calc(10px*var(--fs))] font-mono text-text">
              {observer.name.toUpperCase()}, ES
            </span>
            <span className="text-[calc(9px*var(--fs))] font-mono text-dim">
              {observer.lat.toFixed(3)}° N, {observer.lng.toFixed(3)}° E
            </span>
          </div>

          {/* Controls */}
          <div className="flex items-center gap-1.5 ml-4">
            <div className="text-[calc(8px*var(--fs))] font-mono text-dim tracking-widest mr-1">
              {uptimeStr}
            </div>
            <button
              onClick={() => setShowSettings(true)}
              title="Settings"
              className="w-6 h-6 rounded-full border border-white/[0.12] text-dim hover:text-text
                         hover:border-accent-red/40 flex items-center justify-center text-[calc(10px*var(--fs))]
                         transition-colors font-mono"
            >
              ⚙
            </button>
          </div>
        </div>
      </div>

      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}
    </>
  );
}
