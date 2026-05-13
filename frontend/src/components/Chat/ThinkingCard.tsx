import { useState } from "react";

/** Collapsible card that surfaces the model's `<think>…</think>` content
 *  (Qwen3-style reasoning).  Visually mirrors `ToolCallCard` so reasoning
 *  feels like another inspectable side-channel next to tool calls. */
export default function ThinkingCard({
  content,
  streaming = false,
}: {
  content: string;
  streaming?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const chars = content.length;
  const lines = content ? content.split("\n").length : 0;

  return (
    <div className="bg-white/[0.03] border border-accent-blue/15 rounded text-[calc(9px*var(--fs))] overflow-hidden tool-card-enter">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-2 py-1 text-left hover:bg-white/[0.03] transition-colors"
      >
        <span className="text-[calc(7px*var(--fs))] font-mono text-accent-blue/70 bg-accent-blue/10 border border-accent-blue/20
                         px-1 rounded shrink-0">{streaming ? "···" : "THK"}</span>
        <span className="text-dim font-mono truncate flex-1">
          internal_reasoning
          {streaming && <span className="text-accent-blue/60 animate-pulse"> · streaming</span>}
        </span>
        <span className="text-white/20 font-mono shrink-0">
          {lines}L · {chars}c
        </span>
        <span className="text-dim/40 ml-1 shrink-0">{open ? "▲" : "▼"}</span>
      </button>
      {open && content && (
        <pre className="px-2 pb-1.5 text-[calc(8px*var(--fs))] font-mono text-accent-blue/70 overflow-x-auto max-h-60 overflow-y-auto leading-relaxed whitespace-pre-wrap break-words">
          {content}
        </pre>
      )}
    </div>
  );
}
