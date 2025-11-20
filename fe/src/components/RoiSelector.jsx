import { useEffect, useRef, useState } from "react";

/**
 * streamUrl: URL MJPEG
 * apiBase:   http://host:port untuk REST (snapshot & ROI)
 */
export default function RoiSelector({ streamUrl, apiBase }) {
  const containerRef = useRef(null);

  const [roi, setRoi] = useState(null); // {x,y,w,h} relatif
  const [dragging, setDragging] = useState(false);
  const [start, setStart] = useState(null); // {x,y}
  const [tempRect, setTempRect] = useState(null);
  const [imgErr, setImgErr] = useState(false);
  const [altSrc, setAltSrc] = useState(null);

  // Ambil ROI tersimpan
  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${apiBase}/roi`);
        const data = await r.json();
        if (data?.roi) setRoi(data.roi);
      } catch (e) {
        console.warn("GET /roi gagal", e);
      }
    })();
  }, [apiBase]);

  // Fallback snapshot polling jika MJPEG gagal
  useEffect(() => {
    let timer;
    const tick = () => {
      const u = `${apiBase}/camera/snapshot?ts=${Date.now()}`;
      setAltSrc(u);
      timer = setTimeout(tick, 300);
    };
    if (imgErr) tick();
    return () => timer && clearTimeout(timer);
  }, [imgErr, apiBase]);

  // Hitung posisi relatif 0..1
  const relPos = (e) => {
    const rect = containerRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    return { x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)) };
    // clamp 0..1
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
      x: +roi.x.toFixed(6),
      y: +roi.y.toFixed(6),
      w: +roi.w.toFixed(6),
      h: +roi.h.toFixed(6),
    };
    const r = await fetch(`${apiBase}/roi`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) return alert("Gagal menyimpan ROI: " + (await r.text()));
    alert("ROI tersimpan!");
  };

  const clearROI = async () => {
    await fetch(`${apiBase}/roi`, { method: "DELETE" });
    setRoi(null);
  };

  const styleFromROI = (r) => ({
    position: "absolute",
    left: `${r.x * 100}%`,
    top: `${r.y * 100}%`,
    width: `${r.w * 100}%`,
    height: `${r.h * 100}%`,
    border: "2px solid rgba(34,197,94,0.9)",
    background: "rgba(34,197,94,0.1)",
    borderRadius: 6,
    pointerEvents: "none",
  });

  return (
    <div>
      <div
        ref={containerRef}
        style={{
          position: "relative",
          width: "100%",
          maxWidth: 900,
          margin: "0 auto",
          userSelect: "none",
        }}
      >
        {/* Stream */}
        <img
          src={altSrc || streamUrl}
          alt="camera"
          style={{ width: "100%", display: "block" }}
          draggable={false}
          onError={() => setImgErr(true)}
          onLoad={() => setImgErr(false)}
        />

        {/* Layer untuk drag */}
        <div
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          style={{ position: "absolute", inset: 0, cursor: "crosshair" }}
        />

        {/* ROI tersimpan */}
        {roi && <div style={styleFromROI(roi)} />}

        {/* ROI sementara (biru) */}
        {tempRect && (
          <div
            style={{
              position: "absolute",
              left: `${tempRect.x * 100}%`,
              top: `${tempRect.y * 100}%`,
              width: `${tempRect.w * 100}%`,
              height: `${tempRect.h * 100}%`,
              border: "2px solid rgba(59,130,246,0.9)",
              background: "rgba(59,130,246,0.1)",
              borderRadius: 6,
              pointerEvents: "none",
            }}
          />
        )}
      </div>

      {imgErr && (
        <p style={{ textAlign: "center", color: "#b45309", marginTop: 8 }}>
          MJPEG gagal dimuat, menampilkan snapshot (fallback).
        </p>
      )}

      <div
        style={{
          marginTop: 12,
          display: "flex",
          gap: 8,
          justifyContent: "center",
        }}
      >
        <button
          onClick={saveROI}
          disabled={!roi}
          style={{ padding: "8px 14px" }}
        >
          Simpan ROI
        </button>
        <button onClick={clearROI} style={{ padding: "8px 14px" }}>
          Hapus ROI
        </button>
      </div>

      <p style={{ textAlign: "center", color: "#6b7280", marginTop: 8 }}>
        Tips: drag di atas video untuk memilih area kotak infaq, lalu klik
        “Simpan ROI”.
      </p>
    </div>
  );
}
