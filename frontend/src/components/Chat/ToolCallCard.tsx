import { useState } from "react";
import { ToolCall } from "../../store";

const TOOL_ICONS: Record<string, string> = {
  execute_python:            "⟨/⟩",
  get_sky_objects_tonight:   "SKY",
  get_object_position:       "POS",
  get_moon_info:             "MN",
  get_satellite_passes:      "SAT",
  get_satellites_overhead:   "OVH",
  get_satellite_ground_track:"TRK",
  check_tracking_feasibility:"CHK",
  mount_control:             "MNT",
  get_weather_and_seeing:    "WX",
  search_satellite:          "SRH",
};

function formatOutput(output: string): string {
  try { return JSON.stringify(JSON.parse(output), null, 2); }
  catch { return output; }
}

export default function ToolCallCard({ toolCall }: { toolCall: ToolCall }) {
  const [open, setOpen] = useState(false);
  const icon = TOOL_ICONS[toolCall.tool] ?? "CMD";

  return (
    <div className="bg-white/[0.03] border border-white/[0.06] rounded text-[calc(9px*var(--fs))] overflow-hidden tool-card-enter">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-2 py-1 text-left hover:bg-white/[0.03] transition-colors"
      >
        <span className="text-[calc(7px*var(--fs))] font-mono text-accent-red/60 bg-accent-red/10 border border-accent-red/20
                         px-1 rounded shrink-0">{icon}</span>
        <span className="text-dim font-mono truncate flex-1">{toolCall.tool}</span>
        {toolCall.input && (
          <span className="text-white/20 font-mono truncate max-w-[100px]">
            {Object.entries(toolCall.input).map(([k,v]) => `${k}=${JSON.stringify(v)}`).join(" ")}
          </span>
        )}
        <span className="text-dim/40 ml-auto shrink-0">{open ? "▲" : "▼"}</span>
      </button>
      {open && toolCall.output && (
        <pre className="px-2 pb-1.5 text-[calc(8px*var(--fs))] font-mono text-accent-blue/70 overflow-x-auto max-h-36 overflow-y-auto leading-relaxed">
          {formatOutput(toolCall.output)}
        </pre>
      )}
    </div>
  );
}
