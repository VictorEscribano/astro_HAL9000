import { useAppStore } from "../../store";

const TYPE_FULL: Record<string, string> = {
  Planet: "Planet",
  Gx: "Galaxy",
  OC: "Open Cluster",
  Nb: "Nebula",
  GC: "Globular Cluster",
  Pl: "Planetary Nebula",
  "Double Star": "Double Star",
  Asteroid: "Asteroid",
  Comet: "Comet",
};

export default function ObjectInfoCard() {
  const { infoCard, setInfoCard } = useAppStore();
  if (!infoCard) return null;

  const typeLabel = TYPE_FULL[infoCard.object_type] ?? infoCard.object_type;

  return (
    <div
      className="absolute bottom-16 right-2 z-30 w-64
                 bg-panel/95 border border-white/[0.1] rounded backdrop-blur-sm
                 shadow-[0_0_24px_rgba(0,0,0,0.8)]"
      style={{ animation: "slideIn 0.15s ease-out" }}
    >
      {/* Image area */}
      {infoCard.image_url ? (
        <img
          src={infoCard.image_url}
          alt={infoCard.name}
          className="w-full h-36 object-cover rounded-t opacity-80"
        />
      ) : (
        <div className="w-full h-28 flex items-center justify-center bg-white/[0.02] rounded-t border-b border-white/[0.06]">
          <span className="text-5xl opacity-10">◎</span>
        </div>
      )}

      {/* Content */}
      <div className="p-3">
        <div className="flex items-start justify-between gap-2 mb-2">
          <div>
            <div className="text-text font-sans font-medium text-sm leading-tight">
              {infoCard.name}
            </div>
            {infoCard.catalog_id && infoCard.catalog_id !== infoCard.name && (
              <div className="text-dim text-[calc(10px*var(--fs))] font-mono">{infoCard.catalog_id}</div>
            )}
          </div>
          <button
            onClick={() => setInfoCard(null)}
            className="text-dim hover:text-text text-xs shrink-0 mt-0.5"
          >
            ✕
          </button>
        </div>

        {/* Type badge */}
        <div className="inline-block text-[calc(9px*var(--fs))] font-mono uppercase tracking-wider
                        text-accent-blue border border-accent-blue/30 rounded px-1.5 py-0.5 mb-2">
          {typeLabel}
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[calc(10px*var(--fs))] font-mono mb-2">
          {infoCard.magnitude != null && (
            <>
              <span className="text-dim">Magnitude</span>
              <span className="text-text/80">{infoCard.magnitude.toFixed(1)}</span>
            </>
          )}
          {infoCard.angular_size_arcmin != null && (
            <>
              <span className="text-dim">Size</span>
              <span className="text-text/80">{infoCard.angular_size_arcmin.toFixed(1)}'</span>
            </>
          )}
          {infoCard.alt_deg != null && (
            <>
              <span className="text-dim">Altitude</span>
              <span className="text-text/80">{infoCard.alt_deg.toFixed(1)}°</span>
            </>
          )}
          {infoCard.az_deg != null && (
            <>
              <span className="text-dim">Azimuth</span>
              <span className="text-text/80">{infoCard.az_deg.toFixed(1)}°</span>
            </>
          )}
        </div>

        {/* Description */}
        {infoCard.note && (
          <p className="text-[calc(10px*var(--fs))] text-dim leading-relaxed border-t border-white/[0.06] pt-2">
            {infoCard.note}
          </p>
        )}
      </div>
    </div>
  );
}
