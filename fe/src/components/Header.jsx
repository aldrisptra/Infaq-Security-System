export default function Header() {
  return (
    <nav className="bg-teal-500 shadow-md z-50">
      <div className="max-w-7xl mx-auto px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg">
              <img
                src="/assets/logo.png"
                alt="Logo"
                className="w-10 h-10 object-contain"
              />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">
                Infaq Security System
              </h1>
              <p className="text-xs text-white/80">
                Monitoring Kotak Infaq Real-time
              </p>
            </div>
          </div>
        </div>
      </div>
    </nav>
  );
}
