import { useAppStore, SkyObject } from "../../store";

const TYPE_COLORS: Record<string, string> = {
  Planet:       "text-yellow-400",
  "Gx":         "text-purple-400",
  "OC":         "text-accent-blue",
  "Nb":         "text-green-400",
  "GC":         "text-orange-400",
  "Pl":         "text-cyan-400",
};

function typeColor(t: string) {
  return TYPE_COLORS[t] ?? "text-dim";
}

export default function ObjectList() {
  const { skyObjects, setSelectedTarget, setViewMode, setInfoCard } = useAppStore();

  function handleSelect(obj: SkyObject) {
    setSelectedTarget({
      name: obj.catalog_id ?? obj.name,
      ra_h: obj.ra_h,
      dec_deg: obj.dec_deg,
      type: obj.object_type === "Planet" ? "planet" : "dso",
    });
    setViewMode("skyChart");
    setInfoCard({
      name: obj.name,
      catalog_id: obj.catalog_id,
      object_type: obj.object_type,
      magnitude: obj.magnitude,
      angular_size_arcmin: obj.angular_size_arcmin,
      alt_deg: obj.alt_deg,
      az_deg: obj.az_deg,
      note: obj.note,
    });
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 text-[calc(9px*var(--fs))] font-mono uppercase tracking-widest text-accent-blue/70
                      border-b border-white/[0.06] flex items-center justify-between">
        <span>Tonight</span>
        <span className="text-dim">{skyObjects.length} visible</span>
      </div>
      <div className="overflow-y-auto flex-1">
        {skyObjects.map((obj) => (
          <button
            key={obj.catalog_id ?? obj.name}
            onClick={() => handleSelect(obj)}
            className="w-full flex items-start gap-2 px-3 py-2 text-left
                       hover:bg-white/[0.04] transition-colors border-b border-white/[0.03] group"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-text text-[calc(11px*var(--fs))] font-sans truncate">
                  {obj.name}
                </span>
                <span className={`text-[calc(9px*var(--fs))] font-mono ${typeColor(obj.object_type)} shrink-0`}>
                  {obj.object_type}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-accent-blue text-[calc(9px*var(--fs))] font-mono">
                  {obj.alt_deg?.toFixed(1)}°
                </span>
                {obj.magnitude != null && (
                  <span className="text-dim text-[calc(9px*var(--fs))] font-mono">m{obj.magnitude.toFixed(1)}</span>
                )}
                {obj.angular_size_arcmin != null && (
                  <span className="text-dim text-[calc(9px*var(--fs))] font-mono">{obj.angular_size_arcmin.toFixed(0)}'</span>
                )}
              </div>
            </div>
            <span className="text-dim group-hover:text-accent-blue text-[calc(10px*var(--fs))] shrink-0 mt-0.5 transition-colors">›</span>
          </button>
        ))}
        {skyObjects.length === 0 && (
          <div className="text-dim text-[calc(10px*var(--fs))] font-mono text-center py-8 tracking-wide">
            LOADING…
          </div>
        )}
      </div>
    </div>
  );
}
