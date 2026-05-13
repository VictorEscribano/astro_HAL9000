import { useState, useRef, useEffect, useCallback } from "react";
import { useAppStore, ChatMessage, ToolCall, ChatPlan } from "../../store";
import { CHAT_STREAM_URL } from "../../api";
import ToolCallCard from "./ToolCallCard";
import ThinkingCard from "./ThinkingCard";
import AssistantMarkdown from "./AssistantMarkdown";
import PanelFrame from "../ui/PanelFrame";
import { useKokoroTTS } from "./useKokoroTTS";
import { useMicRecorder } from "./useMicRecorder";

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
// Kokoro v1 voice names: `<lang-prefix><gender>_<style>`.  We surface the
// language groups Kokoro ships with so the user can find their tongue
// quickly in a 50+ voice list.
const KOKORO_LANG_LABEL: Record<string, string> = {
  a: "American English",
  b: "British English",
  e: "Español",
  f: "Français",
  h: "हिन्दी",
  i: "Italiano",
  j: "日本語",
  p: "Português",
  z: "中文",
};

function VoiceSelector({
  grouped, selected, onSelect, onClose,
}: {
  grouped: Record<string, string[]>;
  selected: string | null;
  onSelect: (v: string) => void;
  onClose: () => void;
}) {
  // Sort languages with Spanish + English first, others alphabetical.
  const order = ["e", "a", "b", ...Object.keys(grouped).filter((k) => !"eab".includes(k)).sort()];
  return (
    <div className="absolute bottom-full right-0 mb-1 w-72 bg-panel border border-white/[0.12]
                    rounded shadow-2xl z-50 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/[0.08]">
        <span className="text-[calc(9px*var(--fs))] font-mono text-dim tracking-widest uppercase">Kokoro Voices</span>
        <button onClick={onClose} className="text-dim hover:text-text text-[calc(10px*var(--fs))]">✕</button>
      </div>
      <div className="max-h-64 overflow-y-auto">
        {order.filter((g) => grouped[g]?.length).map((g) => (
          <div key={g}>
            <div className="px-3 py-1 text-[calc(7px*var(--fs))] font-mono text-dim/70 tracking-widest uppercase bg-white/[0.02]">
              {KOKORO_LANG_LABEL[g] ?? g.toUpperCase()}
            </div>
            {grouped[g].map((v) => (
              <button
                key={v}
                onClick={() => { onSelect(v); onClose(); }}
                className={`w-full text-left px-3 py-1 text-[calc(9px*var(--fs))] font-mono transition-colors
                  ${selected === v
                    ? "bg-accent-red/20 text-accent-red"
                    : "text-text/70 hover:bg-white/[0.04] hover:text-text"
                  }`}
              >
                {v}
              </button>
            ))}
          </div>
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
    editorCode, editorAttached,
  } = useAppStore();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showVoicePicker, setShowVoicePicker] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // Track whether the user is "stuck to the bottom" — only auto-scroll when
  // they are.  Once they scroll up to read past messages, stop yanking them
  // back down on every streamed token.
  const stickToBottomRef = useRef(true);
  const abortRef = useRef<AbortController | null>(null);
  const tts = useKokoroTTS();
  const mic = useMicRecorder();

  // Pipe Whisper transcription into the chat input.  We append (with a
  // space when there's already text) so users can dictate in chunks.
  async function toggleMic() {
    const result = await mic.toggle();
    if (result != null && result.trim()) {
      setInput((prev) => prev.trim() ? `${prev.trim()} ${result}` : result);
    } else if (result != null) {
      // Recording finished but Whisper returned empty — probably silence /
      // VAD filtered it out.  Surface a hint instead of failing silently.
      console.info("[mic] transcripción vacía — Whisper no detectó habla");
    }
  }

  // Detect user scroll → update sticky flag.  Threshold of 80px treats
  // "near the bottom" as still sticky to avoid flickering with small scrolls
  // caused by token-induced layout changes.
  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distanceFromBottom < 80;
  }, []);

  useEffect(() => {
    if (stickToBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
    }
  }, [messages]);

  // Hard reset of `loading` if the previous turn died without unwinding the
  // finally block (e.g. a thrown render error swallowed the abort).  This is
  // the safety net for "chat freezes and can't send anymore".
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  function cancelInflight() {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
  }

  async function sendMessage() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    tts.stop();
    stickToBottomRef.current = true;  // user just sent → snap to bottom

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
                // Output can be string, object, array or null depending on the tool.
                // Stringify objects for the history summary so the model sees JSON.
                const outRaw = tc.output == null
                  ? ""
                  : typeof tc.output === "string"
                  ? tc.output
                  : JSON.stringify(tc.output);
                const out = outRaw.slice(0, 400);
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

    // If the user has code attached from the Code Inspector, prefix the
    // message so the planner / response generator sees it.  Surfaced as
    // a fenced ```python block — the LLM reliably parses these.
    let messageForBackend = text;
    if (editorAttached && editorCode.trim()) {
      messageForBackend =
        "[El usuario tiene este código abierto en el Code Inspector y quiere que lo tengas en cuenta:]\n" +
        "```python\n" + editorCode + "\n```\n\n" +
        text;
    }

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content: text };
    addMessage(userMsg);
    addMessage({ id: crypto.randomUUID(), role: "assistant", content: "", toolCalls: [], thinking: "" });
    setLoading(true);

    let currentContent = "";
    let currentThinking = "";
    let currentPlan: ChatPlan | undefined;
    let toolCalls: ToolCall[] = [];
    let pendingTool: Partial<ToolCall> | null = null;

    const ac = new AbortController();
    abortRef.current = ac;

    try {
      const resp = await fetch(CHAT_STREAM_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: messageForBackend, history }),
        signal: ac.signal,
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
                updateLastMessage({ content: currentContent });
              } else if (ev.type === "thinking") {
                currentThinking += ev.content;
                updateLastMessage({ thinking: currentThinking });
              } else if (ev.type === "plan") {
                currentPlan = { steps: ev.steps ?? [], rationale: ev.rationale ?? "" };
                updateLastMessage({ plan: currentPlan });
              } else if (ev.type === "tool_start") {
                pendingTool = { tool: ev.tool, input: ev.input };
              } else if (ev.type === "tool_end") {
                if (pendingTool) {
                  const tc: ToolCall = { tool: pendingTool.tool!, input: pendingTool.input, output: ev.output };
                  toolCalls = [...toolCalls, tc];
                  pendingTool = null;
                  updateLastMessage({ toolCalls });
                  handleToolOutput(tc);
                }
              } else if (ev.type === "ui_command") {
                handleUICommand(ev);
              } else if (ev.type === "error") {
                currentContent += `\n⚠ ${ev.message}`;
                updateLastMessage({ content: currentContent });
              }
            } catch { /* malformed SSE */ }
          }
        }
      }
    } catch (err) {
      // AbortError from cancelInflight is intentional — don't mark as error.
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        const msg = currentContent ? `${currentContent}\n⚠ ${String(err)}` : `⚠ ${String(err)}`;
        updateLastMessage({ content: msg });
      }
    } finally {
      abortRef.current = null;
      setLoading(false);
      // Speak the final response if voice enabled
      if (currentContent.trim()) tts.speak(currentContent);
    }
  }

  function handleToolOutput(tc: ToolCall) {
    if (!tc.output) return;
    // Output may already be a parsed object/array from the SSE handler, or
    // still a JSON string for some tools.  Normalise before pattern matching.
    let data: unknown = tc.output;
    if (typeof data === "string") {
      try { data = JSON.parse(data); } catch { return; }
    }
    if (tc.tool === "get_satellite_ground_track" && Array.isArray(data) && data.length > 0) {
      setGroundTrack(data as { lat: number; lng: number }[]);
    }
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
                disabled={!tts.available}
                title={
                  !tts.available
                    ? "Kokoro TTS backend unavailable — model files missing on backend"
                    : tts.voiceEnabled
                    ? "Voice ON — click to mute"
                    : "Voice OFF — click to enable"
                }
                className={`text-[calc(8px*var(--fs))] font-mono border px-2 py-0.5 rounded tracking-widest transition-colors
                  ${!tts.available
                    ? "text-dim/30 border-white/[0.04] cursor-not-allowed"
                    : tts.voiceEnabled
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
                  grouped={tts.grouped}
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
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-3 py-2 space-y-2"
        >
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

          {messages.map((msg) => {
            const isLast = msg === lastMsg;
            return (
              <div key={msg.id} className="space-y-1 min-w-0">
                {msg.role === "user" ? (
                  <div className="flex gap-2 items-start min-w-0">
                    <span className="text-accent-red text-[calc(9px*var(--fs))] font-mono shrink-0 mt-0.5">›</span>
                    <div className="text-[calc(11px*var(--fs))] font-mono text-text/90 leading-relaxed break-words min-w-0 flex-1">
                      {msg.content}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-1 min-w-0">
                    {msg.plan && msg.plan.rationale && (
                      <div className="bg-white/[0.02] border border-white/[0.06] rounded text-[calc(9px*var(--fs))] px-2 py-1">
                        <span className="text-[calc(7px*var(--fs))] font-mono text-dim/80 bg-white/[0.04] border border-white/[0.06]
                                         px-1 rounded mr-1">PLN</span>
                        <span className="text-dim/80 font-mono">{msg.plan.rationale}</span>
                        {msg.plan.steps.length > 0 && (
                          <span className="text-white/30 font-mono ml-2">[{msg.plan.steps.join(" → ")}]</span>
                        )}
                      </div>
                    )}
                    {msg.thinking && (
                      <ThinkingCard
                        content={msg.thinking}
                        streaming={loading && isLast && !msg.content}
                      />
                    )}
                    {msg.toolCalls && msg.toolCalls.length > 0 && (
                      <div className="space-y-1">
                        {msg.toolCalls.map((tc, i) => <ToolCallCard key={i} toolCall={tc} />)}
                      </div>
                    )}
                    {msg.content ? (
                      <div className="text-[calc(11px*var(--fs))] font-mono text-text/80 leading-relaxed pl-3 border-l border-accent-red/20 break-words min-w-0">
                        <AssistantMarkdown content={msg.content} />
                        {loading && isLast && (
                          <span className="inline-block w-1.5 h-3 bg-accent-red ml-0.5 animate-pulse align-text-bottom" />
                        )}
                      </div>
                    ) : (
                      loading && isLast && !msg.thinking && (
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
            );
          })}
          <div ref={bottomRef} />
        </div>

        {/* Waveform */}
        <div className="shrink-0 px-1 py-0.5 border-t border-white/[0.04]">
          <Waveform active={loading || tts.speaking} />
        </div>

        {/* Input — textarea stays enabled during streaming so the user can type
            the next message while the model is still answering.  SEND is only
            re-enabled when no request is in flight; a STOP button is shown
            instead when one is. */}
        <div className="shrink-0 border-t border-white/[0.06] px-2 py-1.5">
          <div className="flex gap-2 items-end">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
              }}
              placeholder={loading ? "QUERY IN FLIGHT — press STOP to cancel" : "QUERY SYSTEM…"}
              rows={1}
              className="flex-1 bg-white/[0.04] text-text placeholder-dim rounded px-2 py-1.5
                         text-[calc(10px*var(--fs))] font-mono border border-white/[0.06] focus:outline-none
                         focus:border-accent-red/40 resize-none"
            />
            {/* MIC — Whisper STT.  Hidden when backend reports unavailable
                so users on a barebones install don't see a useless button.
                Visual states:
                  idle         → outlined, dim
                  recording    → solid red, pulsing
                  transcribing → outlined red, animated dots */}
            {mic.available && (
              <button
                onClick={toggleMic}
                disabled={mic.state === "transcribing"}
                title={
                  mic.state === "recording"  ? "Stop recording and transcribe"
                  : mic.state === "transcribing" ? "Transcribing…"
                  : "Record voice"
                }
                className={`rounded px-3 py-1.5 text-[calc(9px*var(--fs))] font-mono tracking-widest border transition-colors
                  ${mic.state === "recording"
                    ? "bg-accent-red text-bg border-accent-red animate-pulse"
                    : mic.state === "transcribing"
                    ? "text-accent-red border-accent-red/30"
                    : "text-dim hover:text-accent-red border-white/[0.08] hover:border-accent-red/30"}`}
              >
                {mic.state === "recording"     ? "● REC"
                 : mic.state === "transcribing" ? "··· STT"
                 : "○ MIC"}
              </button>
            )}

            {loading ? (
              <button
                onClick={cancelInflight}
                className="bg-accent-red/15 hover:bg-accent-red/25 text-accent-red border border-accent-red/30
                           rounded px-3 py-1.5 text-[calc(9px*var(--fs))] font-mono tracking-widest transition-colors"
                title="Cancel current response"
              >
                STOP
              </button>
            ) : (
              <button
                onClick={sendMessage}
                disabled={!input.trim()}
                className="bg-accent-red/15 hover:bg-accent-red/25 text-accent-red border border-accent-red/30
                           rounded px-3 py-1.5 text-[calc(9px*var(--fs))] font-mono tracking-widest transition-colors disabled:opacity-30"
              >
                SEND
              </button>
            )}
          </div>
          {mic.error && (
            <div className="mt-1 text-[calc(8px*var(--fs))] font-mono text-red-400/90 break-words">
              ⚠ {mic.error}
            </div>
          )}
        </div>
      </div>
    </PanelFrame>
  );
}
