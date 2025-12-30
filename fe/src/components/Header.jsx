// Header.jsx
import TextType from "./TextType.jsx";

export default function Header({ onLogout }) {
  // <-- terima props onLogout
  return (
    <nav className="bg-emerald-900 shadow-md z-50">
      <div className="max-w-7xl mx-auto px-6 py-4">
        <div className="flex items-center justify-between">
          {/* Kiri: logo + judul */}
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg">
              <img
                src="/assets/logo.png"
                alt="Logo"
                className="w-10 h-10 object-contain bg-amber-50 rounded-lg"
              />
            </div>

            <div>
              <h1 className="text-white text-sm md:text-4xl font-bold leading-tight">
                <TextType
                  text={["Infaq Security System", "Infaq SecuritySystem"]}
                  typingSpeed={75}
                  pauseDuration={1500}
                  showCursor={true}
                  cursorCharacter="|"
                  highlight="Security System"
                  highlightClass="text-emerald-300"
                />
              </h1>
              <p className="text-xs text-emerald-300/80">
                Monitoring Kotak Infaq Real-time
              </p>
            </div>
          </div>

          {/* Kanan: tombol Logout */}
          <div className="flex items-center gap-3">
            {onLogout && (
              <button
                type="button"
                onClick={onLogout}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-teal-600 text-white hover:bg-teal-700 active:scale-95 transition"
              >
                Logout
              </button>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
