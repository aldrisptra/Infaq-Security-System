import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import RoiSelector from "./RoiSelector.jsx";
import Header from "./Header.jsx";

const API_BASE = "http://localhost:8000";

export default function CameraSection() {
  const navigate = useNavigate();

  const [mode, setMode] = useState("webcam"); // webcam | video | ipcam
  const [videoPath, setVideoPath] = useState("sample/mesjid_kotak.mp4");
  const [ipcamUrl, setIpcamUrl] = useState("");

  const [active, setActive] = useState(false);
  const [streamUrl, setStreamUrl] = useState("");
  const [statusText, setStatusText] = useState("");
  const [alertStatus, setAlertStatus] = useState(null);
  const [history, setHistory] = useState([]);

  const lastAlertRef = useRef(null);

  // =========================
  // Load default camera dari DB
  // =========================
  useEffect(() => {
    const token = localStorage.getItem("authToken");
    if (!token) {
      navigate("/login", { replace: true });
      return;
    }

    fetch(`${API_BASE}/camera/default`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((cfg) => {
        if (!cfg) return;

        if (cfg.source === "ipcam") {
          setMode("ipcam");
          setIpcamUrl(cfg.path || "");
        } else if (cfg.source === "video") {
          setMode("video");
          setVideoPath(cfg.path || "sample/mesjid_kotak.mp4");
        } else {
          setMode("webcam");
        }
      })
      .catch(() => {});
  }, [navigate]);

  // =========================
  // Polling status kamera
  // =========================
  const refreshStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/camera/status`);
      if (!response.ok) return;

      const data = await response.json();
      const { running, alert_status } = data;

      setActive(running);
      setAlertStatus(alert_status);

      // add history kalau status berubah
      const last = lastAlertRef.current;
      if (alert_status && alert_status !== last) {
        lastAlertRef.current = alert_status;

        const newEvent = {
          id: Date.now(),
          status: alert_status,
          timestamp: new Date().toLocaleString("id-ID"),
          message:
            alert_status === "missing"
              ? "⚠️ Kotak infaq tidak terdeteksi!"
              : "✓ Kotak infaq terdeteksi",
        };

        setHistory((prev) => [newEvent, ...prev].slice(0, 10));
      }

      if (running) {
        setStreamUrl(`${API_BASE}/camera/stream?ts=${Date.now()}`);
      } else {
        setStreamUrl("");
      }
    } catch (err) {
      // silent
    }
  };

  useEffect(() => {
    refreshStatus();
    const t = setInterval(refreshStatus, 1500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // =========================
  // Start manual (sesuai mode)
  // =========================
  const startCam = async () => {
    try {
      setStatusText("");

      const params = new URLSearchParams();

      if (mode === "video") {
        params.append("source", "video");
        params.append("path", videoPath);
        params.append("loop", "true");
      } else if (mode === "ipcam") {
        if (!ipcamUrl) throw new Error("IP Camera URL masih kosong");
        params.append("source", "ipcam");
        params.append("path", ipcamUrl);
        params.append("loop", "true");
      } else {
        params.append("source", "webcam");
        params.append("index", "0");
      }

      const res = await fetch(`${API_BASE}/camera/start?${params.toString()}`, {
        method: "POST",
      });

      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || "Gagal start kamera");
      }

      setActive(true);
      setStreamUrl(`${API_BASE}/camera/stream?ts=${Date.now()}`);
    } catch (err) {
      setStatusText(`Gagal start: ${err.message}`);
    }
  };

  // =========================
  // Start dari default DB
  // =========================
  const startDefaultFromDb = async () => {
    const token = localStorage.getItem("authToken");
    if (!token) {
      navigate("/login", { replace: true });
      return;
    }

    try {
      setStatusText("");

      const res = await fetch(`${API_BASE}/camera/start-default`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || "Gagal start default camera");
      }

      // refresh status & stream
      await refreshStatus();
    } catch (err) {
      setStatusText(`Gagal start default: ${err.message}`);
    }
  };

  const stopCam = async () => {
    try {
      await fetch(`${API_BASE}/camera/stop`, { method: "POST" });
      setActive(false);
      setStreamUrl("");
      setStatusText("");
      setAlertStatus(null);
      lastAlertRef.current = null;
    } catch (err) {
      setStatusText(`Gagal stop: ${err.message}`);
    }
  };

  const handleLogout = async () => {
    try {
      if (active) await stopCam();
    } catch (_) {}

    localStorage.removeItem("authToken");
    navigate("/login", { replace: true });
  };

  const clearHistory = () => setHistory([]);

  // =========================
  // UI
  // =========================
  return (
    <div className="min-h-screen bg-emerald-900">
      <Header onLogout={handleLogout} />

      <div className="max-w-7xl mx-auto">
        {/* Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6 py-6 px-4 sm:px-7">
          {/* Camera Status */}
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

          {/* Box Status */}
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

          {/* Total Kejadian */}
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

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 sm:px-7 px-4 pb-6">
          {/* Left */}
          <div className="lg:col-span-2 space-y-6">
            {/* Controls */}
            <div className="bg-white rounded-xl shadow-lg p-6">
              <h2 className="text-xl font-bold text-gray-800 mb-4 flex items-center">
                <span className="mr-2">🎛️</span> Kontrol Kamera
              </h2>

              <div className="flex flex-wrap gap-3 items-center">
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  className="border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="webcam">🎥 Webcam</option>
                  <option value="video">📹 Video File</option>
                  <option value="ipcam">📱 IP Camera</option>
                </select>

                {mode === "video" && (
                  <input
                    type="text"
                    value={videoPath}
                    onChange={(e) => setVideoPath(e.target.value)}
                    placeholder="sample/mesjid_kotak.mp4"
                    className="flex-1 min-w-[280px] border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                )}

                {mode === "ipcam" && (
                  <input
                    type="text"
                    value={ipcamUrl}
                    onChange={(e) => setIpcamUrl(e.target.value)}
                    placeholder="http://192.168.1.8:4747/video"
                    className="flex-1 min-w-[280px] border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                )}

                {!active ? (
                  <>
                    <button
                      onClick={startCam}
                      className="px-6 py-2.5 bg-gradient-to-r from-teal-600 to-teal-700 text-white font-medium rounded-lg hover:from-teal-700 hover:to-teal-800 active:scale-95 transition-all shadow-md"
                    >
                      Start Kamera
                    </button>
                    <button
                      onClick={startDefaultFromDb}
                      className="px-5 py-2.5 bg-white border border-emerald-200 text-emerald-800 font-medium rounded-lg hover:bg-emerald-50 active:scale-95 transition-all"
                      title="Ambil sumber kamera default dari database"
                    >
                      Start Default (DB)
                    </button>
                  </>
                ) : (
                  <button
                    onClick={stopCam}
                    className="px-6 py-2.5 bg-gradient-to-r from-red-500 to-red-600 text-white font-medium rounded-lg hover:from-red-600 hover:to-red-700 active:scale-95 transition-all shadow-md"
                  >
                    Stop Kamera
                  </button>
                )}
              </div>

              {statusText && (
                <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm text-red-600">{statusText}</p>
                </div>
              )}
            </div>

            {/* Video Feed */}
            <div className="bg-white rounded-xl shadow-lg p-6">
              <h2 className="text-xl font-bold text-gray-800 mb-4 flex items-center">
                <span className="mr-2">📡</span> Live Camera
              </h2>

              {active ? (
                <RoiSelector streamUrl={streamUrl} apiBase={API_BASE} />
              ) : (
                <div className="text-center py-20 bg-gradient-to-br from-gray-50 to-gray-100 rounded-lg border-2 border-dashed border-gray-300">
                  <p className="text-gray-500 font-medium">
                    Kamera belum aktif
                  </p>
                  <p className="text-sm text-gray-400 mt-1">
                    Klik "Start Kamera" atau "Start Default (DB)"
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Right - History */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-xl shadow-lg p-6 sticky top-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold text-gray-800 flex items-center">
                  <span className="mr-2">🕒</span> Riwayat Kejadian
                </h2>
                {history.length > 0 && (
                  <button
                    onClick={clearHistory}
                    className="text-xs text-gray-500 hover:text-red-600"
                  >
                    Clear
                  </button>
                )}
              </div>

              <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
                {history.length === 0 ? (
                  <div className="text-center py-10">
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
                      }`}
                    >
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
