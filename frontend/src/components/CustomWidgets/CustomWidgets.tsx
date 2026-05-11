import { useEffect, useState } from "react";
import { useAppStore, CustomWidget } from "../../store";
import PanelFrame from "../ui/PanelFrame";

const API = "/api/widgets";

export default function CustomWidgets() {
  const { customWidgets, setCustomWidgets, removeCustomWidget } = useAppStore();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeWidget, setActiveWidget] = useState<(CustomWidget & { html_content: string }) | null>(null);
  const [loadingHtml, setLoadingHtml] = useState(false);

  // Load widget list from API on mount
  useEffect(() => {
    fetch(API)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setCustomWidgets(data);
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Load full HTML when a widget is selected
  useEffect(() => {
    if (!activeId) { setActiveWidget(null); return; }
    setLoadingHtml(true);
    fetch(`${API}/${activeId}`)
      .then((r) => r.json())
      .then((data) => setActiveWidget(data))
      .catch(() => setActiveWidget(null))
      .finally(() => setLoadingHtml(false));
  }, [activeId]);

  function handleDelete(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    fetch(`${API}/${id}`, { method: "DELETE" }).catch(() => {});
    removeCustomWidget(id);
    if (activeId === id) { setActiveId(null); setActiveWidget(null); }
  }

  return (
    <PanelFrame title="CUSTOM WIDGETS" accent="red" className="h-full flex flex-col">
      <div className="flex h-full min-h-0">
        {/* Sidebar */}
        <div className="w-32 shrink-0 border-r border-white/[0.06] overflow-y-auto flex flex-col">
          {customWidgets.length === 0 ? (
            <div className="p-3 text-[calc(8px*var(--fs))] font-mono text-dim/40 text-center leading-relaxed">
              Ask HAL to create a widget
            </div>
          ) : (
            customWidgets.map((w) => (
              <button
                key={w.id}
                onClick={() => setActiveId(w.id)}
                className={`group w-full text-left px-2 py-2 border-b border-white/[0.04] transition-colors
                  ${activeId === w.id
                    ? "bg-accent-red/10 text-accent-red"
                    : "text-text/60 hover:bg-white/[0.03] hover:text-text"
                  }`}
              >
                <div className="flex items-start justify-between gap-1">
                  <span className="text-[calc(8px*var(--fs))] font-mono truncate flex-1">{w.name}</span>
                  <button
                    onClick={(e) => handleDelete(w.id, e)}
                    className="text-[calc(8px*var(--fs))] text-dim/30 hover:text-accent-red opacity-0 group-hover:opacity-100 transition-all shrink-0"
                    title="Delete widget"
                  >
                    ✕
                  </button>
                </div>
                <div className="text-[calc(7px*var(--fs))] font-mono text-dim/40 truncate mt-0.5">
                  {w.description}
                </div>
              </button>
            ))
          )}
        </div>

        {/* Widget iframe */}
        <div className="flex-1 min-w-0 min-h-0 overflow-hidden">
          {loadingHtml ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-[calc(9px*var(--fs))] font-mono text-dim animate-pulse">LOADING…</div>
            </div>
          ) : activeWidget ? (
            <iframe
              key={activeWidget.id}
              srcDoc={activeWidget.html_content}
              sandbox="allow-scripts"
              title={activeWidget.name}
              className="w-full h-full border-0"
            />
          ) : (
            <div className="flex items-center justify-center h-full text-[calc(8px*var(--fs))] font-mono text-dim/30">
              {customWidgets.length > 0 ? "← Select a widget" : "No widgets yet"}
            </div>
          )}
        </div>
      </div>
    </PanelFrame>
  );
}
