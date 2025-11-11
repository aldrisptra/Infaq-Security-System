import React, { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useLocation, useNavigate } from "react-router-dom";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || "/app";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    const res = await login(email.trim(), password);
    setSubmitting(false);

    if (res.ok) {
      navigate(from, { replace: true });
    } else {
      setError(res.message || "Login gagal.");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow p-6">
        <h1 className="text-2xl font-semibold text-center mb-1">
          Login Sistem Kotak Infaq
        </h1>
        <p className="text-sm text-gray-500 text-center mb-6">
          Gunakan akunmu untuk melanjutkan
        </p>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="block text-sm mb-1">Email</label>
            <input
              type="email"
              className="w-full rounded-xl border px-3 py-2 outline-none focus:ring-2 focus:ring-emerald-500"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label className="block text-sm mb-1">Password</label>
            <input
              type="password"
              className="w-full rounded-xl border px-3 py-2 outline-none focus:ring-2 focus:ring-emerald-500"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          {error && (
            <div className="text-sm text-rose-600 bg-rose-50 border border-rose-100 rounded-xl p-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-xl bg-emerald-600 text-white py-2.5 hover:opacity-90 disabled:opacity-60"
          >
            {submitting ? "Masuk..." : "Masuk"}
          </button>

          <p className="text-xs text-gray-500 mt-1">
            (Dev cepat: email <b>admin@demo.test</b> & password <b>123456</b>)
          </p>
        </form>
      </div>
    </div>
  );
}
