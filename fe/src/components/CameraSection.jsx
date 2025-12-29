// src/components/RoiSelector.jsx
import { useEffect, useRef, useState } from "react";

function getRequestHeaders(isJson = false) {
  const headers = {};

  // 1) Edge key (untuk edge laptop)
  const edgeKey = import.meta.env.VITE_EDGE_KEY || "";
  if (edgeKey) headers["X-Edge-Key"] = edgeKey;

  // 2) Bearer token (kalau edge masih butuh auth juga)
  const token = localStorage.getItem("authToken");
  if (token) headers["Authorization"] = `Bearer ${token}`;

  if (isJson) headers["Content-Type"] = "application/json";
  headers["Accept"] = "application/json";

  return headers;
}

export default function RoiSelector({ streamUrl, apiBase }) {
  const containerRef = useRef(null);
  const [roi, setRoi] = useState(null); // {x, y, w, h} dalam 0–1
  const [dragging, setDragging] = useState(false);
  const [startPos, setStartPos] = useState(null);
  const [statusText, setStatusText] = useState("");

  // Ambil ROI awal dari backend
  useEffect(() => {
    async function fetchROI() {
      try {
        const res = await fetch(`${apiBase}/roi`, {
          headers: getRequestHeaders(false),
        });
        if (!res.ok) return;
        const data = await res.json();
        if (data?.roi) setRoi(data.roi);
      } catch (err) {
        console.error("Gagal ambil ROI:", err);
      }
    }

    fetchROI();
  }, [apiBase]);

  const clamp01 = (v) => Math.min(1, Math.max(0, v));

  const handleMouseDown = (e) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = clamp01((e.clientX - rect.left) / rect.width);
    const y = clamp01((e.clientY - rect.top) / rect.height);

    setStartPos({ x, y });
    setRoi({ x, y, w: 0, h: 0 });
    setDragging(true);
  };

  const handleMouseMove = (e) => {
    if (!dragging || !containerRef.current || !startPos) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = clamp01((e.clientX - rect.left) / rect.width);
    const y = clamp01((e.clientY - rect.top) / rect.height);

    const x1 = startPos.x;
    const y1 = startPos.y;
    const left = Math.min(x1, x);
    const top = Math.min(y1, y);
    const w = Math.abs(x - x1);
    const h = Math.abs(y - y1);

    setRoi({ x: left, y: top, w, h });
  };

  const endDrag = () => {
    setDragging(false);
    setStartPos(null);
  };

  async function handleSave() {
    try {
      if (!roi || roi.w === 0 || roi.h === 0) {
        setStatusText("Gambar dulu area ROI di atas video.");
        return;
      }
      setStatusText("Menyimpan ROI...");

      const res = await fetch(`${apiBase}/roi`, {
        method: "POST",
        headers: getRequestHeaders(true),
        body: JSON.stringify(roi),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Gagal menyimpan ROI");
      }

      setStatusText("ROI berhasil disimpan ✅");
    } catch (err) {
      console.error(err);
      setStatusText(err.message || "Gagal menyimpan ROI");
    }
  }

  async function handleClear() {
    try {
      setStatusText("Menghapus ROI...");
      const res = await fetch(`${apiBase}/roi`, {
        method: "DELETE",
        headers: getRequestHeaders(false),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Gagal menghapus ROI");
      }

      setRoi(null);
      setStatusText("ROI dihapus.");
    } catch (err) {
      console.error(err);
      setStatusText(err.message || "Gagal menghapus ROI");
    }
  }

  return (
    <div className="space-y-3">
      <div
        ref={containerRef}
        className="relative w-full bg-black rounded-lg overflow-hidden cursor-crosshair aspect-video"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={endDrag}
        onMouseLeave={endDrag}
      >
        {streamUrl ? (
          <img
            src={streamUrl}
            alt="Camera stream"
            className="w-full h-full object-contain select-none pointer-events-none"
            draggable={false}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">
            Stream belum tersedia
          </div>
        )}

        {roi && roi.w > 0 && roi.h > 0 && (
          <div
            className="absolute border-2 border-amber-400 bg-amber-300/10"
            style={{
              left: `${roi.x * 100}%`,
              top: `${roi.y * 100}%`,
              width: `${roi.w * 100}%`,
              height: `${roi.h * 100}%`,
            }}
          />
        )}
      </div>

      <p className="text-xs text-gray-600">
        🖱️ Klik & drag pada video untuk menentukan area kotak infaq (ROI).
        Kemudian klik <span className="font-semibold">Simpan ROI</span>.
      </p>

      <div className="flex gap-3">
        <button
          type="button"
          onClick={handleSave}
          className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 transition"
        >
          Simpan ROI
        </button>
        <button
          type="button"
          onClick={handleClear}
          className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 text-sm hover:bg-gray-50 transition"
        >
          Hapus ROI
        </button>
      </div>

      {statusText && <p className="text-xs text-gray-500 mt-1">{statusText}</p>}
    </div>
  );
}
