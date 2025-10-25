export default function VideoPanel({ active, streamUrl }) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900 shadow-[inset_0_0_0_1px_#ffffff0d,0_14px_30px_rgba(2,12,27,0.32)] p-4 mx-4 sm:mx-8 lg:mx-16">
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
