export default function VideoPanel({ active, streamUrl }) {
  return (
    <section className="relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-[inset_0_0_0_1px_#ffffff0d,0_14px_30px_rgba(2,12,27,0.32)] p-4">
      {/* LIVE badge (top-left) - appears only when camera is active */}
      {active && (
        <div className="absolute top-3 left-3 z-30 flex items-center gap-2 bg-white/90 text-red-600 text-xs font-semibold px-2.5 py-1 rounded-full shadow">
          <span className="h-2 w-2 rounded-full bg-red-600 animate-pulse inline-block" />
          <span>LIVE</span>
        </div>
      )}

      {!active ? (
        <div className="h-[420px] rounded-xl bg-gradient-to-b from-slate-900 to-slate-950 flex flex-col items-center justify-center text-slate-300">
          {/* ...placeholder... */}
        </div>
      ) : (
        <div className="grid place-items-center">
          <img
            src={streamUrl}
            alt="stream"
            className="rounded-xl w-full h-auto bg-black object-contain select-none"
            draggable={false}
          />
        </div>
      )}
    </section>
  );
}
