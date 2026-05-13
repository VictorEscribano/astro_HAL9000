import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../../api";

/** Browser-side voice capture → Whisper transcription.
 *
 *  MediaRecorder gives us WebM/Opus chunks which faster-whisper feeds to
 *  ffmpeg under the hood, so no transcoding is needed on the JS side.
 *
 *  Lifecycle:
 *    state="idle"        — nothing in flight
 *    state="recording"   — mic is open, capturing
 *    state="transcribing" — recording stopped, awaiting backend response
 *
 *  The hook owns nothing display-side; callers render their own button
 *  and place the returned `text` wherever they want (chat input). */
export type MicState = "idle" | "recording" | "transcribing";

export interface MicHandle {
  state: MicState;
  /** Whether the backend reports Whisper available.  Hides the button if false. */
  available: boolean;
  /** Most recent error message, if any (cleared on next start). */
  error: string | null;
  start: () => Promise<void>;
  stop: () => Promise<string>;
  toggle: () => Promise<string | null>;
}

export function useMicRecorder(): MicHandle {
  const [state, setState] = useState<MicState>("idle");
  const [available, setAvailable] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Mirror `state` into a ref so the click-driven `toggle` callback always
  // sees the LATEST value, regardless of React's render scheduling.  This
  // also lets us avoid putting `state` in useCallback deps (which caused
  // stale closures in some browsers when the user clicked twice fast).
  const stateRef = useRef<MicState>("idle");
  useEffect(() => { stateRef.current = state; }, [state]);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const mimeRef = useRef<string>("");
  // Resolver that the .start() Promise hands to stop() — lets stop()
  // return the transcribed text directly without callers fighting over
  // state updates.
  const finishRef = useRef<((text: string) => void) | null>(null);
  const failRef = useRef<((err: Error) => void) | null>(null);

  // Probe whisper health once on mount.
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE_URL}/api/voice/transcribe/health`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (!cancelled) setAvailable(!!d?.available); })
      .catch(() => { if (!cancelled) setAvailable(false); });
    return () => { cancelled = true; };
  }, []);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      try { recorderRef.current?.stop(); } catch { /* */ }
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const start = useCallback(async () => {
    setError(null);
    if (stateRef.current !== "idle") return;

    // getUserMedia requires a secure origin: HTTPS or localhost.  If the
    // user opened the dev URL by LAN IP, the browser silently fails.
    const isSecure = window.isSecureContext;
    if (!isSecure) {
      setError("Mic requires HTTPS or http://localhost (not LAN IP).  Open http://localhost:5173 instead.");
      console.warn("[mic] insecure context — getUserMedia will fail");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Tu navegador no soporta MediaRecorder.");
      return;
    }

    let stream: MediaStream;
    try {
      console.debug("[mic] requesting getUserMedia");
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      console.debug("[mic] got stream, tracks:", stream.getAudioTracks().length);
    } catch (e) {
      const msg = String(e);
      setError("Mic permission denied or device missing: " + msg);
      console.error("[mic] getUserMedia failed:", e);
      return;
    }

    // Prefer opus in webm; the backend uses ffmpeg under the hood so almost
    // anything works, but webm/opus is the smallest payload.
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/webm")
      ? "audio/webm"
      : MediaRecorder.isTypeSupported("audio/mp4")
      ? "audio/mp4"
      : "";
    mimeRef.current = mime;
    console.debug("[mic] using mime:", mime || "(browser default)");

    let rec: MediaRecorder;
    try {
      rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    } catch (e) {
      setError("MediaRecorder construction failed: " + String(e));
      stream.getTracks().forEach((t) => t.stop());
      return;
    }

    chunksRef.current = [];
    rec.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        chunksRef.current.push(e.data);
        console.debug("[mic] chunk:", e.data.size, "bytes, total:", chunksRef.current.length);
      }
    };
    rec.onerror = (ev) => {
      console.error("[mic] MediaRecorder error:", ev);
      setError("MediaRecorder error");
      failRef.current?.(new Error("MediaRecorder error"));
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setState("idle");
    };
    rec.onstop = async () => {
      console.debug("[mic] onstop fired; chunks=", chunksRef.current.length);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      const blob = new Blob(chunksRef.current, { type: mimeRef.current || "audio/webm" });
      chunksRef.current = [];
      if (blob.size === 0) {
        console.warn("[mic] empty blob — nothing recorded");
        setError("No se capturó audio.  ¿Está el micrófono mudo a nivel de sistema?");
        finishRef.current?.("");
        finishRef.current = null;
        failRef.current = null;
        setState("idle");
        return;
      }
      console.debug("[mic] blob size:", blob.size, "bytes, type:", blob.type);
      setState("transcribing");
      try {
        const form = new FormData();
        const ext = (mimeRef.current.includes("mp4") ? "m4a" : "webm");
        form.append("audio", blob, `recording.${ext}`);
        console.debug("[mic] POST /api/voice/transcribe");
        const resp = await fetch(`${API_BASE_URL}/api/voice/transcribe`, {
          method: "POST",
          body: form,
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status} ${resp.statusText}`);
        const data = await resp.json();
        console.debug("[mic] transcript:", JSON.stringify(data));
        finishRef.current?.(data.text || "");
      } catch (e) {
        console.error("[mic] transcribe failed:", e);
        setError("Transcripción falló: " + String(e));
        failRef.current?.(e instanceof Error ? e : new Error(String(e)));
      } finally {
        finishRef.current = null;
        failRef.current = null;
        setState("idle");
      }
    };

    recorderRef.current = rec;
    streamRef.current = stream;
    // Request a chunk every 1000 ms so we have data even if the user
    // stops very quickly (without timeslice some browsers buffer
    // everything and only emit on stop, which is fine — but explicit
    // timeslice protects against driver quirks).
    try {
      rec.start(1000);
      console.debug("[mic] recorder started, state=", rec.state);
    } catch (e) {
      setError("MediaRecorder.start() failed: " + String(e));
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    setState("recording");
  }, []);

  const stop = useCallback(() => {
    return new Promise<string>((resolve, reject) => {
      const rec = recorderRef.current;
      if (!rec || rec.state === "inactive") {
        console.warn("[mic] stop() called but recorder is", rec?.state);
        resolve("");
        return;
      }
      finishRef.current = resolve;
      failRef.current = reject;
      try {
        console.debug("[mic] stopping recorder, state=", rec.state);
        rec.stop();
      } catch (e) {
        console.error("[mic] rec.stop() threw:", e);
        reject(e instanceof Error ? e : new Error(String(e)));
      }
    });
  }, []);

  const toggle = useCallback(async (): Promise<string | null> => {
    const current = stateRef.current;
    console.debug("[mic] toggle from state:", current);
    if (current === "idle") {
      await start();
      return null;
    }
    if (current === "recording") {
      try { return await stop(); }
      catch (e) { console.error("[mic] toggle/stop error:", e); return null; }
    }
    return null;  // transcribing — wait
  }, [start, stop]);

  return { state, available, error, start, stop, toggle };
}
