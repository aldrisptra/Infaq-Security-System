import React from "react";
import { useAuth } from "../auth/AuthContext";
import CameraSection from "../components/CameraSection"; // kalau sudah ada

export default function Dashboard() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="font-semibold">Kotak Infaq Security</div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-600 hidden sm:inline">
              {user?.name || user?.email}
            </span>
            <button
              onClick={logout}
              className="px-3 py-1.5 rounded-xl bg-gray-200 hover:bg-gray-300 text-sm"
            >
              Keluar
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        <h2 className="text-xl font-semibold mb-4">Dashboard</h2>
        {/* Taruh komponen utama kamu di sini */}
        <CameraSection />
      </main>
    </div>
  );
}
