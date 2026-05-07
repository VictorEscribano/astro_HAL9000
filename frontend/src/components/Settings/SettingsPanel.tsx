import { useAppStore, FontSize } from "../../store";

const FONT_SIZES: { key: FontSize; label: string; cls: string }[] = [
  { key: "xs", label: "XS", cls: "text-[calc(8px*var(--fs))]" },
  { key: "sm", label: "SM", cls: "text-[calc(10px*var(--fs))]" },
  { key: "md", label: "MD", cls: "text-[calc(12px*var(--fs))]" },
  { key: "lg", label: "LG", cls: "text-[calc(14px*var(--fs))]" },
];

interface Props { onClose: () => void }

export default function SettingsPanel({ onClose }: Props) {
  const { fontSize, setFontSize, themeAccent, setThemeAccent, observer, setObserver, clearMessages } = useAppStore();

  return (
    <div
      className="fixed inset-0 z-[99999] flex items-start justify-end"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Panel */}
      <div className="relative z-10 w-80 h-full bg-panel border-l border-white/[0.08] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.08] shrink-0">
          <div>
            <div className="text-[calc(10px*var(--fs))] font-mono tracking-[0.2em] text-accent-red uppercase">Settings</div>
            <div className="text-[calc(8px*var(--fs))] font-mono text-dim tracking-widest">AstroAgent Configuration</div>
          </div>
          <button
            onClick={onClose}
            className="w-6 h-6 flex items-center justify-center text-dim hover:text-text
                       border border-white/[0.08] hover:border-accent-red/30 rounded transition-colors text-[calc(10px*var(--fs))]"
          >✕</button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          {/* Font size */}
          <section>
            <div className="text-[calc(8px*var(--fs))] font-mono text-accent-red/60 tracking-[0.15em] uppercase mb-2 pb-1
                            border-b border-white/[0.06]">
              Display
            </div>
            <div className="mb-3">
              <div className="text-[calc(9px*var(--fs))] font-mono text-dim tracking-widest mb-1.5 uppercase">Font Size</div>
              <div className="grid grid-cols-4 gap-1">
                {FONT_SIZES.map(({ key, label, cls }) => (
                  <button
                    key={key}
                    onClick={() => setFontSize(key)}
                    className={`py-1.5 rounded border text-center transition-colors
                      ${fontSize === key
                        ? "bg-accent-red/20 border-accent-red/50 text-accent-red"
                        : "border-white/[0.08] text-dim hover:text-text hover:border-white/[0.15]"
                      } ${cls} font-mono`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="mt-1 text-[calc(8px*var(--fs))] font-mono text-dim">
                Preview: <span className={`${FONT_SIZES.find(f => f.key === fontSize)?.cls} text-text/60`}>
                  M42 Orion Nebula Alt=42.3°
                </span>
              </div>
            </div>

            {/* Theme accent */}
            <div>
              <div className="text-[calc(9px*var(--fs))] font-mono text-dim tracking-widest mb-1.5 uppercase">Accent Color</div>
              <div className="flex gap-2">
                {(["red", "blue", "green"] as const).map((color) => (
                  <button
                    key={color}
                    onClick={() => setThemeAccent(color)}
                    className={`flex-1 py-1.5 rounded border text-[calc(9px*var(--fs))] font-mono uppercase tracking-widest
                                transition-colors
                      ${themeAccent === color ? "border-white/40 font-bold" : "border-white/[0.08] text-dim"}`}
                    style={{
                      color: themeAccent === color
                        ? color === "red" ? "#FF3B3B" : color === "blue" ? "#3BA7FF" : "#34d399"
                        : undefined,
                      borderColor: themeAccent === color
                        ? color === "red" ? "rgba(255,59,59,0.5)" : color === "blue" ? "rgba(59,167,255,0.5)" : "rgba(52,211,153,0.5)"
                        : undefined,
                    }}
                  >
                    {color}
                  </button>
                ))}
              </div>
            </div>
          </section>

          {/* Observer location */}
          <section>
            <div className="text-[calc(8px*var(--fs))] font-mono text-accent-red/60 tracking-[0.15em] uppercase mb-2 pb-1
                            border-b border-white/[0.06]">
              Observer Location
            </div>
            <div className="space-y-2">
              {[
                { label: "Name",      key: "name",  type: "text",   val: observer.name  },
                { label: "Latitude",  key: "lat",   type: "number", val: String(observer.lat) },
                { label: "Longitude", key: "lng",   type: "number", val: String(observer.lng) },
                { label: "Altitude m",key: "alt_m", type: "number", val: String(observer.alt_m) },
              ].map(({ label, key, type, val }) => (
                <div key={key}>
                  <label className="text-[calc(8px*var(--fs))] font-mono text-dim tracking-widest uppercase block mb-0.5">
                    {label}
                  </label>
                  <input
                    type={type}
                    defaultValue={val}
                    step={type === "number" ? "0.001" : undefined}
                    onBlur={(e) => {
                      const newVal = type === "number" ? parseFloat(e.target.value) : e.target.value;
                      setObserver({ ...observer, [key]: newVal });
                    }}
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1
                               text-[calc(10px*var(--fs))] font-mono text-text focus:outline-none focus:border-accent-red/40"
                  />
                </div>
              ))}
            </div>
          </section>

          {/* Session */}
          <section>
            <div className="text-[calc(8px*var(--fs))] font-mono text-accent-red/60 tracking-[0.15em] uppercase mb-2 pb-1
                            border-b border-white/[0.06]">
              Session
            </div>
            <button
              onClick={() => { clearMessages(); onClose(); }}
              className="w-full py-2 text-[calc(9px*var(--fs))] font-mono text-dim hover:text-accent-red tracking-widest
                         border border-white/[0.08] hover:border-accent-red/30 rounded transition-colors uppercase"
            >
              Clear Chat History
            </button>
          </section>

          {/* About */}
          <section>
            <div className="text-[calc(8px*var(--fs))] font-mono text-accent-red/60 tracking-[0.15em] uppercase mb-2 pb-1
                            border-b border-white/[0.06]">
              About
            </div>
            <div className="space-y-1 text-[calc(9px*var(--fs))] font-mono text-dim">
              <div className="flex justify-between">
                <span>AstroAgent</span><span className="text-text/60">v0.1.0</span>
              </div>
              <div className="flex justify-between">
                <span>Backend</span><span className="text-text/60">FastAPI + LangGraph</span>
              </div>
              <div className="flex justify-between">
                <span>AI Model</span><span className="text-text/60">Ollama local</span>
              </div>
              <div className="flex justify-between">
                <span>Mount</span><span className="text-text/60">OpenAstroTracker</span>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
