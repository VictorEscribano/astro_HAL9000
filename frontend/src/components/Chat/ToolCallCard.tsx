import { useState } from "react";
import { ToolCall, useAppStore } from "../../store";

// Keys here are the *Pydantic class names* the backend emits in tool_start /
// tool_end events (`type(call).__name__`), not the snake_case dispatch keys.
const TOOL_ICONS: Record<string, string> = {
  PythonExec:                "⟨/⟩",
  SkyTonightQuery:           "SKY",
  ObjectPositionQuery:       "POS",
  MoonInfoQuery:             "MN",
  SatellitePassesQuery:      "SAT",
  SatelliteGroundTrack:      "TRK",
  TrackingFeasibilityCheck:  "CHK",
  MountGoto:                 "MNT",
  MountTrack:                "TRK",
  MountPark:                 "PRK",
  MountAbort:                "ABT",
  WeatherQuery:              "WX",
  SatelliteSearch:           "SRH",
  WebSearch:                 "WEB",
  CameraExposure:            "CAM",
  CameraSequence:            "CAM",
};

function formatOutput(output: unknown): string {
  if (output == null) return "";
  if (typeof output === "object") {
    try { return JSON.stringify(output, null, 2); }
    catch { return String(output); }
  }
  if (typeof output !== "string") return String(output);
  try { return JSON.stringify(JSON.parse(output), null, 2); }
  catch { return output; }
}

/** Short, single-line preview of the tool's input arguments — shown in
 *  the collapsed card header.  Long values (like a multi-line `code`
 *  field) are truncated to the first line. */
function inputPreview(input: Record<string, unknown> | undefined): string {
  if (!input) return "";
  return Object.entries(input)
    .map(([k, v]) => {
      if (typeof v === "string") {
        const firstLine = v.split("\n")[0];
        const trimmed = firstLine.length > 60 ? firstLine.slice(0, 60) + "…" : firstLine;
        return `${k}="${trimmed}"`;
      }
      return `${k}=${JSON.stringify(v)}`;
    })
    .join(" ");
}

/** Type-guard for the python_exec envelope shape so we can render its
 *  fields (`code`/`stdout`/`result`/`error`) as separate sections. */
interface PythonExecOutput {
  ok?: boolean;
  result?: unknown;
  stdout?: string;
  error?: string | null;
}
function asPythonExecOutput(out: unknown): PythonExecOutput | null {
  if (!out || typeof out !== "object") return null;
  const o = out as Record<string, unknown>;
  if (!("ok" in o) && !("stdout" in o) && !("result" in o)) return null;
  return o as PythonExecOutput;
}

export default function ToolCallCard({ toolCall }: { toolCall: ToolCall }) {
  const [open, setOpen] = useState(false);
  const openCodeInEditor = useAppStore((s) => s.openCodeInEditor);
  const icon = TOOL_ICONS[toolCall.tool] ?? "CMD";
  const isPythonExec = toolCall.tool === "PythonExec";
  const code = isPythonExec && typeof toolCall.input?.code === "string"
    ? (toolCall.input.code as string)
    : null;
  const pyOut = isPythonExec ? asPythonExecOutput(toolCall.output) : null;

  return (
    <div className="bg-white/[0.03] border border-white/[0.06] rounded text-[calc(9px*var(--fs))] overflow-hidden tool-card-enter">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-2 py-1 text-left hover:bg-white/[0.03] transition-colors"
      >
        <span className="text-[calc(7px*var(--fs))] font-mono text-accent-red/60 bg-accent-red/10 border border-accent-red/20
                         px-1 rounded shrink-0">{icon}</span>
        <span className="text-dim font-mono truncate flex-1">{toolCall.tool}</span>
        <span className="text-white/20 font-mono truncate max-w-[160px]">
          {inputPreview(toolCall.input)}
        </span>
        <span className="text-dim/40 ml-auto shrink-0">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="px-2 pb-1.5 space-y-1.5">
          {/* For python_exec, surface the code as its own section so the
              user can read what was actually run.  The "OPEN IN EDITOR"
              button loads it into the Code Inspector tab on the right
              panel for editing. */}
          {code !== null && (
            <div>
              <div className="flex items-center justify-between mt-1 mb-0.5">
                <div className="text-[calc(7px*var(--fs))] font-mono text-dim/70 tracking-widest">CODE</div>
                <button
                  onClick={(e) => { e.stopPropagation(); openCodeInEditor(code); }}
                  className="text-[calc(7px*var(--fs))] font-mono text-accent-red/80 hover:text-accent-red
                             border border-accent-red/30 hover:border-accent-red/60 bg-accent-red/5
                             px-1.5 py-0.5 rounded tracking-widest transition-colors"
                  title="Load this code into the Code Inspector tab so you can edit it"
                >
                  ⟨/⟩ OPEN IN EDITOR
                </button>
              </div>
              <pre className="text-[calc(8px*var(--fs))] font-mono text-accent-red/80 bg-black/30 rounded px-1.5 py-1
                              overflow-x-auto max-h-48 overflow-y-auto leading-relaxed whitespace-pre">
                {code}
              </pre>
            </div>
          )}

          {/* Structured python_exec envelope */}
          {pyOut && (
            <>
              {pyOut.stdout && (
                <div>
                  <div className="text-[calc(7px*var(--fs))] font-mono text-dim/70 tracking-widest mb-0.5">STDOUT</div>
                  <pre className="text-[calc(8px*var(--fs))] font-mono text-text/70 bg-black/30 rounded px-1.5 py-1
                                  overflow-x-auto max-h-32 overflow-y-auto leading-relaxed whitespace-pre-wrap">
                    {pyOut.stdout}
                  </pre>
                </div>
              )}
              {pyOut.result !== undefined && pyOut.result !== null && (
                <div>
                  <div className="text-[calc(7px*var(--fs))] font-mono text-dim/70 tracking-widest mb-0.5">RESULT</div>
                  <pre className="text-[calc(8px*var(--fs))] font-mono text-accent-blue/80 bg-black/30 rounded px-1.5 py-1
                                  overflow-x-auto max-h-40 overflow-y-auto leading-relaxed whitespace-pre-wrap">
                    {formatOutput(pyOut.result)}
                  </pre>
                </div>
              )}
              {pyOut.error && (
                <div>
                  <div className="text-[calc(7px*var(--fs))] font-mono text-red-400/80 tracking-widest mb-0.5">ERROR</div>
                  <pre className="text-[calc(8px*var(--fs))] font-mono text-red-300/80 bg-red-950/30 rounded px-1.5 py-1
                                  overflow-x-auto max-h-32 overflow-y-auto leading-relaxed whitespace-pre-wrap">
                    {pyOut.error}
                  </pre>
                </div>
              )}
            </>
          )}

          {/* Generic output for non-python_exec tools (or python_exec without
              a recognisable envelope, e.g. when the wrapper itself failed). */}
          {!pyOut && toolCall.output != null && (
            <div>
              <div className="text-[calc(7px*var(--fs))] font-mono text-dim/70 tracking-widest mb-0.5">OUTPUT</div>
              <pre className="text-[calc(8px*var(--fs))] font-mono text-accent-blue/70 bg-black/30 rounded px-1.5 py-1
                              overflow-x-auto max-h-48 overflow-y-auto leading-relaxed whitespace-pre-wrap break-words">
                {formatOutput(toolCall.output)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
