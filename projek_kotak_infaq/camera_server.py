# camera_server.py — FastAPI MJPEG + YOLO overlay (CPU) + ROI + debounce + Telegram (no GUI)
import os, time, json, threading
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from ultralytics import YOLO
import httpx

# ========= FastAPI =========
app = FastAPI(docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/")
def root():
    return {"ok": True, "msg": "camera_server up"}

# ========= Global State =========
cap: Optional[cv2.VideoCapture] = None
running = False
latest_jpeg: Optional[bytes] = None
lock = threading.Lock()

# ========= Konfigurasi via ENV (default mirip versi lama) =========
MISSING_WINDOW   = int(os.getenv("MISSING_WINDOW",  "24"))     # panjang moving avg (frame)
WARN_THRESHOLD   = float(os.getenv("WARN_THRESHOLD",  "0.40")) # rata2 'absent' utk WARN
ALERT_THRESHOLD  = float(os.getenv("ALERT_THRESHOLD", "0.70")) # rata2 'absent' utk ALERT
PRESENT_GRACE    = int(os.getenv("PRESENT_GRACE", "10"))       # toleransi frame hilang

BASE_DIR         = os.path.dirname(os.path.abspath(__file__))

# Cari weight default: .\best.pt atau runs\detect\train_box\weights\best.pt
DEFAULT_WEIGHT = os.path.join(BASE_DIR, "best.pt")
ALT_WEIGHT     = os.path.join(BASE_DIR, "runs", "detect", "train_box", "weights", "best.pt")
if not os.path.isfile(DEFAULT_WEIGHT) and os.path.isfile(ALT_WEIGHT):
    DEFAULT_WEIGHT = ALT_WEIGHT
YOLO_WEIGHTS     = os.getenv("YOLO_WEIGHTS", DEFAULT_WEIGHT)

# YOLO hyperparam
YOLO_CONF_DEF    = float(os.getenv("YOLO_CONF", "0.25"))
YOLO_IOU_DEF     = float(os.getenv("YOLO_IOU", "0.60"))
YOLO_IMG_DEF     = int(os.getenv("YOLO_IMG",  "800"))
MIN_AREA_RATIO   = float(os.getenv("MIN_AREA_RATIO", "0.01"))  # relatif ke area ROI / frame

# Inference throttling (biar FPS tetap): infer tiap N frame
INFER_EVERY      = int(os.getenv("INFER_EVERY", "1"))  # 1 = tiap frame

# Kamera backend (Windows: DSHOW/MSMF)
CAM_BACKEND      = os.getenv("CAM_BACKEND", "DSHOW").upper()  # MSMF | DSHOW | ANY
CAP_MAP = {"MSMF": cv2.CAP_MSMF, "DSHOW": cv2.CAP_DSHOW, "ANY": cv2.CAP_ANY}

# Telegram (opsional)
TG_TOKEN         = os.getenv("tg_token", "7697921487:AAEvZXLkC61Nzx-eh1e2BES1VfqSJ3wN32E")
TG_CHAT_ID       = os.getenv("tg_chat_id", "1215968232")
TG_COOLDOWN_S    = int(os.getenv("tg_cooldown", "10"))

# ROI file (dipakai headless; atur dengan menulis roi.json manual)
ROI_JSON         = os.getenv("ROI_JSON", os.path.join(BASE_DIR, "roi.json"))

# ========= Utils =========
def send_telegram(text: str):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        httpx.post(url, data={"chat_id": TG_CHAT_ID, "text": text}, timeout=10.0)
    except Exception as e:
        print("[TG] gagal kirim pesan:", e)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def load_roi(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict) and all(k in obj for k in ("x1","y1","x2","y2")):
            return obj
    except Exception:
        pass
    return None

# ========= YOLO (lazy load) =========
_yolo_model = None
_model_names = None

def _ensure_model(weights_path: str, conf: float, iou: float, imgsz: int):
    global _yolo_model, _model_names
    if _yolo_model is not None:
        return
    if not os.path.isfile(weights_path):
        raise FileNotFoundError(f"YOLO_WEIGHTS tidak ditemukan: {weights_path}")
    _yolo_model = YOLO(weights_path)
    _yolo_model.to("cpu")
    _model_names = _yolo_model.names
    print("[YOLO] loaded:", weights_path, "| conf=", conf, "iou=", iou, "img=", imgsz)

def _infer_and_draw(frame, counter, conf, iou, imgsz, min_area_ratio, roi_rect):
    """Infer tiap INFER_EVERY frame, draw bbox ke frame (stream)."""
    if _yolo_model is None:
        return

    if counter % INFER_EVERY != 0:
        return

    H, W = frame.shape[:2]
    # siapkan sumber inferensi: ROI atau fullframe
    if roi_rect:
        rx1, ry1, rx2, ry2 = roi_rect
        crop = frame[ry1:ry2, rx1:rx2]
        base_area = max(1, (ry2-ry1)*(rx2-rx1))
        res = _yolo_model.predict(source=crop, imgsz=imgsz, conf=conf, iou=iou,
                                  max_det=50, device="cpu", verbose=False)[0]
    else:
        base_area = max(1, H*W)
        res = _yolo_model.predict(source=frame, imgsz=imgsz, conf=conf, iou=iou,
                                  max_det=50, device="cpu", verbose=False)[0]

    # kumpulkan deteksi (mapping koordinat bila ROI)
    dets = []
    if res.boxes is not None and len(res.boxes) > 0:
        for b in res.boxes:
            conf_b = float(b.conf[0]) if hasattr(b, "conf") else 0.0
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0]]
            if roi_rect:
                x1 += rx1; x2 += rx1
                y1 += ry1; y2 += ry1
            area = max(1, (x2 - x1) * (y2 - y1))
            if (area / base_area) < min_area_ratio:
                continue
            cls_id = int(b.cls[0]) if hasattr(b, "cls") and b.cls is not None else -1
            dets.append((x1, y1, x2, y2, conf_b, cls_id))

    # draw bbox
    for (x1, y1, x2, y2, conf_b, cls_id) in dets[:50]:
        if isinstance(_model_names, dict):
            label = _model_names.get(cls_id, "obj")
        elif isinstance(_model_names, (list, tuple)) and 0 <= cls_id < len(_model_names):
            label = str(_model_names[cls_id])
        else:
            label = "obj"
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 215, 0), 2)
        cv2.putText(frame, f"{label} {conf_b:.2f}", (x1, max(12, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 215, 0), 2, cv2.LINE_AA)

    return dets

# ========= Capture loop =========
def capture_loop(cam_index=0):
    global cap, running, latest_jpeg

    # load model
    try:
        _ensure_model(YOLO_WEIGHTS, YOLO_CONF_DEF, YOLO_IOU_DEF, YOLO_IMG_DEF)
    except Exception as e:
        print("[YOLO] gagal load:", e)
        running = False
        return

    # open cam
    backend = CAP_MAP.get(CAM_BACKEND, cv2.CAP_ANY)
    cap = cv2.VideoCapture(cam_index, backend)
    if not cap.isOpened() and backend != cv2.CAP_ANY:
        cap = cv2.VideoCapture(cam_index, cv2.CAP_ANY)
    if not cap.isOpened():
        print(f"[CAM] gagal membuka kamera index {cam_index}")
        running = False
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # state untuk alert logic
    absent_hist = []
    missing_streak = 0
    last_status = "NORMAL"
    last_alert_ts = 0.0
    counter = 0

    # load ROI (sekali di awal, bisa diubah dengan mengedit file roi.json)
    roi_raw = load_roi(ROI_JSON)
    roi_rect = None
    if roi_raw:
        # sanitize ROI
        temp_frame_ok, temp_frame = cap.read()
        if temp_frame_ok:
            H, W = temp_frame.shape[:2]
            x1 = clamp(int(roi_raw["x1"]), 0, W-1)
            y1 = clamp(int(roi_raw["y1"]), 0, H-1)
            x2 = clamp(int(roi_raw["x2"]), 1, W)
            y2 = clamp(int(roi_raw["y2"]), 1, H)
            if (x2 - x1) >= 4 and (y2 - y1) >= 4:
                roi_rect = (x1, y1, x2, y2)
                print("[ROI] aktif:", roi_rect)

    while running:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.02)
            continue

        counter += 1

        # infer + draw
        try:
            dets = _infer_and_draw(
                frame=frame,
                counter=counter,
                conf=YOLO_CONF_DEF,
                iou=YOLO_IOU_DEF,
                imgsz=YOLO_IMG_DEF,
                min_area_ratio=MIN_AREA_RATIO,
                roi_rect=roi_rect
            ) or []
        except Exception as e:
            print("[YOLO] inference error:", e)
            dets = []

        # absent logic (debounce + moving average)
        present_raw = len(dets) > 0
        if present_raw:
            missing_streak = 0
        else:
            missing_streak += 1
        present = True if present_raw or missing_streak <= PRESENT_GRACE else False

        absent_hist.append(0 if present else 1)
        if len(absent_hist) > MISSING_WINDOW:
            absent_hist.pop(0)
        avg_absent = float(np.mean(absent_hist)) if absent_hist else (0.0 if present else 1.0)

        # status
        status = "NORMAL"
        if avg_absent >= ALERT_THRESHOLD:
            status = "ALERT"
        elif avg_absent >= WARN_THRESHOLD:
            status = "WARN"

        # draw header & ROI box (untuk stream)
        if roi_rect:
            cv2.rectangle(frame, (roi_rect[0], roi_rect[1]), (roi_rect[2], roi_rect[3]), (255, 165, 0), 2)

        color = (0, 255, 255) if status == "NORMAL" else ((0, 165, 255) if status == "WARN" else (0, 0, 255))
        H, W = frame.shape[:2]
        cv2.rectangle(frame, (0, 0), (W, 44), (0, 0, 0), -1)
        hud = f"Status: {status} | absent≈{avg_absent:.2f} | dets={len(dets)}"
        cv2.putText(frame, hud, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2, cv2.LINE_AA)

        # Telegram saat naik ALERT (dengan cooldown)
        if TG_TOKEN and TG_CHAT_ID and status == "ALERT" and last_status != "ALERT":
            now = time.time()
            if now - last_alert_ts > TG_COOLDOWN_S:
                last_alert_ts = now
                send_telegram("⚠️ Kotak infaq tidak terdeteksi di kamera! (status=ALERT)")

        last_status = status

        # encode ke JPEG (stream)
        ok2, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if ok2:
            with lock:
                latest_jpeg = jpg.tobytes()

        time.sleep(0.01)

    if cap:
        cap.release()

# ========= MJPEG generator =========
def mjpeg_gen():
    boundary = "frame"
    while True:
        with lock:
            buf = latest_jpeg
        if buf is not None:
            yield (b"--" + boundary.encode() + b"\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + buf + b"\r\n")
        time.sleep(0.02)

# ========= API =========
@app.get("/camera/status")
def status():
    return {
        "running": running,
        "weights": YOLO_WEIGHTS,
        "conf": YOLO_CONF_DEF,
        "iou": YOLO_IOU_DEF,
        "imgsz": YOLO_IMG_DEF,
        "infer_every": INFER_EVERY,
        "roi_json": ROI_JSON,
    }

@app.post("/camera/start")
def start(index: int = 0):
    global running
    if running:
        return {"ok": True, "msg": "already running"}
    running = True
    threading.Thread(target=capture_loop, kwargs={"cam_index": index}, daemon=True).start()
    return {"ok": True}

@app.post("/camera/stop")
def stop():
    global running
    running = False
    return {"ok": True}

@app.get(
    "/camera/stream",
    response_class=StreamingResponse,
    responses={200: {"description": "MJPEG stream", "content": {"multipart/x-mixed-replace; boundary=frame": {}}}},
)
def stream():
    if not running:
        raise HTTPException(status_code=400, detail="camera not running")
    return StreamingResponse(mjpeg_gen(), media_type="multipart/x-mixed-replace; boundary=frame")
