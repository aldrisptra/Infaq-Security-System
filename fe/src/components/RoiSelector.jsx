// src/components/RoiSelector.jsx
import { useEffect, useRef, useState } from "react";

function getRequestHeaders(isJson = false) {
  const headers = {};
  const edgeKey = import.meta.env.VITE_EDGE_KEY || "";
  if (edgeKey) headers["X-Edge-Key"] = edgeKey;

  const token = localStorage.getItem("authToken");
  if (token) headers["Authorization"] = `Bearer ${token}`;

  headers["Accept"] = "application/json";
  if (isJson) headers["Content-Type"] = "application/json";
  return headers;
}

export default function RoiSelector({ streamUrl, apiBase }) {
  const containerRef = useRef(null);
  const [roi, setRoi] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [startPos, setStartPos] = useState(null);
  const [statusText, setStatusText] = useState("");

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

  const getXY = (e) => {
    const el = containerRef.current;
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    const x = clamp01((e.clientX - rect.left) / rect.width);
    const y = clamp01((e.clientY - rect.top) / rect.height);
    return { x, y };
  };

  const handlePointerDown = (e) => {
    if (!containerRef.current) return;
    // penting biar di HP nggak scroll/zoom saat drag
    e.preventDefault();

    // “kunci” pointer biar move tetap masuk walau jari keluar sedikit dari area
    try {
      containerRef.current.setPointerCapture(e.pointerId);
    } catch (_) {}

    const p = getXY(e);
    if (!p) return;

    setStartPos(p);
    setRoi({ x: p.x, y: p.y, w: 0, h: 0 });
    setDragging(true);
  };

  const handlePointerMove = (e) => {
    if (!dragging || !startPos || !containerRef.current) return;
    e.preventDefault();

    const p = getXY(e);
    if (!p) return;

    const left = Math.min(startPos.x, p.x);
    const top = Math.min(startPos.y, p.y);
    const w = Math.abs(p.x - startPos.x);
    const h = Math.abs(p.y - startPos.y);

    setRoi({ x: left, y: top, w, h });
  };

  const endDrag = (e) => {
    if (e) e.preventDefault();
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
        className="relative w-full bg-black rounded-lg overflow-hidden cursor-crosshair aspect-video select-none"
        style={{ touchAction: "none" }} // ini kuncinya untuk HP
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onPointerLeave={endDrag}
      >
        {streamUrl ? (
          <img
            src={streamUrl}
            alt="Camera stream"
            className="w-full h-full object-contain pointer-events-none"
            draggable={false}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">
            Stream belum tersedia
          </div>
        )}

        {roi && roi.w > 0 && roi.h > 0 && (
          <div
            className="absolute border-2 border-amber-400 bg-amber-300/10 pointer-events-none"
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
        🖱️ Klik/drag pada video untuk menentukan area ROI, lalu klik{" "}
        <span className="font-semibold">Simpan ROI</span>.
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
