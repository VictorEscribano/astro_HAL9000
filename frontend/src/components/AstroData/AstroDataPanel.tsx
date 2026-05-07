import { useState, useEffect } from "react";
import { useAppStore } from "../../store";

function raToHMS(ra_h: number): string {
  const h = Math.floor(ra_h);
  const m = Math.floor((ra_h - h) * 60);
  const s = Math.floor(((ra_h - h) * 60 - m) * 60);
  return `${String(h).padStart(2, "0")}h ${String(m).padStart(2, "0")}m ${String(s).padStart(2, "0")}s`;
}

function decToDMS(dec: number): string {
  const sign = dec >= 0 ? "+" : "−";
  const abs = Math.abs(dec);
  const d = Math.floor(abs);
  const m = Math.floor((abs - d) * 60);
  const s = Math.floor(((abs - d) * 60 - m) * 60);
  return `${sign}${String(d).padStart(2, "0")}° ${String(m).padStart(2, "0")}' ${String(s).padStart(2, "0")}"`;
}

function hourAngle(ra_h: number, lst_h: number): string {
  let ha = lst_h - ra_h;
  if (ha < -12) ha += 24;
  if (ha > 12) ha -= 24;
  const sign = ha >= 0 ? "+" : "−";
  const abs = Math.abs(ha);
  const h = Math.floor(abs);
  const m = Math.floor((abs - h) * 60);
  return `${sign}${String(h).padStart(2, "0")}h ${String(m).padStart(2, "0")}m`;
}

function airmass(alt_deg: number): string {
  if (alt_deg <= 0) return "∞";
  const z = (90 - alt_deg) * (Math.PI / 180);
  return (1 / Math.cos(z)).toFixed(2);
}

function limitingMag(alt_deg: number): string {
  // simplified Pogson approximation
  if (alt_deg <= 0) return "—";
  const am = 1 / Math.cos((90 - alt_deg) * (Math.PI / 180));
  return (6.5 - 0.5 * (am - 1)).toFixed(1);
}

function siderealHours(lng: number, d: Date): number {
  const jd = d.getTime() / 86400000 + 2440587.5;
  const T = (jd - 2451545.0) / 36525.0;
  let gst = 280.46061837 + 360.98564736629 * (jd - 2451545.0)
    + T * T * (0.000387933 - T / 38710000.0);
  gst = ((gst % 360) + 360) % 360;
  const lst = ((gst + lng) % 360 + 360) % 360;
  return lst / 15;
}

function julianDay(d: Date): string {
  return (d.getTime() / 86400000 + 2440587.5).toFixed(4);
}

function j2000Epoch(d: Date): string {
  const jd = d.getTime() / 86400000 + 2440587.5;
  return "J" + (2000.0 + (jd - 2451545.0) / 365.25).toFixed(3);
}

interface DataRow { label: string; value: string; sim?: boolean }

function Row({ label, value, sim }: DataRow) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-[2px]">
      <span className="text-dim text-[calc(9px*var(--fs))] uppercase tracking-wider shrink-0">{label}</span>
      <span className={`text-[calc(10px*var(--fs))] font-mono tabular-nums ${sim ? "text-yellow-400/70" : "text-text/80"}`}>
        {value}{sim && <span className="text-[calc(8px*var(--fs))] text-yellow-400/50 ml-0.5">[SIM]</span>}
      </span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-2">
      <div className="text-[calc(8px*var(--fs))] font-mono uppercase tracking-[0.15em] text-accent-red/60 mb-1 pb-[2px] border-b border-white/[0.06]">
        {title}
      </div>
      {children}
    </div>
  );
}

export default function AstroDataPanel() {
  const { selectedTarget, mountStatus, observer } = useAppStore();
  const [open, setOpen] = useState(true);
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const ra = selectedTarget?.ra_h ?? mountStatus?.ra_h;
  const dec = selectedTarget?.dec_deg ?? mountStatus?.dec_deg;
  const alt = selectedTarget?.ra_h ? undefined : mountStatus?.alt_deg;
  const az = selectedTarget?.ra_h ? undefined : mountStatus?.az_deg;
  const noHardware = !mountStatus;
  const lst = siderealHours(observer.lng, now);

  return (
    <div className="absolute bottom-2 left-10 z-20">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 px-2 py-1 bg-panel/90 border border-white/[0.08]
                   rounded text-[calc(9px*var(--fs))] font-mono uppercase tracking-widest text-dim hover:text-accent-red transition-colors mb-1"
      >
        <span className={`w-1 h-1 rounded-full ${open ? "bg-accent-red" : "bg-dim"}`} />
        TELEMETRY
      </button>

      {open && (
        <div className="bg-panel/95 border border-white/[0.08] rounded p-2 w-44 backdrop-blur-sm">
          <Section title="Coordinates">
            <Row label="RA"  value={ra != null ? raToHMS(ra) : "—"} sim={noHardware && ra != null} />
            <Row label="DEC" value={dec != null ? decToDMS(dec) : "—"} sim={noHardware && dec != null} />
            <Row label="HA"  value={ra != null ? hourAngle(ra, lst) : "—"} sim={noHardware && ra != null} />
            <Row label="AZ"  value={az != null ? az.toFixed(2) + "°" : "—"} sim={noHardware} />
            <Row label="ALT" value={alt != null ? alt.toFixed(2) + "°" : "—"} sim={noHardware} />
          </Section>

          <Section title="Atmosphere">
            <Row label="AIRMASS" value={alt != null ? airmass(alt) : "—"} />
            <Row label="LIM MAG" value={alt != null ? limitingMag(alt) : "—"} />
          </Section>

          <Section title="Error Model">
            <Row label="ΔRA"  value={noHardware ? "0.00\"" : "—"} sim={noHardware} />
            <Row label="ΔDEC" value={noHardware ? "0.00\"" : "—"} sim={noHardware} />
          </Section>

          <Section title="Mount">
            <Row
              label="TRACK"
              value={mountStatus?.tracking
                ? (mountStatus.tracking_rate ?? "SIDEREAL").toUpperCase()
                : "OFF"}
              sim={noHardware}
            />
            <Row label="SLEWING" value={mountStatus?.slewing ? "YES" : "NO"} sim={noHardware} />
          </Section>

          <Section title="Time">
            <Row label="LST" value={`${String(Math.floor(lst)).padStart(2,"0")}h${String(Math.floor((lst%1)*60)).padStart(2,"0")}m`} />
            <Row label="EPOCH" value={j2000Epoch(now)} />
            <Row label="JD" value={julianDay(now)} />
          </Section>
        </div>
      )}
    </div>
  );
}
