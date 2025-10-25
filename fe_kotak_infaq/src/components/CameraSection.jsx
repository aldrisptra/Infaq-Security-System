import React, { useState } from "react";
import VideoPanel from "./VideoPanel";
import StatusCard from "./StatusCard";

export default function CameraSection() {
  const [active, setActive] = useState(false);
  const [streamUrl, setStreamUrl] = useState("");

  // pakai path relatif karena sudah ada proxy Vite
  const startCam = async () => {
    const r = await fetch("/camera/start", { method: "POST" });
    if (!r.ok) throw new Error("Start kamera gagal");
    // set URL MJPEG supaya <img> mulai render
    setStreamUrl(`/camera/stream?ts=${Date.now()}`);
    setActive(true);
  };

  const stopCam = async () => {
    await fetch("/camera/stop", { method: "POST" });
    setActive(false);
    setStreamUrl("");
  };

  const handleToggle = async () => {
    try {
      if (!active) await startCam();
      else await stopCam();
    } catch (e) {
      console.error(e);
      alert("Gagal toggle kamera");
    }
  };

  return (
    <div className="space-y-4">
      <StatusCard active={active} onToggle={handleToggle} />
      <VideoPanel active={active} streamUrl={streamUrl} />
    </div>
  );
}
