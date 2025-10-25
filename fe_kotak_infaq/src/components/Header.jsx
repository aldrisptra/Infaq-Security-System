export default function InfaqHeader() {
  return (
    <header className="w-full bg-gradient-to-b from-emerald-2000 to-emerald-400/60 border-b border-emerald-400/70">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-4 flex items-center justify-center">
        {/* Left: Logo + Title */}
        <div className="flex items-center gap-3">
          {/* Logo mark */}
          <div className="shrink-0 grid place-items-center h-10 w-10 rounded-2xl bg-blue-600 text-white shadow-sm">
            {/* Shield with camera icon (inline SVG for zero deps) */}
            <svg
              viewBox="0 0 24 24"
              aria-hidden="true"
              className="h-6 w-6"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {/* shield */}
              <path
                d="M12 2.5l7 2.5v6.2c0 4.4-2.9 8.4-7 9.8-4.1-1.4-7-5.4-7-9.8V5l7-2.5z"
                fill="currentColor"
                opacity=".2"
              />
              <path d="M12 2.5l7 2.5v6.2c0 4.4-2.9 8.4-7 9.8-4.1-1.4-7-5.4-7-9.8V5l7-2.5z" />
              {/* tiny camera */}
              <rect x="8.5" y="9" width="7" height="5" rx="1.2" />
              <circle cx="12" cy="11.5" r="1.4" />
              <path d="M9.5 9l.6-1h3.8l.6 1" />
            </svg>
          </div>

          {/* Title + Subtitle */}
          <div className="leading-tight">
            <h1 className="text-xl font-semibold tracking-tight text-slate-900">
              INFAQ
            </h1>
            <p className="text-sm text-slate-900">Infaq Security System</p>
          </div>
        </div>
      </div>
    </header>
  );
}
