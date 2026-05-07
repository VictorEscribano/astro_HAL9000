import { useState } from "react";
import { useAppStore } from "../../store";
import { api } from "../../api";

export default function SatelliteBrowser() {
  const { satelliteCategories, setGroundTrack, setViewMode, setSelectedTarget, setInfoCard } = useAppStore();
  const [activeCat, setActiveCat] = useState<number | null>(null);
  const [satellites, setSatellites] = useState<unknown[]>([]);
  const [loadingCat, setLoadingCat] = useState(false);
  const [loadingTrack, setLoadingTrack] = useState<number | null>(null);

  async function selectCategory(catId: number) {
    setActiveCat(catId);
    setLoadingCat(true);
    try {
      const data = await api.satellitesAbove(catId);
      setSatellites(Array.isArray(data) ? data : []);
    } catch {
      setSatellites([]);
    } finally {
      setLoadingCat(false);
    }
  }

  async function showGroundTrack(sat: Record<string, unknown>) {
    const norad = sat.satid as number;
    setLoadingTrack(norad);
    try {
      const track = await api.groundTrack(norad);
      setGroundTrack(track.map((p: Record<string, unknown>) => ({ lat: p.lat as number, lng: p.lng as number })));
      setViewMode("earthMap");
      const name = sat.satname as string;
      setSelectedTarget({ name, norad_id: norad, type: "satellite" });
      setInfoCard({
        name,
        object_type: "Satellite",
        note: `NORAD ${norad} · Elevation: ${(sat.elevation as number)?.toFixed(1)}°`,
        alt_deg: sat.elevation as number,
      });
    } catch {
      // ignore
    } finally {
      setLoadingTrack(null);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 text-[calc(9px*var(--fs))] font-mono uppercase tracking-widest text-accent-blue/70
                      border-b border-white/[0.06]">
        Satellites
      </div>

      {/* Category list */}
      <div className="flex flex-wrap gap-1 p-2 border-b border-white/[0.06]">
        {satelliteCategories.map((cat) => (
          <button
            key={cat.id}
            onClick={() => selectCategory(cat.id)}
            className={`text-[calc(9px*var(--fs))] font-mono px-1.5 py-0.5 rounded transition-colors border
              ${activeCat === cat.id
                ? "bg-accent-blue/15 border-accent-blue/40 text-accent-blue"
                : "bg-white/[0.03] border-white/[0.06] text-dim hover:text-text"
              }`}
          >
            {cat.name.replace("Operational", "").trim()}
          </button>
        ))}
      </div>

      {/* Satellite list */}
      <div className="overflow-y-auto flex-1">
        {loadingCat && (
          <div className="text-dim text-[calc(10px*var(--fs))] font-mono text-center py-4 tracking-wide">FETCHING…</div>
        )}
        {!loadingCat && satellites.length === 0 && activeCat && (
          <div className="text-dim text-[calc(10px*var(--fs))] font-mono text-center py-4">No sats overhead</div>
        )}
        {!loadingCat && !activeCat && (
          <div className="text-dim text-[calc(10px*var(--fs))] font-mono text-center py-8">Select category</div>
        )}
        {(satellites as Record<string, unknown>[]).map((sat) => (
          <button
            key={sat.satid as number}
            onClick={() => showGroundTrack(sat)}
            className="w-full flex items-center justify-between px-3 py-2 text-left
                       hover:bg-white/[0.04] border-b border-white/[0.03] group transition-colors"
          >
            <div>
              <div className="text-text text-[calc(11px*var(--fs))] font-sans">{sat.satname as string}</div>
              <div className="text-dim text-[calc(9px*var(--fs))] font-mono mt-0.5">
                {sat.satid as number} · {(sat.elevation as number)?.toFixed(1)}° el
              </div>
            </div>
            {loadingTrack === (sat.satid as number) ? (
              <span className="text-accent-blue text-[calc(10px*var(--fs))] animate-spin">◌</span>
            ) : (
              <span className="text-dim group-hover:text-accent-blue text-[calc(10px*var(--fs))] transition-colors">›</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
