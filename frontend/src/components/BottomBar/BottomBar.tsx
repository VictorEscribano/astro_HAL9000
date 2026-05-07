import { useEffect, useState } from "react";

function useSimulatedMetric(base: number, variance: number, intervalMs = 3000) {
  const [val, setVal] = useState(base);
  useEffect(() => {
    const id = setInterval(() => {
      setVal(+(base + (Math.random() - 0.5) * variance * 2).toFixed(1));
    }, intervalMs);
    return () => clearInterval(id);
  }, [base, variance, intervalMs]);
  return val;
}

export default function BottomBar() {
  const [uptime, setUptime] = useState(0);
  const dataRate = useSimulatedMetric(2.3, 0.4);
  const gpu = useSimulatedMetric(42, 8);
  const memUsed = useSimulatedMetric(6.1, 0.3);

  useEffect(() => {
    const id = setInterval(() => setUptime((u) => u + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const uptimeStr = [
    String(Math.floor(uptime / 3600)).padStart(2, "0"),
    String(Math.floor((uptime % 3600) / 60)).padStart(2, "0"),
    String(uptime % 60).padStart(2, "0"),
  ].join(":");

  const items = [
    { label: "NETWORK",       value: "STABLE",               ok: true },
    { label: "DATA RATE",     value: `${dataRate} MB/S`,      ok: true },
    { label: "SYSTEM UPTIME", value: uptimeStr,               ok: true },
    { label: "GPU",           value: `${Math.round(gpu)}%`,  ok: true },
    { label: "MEMORY",        value: `${memUsed.toFixed(1)} / 8.0 GB`, ok: true },
    { label: "LOGS",          value: "NO ERRORS",             ok: true },
  ];

  return (
    <div className="flex items-center justify-between px-4 h-7 bg-panel border-t border-white/[0.06]
                    shrink-0 select-none">
      {items.map(({ label, value, ok }, i) => (
        <div key={label} className="flex items-center gap-2">
          {i > 0 && <span className="w-px h-3 bg-white/[0.08]" />}
          <span className="text-[calc(8px*var(--fs))] font-mono text-dim tracking-widest uppercase">{label}</span>
          <span className={`text-[calc(9px*var(--fs))] font-mono font-medium tracking-wider
            ${ok ? "text-accent-red" : "text-dim"}`}
            style={ok ? { textShadow: "0 0 6px rgba(255,59,59,0.35)" } : undefined}
          >
            {(label === "NETWORK" || label === "LOGS") && (
              <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle
                ${ok ? "bg-accent-red" : "bg-dim"}`}
                style={ok ? { boxShadow: "0 0 4px #FF3B3B" } : undefined}
              />
            )}
            {value}
          </span>
        </div>
      ))}
    </div>
  );
}
