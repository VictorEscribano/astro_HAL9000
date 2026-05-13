import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../../api";
import { useAppStore } from "../../store";

/** Voice catalogue returned by `/api/voice/voices`.  Keyed by leading
 *  letter (`a` = American English, `e` = Spanish, `b` = British, …). */
export interface VoiceCatalogue {
  voices: string[];
  grouped: Record<string, string[]>;
}

/** Public shape kept compatible with the previous Web-Speech `useTTS` hook
 *  so the Chat UI doesn't have to branch on backend. */
export interface KokoroTTSHandle {
  voiceEnabled: boolean;
  setVoiceEnabled: (v: boolean) => void;
  voices: string[];
  grouped: Record<string, string[]>;
  selectedVoice: string | null;
  setSelectedVoice: (v: string) => void;
  /** True from the first audio chunk start until the last one ends. */
  speaking: boolean;
  /** Backend availability — `/api/voice/health` returned available=true. */
  available: boolean;
  /** Speak the assistant's full reply.  The backend filters out
   *  thinking / code / markdown internally; pass the raw response. */
  speak: (text: string) => void;
  stop: () => void;
}

/** Default voice per language, mirrors what `KokoroEngine.resolve_voice`
 *  picks on the backend when none is given.  Used for the initial UI
 *  selection — the picker can override it. */
const DEFAULT_VOICE_ES = "ef_dora";
const DEFAULT_VOICE_EN = "af_heart";

interface AudioChunk {
  sentence: string;
  buffer: AudioBuffer;
}

export function useKokoroTTS(): KokoroTTSHandle {
  // Voice prefs live in the Zustand store so they survive across hook
  // mounts AND get hydrated from the active user's saved profile on app
  // load.  We expose the *same shape* the old useState-based hook did so
  // Chat.tsx's call sites don't have to change.
  const voicePrefs = useAppStore((s) => s.voicePrefs);
  const setVoicePrefs = useAppStore((s) => s.setVoicePrefs);
  const voiceEnabled = voicePrefs.enabled;
  const selectedVoice = voicePrefs.voice || null;
  const setVoiceEnabled = useCallback((v: boolean) => setVoicePrefs({ enabled: v }), [setVoicePrefs]);
  const setSelectedVoice = useCallback((v: string) => setVoicePrefs({ voice: v }), [setVoicePrefs]);

  const [available, setAvailable] = useState(false);
  const [voices, setVoices] = useState<string[]>([]);
  const [grouped, setGrouped] = useState<Record<string, string[]>>({});
  const [speaking, setSpeaking] = useState(false);

  // ── refs that survive renders without re-firing effects ───────────────────
  const audioCtxRef = useRef<AudioContext | null>(null);
  // Time at which the next scheduled chunk should start playing.  Kept on a
  // ref because AudioContext currentTime keeps advancing in real time and
  // re-renders would be too laggy to track it precisely in state.
  const nextStartTimeRef = useRef<number>(0);
  // Sources we've started but haven't finished — needed so stop() can kill
  // them without waiting for natural end.
  const liveSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  // AbortController for the in-flight SSE fetch.
  const abortRef = useRef<AbortController | null>(null);
  // Count of chunks scheduled but not yet ended — used to flip `speaking`
  // off only when EVERY chunk has finished playing (the SSE stream might
  // close while later sentences are still queued).
  const pendingRef = useRef<number>(0);
  // Streaming finished? When this is true AND pendingRef is 0, we flip off.
  const streamDoneRef = useRef<boolean>(false);

  // Probe backend availability + voice catalogue once on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const h = await fetch(`${API_BASE_URL}/api/voice/health`).then((r) => r.json());
        if (cancelled) return;
        setAvailable(!!h.available);
        if (!h.available) return;
        const v = await fetch(`${API_BASE_URL}/api/voice/voices`).then((r) => r.json());
        if (cancelled) return;
        const list: string[] = v.voices ?? [];
        setVoices(list);
        setGrouped(v.grouped ?? {});
        // Pick the user's language default ONLY if no voice has been set
        // yet (fresh install / never-edited profile).  Saved preferences
        // come in via applyProfile() in the store, which runs before this
        // catalogue fetch most of the time.
        const current = useAppStore.getState().voicePrefs.voice;
        if (!current || !list.includes(current)) {
          const lang = (navigator.language || "en").toLowerCase();
          const prefer = lang.startsWith("es") ? DEFAULT_VOICE_ES : DEFAULT_VOICE_EN;
          if (list.includes(prefer)) setSelectedVoice(prefer);
          else if (list.length > 0) setSelectedVoice(list[0]);
        }
      } catch {
        if (!cancelled) setAvailable(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Tear down everything on unmount.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      liveSourcesRef.current.forEach((s) => { try { s.stop(); } catch { /* */ } });
      liveSourcesRef.current.clear();
      audioCtxRef.current?.close().catch(() => {});
    };
  }, []);

  const ensureAudioContext = useCallback(async (): Promise<AudioContext> => {
    if (!audioCtxRef.current) {
      // Browser policy: must be triggered by a user gesture.  `speak()` is
      // called from a click/keyboard handler so this is safe.
      const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      audioCtxRef.current = new Ctx();
    }
    if (audioCtxRef.current.state === "suspended") {
      try { await audioCtxRef.current.resume(); } catch { /* */ }
    }
    return audioCtxRef.current;
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    liveSourcesRef.current.forEach((s) => { try { s.stop(); } catch { /* */ } });
    liveSourcesRef.current.clear();
    pendingRef.current = 0;
    streamDoneRef.current = true;
    nextStartTimeRef.current = audioCtxRef.current?.currentTime ?? 0;
    setSpeaking(false);
  }, []);

  /** Schedule a decoded chunk to play right after the previous one. */
  const enqueueChunk = useCallback((ctx: AudioContext, chunk: AudioChunk) => {
    const startAt = Math.max(ctx.currentTime, nextStartTimeRef.current);
    const src = ctx.createBufferSource();
    src.buffer = chunk.buffer;
    src.connect(ctx.destination);
    src.start(startAt);
    liveSourcesRef.current.add(src);
    pendingRef.current += 1;
    if (!speaking) setSpeaking(true);
    src.onended = () => {
      liveSourcesRef.current.delete(src);
      pendingRef.current -= 1;
      if (pendingRef.current <= 0 && streamDoneRef.current) {
        setSpeaking(false);
      }
    };
    nextStartTimeRef.current = startAt + chunk.buffer.duration;
  }, [speaking]);

  const speak = useCallback((text: string) => {
    if (!voiceEnabled || !available || !text.trim()) return;
    // Cancel anything currently playing — start fresh.
    stop();
    streamDoneRef.current = false;

    const ac = new AbortController();
    abortRef.current = ac;

    (async () => {
      const ctx = await ensureAudioContext();
      nextStartTimeRef.current = ctx.currentTime;

      const lang = (navigator.language || "en").toLowerCase().startsWith("es") ? "es" : "en";
      let resp: Response;
      try {
        resp = await fetch(`${API_BASE_URL}/api/voice/speak`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text,
            voice: selectedVoice ?? undefined,
            lang,
            speed: voicePrefs.speed,
          }),
          signal: ac.signal,
        });
      } catch {
        return;  // network error / abort
      }
      if (!resp.ok || !resp.body) return;

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      // The browser sees SSE as plain text — we parse "data: …\n\n" frames
      // manually so we don't add an EventSource dependency.
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop() ?? "";
          for (const part of parts) {
            for (const line of part.split("\n")) {
              if (!line.startsWith("data: ")) continue;
              const data = line.slice(6).trim();
              if (!data) continue;
              try {
                const ev = JSON.parse(data);
                if (ev.type === "audio" && typeof ev.wav_b64 === "string") {
                  // Decode base64 → ArrayBuffer → AudioBuffer, then queue.
                  const bin = atob(ev.wav_b64);
                  const ab = new Uint8Array(bin.length);
                  for (let i = 0; i < bin.length; i++) ab[i] = bin.charCodeAt(i);
                  try {
                    const audioBuf = await ctx.decodeAudioData(ab.buffer);
                    enqueueChunk(ctx, { sentence: ev.sentence ?? "", buffer: audioBuf });
                  } catch {
                    // Decoder failure — skip this chunk, keep streaming.
                  }
                } else if (ev.type === "done" || ev.type === "error") {
                  streamDoneRef.current = true;
                  if (pendingRef.current <= 0) setSpeaking(false);
                }
              } catch { /* malformed SSE — skip */ }
            }
          }
        }
      } catch {
        // Aborted or network — flush state.
      } finally {
        streamDoneRef.current = true;
        if (pendingRef.current <= 0) setSpeaking(false);
      }
    })();
  }, [voiceEnabled, available, selectedVoice, ensureAudioContext, enqueueChunk, stop]);

  return {
    voiceEnabled,
    setVoiceEnabled,
    voices,
    grouped,
    selectedVoice,
    setSelectedVoice,
    speaking,
    available,
    speak,
    stop,
  };
}
