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

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
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
    if (state !== "idle") return;
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      setError("No se pudo acceder al micrófono: " + String(e));
      return;
    }
    // Prefer opus in webm — well-supported and faster-whisper handles it.
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/webm")
      ? "audio/webm"
      : "";
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    chunksRef.current = [];
    rec.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
    rec.onerror = () => {
      setError("MediaRecorder error");
      failRef.current?.(new Error("MediaRecorder error"));
      streamRef.current?.getTracks().forEach((t) => t.stop());
      setState("idle");
    };
    rec.onstop = async () => {
      // Tear down the mic so the browser tab indicator goes away.
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      const blob = new Blob(chunksRef.current, { type: mime || "audio/webm" });
      chunksRef.current = [];
      if (blob.size === 0) {
        finishRef.current?.("");
        setState("idle");
        return;
      }
      setState("transcribing");
      try {
        const form = new FormData();
        form.append("audio", blob, "recording.webm");
        const resp = await fetch(`${API_BASE_URL}/api/voice/transcribe`, {
          method: "POST",
          body: form,
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        finishRef.current?.(data.text || "");
      } catch (e) {
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
    rec.start();
    setState("recording");
  }, [state]);

  const stop = useCallback(() => {
    return new Promise<string>((resolve, reject) => {
      const rec = recorderRef.current;
      if (!rec || rec.state === "inactive") {
        resolve("");
        return;
      }
      finishRef.current = resolve;
      failRef.current = reject;
      try { rec.stop(); } catch (e) { reject(e instanceof Error ? e : new Error(String(e))); }
    });
  }, []);

  const toggle = useCallback(async (): Promise<string | null> => {
    if (state === "idle") {
      await start();
      return null;
    }
    if (state === "recording") {
      try { return await stop(); }
      catch { return null; }
    }
    return null;  // transcribing — wait
  }, [state, start, stop]);

  return { state, available, error, start, stop, toggle };
}
