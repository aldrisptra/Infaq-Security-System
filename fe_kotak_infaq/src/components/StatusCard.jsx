export default function StatusCard({ active, onToggle }) {
  return (
  <section className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-medium ${
              active
                ? "bg-green-100 text-green-700"
                : "bg-slate-100 text-slate-600"
            }`}
          >
            <span className="inline-block h-2 w-2 rounded-full bg-current"></span>
            {active ? "Aktif" : "Tidak Aktif"}
          </span>
          <span className="text-slate-300">Status Kamera</span>
        </div>
        <button
          onClick={onToggle}
          className={`px-3 py-2 rounded-xl text-sm font-medium shadow-sm ${
            active
              ? "bg-white text-red-700 border border-red-300 hover:bg-red-50"
              : "bg-green-600 text-white hover:bg-green-700"
          }`}
        >
          {active ? "Matikan Kamera" : "Aktifkan Kamera"}
        </button>
      </div>
    </section>
  );
}
