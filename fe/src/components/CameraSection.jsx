// src/components/CameraSection.jsx (cuplikan)
import React, { useState } from "react";
import RoiSelector from "./RoiSelector";

export default function CameraSection() {
  const [active, setActive] = useState(false);
  const [streamUrl, setStreamUrl] = useState("");

  const startCam = async () => {
    const r = await fetch("/camera/start", { method: "POST" });
    if (!r.ok) throw new Error("Start kamera gagal");
    setStreamUrl(`/camera/stream?ts=${Date.now()}`);
    setActive(true);
  };

  const stopCam = async () => {
    await fetch("/camera/stop", { method: "POST" });
    setActive(false);
    setStreamUrl("");
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {!active ? (
          <button
            onClick={startCam}
            className="px-4 py-2 rounded bg-blue-600 text-white"
          >
            Start Kamera
          </button>
        ) : (
          <button
            onClick={stopCam}
            className="px-4 py-2 rounded bg-rose-600 text-white"
          >
            Stop Kamera
          </button>
        )}
      </div>

      {active && <RoiSelector streamUrl={streamUrl} />}
    </div>
  );
}
