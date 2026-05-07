import { useRef, useEffect } from "react";
import { useAppStore, type StelSelection } from "../../store";

// Stellarium's left nav-drawer is 300 px wide (open by default).
// Shifting the iframe 300 px left + widening it clips the drawer out of view.
const LEFT_CLIP = 300;

// Our catalog uses zero-padded IDs; Stellarium wants "NGC 224" / "M 31".
function toStelName(name: string): string {
  const m = name.match(/^(NGC|IC|M)\s*0*(\d+)$/i);
  if (m) return `${m[1].toUpperCase()} ${m[2]}`;
  return name;
}

export default function StellariumView() {
  const { observer, selectedTarget, setStelSelection } = useAppStore();
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // The injected bridge inside Stellarium pushes a {t:"stel-selection",info}
  // message whenever the engine's selection changes.  Mirror that into the
  // store so the ObjectView can render Stellarium's authoritative data
  // (RA/DEC, Az/Alt, vmag, distance, phase, rise/set).
  useEffect(() => {
    const onMsg = (ev: MessageEvent) => {
      const d = ev.data;
      if (!d || d.t !== "stel-selection") return;
      setStelSelection((d.info as StelSelection | null) ?? null);
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [setStelSelection]);

  // The iframe loads our backend-proxied Stellarium page.
  // Vite dev-proxy forwards /stel → localhost:8000/stel, making it same-origin
  // with the React app.  The backend injects a postMessage listener into the
  // Stellarium HTML that calls stel.pointAndLock(obj) when we post a message.
  const initialSrc = useRef("");
  if (!initialSrc.current) {
    const { lat, lng, alt_m } = observer;
    const date = encodeURIComponent(new Date().toISOString());
    initialSrc.current =
      `/stel/?lat=${lat.toFixed(5)}&lng=${lng.toFixed(5)}&elev=${Math.round(alt_m)}&date=${date}`;
  }

  // When a non-satellite target is selected, tell the injected SWE bridge to
  // point and lock onto it.  postMessage works here because both the parent
  // (localhost:5173) and the iframe (/stel/ proxied via Vite) are same-origin.
  const lastTarget = useRef<string | null>(null);
  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe?.contentWindow) return;
    if (!selectedTarget || selectedTarget.type === "satellite") return;
    if (selectedTarget.name === lastTarget.current) return;
    lastTarget.current = selectedTarget.name;
    iframe.contentWindow.postMessage(
      { t: "sel", n: toStelName(selectedTarget.name) },
      "*",
    );
  }, [selectedTarget?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    // overflow-hidden clips the 300 px left strip (Stellarium nav drawer + banner)
    <div className="relative w-full h-full overflow-hidden bg-black">
      <iframe
        ref={iframeRef}
        src={initialSrc.current}
        title="Stellarium Web"
        allow="fullscreen; geolocation"
        style={{
          position: "absolute",
          top: 0,
          left: -LEFT_CLIP,
          width: `calc(100% + ${LEFT_CLIP}px)`,
          height: "100%",
          border: "none",
        }}
      />
    </div>
  );
}
