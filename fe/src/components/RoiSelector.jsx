// src/components/RoiSelector.jsx
import React, { useEffect, useRef, useState } from "react";

export default function RoiSelector({ streamUrl }) {
  const containerRef = useRef(null);
  const [roi, setRoi] = useState(null); // {x,y,w,h} relatif 0..1
  const [dragging, setDragging] = useState(false);
  const [start, setStart] = useState(null); // {x,y} relatif 0..1
  const [tempRect, setTempRect] = useState(null); // rect sementara saat drag

  // Ambil ROI yang tersimpan
  useEffect(() => {
    (async () => {
      try {
        const r = await fetch("/roi");
        const data = await r.json();
        if (data?.roi) setRoi(data.roi);
      } catch (e) {
        console.error("Gagal GET /roi", e);
      }
    })();
  }, []);

  // hitung posisi relatif 0..1 dari event mouse
  const relPos = (e) => {
    const rect = containerRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    // clamp 0..1
    return { x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)) };
  };

  const onMouseDown = (e) => {
    if (!containerRef.current) return;
    const p = relPos(e);
    setStart(p);
    setTempRect({ x: p.x, y: p.y, w: 0, h: 0 });
    setDragging(true);
  };

  const onMouseMove = (e) => {
    if (!dragging || !start) return;
    const p = relPos(e);
    const x = Math.min(start.x, p.x);
    const y = Math.min(start.y, p.y);
    const w = Math.abs(p.x - start.x);
    const h = Math.abs(p.y - start.y);
    setTempRect({ x, y, w, h });
  };

  const onMouseUp = () => {
    if (tempRect && tempRect.w > 0.002 && tempRect.h > 0.002) {
      setRoi(tempRect);
    }
    setDragging(false);
    setStart(null);
    setTempRect(null);
  };

  const saveROI = async () => {
    if (!roi) return;
    const payload = {
      x: Number(roi.x.toFixed(6)),
      y: Number(roi.y.toFixed(6)),
      w: Number(roi.w.toFixed(6)),
      h: Number(roi.h.toFixed(6)),
    };
    const r = await fetch("/roi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      const msg = await r.text();
      alert("Gagal menyimpan ROI: " + msg);
      return;
    }
    alert("ROI tersimpan!");
  };

  const clearROI = async () => {
    await fetch("/roi", { method: "DELETE" });
    setRoi(null);
  };

  // Helper: style div overlay dari ROI relatif (pakai persen)
  const styleFromROI = (r) => ({
    left: `${r.x * 100}%`,
    top: `${r.y * 100}%`,
    width: `${r.w * 100}%`,
    height: `${r.h * 100}%`,
  });

  return (
    <div className="w-full">
      <div
        ref={containerRef}
        className="relative w-full max-w-3xl mx-auto select-none"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
      >
        {/* Stream kamera */}
        <img
          src={streamUrl}
          alt="camera"
          className="w-full block"
          draggable={false}
        />

        {/* Area interaktif transparan untuk drag */}
        <div className="absolute inset-0 cursor-crosshair" />

        {/* ROI persist (garis hijau) */}
        {roi && (
          <div
            className="absolute border-2 border-green-500/90 bg-green-500/10 rounded"
            style={styleFromROI(roi)}
          />
        )}

        {/* Rect sementara saat drag (garis biru) */}
        {tempRect && (
          <div
            className="absolute border-2 border-blue-500/90 bg-blue-500/10 rounded pointer-events-none"
            style={styleFromROI(tempRect)}
          />
        )}
      </div>

      <div className="mt-3 flex gap-2 justify-center">
        <button
          onClick={saveROI}
          className="px-4 py-2 rounded-xl bg-emerald-600 text-white hover:opacity-90"
          disabled={!roi}
        >
          Simpan ROI
        </button>
        <button
          onClick={clearROI}
          className="px-4 py-2 rounded-xl bg-gray-200 hover:bg-gray-300"
        >
          Hapus ROI
        </button>
      </div>

      <p className="text-sm text-gray-500 mt-2 text-center">
        Tips: Drag di atas video untuk memilih area kotak infaq. Klik “Simpan
        ROI”.
      </p>
    </div>
  );
}
