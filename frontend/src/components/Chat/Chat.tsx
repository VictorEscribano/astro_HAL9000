import { useState, useRef, useEffect, useCallback } from "react";
import { useAppStore, ChatMessage, ToolCall, WebSource } from "../../store";
import { CHAT_STREAM_URL } from "../../api";
import ToolCallCard from "./ToolCallCard";
import PanelFrame from "../ui/PanelFrame";

// Render text with markdown links: [title](url) → <a>
function TextWithLinks({ text }: { text: string }) {
  const parts: React.ReactNode[] = [];
  const linkRe = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
  let last = 0, m: RegExpExecArray | null;
  while ((m = linkRe.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push(
      <a key={m.index} href={m[2]} target="_blank" rel="noreferrer"
        className="text-accent-red/80 hover:text-accent-red underline underline-offset-2 transition-colors">
        {m[1]}
      </a>
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

// Sources footer rendered below an assistant message
function SourcesBar({ sources }: { sources: WebSource[] }) {
  if (!sources.length) return null;
  return (
    <div className="mt-1.5 pt-1.5 border-t border-white/[0.06] flex flex-wrap gap-x-3 gap-y-0.5">
      <span className="text-[calc(7.5px*var(--fs))] font-mono text-dim/50 tracking-widest uppercase">Fuentes:</span>
      {sources.map((s, i) => (
        <a key={i} href={s.url} target="_blank" rel="noreferrer"
          title={s.snippet}
          className="text-[calc(7.5px*var(--fs))] font-mono text-accent-red/60 hover:text-accent-red transition-colors underline underline-offset-2 truncate max-w-[200px]">
          {s.title || s.url}
        </a>
      ))}
    </div>
  );
}

// ── Voice / TTS ────────────────────────────────────────────────────────────
function useTTS() {
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<SpeechSynthesisVoice | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    function loadVoices() {
      const all = speechSynthesis.getVoices();
      // Prefer voices that sound natural: Google, Microsoft Neural, or language-matching
      const filtered = all.filter((v) =>
        v.name.toLowerCase().includes("google") ||
        v.name.toLowerCase().includes("neural") ||
        v.name.toLowerCase().includes("natural") ||
        v.lang.startsWith("es") ||
        v.lang.startsWith("en")
      );
      setVoices(filtered.length ? filtered : all.slice(0, 12));
    }
    loadVoices();
    speechSynthesis.addEventListener("voiceschanged", loadVoices);
    return () => speechSynthesis.removeEventListener("voiceschanged", loadVoices);
  }, []);

  const speak = useCallback((text: string) => {
    if (!voiceEnabled || !text.trim()) return;
    speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(text);
    if (selectedVoice) utt.voice = selectedVoice;
    utt.rate = 1.05;
    utt.pitch = 1.0;
    utt.volume = 0.9;
    utt.onstart = () => setSpeaking(true);
    utt.onend = () => setSpeaking(false);
    utt.onerror = () => setSpeaking(false);
    utteranceRef.current = utt;
    speechSynthesis.speak(utt);
  }, [voiceEnabled, selectedVoice]);

  const stop = useCallback(() => {
    speechSynthesis.cancel();
    setSpeaking(false);
  }, []);

  return { voiceEnabled, setVoiceEnabled, voices, selectedVoice, setSelectedVoice, speaking, speak, stop };
}

// ── Waveform ───────────────────────────────────────────────────────────────
function Waveform({ active }: { active: boolean }) {
  const BARS = 48;
  return (
    <div className="flex items-end gap-px h-6 px-1">
      {Array.from({ length: BARS }).map((_, i) => {
        const base = 0.15 + 0.1 * Math.sin(i * 0.6);
        const h = active
          ? `${Math.round((base + 0.6 * Math.abs(Math.sin(i * 1.1))) * 100)}%`
          : `${Math.round(base * 100)}%`;
        return (
          <div
            key={i}
            className={`flex-1 ${active ? "bg-accent-red/60" : "bg-white/10"} transition-all duration-300`}
            style={{ height: h, animationDelay: active ? `${i * 30}ms` : "0ms" }}
          />
        );
      })}
    </div>
  );
}

// ── Voice selector popup ───────────────────────────────────────────────────
function VoiceSelector({
  voices, selected, onSelect, onClose,
}: {
  voices: SpeechSynthesisVoice[];
  selected: SpeechSynthesisVoice | null;
  onSelect: (v: SpeechSynthesisVoice) => void;
  onClose: () => void;
}) {
  return (
    <div className="absolute bottom-full right-0 mb-1 w-64 bg-panel border border-white/[0.12]
                    rounded shadow-2xl z-50 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/[0.08]">
        <span className="text-[calc(9px*var(--fs))] font-mono text-dim tracking-widest uppercase">Voice Catalog</span>
        <button onClick={onClose} className="text-dim hover:text-text text-[calc(10px*var(--fs))]">✕</button>
      </div>
      <div className="max-h-48 overflow-y-auto">
        {voices.length === 0 && (
          <div className="px-3 py-2 text-[calc(9px*var(--fs))] font-mono text-dim">No voices available</div>
        )}
        {voices.map((v, i) => (
          <button
            key={i}
            onClick={() => { onSelect(v); onClose(); }}
            className={`w-full text-left px-3 py-1.5 text-[calc(9px*var(--fs))] font-mono transition-colors
              ${selected?.name === v.name
                ? "bg-accent-red/20 text-accent-red"
                : "text-text/70 hover:bg-white/[0.04] hover:text-text"
              }`}
          >
            <span className="block truncate">{v.name}</span>
            <span className="text-[calc(8px*var(--fs))] text-dim">{v.lang}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Main Chat component ─────────────────────────────────────────────────────
export default function Chat() {
  const {
    messages, addMessage, updateLastMessage, clearMessages,
    ollamaOnline, setSelectedTarget, setViewMode, setGroundTrack, setSkyObjects, setInfoCard,
    setYoutubeVideo, addCustomWidget, setPendingSources,
  } = useAppStore();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showVoicePicker, setShowVoicePicker] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const tts = useTTS();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    tts.stop();

    // Include tool-call summaries so the AI retains full context across turns
    const history = messages
      .map((m) => {
        if (m.role === "assistant") {
          let content = m.content;
          if (m.toolCalls?.length) {
            const summary = m.toolCalls
              .map((tc) => {
                const args = tc.input
                  ? Object.entries(tc.input).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")
                  : "";
                const out = tc.output ? tc.output.slice(0, 400) : "";
                return `[Tool: ${tc.tool}(${args}) → ${out}]`;
              })
              .join("\n");
            content = content ? `${content}\n${summary}` : summary;
          }
          return content ? { role: m.role as "user" | "assistant", content } : null;
        }
        return m.content.trim() ? { role: m.role as "user" | "assistant", content: m.content } : null;
      })
      .filter(Boolean) as { role: "user" | "assistant"; content: string }[];

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content: text };
    addMessage(userMsg);
    addMessage({ id: crypto.randomUUID(), role: "assistant", content: "", toolCalls: [] });
    setLoading(true);

    let currentContent = "";
    let toolCalls: ToolCall[] = [];
    let pendingTool: Partial<ToolCall> | null = null;
    let collectedSources: WebSource[] = [];

    try {
      const resp = await fetch(CHAT_STREAM_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history }),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      if (!resp.body) throw new Error("No body");

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";

        for (const part of parts) {
          for (const line of part.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            const data = line.slice(6).trim();
            if (data === "[DONE]") continue;
            try {
              const ev = JSON.parse(data);
              if (ev.type === "token") {
                currentContent += ev.content;
                updateLastMessage(currentContent, toolCalls);
              } else if (ev.type === "tool_start") {
                pendingTool = { tool: ev.tool, input: ev.input };
              } else if (ev.type === "tool_end") {
                if (pendingTool) {
                  const tc: ToolCall = { tool: pendingTool.tool!, input: pendingTool.input, output: ev.output };
                  toolCalls = [...toolCalls, tc];
                  pendingTool = null;
                  updateLastMessage(currentContent, toolCalls);
                  handleToolOutput(tc);
                }
              } else if (ev.type === "ui_command") {
                if (ev.action === "show_sources" && Array.isArray(ev.sources)) {
                  collectedSources = [...collectedSources, ...ev.sources];
                }
                handleUICommand(ev);
              } else if (ev.type === "error") {
                currentContent += `\n⚠ ${ev.message}`;
                updateLastMessage(currentContent, toolCalls);
              }
            } catch { /* malformed SSE */ }
          }
        }
      }
    } catch (err) {
      updateLastMessage(`⚠ ${String(err)}`);
    } finally {
      setLoading(false);
      if (collectedSources.length > 0) {
        updateLastMessage(currentContent, toolCalls, collectedSources);
        setPendingSources([]);
      }
      if (currentContent.trim()) tts.speak(currentContent);
    }
  }

  function handleToolOutput(tc: ToolCall) {
    if (!tc.output) return;
    try {
      const data = JSON.parse(tc.output);
      if (tc.tool === "get_satellite_ground_track" && Array.isArray(data) && data.length > 0) {
        setGroundTrack(data);
      }
    } catch { /* not JSON */ }
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function handleUICommand(cmd: Record<string, any>) {
    switch (cmd.action) {
      case "select_target":
        setSelectedTarget({ name: cmd.name, ra_h: cmd.ra_h, dec_deg: cmd.dec_deg, type: "dso" });
        setViewMode("skyChart");
        if (cmd.name) setInfoCard({ name: cmd.name, object_type: "DSO", alt_deg: cmd.alt_deg, az_deg: cmd.az_deg });
        break;
      case "select_satellite":
        setSelectedTarget({ name: cmd.name, norad_id: cmd.norad_id, type: "satellite" });
        if (cmd.name) setInfoCard({ name: cmd.name, object_type: "Satellite" });
        break;
      case "show_ground_track":
        setViewMode("earthMap");
        break;
      case "refresh_sky_objects":
        import("../../api").then(({ api }) => api.skyObjectsTonight().then(setSkyObjects).catch(() => {}));
        break;
      case "open_youtube":
        if (cmd.video_id) {
          setYoutubeVideo({
            video_id: cmd.video_id,
            title: cmd.title || cmd.video_id,
            embed_url: cmd.embed_url,
            url: cmd.url,
          });
          setViewMode("youtube");
        }
        break;
      case "show_sources":
        if (Array.isArray(cmd.sources)) {
          setPendingSources(cmd.sources);
        }
        break;
      case "new_widget":
        if (cmd.widget_id) {
          addCustomWidget({
            id: cmd.widget_id,
            name: cmd.name || "Widget",
            description: "",
            created_at: Date.now() / 1000,
          });
        }
        break;
    }
  }

  const lastMsg = messages[messages.length - 1];

  return (
    <PanelFrame title="AI RESPONSE" className="h-full flex flex-col" accent="red">
      <div className="flex flex-col h-full">
        {/* Header strip */}
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/[0.06] shrink-0 gap-2">
          {!ollamaOnline ? (
            <span className="text-[calc(9px*var(--fs))] font-mono text-yellow-400/80">⚠ AI OFFLINE</span>
          ) : (
            <span className="text-[calc(9px*var(--fs))] font-mono text-dim">
              {loading ? (
                <span className="text-accent-red animate-pulse">● PROCESSING</span>
              ) : tts.speaking ? (
                <span className="text-accent-red/70 animate-pulse">◉ SPEAKING</span>
              ) : (
                <span className="text-dim">● STANDBY</span>
              )}
            </span>
          )}

          <div className="flex items-center gap-1.5 ml-auto">
            {/* Voice controls */}
            <div className="relative flex items-center gap-1">
              <button
                onClick={() => tts.setVoiceEnabled(!tts.voiceEnabled)}
                title={tts.voiceEnabled ? "Voice ON — click to mute" : "Voice OFF — click to enable"}
                className={`text-[calc(8px*var(--fs))] font-mono border px-2 py-0.5 rounded tracking-widest transition-colors
                  ${tts.voiceEnabled
                    ? "text-accent-red border-accent-red/40 bg-accent-red/10"
                    : "text-dim border-white/[0.08] hover:text-accent-red"
                  }`}
              >
                {tts.speaking ? "◉ VOX" : tts.voiceEnabled ? "◎ VOX" : "○ VOX"}
              </button>
              {tts.voiceEnabled && (
                <button
                  onClick={() => setShowVoicePicker((v) => !v)}
                  className="text-[calc(8px*var(--fs))] font-mono text-dim hover:text-text border border-white/[0.08]
                             hover:border-accent-red/30 px-1.5 py-0.5 rounded transition-colors"
                  title="Select voice"
                >
                  ▾
                </button>
              )}
              {showVoicePicker && (
                <VoiceSelector
                  voices={tts.voices}
                  selected={tts.selectedVoice}
                  onSelect={tts.setSelectedVoice}
                  onClose={() => setShowVoicePicker(false)}
                />
              )}
            </div>
            {tts.speaking && (
              <button
                onClick={tts.stop}
                className="text-[calc(8px*var(--fs))] font-mono text-accent-red border border-accent-red/30 px-2 py-0.5 rounded tracking-wider"
              >
                STOP
              </button>
            )}
            <button
              onClick={clearMessages}
              className="text-[calc(8px*var(--fs))] font-mono text-dim hover:text-accent-red transition-colors
                         border border-white/[0.08] hover:border-accent-red/30 px-2 py-0.5 rounded tracking-wider"
            >
              NEW SESSION
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2 space-y-2">
          {messages.length === 0 && (
            <div className="text-center mt-8 space-y-2">
              <div className="text-[calc(9px*var(--fs))] font-mono text-dim tracking-[0.2em] uppercase">
                System ready. Awaiting query.
              </div>
              <div className="text-[calc(8px*var(--fs))] font-mono text-dim/50 leading-relaxed">
                Ask about sky objects, satellite passes,<br />
                or say "Point at M42"
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id} className="space-y-1">
              {msg.role === "user" ? (
                <div className="flex gap-2 items-start">
                  <span className="text-accent-red text-[calc(9px*var(--fs))] font-mono shrink-0 mt-0.5">›</span>
                  <div className="text-[calc(11px*var(--fs))] font-mono text-text/90 leading-relaxed">{msg.content}</div>
                </div>
              ) : (
                <div className="space-y-1">
                  {msg.toolCalls && msg.toolCalls.length > 0 && (
                    <div className="space-y-1">
                      {msg.toolCalls.map((tc, i) => <ToolCallCard key={i} toolCall={tc} />)}
                    </div>
                  )}
                  {msg.content ? (
                    <div className="text-[calc(11px*var(--fs))] font-mono text-text/80 leading-relaxed pl-3 border-l border-accent-red/20 whitespace-pre-wrap">
                      <TextWithLinks text={msg.content} />
                      {loading && msg === lastMsg && (
                        <span className="inline-block w-1.5 h-3 bg-accent-red ml-0.5 animate-pulse align-text-bottom" />
                      )}
                      {msg.sources && msg.sources.length > 0 && (
                        <SourcesBar sources={msg.sources} />
                      )}
                    </div>
                  ) : (
                    loading && msg === lastMsg && (
                      <div className="flex gap-1 pl-3 pt-1">
                        {[0, 150, 300].map((d) => (
                          <span key={d} className="w-1 h-1 bg-accent-red rounded-full animate-bounce"
                            style={{ animationDelay: `${d}ms` }} />
                        ))}
                      </div>
                    )
                  )}
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Waveform */}
        <div className="shrink-0 px-1 py-0.5 border-t border-white/[0.04]">
          <Waveform active={loading || tts.speaking} />
        </div>

        {/* Input */}
        <div className="shrink-0 border-t border-white/[0.06] px-2 py-1.5">
          <div className="flex gap-2 items-end">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
              }}
              placeholder="QUERY SYSTEM…"
              rows={1}
              disabled={loading}
              className="flex-1 bg-white/[0.04] text-text placeholder-dim rounded px-2 py-1.5
                         text-[calc(10px*var(--fs))] font-mono border border-white/[0.06] focus:outline-none
                         focus:border-accent-red/40 resize-none disabled:opacity-40"
            />
            <button
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              className="bg-accent-red/15 hover:bg-accent-red/25 text-accent-red border border-accent-red/30
                         rounded px-3 py-1.5 text-[calc(9px*var(--fs))] font-mono tracking-widest transition-colors disabled:opacity-30"
            >
              {loading ? "···" : "SEND"}
            </button>
          </div>
        </div>
      </div>
    </PanelFrame>
  );
}
