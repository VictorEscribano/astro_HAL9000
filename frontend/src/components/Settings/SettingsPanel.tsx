import { useEffect, useState } from "react";
import { useAppStore, FontSize, ThemeAccent } from "../../store";
import { api } from "../../api";

const FONT_SIZES: { key: FontSize; label: string; cls: string }[] = [
  { key: "xs", label: "XS", cls: "text-[calc(8px*var(--fs))]" },
  { key: "sm", label: "SM", cls: "text-[calc(10px*var(--fs))]" },
  { key: "md", label: "MD", cls: "text-[calc(12px*var(--fs))]" },
  { key: "lg", label: "LG", cls: "text-[calc(14px*var(--fs))]" },
];

type Tab = "appearance" | "session" | "settings";

interface Props { onClose: () => void }

// ── Small primitives so the three tabs stay readable ────────────────────────
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[calc(8px*var(--fs))] font-mono text-accent-red/60 tracking-[0.15em] uppercase mb-2 pb-1
                    border-b border-white/[0.06]">
      {children}
    </div>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="text-[calc(8px*var(--fs))] font-mono text-dim tracking-widest uppercase block mb-0.5">
      {children}
    </label>
  );
}

function TextInput({ value, onChange, placeholder, type = "text", step }: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string; step?: string;
}) {
  return (
    <input
      type={type}
      step={step}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1
                 text-[calc(10px*var(--fs))] font-mono text-text focus:outline-none focus:border-accent-red/40"
    />
  );
}

// ── Tab: Appearance ─────────────────────────────────────────────────────────
function AppearanceTab() {
  const { fontSize, setFontSize, themeAccent, setThemeAccent } = useAppStore();
  return (
    <>
      <section>
        <SectionLabel>Tipografía</SectionLabel>
        <FieldLabel>Tamaño de fuente</FieldLabel>
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
            >{label}</button>
          ))}
        </div>
        <div className="mt-1 text-[calc(8px*var(--fs))] font-mono text-dim">
          Preview:&nbsp;
          <span className={`${FONT_SIZES.find(f => f.key === fontSize)?.cls} text-text/60`}>
            M42 Orion Nebula Alt=42.3°
          </span>
        </div>
      </section>

      <section>
        <SectionLabel>Color de acento</SectionLabel>
        <div className="flex gap-2">
          {(["red", "blue", "green"] as const).map((color) => (
            <button
              key={color}
              onClick={() => setThemeAccent(color as ThemeAccent)}
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
            >{color}</button>
          ))}
        </div>
      </section>
    </>
  );
}

// ── Tab: Session ────────────────────────────────────────────────────────────
function SessionTab({ onUsersChanged }: { onUsersChanged: () => void }) {
  const {
    observer, setObserver, clearMessages,
    currentUser, knownUsers,
  } = useAppStore();
  const [creating, setCreating] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function switchUser(name: string) {
    if (!name || name === currentUser) return;
    setError(null);
    try {
      await api.userSetActive(name);
      const profile = await api.userCurrent();
      useAppStore.getState().applyProfile(profile);
      useAppStore.getState().setCurrentUser(name);
    } catch (e) {
      setError(String(e));
    }
  }

  async function createUser() {
    const name = creating.trim();
    if (!name) return;
    setError(null);
    try {
      await api.userCreate(name);
      setCreating("");
      onUsersChanged();
    } catch (e) {
      setError(String(e));
    }
  }

  async function deleteCurrentUser() {
    if (!currentUser) return;
    if (knownUsers.length <= 1) {
      setError("No puedes borrar el único usuario que existe.");
      return;
    }
    if (!confirm(`¿Borrar el usuario "${currentUser}"?  Esta acción no se puede deshacer.`)) return;
    try {
      await api.userDelete(currentUser);
      onUsersChanged();
      // Backend will have re-pointed `.active` at another user; pull it.
      const list = await api.usersList();
      if (list.active) {
        const profile = await api.userCurrent();
        useAppStore.getState().applyProfile(profile);
        useAppStore.getState().setCurrentUser(list.active);
      }
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <>
      <section>
        <SectionLabel>Usuario</SectionLabel>
        <FieldLabel>Activo</FieldLabel>
        <select
          value={currentUser ?? ""}
          onChange={(e) => switchUser(e.target.value)}
          className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1
                     text-[calc(10px*var(--fs))] font-mono text-text focus:outline-none focus:border-accent-red/40"
        >
          {knownUsers.map((u) => <option key={u} value={u}>{u}</option>)}
          {currentUser && !knownUsers.includes(currentUser) && (
            <option value={currentUser}>{currentUser}</option>
          )}
        </select>

        <div className="mt-2 flex gap-1.5">
          <input
            type="text"
            value={creating}
            onChange={(e) => setCreating(e.target.value)}
            placeholder="nombre nuevo usuario"
            className="flex-1 bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1
                       text-[calc(10px*var(--fs))] font-mono text-text focus:outline-none focus:border-accent-red/40"
          />
          <button
            onClick={createUser}
            disabled={!creating.trim()}
            className="px-3 text-[calc(8px*var(--fs))] font-mono text-accent-red border border-accent-red/30
                       hover:bg-accent-red/10 rounded transition-colors tracking-widest disabled:opacity-30"
          >CREAR</button>
        </div>
        <button
          onClick={deleteCurrentUser}
          disabled={!currentUser || knownUsers.length <= 1}
          className="mt-1.5 w-full py-1.5 text-[calc(8px*var(--fs))] font-mono text-dim hover:text-red-400 tracking-widest
                     border border-white/[0.08] hover:border-red-400/30 rounded transition-colors uppercase
                     disabled:opacity-30 disabled:hover:text-dim disabled:hover:border-white/[0.08]"
        >Borrar usuario actual</button>

        {error && (
          <div className="mt-2 text-[calc(8px*var(--fs))] font-mono text-red-400 break-words">{error}</div>
        )}
      </section>

      <section>
        <SectionLabel>Observador</SectionLabel>
        <div className="space-y-2">
          <div>
            <FieldLabel>Nombre</FieldLabel>
            <TextInput value={observer.name} onChange={(v) => setObserver({ ...observer, name: v })} />
          </div>
          <div className="grid grid-cols-3 gap-1.5">
            <div>
              <FieldLabel>Lat (°)</FieldLabel>
              <TextInput type="number" step="0.0001" value={String(observer.lat)}
                onChange={(v) => setObserver({ ...observer, lat: parseFloat(v) || 0 })} />
            </div>
            <div>
              <FieldLabel>Lon (°)</FieldLabel>
              <TextInput type="number" step="0.0001" value={String(observer.lng)}
                onChange={(v) => setObserver({ ...observer, lng: parseFloat(v) || 0 })} />
            </div>
            <div>
              <FieldLabel>Alt (m)</FieldLabel>
              <TextInput type="number" step="1" value={String(observer.alt_m)}
                onChange={(v) => setObserver({ ...observer, alt_m: parseFloat(v) || 0 })} />
            </div>
          </div>
        </div>
      </section>

      <section>
        <SectionLabel>Chat</SectionLabel>
        <button
          onClick={() => { clearMessages(); }}
          className="w-full py-2 text-[calc(9px*var(--fs))] font-mono text-dim hover:text-accent-red tracking-widest
                     border border-white/[0.08] hover:border-accent-red/30 rounded transition-colors uppercase"
        >Limpiar historial</button>
      </section>
    </>
  );
}

// ── Tab: Settings (LLM + voice) ─────────────────────────────────────────────
function SettingsTab() {
  const { llmPrefs, setLlmPrefs, voicePrefs, setVoicePrefs } = useAppStore();
  const [voices, setVoices] = useState<Record<string, string[]>>({});

  useEffect(() => {
    let cancelled = false;
    fetch("/api/voice/voices")
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (!cancelled && d) setVoices(d.grouped ?? {}); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  return (
    <>
      <section>
        <SectionLabel>Modelo LLM</SectionLabel>
        <div className="space-y-2">
          <div>
            <FieldLabel>Backend</FieldLabel>
            <select
              value={llmPrefs.backend}
              onChange={(e) => setLlmPrefs({ backend: e.target.value })}
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1
                         text-[calc(10px*var(--fs))] font-mono text-text focus:outline-none focus:border-accent-red/40"
            >
              <option value="ik_llama">ik_llama (local GGUF)</option>
              <option value="ollama">ollama</option>
            </select>
          </div>
          <div>
            <FieldLabel>Modelo (substring)</FieldLabel>
            <TextInput value={llmPrefs.model_hint}
              onChange={(v) => setLlmPrefs({ model_hint: v })}
              placeholder="4b · 35b · 8b · …" />
            <div className="mt-0.5 text-[calc(8px*var(--fs))] font-mono text-dim/70">
              Coincide por substring contra los GGUF en models/. Cambios surten efecto en el próximo ./start.
            </div>
          </div>
          <div>
            <FieldLabel>Idioma de respuesta</FieldLabel>
            <select
              value={llmPrefs.language}
              onChange={(e) => setLlmPrefs({ language: e.target.value })}
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1
                         text-[calc(10px*var(--fs))] font-mono text-text focus:outline-none focus:border-accent-red/40"
            >
              <option value="es">Español</option>
              <option value="en">English</option>
            </select>
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={llmPrefs.thinking}
              onChange={(e) => setLlmPrefs({ thinking: e.target.checked })}
              className="accent-accent-red"
            />
            <span className="text-[calc(9px*var(--fs))] font-mono text-text/80">
              Thinking ON (más calidad, más latencia)
            </span>
          </label>
        </div>
      </section>

      <section>
        <SectionLabel>Voz (Kokoro)</SectionLabel>
        <div className="space-y-2">
          <div>
            <FieldLabel>Voz</FieldLabel>
            <select
              value={voicePrefs.voice}
              onChange={(e) => setVoicePrefs({ voice: e.target.value })}
              className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1
                         text-[calc(10px*var(--fs))] font-mono text-text focus:outline-none focus:border-accent-red/40"
            >
              {Object.entries(voices).map(([prefix, list]) => (
                <optgroup key={prefix} label={
                  ({ a: "American English", b: "British English", e: "Español", f: "Français",
                     i: "Italiano", j: "日本語", p: "Português", z: "中文", h: "हिन्दी" } as Record<string, string>)[prefix]
                  ?? prefix.toUpperCase()
                }>
                  {list.map((v) => <option key={v} value={v}>{v}</option>)}
                </optgroup>
              ))}
            </select>
          </div>
          <div>
            <FieldLabel>Velocidad ({voicePrefs.speed.toFixed(2)}x)</FieldLabel>
            <input
              type="range"
              min={0.5} max={1.5} step={0.05}
              value={voicePrefs.speed}
              onChange={(e) => setVoicePrefs({ speed: parseFloat(e.target.value) })}
              className="w-full accent-accent-red"
            />
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={voicePrefs.enabled}
              onChange={(e) => setVoicePrefs({ enabled: e.target.checked })}
              className="accent-accent-red"
            />
            <span className="text-[calc(9px*var(--fs))] font-mono text-text/80">
              Voz activa por defecto en cada sesión
            </span>
          </label>
        </div>
      </section>
    </>
  );
}

// ── Main panel ──────────────────────────────────────────────────────────────
export default function SettingsPanel({ onClose }: Props) {
  const [tab, setTab] = useState<Tab>("appearance");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveError, setSaveError] = useState<string | null>(null);

  const refreshUsers = async () => {
    try {
      const list = await api.usersList();
      useAppStore.getState().setKnownUsers(list.users ?? []);
      useAppStore.getState().setCurrentUser(list.active ?? null);
    } catch { /* silent — keep last-known list */ }
  };

  useEffect(() => { refreshUsers(); }, []);

  async function save() {
    const s = useAppStore.getState();
    if (!s.currentUser) return;
    setSaveState("saving");
    setSaveError(null);
    try {
      await api.userUpdate(s.currentUser, {
        appearance: { fontSize: s.fontSize, themeAccent: s.themeAccent },
        session: { observer: s.observer },
        llm: s.llmPrefs,
        voice: s.voicePrefs,
      });
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 1500);
    } catch (e) {
      setSaveState("error");
      setSaveError(String(e));
    }
  }

  return (
    <div className="fixed inset-0 z-[99999] flex items-start justify-end"
         onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      <div className="relative z-10 w-96 h-full bg-panel border-l border-white/[0.08] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.08] shrink-0">
          <div>
            <div className="text-[calc(10px*var(--fs))] font-mono tracking-[0.2em] text-accent-red uppercase">Ajustes</div>
            <div className="text-[calc(8px*var(--fs))] font-mono text-dim tracking-widest">
              {useAppStore.getState().currentUser
                ? `Usuario: ${useAppStore.getState().currentUser}`
                : "Cargando usuario…"}
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-6 h-6 flex items-center justify-center text-dim hover:text-text
                       border border-white/[0.08] hover:border-accent-red/30 rounded transition-colors text-[calc(10px*var(--fs))]"
          >✕</button>
        </div>

        {/* Tabs */}
        <div className="flex shrink-0 border-b border-white/[0.06]">
          {([
            ["appearance", "Apariencia"],
            ["session",    "Sesión"],
            ["settings",   "Settings"],
          ] as [Tab, string][]).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex-1 py-1.5 text-[calc(8px*var(--fs))] font-mono uppercase tracking-widest transition-colors
                ${tab === key
                  ? "text-accent-red border-b border-accent-red"
                  : "text-dim hover:text-text"}`}
            >{label}</button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          {tab === "appearance" && <AppearanceTab />}
          {tab === "session" && <SessionTab onUsersChanged={refreshUsers} />}
          {tab === "settings" && <SettingsTab />}
        </div>

        {/* Footer / save bar */}
        <div className="shrink-0 border-t border-white/[0.08] p-3 flex items-center gap-2">
          <div className="flex-1 text-[calc(8px*var(--fs))] font-mono">
            {saveState === "saved"  && <span className="text-green-400">✓ Guardado</span>}
            {saveState === "saving" && <span className="text-dim animate-pulse">Guardando…</span>}
            {saveState === "error"  && <span className="text-red-400 truncate" title={saveError ?? ""}>⚠ {saveError}</span>}
            {saveState === "idle"   && (
              <span className="text-dim">Cambios sin guardar se aplican en vivo</span>
            )}
          </div>
          <button
            onClick={save}
            disabled={saveState === "saving" || !useAppStore.getState().currentUser}
            className="bg-accent-red/15 hover:bg-accent-red/25 text-accent-red border border-accent-red/30
                       rounded px-4 py-1.5 text-[calc(9px*var(--fs))] font-mono tracking-widest transition-colors disabled:opacity-30"
          >GUARDAR</button>
        </div>
      </div>
    </div>
  );
}
