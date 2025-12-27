import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";

const API_BASE_URL = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

export default function RegisterPage() {
  const navigate = useNavigate();

  const [namaMasjid, setNamaMasjid] = useState("");
  const [alamat, setAlamat] = useState("");
  const [tgChatId, setTgChatId] = useState("");

  const [cameraNama, setCameraNama] = useState("Kamera Utama");
  const [cameraUrl, setCameraUrl] = useState("");

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setErrorMsg("");
    setSuccessMsg("");
    setIsSubmitting(true);

    try {
      const payload = {
        nama_masjid: namaMasjid,
        alamat: alamat || null,
        tg_chat_id: tgChatId || null,
        camera_nama: cameraNama || "Kamera Utama",
        camera_url: cameraUrl,
        username,
        password,
      };

      const res = await fetch(`${API_BASE_URL}/auth/register-masjid`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        let detail = "Registrasi gagal.";
        try {
          const data = await res.json();
          if (data?.detail) detail = data.detail;
        } catch (_) {}
        throw new Error(detail);
      }

      const data = await res.json();

      setSuccessMsg(
        `Berhasil daftar! Masjid ID: ${data.masjid_id}. Silakan login.`
      );

      // arahkan ke login setelah 1 detik
      setTimeout(() => navigate("/login"), 800);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-emerald-900 via-slate-900 to-emerald-700">
      <div className="w-full max-w-lg bg-white/95 rounded-2xl shadow-2xl p-8 mx-4">
        <div className="flex flex-col items-center mb-6">
          <div className="w-14 h-14 rounded-2xl bg-emerald-100 flex items-center justify-center mb-3">
            <span className="text-3xl">🕌</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-800 text-center">
            Registrasi Masjid
          </h1>
          <p className="text-sm text-slate-500 text-center mt-1">
            Buat akun admin + data masjid + konfigurasi kamera awal
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* MASJID */}
          <div className="p-4 rounded-xl border border-slate-200">
            <p className="text-xs font-semibold text-slate-500 mb-3">
              Data Masjid
            </p>

            <label className="block text-sm font-medium text-slate-700 mb-1">
              Nama Masjid
            </label>
            <input
              type="text"
              required
              value={namaMasjid}
              onChange={(e) => setNamaMasjid(e.target.value)}
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
              placeholder="Masjid Al-Ikhlas"
            />

            <label className="block text-sm font-medium text-slate-700 mb-1 mt-3">
              Alamat (opsional)
            </label>
            <textarea
              value={alamat}
              onChange={(e) => setAlamat(e.target.value)}
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
              placeholder="Jl. ..."
              rows={2}
            />

            <label className="block text-sm font-medium text-slate-700 mb-1 mt-3">
              Telegram Chat ID (opsional dulu)
            </label>
            <input
              type="text"
              value={tgChatId}
              onChange={(e) => setTgChatId(e.target.value)}
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
              placeholder="contoh: 1215968232"
            />
            <p className="text-[11px] text-slate-400 mt-1">
              Nanti bisa kamu pakai untuk notifikasi per masjid.
            </p>
          </div>

          {/* KAMERA */}
          <div className="p-4 rounded-xl border border-slate-200">
            <p className="text-xs font-semibold text-slate-500 mb-3">
              Kamera Masjid
            </p>

            <label className="block text-sm font-medium text-slate-700 mb-1">
              Nama Kamera
            </label>
            <input
              type="text"
              value={cameraNama}
              onChange={(e) => setCameraNama(e.target.value)}
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
              placeholder="Kamera Utama"
            />

            <label className="block text-sm font-medium text-slate-700 mb-1 mt-3">
              URL / Stream Kamera
            </label>
            <input
              type="text"
              required
              value={cameraUrl}
              onChange={(e) => setCameraUrl(e.target.value)}
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
              placeholder="http://... atau rtsp://..."
            />
            <p className="text-[11px] text-slate-400 mt-1">
              Bisa isi link DroidCam / IP cam / RTSP.
            </p>
          </div>

          {/* ADMIN */}
          <div className="p-4 rounded-xl border border-slate-200">
            <p className="text-xs font-semibold text-slate-500 mb-3">
              Akun Admin Masjid
            </p>

            <label className="block text-sm font-medium text-slate-700 mb-1">
              Username
            </label>
            <input
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
              placeholder="admin_masjid_xxx"
            />

            <label className="block text-sm font-medium text-slate-700 mb-1 mt-3">
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
              placeholder="••••••••"
            />
          </div>

          {errorMsg && (
            <div className="rounded-xl bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
              {errorMsg}
            </div>
          )}

          {successMsg && (
            <div className="rounded-xl bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs text-emerald-700">
              {successMsg}
            </div>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full inline-flex items-center justify-center rounded-xl bg-emerald-600 text-white text-sm font-semibold py-2.5 hover:bg-emerald-700 disabled:opacity-60 disabled:cursor-not-allowed transition"
          >
            {isSubmitting ? "Mendaftarkan..." : "Daftarkan Masjid"}
          </button>
        </form>

        <div className="mt-4 text-center">
          <Link
            to="/login"
            className="text-xs text-slate-500 hover:text-emerald-700"
          >
            Sudah punya akun? Login
          </Link>
        </div>
      </div>
    </div>
  );
}
