import { useState } from "react";
import { useNavigate } from "react-router-dom";

const API_BASE_URL = "http://localhost:8000";

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setErrorMsg("");
    setIsSubmitting(true);

    try {
      const body = new URLSearchParams();
      body.append("username", username);
      body.append("password", password);
      body.append("scope", "");

      const res = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body,
      });

      if (!res.ok) {
        let detail = "Login gagal. Periksa kembali username / password.";
        try {
          const data = await res.json();
          if (data?.detail) detail = data.detail;
        } catch (_) {}
        throw new Error(detail);
      }

      const data = await res.json();

      localStorage.setItem("authToken", data.access_token);

      navigate("/camera");
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-emerald-900 via-slate-900 to-emerald-700">
      <div className="w-full max-w-md bg-white/95 rounded-2xl shadow-2xl p-8 mx-4">
        <div className="flex flex-col items-center mb-6">
          <div className="w-14 h-14 rounded-2xl bg-emerald-100 flex items-center justify-center mb-3">
            <span className="text-3xl">🔒</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-800 text-center">
            Infaq Security System
          </h1>
          <p className="text-sm text-slate-500 text-center mt-1">
            Login admin masjid untuk mengatur kamera dan posisi ROI kotak infaq
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="username"
              className="block text-sm font-medium text-slate-700 mb-1"
            >
              Username
            </label>
            <input
              id="username"
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
              placeholder="contoh: admin_masjid_demo"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-slate-700 mb-1"
            >
              Password
            </label>
            <input
              id="password"
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

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full inline-flex items-center justify-center rounded-xl bg-emerald-600 text-white text-sm font-semibold py-2.5 mt-2 hover:bg-emerald-700 disabled:opacity-60 disabled:cursor-not-allowed transition"
          >
            {isSubmitting ? "Masuk..." : "Masuk sebagai Admin"}
          </button>
        </form>

        <p className="mt-4 text-[11px] text-slate-400 text-center">
          Gunakan akun admin yang sudah dibuat di database.
        </p>
        <p className="mt-2 text-[11px] text-slate-400 text-center">
          Belum punya akun?{" "}
          <a href="/register" className="text-emerald-700 hover:underline">
            Registrasi Masjid
          </a>
        </p>
      </div>
    </div>
  );
}
