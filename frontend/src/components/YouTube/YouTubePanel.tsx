import { useAppStore } from "../../store";

export default function YouTubePanel() {
  const { youtubeVideo, setYoutubeVideo } = useAppStore();

  if (!youtubeVideo) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-dim font-mono select-none">
        <div className="text-[calc(9px*var(--fs))] tracking-[0.2em] uppercase opacity-50">
          MULTIMEDIA OFFLINE
        </div>
        <div className="text-[calc(8px*var(--fs))] mt-2 opacity-30">
          Ask HAL to play something
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full w-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-1.5 shrink-0 border-b border-white/[0.06]">
        <span
          className="text-[calc(9px*var(--fs))] font-mono text-text/70 truncate max-w-[80%]"
          title={youtubeVideo.title}
        >
          {youtubeVideo.title}
        </span>
        <div className="flex items-center gap-2">
          <a
            href={youtubeVideo.url}
            target="_blank"
            rel="noreferrer"
            className="text-[calc(8px*var(--fs))] font-mono text-dim hover:text-accent-red transition-colors tracking-widest"
            title="Open in YouTube"
          >
            ↗ YT
          </a>
          <button
            onClick={() => setYoutubeVideo(null)}
            className="text-[calc(8px*var(--fs))] font-mono text-dim hover:text-accent-red transition-colors"
            title="Close"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Player */}
      <div className="flex-1 min-h-0">
        <iframe
          src={youtubeVideo.embed_url}
          title={youtubeVideo.title}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          className="w-full h-full border-0"
        />
      </div>
    </div>
  );
}
