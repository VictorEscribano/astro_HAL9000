import { useEffect } from "react";
import { useAppStore } from "../../store";
import { api } from "../../api";

export default function MountPanel() {
  const { mountStatus, setMountStatus } = useAppStore();

  useEffect(() => {
    const refresh = async () => {
      try {
        const s = await api.mountStatus();
        setMountStatus(s);
      } catch {
        // backend not ready yet
      }
    };
    refresh();
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, []);

  if (!mountStatus) return null;

  return (
    <div className="px-3 py-2 bg-space-800/50 border-t border-space-700/50 text-xs">
      <div className="flex items-center gap-3 mb-1">
        <span className="text-nebula/70 font-semibold uppercase tracking-wider text-[calc(10px*var(--fs))]">Mount</span>
        <span className={`px-1.5 py-0.5 rounded text-[calc(10px*var(--fs))] ${
          mountStatus.parked
            ? "bg-space-700 text-space-600"
            : mountStatus.tracking
            ? "bg-aurora/20 text-aurora"
            : "bg-yellow-900/30 text-yellow-400"
        }`}>
          {mountStatus.parked ? "PARKED" : mountStatus.tracking ? `TRACKING (${mountStatus.tracking_rate ?? "sidereal"})` : "IDLE"}
        </span>
        {mountStatus.target_name && (
          <span className="text-star/60">{mountStatus.target_name}</span>
        )}
      </div>
      <div className="flex gap-4 text-space-600">
        <span>RA {mountStatus.ra_h.toFixed(4)}h</span>
        <span>Dec {mountStatus.dec_deg.toFixed(3)}°</span>
        <span>Alt {mountStatus.alt_deg.toFixed(1)}°</span>
        <span>Az {mountStatus.az_deg.toFixed(1)}°</span>
      </div>
      {mountStatus.log.length > 0 && (
        <div className="mt-1 font-mono text-[calc(9px*var(--fs))] text-aurora/50 truncate">
          {mountStatus.log[mountStatus.log.length - 1]}
        </div>
      )}

      <div className="flex gap-2 mt-1.5">
        <button
          onClick={() => api.mountStop().then((s) => setMountStatus(s))}
          className="px-2 py-0.5 bg-red-900/30 border border-red-800/40 text-red-400 rounded text-[calc(10px*var(--fs))] hover:bg-red-900/50 transition-colors"
        >
          STOP
        </button>
        <button
          onClick={() => api.mountPark().then((s) => setMountStatus(s))}
          className="px-2 py-0.5 bg-space-700/50 border border-space-600/40 text-space-600 rounded text-[calc(10px*var(--fs))] hover:bg-space-700 transition-colors"
        >
          PARK
        </button>
      </div>
    </div>
  );
}
