import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import RoiSelector from "./RoiSelector.jsx";
import Header from "./Header.jsx";

const API_BASE = "http://localhost:8000";

export default function CameraSection() {
  const [mode, setMode] = useState("video");
  const [videoPath, setVideoPath] = useState("sample/mesjid_kotak.mp4");
  const [active, setActive] = useState(false);
  const [streamUrl, setStreamUrl] = useState("");
  const [statusText, setStatusText] = useState("");
  const [alertStatus, setAlertStatus] = useState(null);
  const [history, setHistory] = useState([]);
  const navigate = useNavigate();

  // Fetch camera status
  const refreshStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/camera/status`);
      const { running, alert_status } = await response.json();

      // Deteksi perubahan status dan tambahkan ke history
      if (alert_status && alert_status !== alertStatus) {
        const newEvent = {
          id: Date.now(),
          status: alert_status,
          timestamp: new Date().toLocaleString("id-ID"),
          message:
            alert_status === "missing"
              ? "⚠️ Kotak infaq tidak terdeteksi!"
              : "✓ Kotak infaq terdeteksi",
        };

        setHistory((prev) => [newEvent, ...prev].slice(0, 10)); // Simpan max 10 riwayat
      }

      setActive(running);
      setAlertStatus(alert_status);
      if (running) {
        setStreamUrl(`${API_BASE}/camera/stream?ts=${Date.now()}`);
      }
    } catch (error) {
      setActive(false);
      console.error("Failed to fetch status:", error);
    }
  };

  useEffect(() => {
    refreshStatus();
    const interval = setInterval(refreshStatus, 2000);
    return () => clearInterval(interval);
  }, [alertStatus]);

  const startCam = async () => {
    try {
      const params = new URLSearchParams();

      if (mode === "video") {
        params.append("source", "video");
        params.append("path", videoPath);
        params.append("loop", "true");
      } else {
        params.append("source", "webcam");
      }

      const response = await fetch(`${API_BASE}/camera/start?${params}`, {
        method: "POST",
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      setStreamUrl(`${API_BASE}/camera/stream?ts=${Date.now()}`);
      setActive(true);
      setStatusText("");
    } catch (error) {
      setStatusText(`Gagal start: ${error.message}`);
      console.error("Start camera error:", error);
    }
  };

  const stopCam = async () => {
    try {
      await fetch(`${API_BASE}/camera/stop`, { method: "POST" });
      setActive(false);
      setStreamUrl("");
      setStatusText("");
      setAlertStatus(null);
    } catch (error) {
      setStatusText(`Gagal stop: ${error.message}`);
      console.error("Stop camera error:", error);
    }
  };

  const handleLogout = async () => {
    try {
      // kalau kamera lagi aktif, kita stop dulu (biar rapi)
      if (active) {
        await stopCam();
      }
    } catch (e) {
      console.error("Gagal stop kamera saat logout:", e);
    }

    // hapus token auth
    localStorage.removeItem("authToken");

    // arahkan balik ke halaman login
    navigate("/login", { replace: true });
  };

  const clearHistory = () => {
    setHistory([]);
  };

  return (
    <div className="min-h-screen bg-emerald-900">
      {/* Navbar + tombol Logout */}
      <Header onLogout={handleLogout} />

      <div className="max-w-7xl mx-auto">
        {/* Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6 py-6 px-4 sm:px-7">
          {/* Camera Status Card */}
          <div className="bg-white rounded-xl shadow-lg p-6 border-l-4 border-blue-500">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500 font-medium">
                  Status Kamera
                </p>
                <p
                  className={`text-2xl font-bold mt-1 ${
                    active ? "text-emerald-700" : "text-gray-400"
                  }`}
                >
                  {active ? "Aktif" : "Nonaktif"}
                </p>
              </div>
              <div
                className={`p-3 rounded-full ${
                  active ? "bg-emerald-100" : "bg-gray-100"
                }`}
              >
                <svg
                  className={`w-8 h-8 ${
                    active ? "text-emerald-700" : "text-gray-400"
                  }`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                  />
                </svg>
              </div>
            </div>
          </div>

          {/* Box Status Card */}
          <div
            className={`bg-white rounded-xl shadow-lg p-6 border-l-4 ${
              alertStatus === "missing"
                ? "border-red-500"
                : "border-emerald-700"
            }`}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500 font-medium">
                  Status Kotak
                </p>
                <p
                  className={`text-2xl font-bold mt-1 ${
                    alertStatus === "missing"
                      ? "text-red-600"
                      : "text-emerald-700"
                  }`}
                >
                  {alertStatus === "missing"
                    ? "Hilang"
                    : alertStatus === "present"
                    ? "Aman"
                    : "-"}
                </p>
              </div>
              <div
                className={`p-3 rounded-full ${
                  alertStatus === "missing" ? "bg-red-100" : "bg-emerald-100"
                }`}
              >
                <svg
                  className={`w-8 h-8 ${
                    alertStatus === "missing"
                      ? "text-red-600"
                      : "text-emerald-700"
                  }`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
                  />
                </svg>
              </div>
            </div>
          </div>

          {/* Alert Count Card */}
          <div className="bg-white rounded-xl shadow-lg p-6 border-l-4 border-emerald-700">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500 font-medium">
                  Total Kejadian
                </p>
                <p className="text-2xl font-bold text-emerald-700 mt-1">
                  {history.length}
                </p>
              </div>
              <div className="p-3 rounded-full bg-emerald-100">
                <svg
                  className="w-8 h-8 text-emerald-700"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
              </div>
            </div>
          </div>
        </div>
        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 sm:px-7 px-4 pb-6">
          {/* Left Column - Camera Feed */}
          <div className="lg:col-span-2 space-y-6">
            {/* Controls Card */}
            <div className="bg-white rounded-xl shadow-lg p-6 ">
              <h2 className="text-xl font-bold text-gray-800 mb-4 flex items-center">
                <svg
                  className="w-6 h-6 mr-2 text-blue-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"
                  />
                </svg>
                Kontrol Kamera
              </h2>

              <div className="flex flex-wrap gap-3 items-center">
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  className="border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="video">📹 Video File</option>
                  <option value="webcam">🎥 Webcam</option>
                </select>

                {mode === "video" && (
                  <input
                    type="text"
                    value={videoPath}
                    onChange={(e) => setVideoPath(e.target.value)}
                    placeholder="path/to/video.mp4"
                    className="flex-1 min-w-[300px] border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                )}

                {!active ? (
                  <button
                    onClick={startCam}
                    className="px-6 py-2.5 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-lg hover:from-blue-600 hover:to-blue-700 active:scale-95 transition-all shadow-md flex items-center gap-2"
                  >
                    <svg
                      className="w-5 h-5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                      />
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    Start Kamera
                  </button>
                ) : (
                  <button
                    onClick={stopCam}
                    className="px-6 py-2.5 bg-gradient-to-r from-red-500 to-red-600 text-white font-medium rounded-lg hover:from-red-600 hover:to-red-700 active:scale-95 transition-all shadow-md flex items-center gap-2"
                  >
                    <svg
                      className="w-5 h-5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z"
                      />
                    </svg>
                    Stop Kamera
                  </button>
                )}
              </div>

              {statusText && (
                <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm text-red-600 flex items-center gap-2">
                    <svg
                      className="w-4 h-4"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
                      <path
                        fillRule="evenodd"
                        d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                        clipRule="evenodd"
                      />
                    </svg>
                    {statusText}
                  </p>
                </div>
              )}
            </div>

            {/* Video Feed Card */}
            <div className="bg-white rounded-xl shadow-lg p-6">
              <h2 className="text-xl font-bold text-gray-800 mb-4 flex items-center">
                <svg
                  className="w-6 h-6 mr-2 text-blue-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                  />
                </svg>
                Live Camera
              </h2>

              {active ? (
                <RoiSelector streamUrl={streamUrl} apiBase={API_BASE} />
              ) : (
                <div className="text-center py-20 bg-gradient-to-br from-gray-50 to-gray-100 rounded-lg border-2 border-dashed border-gray-300">
                  <svg
                    className="w-16 h-16 mx-auto text-gray-400 mb-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                    />
                  </svg>
                  <p className="text-gray-500 font-medium">
                    Kamera belum aktif
                  </p>
                  <p className="text-sm text-gray-400 mt-1">
                    Klik "Start Kamera" untuk memulai monitoring
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Right Column - History */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-xl shadow-lg p-6 sticky top-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold text-gray-800 flex items-center">
                  <svg
                    className="w-6 h-6 mr-2 text-emerald-700"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                  Riwayat Kejadian
                </h2>
                {history.length > 0 && (
                  <button
                    onClick={clearHistory}
                    className="text-xs text-gray-500 hover:text-red-600 transition-colors"
                  >
                    Clear
                  </button>
                )}
              </div>

              <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
                {history.length === 0 ? (
                  <div className="text-center py-12">
                    <svg
                      className="w-12 h-12 mx-auto text-gray-300 mb-3"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                      />
                    </svg>
                    <p className="text-sm text-gray-400">Belum ada kejadian</p>
                  </div>
                ) : (
                  history.map((event) => (
                    <div
                      key={event.id}
                      className={`p-4 rounded-lg border-l-4 ${
                        event.status === "missing"
                          ? "bg-red-50 border-red-500"
                          : "bg-green-50 border-green-500"
                      } transition-all hover:shadow-md`}
                    >
                      <div className="flex items-start gap-3">
                        <div
                          className={`p-2 rounded-full ${
                            event.status === "missing"
                              ? "bg-red-100"
                              : "bg-green-100"
                          }`}
                        >
                          {event.status === "missing" ? (
                            <svg
                              className="w-4 h-4 text-red-600"
                              fill="currentColor"
                              viewBox="0 0 20 20"
                            >
                              <path
                                fillRule="evenodd"
                                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                                clipRule="evenodd"
                              />
                            </svg>
                          ) : (
                            <svg
                              className="w-4 h-4 text-green-600"
                              fill="currentColor"
                              viewBox="0 0 20 20"
                            >
                              <path
                                fillRule="evenodd"
                                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                                clipRule="evenodd"
                              />
                            </svg>
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p
                            className={`text-sm font-medium ${
                              event.status === "missing"
                                ? "text-red-800"
                                : "text-green-800"
                            }`}
                          >
                            {event.message}
                          </p>
                          <p className="text-xs text-gray-500 mt-1">
                            {event.timestamp}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
