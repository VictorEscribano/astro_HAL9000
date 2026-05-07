interface Props {
  title?: string;
  children: React.ReactNode;
  className?: string;
  accent?: "red" | "blue";
  noPad?: boolean;
}

export default function PanelFrame({ title, children, className = "", accent = "red", noPad }: Props) {
  const c = accent === "red" ? "border-accent-red/50" : "border-accent-blue/50";
  const tc = accent === "red" ? "text-accent-red" : "text-accent-blue";

  return (
    <div className={`relative border border-white/[0.06] bg-panel ${noPad ? "" : ""} ${className}`}>
      {/* Corner brackets */}
      <span className={`absolute top-0 left-0 w-3 h-3 border-t border-l ${c} pointer-events-none z-10`} />
      <span className={`absolute top-0 right-0 w-3 h-3 border-t border-r ${c} pointer-events-none z-10`} />
      <span className={`absolute bottom-0 left-0 w-3 h-3 border-b border-l ${c} pointer-events-none z-10`} />
      <span className={`absolute bottom-0 right-0 w-3 h-3 border-b border-r ${c} pointer-events-none z-10`} />

      {title && (
        <div className={`absolute top-0 left-5 -translate-y-1/2 px-1.5 bg-panel
                         text-[calc(8px*var(--fs))] font-mono tracking-[0.18em] uppercase ${tc} z-10`}>
          {title}
        </div>
      )}

      <div className="w-full h-full overflow-hidden">
        {children}
      </div>
    </div>
  );
}
