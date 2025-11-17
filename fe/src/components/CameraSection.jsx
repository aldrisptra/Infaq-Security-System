import React, { useEffect, useState } from "react";
import RoiSelector from "./RoiSelector.jsx";

const API_BASE = "http://localhost:8000";

export default function CameraSection() {
  const [mode, setMode] = useState("video");
  const [videoPath, setVideoPath] = useState("sample/mesjid_kotak.mp4");
  const [active, setActive] = useState(false);
  const [streamUrl, setStreamUrl] = useState("");
  const [statusText, setStatusText] = useState("");

  // Fetch camera status
  const refreshStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/camera/status`);
      const { running } = await response.json();
      setActive(running);
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
  }, []);

  // Start camera
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

  // Stop camera
  const stopCam = async () => {
    try {
      await fetch(`${API_BASE}/camera/stop`, { method: "POST" });
      setActive(false);
      setStreamUrl("");
      setStatusText("");
    } catch (error) {
      setStatusText(`Gagal stop: ${error.message}`);
      console.error("Stop camera error:", error);
    }
  };

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          className="border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="video">Video file</option>
          <option value="webcam">Webcam</option>
        </select>

        {mode === "video" && (
          <input
            type="text"
            value={videoPath}
            onChange={(e) => setVideoPath(e.target.value)}
            placeholder="path/to/video.mp4"
            className="flex-1 min-w-[300px] border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        )}

        {!active ? (
          <button
            onClick={startCam}
            className="px-6 py-2 bg-blue-500 text-white font-medium rounded-md hover:bg-blue-600 active:bg-blue-700 transition-colors"
          >
            Start Kamera
          </button>
        ) : (
          <button
            onClick={stopCam}
            className="px-6 py-2 bg-red-500 text-white font-medium rounded-md hover:bg-red-600 active:bg-red-700 transition-colors"
          >
            Stop Kamera
          </button>
        )}
      </div>

      {/* Status */}
      <div className="text-sm">
        <span
          className={`font-medium ${
            active ? "text-green-600" : "text-gray-500"
          }`}
        >
          {active ? "● Stream aktif" : "○ Stream nonaktif"}
        </span>
        {statusText && (
          <span className="ml-2 text-red-600">— {statusText}</span>
        )}
      </div>

      {/* Divider */}
      <hr className="border-gray-200" />

      {/* Content */}
      {active ? (
        <RoiSelector streamUrl={streamUrl} apiBase={API_BASE} />
      ) : (
        <div className="text-center py-12 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
          <p className="text-gray-500">
            Mulai kamera untuk menampilkan video & memilih ROI
          </p>
        </div>
      )}
    </div>
  );
}
