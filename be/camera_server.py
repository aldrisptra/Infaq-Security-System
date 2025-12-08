# camera_server.py
import os, time, threading, json
from typing import Optional, Tuple

import cv2
import numpy as np
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from pydantic import BaseModel, confloat
from ultralytics import YOLO
import httpx

from sqlalchemy.orm import Session
from database import get_db
from models import Camera

# ====== IMPORT AUTH ======
from auth import router as auth_router
from auth import get_current_user, CurrentUser


# ========= FastAPI =========
app = FastAPI(docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/")
def root():
    return {"ok": True, "msg": "camera_server up"}


# ========= Global State =========
cap: Optional[cv2.VideoCapture] = None
running = False
latest_jpeg: Optional[bytes] = None
lock = threading.Lock()

alert_status = "present"
last_alert_photo_ts = 0.0

CUR_SOURCE = "webcam"   # webcam | video | ipcam
CUR_INDEX  = 0
CUR_PATH   = None
CUR_LOOP   = False

BASE_DIR = Path(__file__).resolve().parent


# ========= Helpers DB camera =========
def _get_camera_id_col():
    # antisipasi nama kolom id berbeda di model
    return getattr(Camera, "id", None) or getattr(Camera, "id_camera", None)

def _get_latest_camera_for_masjid(db: Session, masjid_id: int) -> Optional[Camera]:
    q = db.query(Camera).filter(Camera.id_masjid == masjid_id)
    cam_id_col = _get_camera_id_col()
    if cam_id_col is not None:
        q = q.order_by(cam_id_col.desc())
    return q.first()


# ========= Default camera from DB =========
@app.get("/camera/default")
def get_default_camera(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cam = _get_latest_camera_for_masjid(db, current_user.id_masjid)

    # fallback kalau belum ada kamera di DB
    if not cam:
        return {
            "source": "webcam",
            "index": 0,
            "path": None,
            "loop": True,
            "camera_name": None,
        }

    source = getattr(cam, "source_type", None) or "ipcam"
    path   = getattr(cam, "source_path", None)
    index  = getattr(cam, "source_index", 0) or 0

    if source not in ("webcam", "video", "ipcam"):
        source = "ipcam"

    return {
        "source": source,
        "index": index,
        "path": path,
        "loop": True,
        "camera_name": getattr(cam, "nama", None),
    }


@app.post("/camera/start-default")
def start_default_camera(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cam = _get_latest_camera_for_masjid(db, current_user.id_masjid)
    if not cam:
        raise HTTPException(404, "Default camera belum ada di database")

    source = getattr(cam, "source_type", None) or "ipcam"
    path   = getattr(cam, "source_path", None)
    index  = getattr(cam, "source_index", 0) or 0

    if source not in ("webcam", "video", "ipcam"):
        source = "ipcam"

    # kalau ipcam/video tapi path kosong -> error jelas
    if source in ("ipcam", "video") and not path:
        raise HTTPException(400, "Default camera di database belum punya source_path")

    return start(source=source, index=index, path=path, loop=True)


# ========= ROI (FILE-BASED, AUTH) =========
class ROISchema(BaseModel):
    x: confloat(ge=0.0, le=1.0)
    y: confloat(ge=0.0, le=1.0)
    w: confloat(ge=0.0, le=1.0)
    h: confloat(ge=0.0, le=1.0)

ROI_PATH = BASE_DIR / "roi_config.json"

def load_roi_rel() -> Optional[ROISchema]:
    if not ROI_PATH.exists():
        return None
    try:
        text = ROI_PATH.read_text(encoding="utf-8").strip()
        if not text:
            return None
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        return ROISchema(**data)
    except Exception as e:
        print("[ROI] error load:", e)
        return None

def save_roi_rel(roi: ROISchema) -> None:
    try:
        if hasattr(roi, "model_dump_json"):
            ROI_PATH.write_text(roi.model_dump_json(), encoding="utf-8")
        else:
            ROI_PATH.write_text(roi.json(), encoding="utf-8")
    except Exception as e:
        print("[ROI] error save:", e)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def get_roi_rect_pixels(frame_shape) -> Optional[Tuple[int, int, int, int]]:
    roi = load_roi_rel()
    if not roi:
        return None
    H, W = frame_shape[:2]
    x1 = clamp(int(roi.x * W), 0, W - 1)
    y1 = clamp(int(roi.y * H), 0, H - 1)
    x2 = clamp(int((roi.x + roi.w) * W), 1, W)
    y2 = clamp(int((roi.y + roi.h) * H), 1, H)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    return (x1, y1, x2, y2)

class ROIResponse(BaseModel):
    roi: Optional[ROISchema] = None

@app.get("/roi", response_model=ROIResponse)
def get_roi(current_user: CurrentUser = Depends(get_current_user)):
    return ROIResponse(roi=load_roi_rel())

@app.post("/roi", response_model=ROIResponse)
def set_roi(
    roi: ROISchema,
    current_user: CurrentUser = Depends(get_current_user),
):
    if roi.w <= 0 or roi.h <= 0:
        raise HTTPException(400, "w/h harus > 0")
    if roi.x + roi.w > 1 or roi.y + roi.h > 1:
        raise HTTPException(400, "ROI keluar dari frame")
    save_roi_rel(roi)
    return ROIResponse(roi=roi)

@app.delete("/roi")
def clear_roi(current_user: CurrentUser = Depends(get_current_user)):
    try:
        ROI_PATH.unlink(missing_ok=True)
    except Exception as e:
        print("[ROI] error delete:", e)
    return {"ok": True}


# ========= Konfigurasi Deteksi =========
MISSING_WINDOW   = int(os.getenv("MISSING_WINDOW",  "24"))
WARN_THRESHOLD   = float(os.getenv("WARN_THRESHOLD",  "0.40"))
ALERT_THRESHOLD  = float(os.getenv("ALERT_THRESHOLD", "0.70"))
PRESENT_GRACE    = int(os.getenv("PRESENT_GRACE", "10"))

LABEL_DISPLAY = {
    "box": "Kotak Infaq",
    "donation_box": "Kotak Amal",
}

DEFAULT_WEIGHT = BASE_DIR / "best.pt"
ALT_WEIGHT     = BASE_DIR / "runs" / "detect" / "train_box" / "weights" / "best.pt"
if (not DEFAULT_WEIGHT.is_file()) and ALT_WEIGHT.is_file():
    DEFAULT_WEIGHT = ALT_WEIGHT

YOLO_WEIGHTS    = os.getenv("YOLO_WEIGHTS", str(DEFAULT_WEIGHT))
YOLO_CONF_DEF   = float(os.getenv("YOLO_CONF", "0.5"))
YOLO_IOU_DEF    = float(os.getenv("YOLO_IOU", "0.90"))
YOLO_IMG_DEF    = int(os.getenv("YOLO_IMG",  "800"))
MIN_AREA_RATIO  = float(os.getenv("MIN_AREA_RATIO", "0.01"))
INFER_EVERY     = int(os.getenv("INFER_EVERY", "1"))

CAM_BACKEND     = os.getenv("CAM_BACKEND", "DSHOW").upper()
CAP_MAP = {"MSMF": cv2.CAP_MSMF, "DSHOW": cv2.CAP_DSHOW, "ANY": cv2.CAP_ANY}

TARGET_CLASS_IDS = {
    int(s) for s in os.getenv("TARGET_CLASS_IDS", "").split(",") if s.strip().isdigit()
}
CENTER_IN_ROI = int(os.getenv("CENTER_IN_ROI", "1")) == 1
ROI_STRATEGY  = os.getenv("ROI_STRATEGY", "crop").lower()
REQUIRE_ROI   = int(os.getenv("REQUIRE_ROI", "0")) == 1

TARGET_LABELS = {
    s.strip().lower()
    for s in os.getenv("TARGET_LABELS", "").split(",")
    if s.strip()
}

DEBUG_LOG  = int(os.getenv("DEBUG_LOG", "1")) == 1

def _matches_target(cls_id: int, label: str) -> bool:
    label_l = (label or "").lower()
    if TARGET_CLASS_IDS:
        return cls_id in TARGET_CLASS_IDS
    if TARGET_LABELS:
        return label_l in TARGET_LABELS
    return True


# ========= Telegram =========
TG_TOKEN      = os.getenv("TG_TOKEN", "")
TG_CHAT_ID    = os.getenv("TG_CHAT_ID", "")
TG_COOLDOWN_S = int(os.getenv("TG_COOLDOWN", "10"))

def send_telegram_photo(jpg_bytes: bytes, caption: str = ""):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        files = {"photo": ("capture.jpg", jpg_bytes, "image/jpeg")}
        data = {"chat_id": TG_CHAT_ID, "caption": caption}
        httpx.post(url, data=data, files=files, timeout=20.0)
    except Exception as e:
        print("[TG] gagal kirim foto:", e)


# ========= YOLO Model =========
_yolo_model = None
_model_names = None

def _ensure_model(weights_path: str, conf: float, iou: float, imgsz: int):
    global _yolo_model, _model_names
    if _yolo_model is not None:
        return
    if not Path(weights_path).is_file():
        raise FileNotFoundError(f"YOLO_WEIGHTS tidak ditemukan: {weights_path}")
    _yolo_model = YOLO(weights_path)
    _yolo_model.to("cpu")
    _model_names = _yolo_model.names
    print("[YOLO] loaded:", weights_path, "| conf=", conf, "iou=", iou, "img=", imgsz)

def _infer_and_draw(frame, counter, conf, iou, imgsz, min_area_ratio, roi_rect):
    if _yolo_model is None:
        return []
    if counter % INFER_EVERY != 0:
        return []

    H, W = frame.shape[:2]
    use_crop = (roi_rect is not None) and (ROI_STRATEGY == "crop")

    if use_crop:
        rx1, ry1, rx2, ry2 = roi_rect
        crop = frame[ry1:ry2, rx1:rx2]
        base_area = max(1, (ry2 - ry1) * (rx2 - rx1))
        res = _yolo_model.predict(
            source=crop, imgsz=imgsz, conf=conf, iou=iou,
            max_det=50, device="cpu", verbose=False
        )[0]
    else:
        base_area = max(1, H * W) if roi_rect is None else max(
            1, (roi_rect[3]-roi_rect[1])*(roi_rect[2]-roi_rect[0])
        )
        res = _yolo_model.predict(
            source=frame, imgsz=imgsz, conf=conf, iou=iou,
            max_det=50, device="cpu", verbose=False
        )[0]

    dets_target = []
    n_total = int(len(res.boxes) if (res.boxes is not None) else 0)
    drop_label = drop_area = drop_center = 0

    if res.boxes is not None and n_total > 0:
        if roi_rect:
            rx1, ry1, rx2, ry2 = roi_rect

        for b in res.boxes:
            conf_b = float(b.conf[0]) if hasattr(b, "conf") else 0.0
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0]]
            cls_id = int(b.cls[0]) if hasattr(b, "cls") and b.cls is not None else -1

            if use_crop:
                x1 += rx1; x2 += rx1
                y1 += ry1; y2 += ry1

            if isinstance(_model_names, dict):
                label = _model_names.get(cls_id, "obj")
            elif isinstance(_model_names, (list, tuple)) and 0 <= cls_id < len(_model_names):
                label = str(_model_names[cls_id])
            else:
                label = "obj"

            if not _matches_target(cls_id, label):
                drop_label += 1
                continue

            area = max(1, (x2 - x1) * (y2 - y1))
            if (area / base_area) < min_area_ratio:
                drop_area += 1
                continue

            if roi_rect and CENTER_IN_ROI:
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                if not (rx1 <= cx <= rx2 and ry1 <= cy <= ry2):
                    drop_center += 1
                    continue

            dets_target.append((x1, y1, x2, y2, conf_b, cls_id, label))

    for (x1, y1, x2, y2, conf_b, cls_id, label) in dets_target[:50]:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 215, 0), 2)
        display_label = LABEL_DISPLAY.get(label.lower(), label)
        cv2.putText(
            frame, f"{display_label} {conf_b:.2f}",
            (x1, max(12, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6,
            (0, 215, 0), 2, cv2.LINE_AA
        )

    if DEBUG_LOG and (counter % 15 == 0):
        print(f"[DEBUG] boxes={n_total} kept={len(dets_target)} drop(label/area/center)={drop_label}/{drop_area}/{drop_center}")

    return dets_target


# ========= Open Source =========
def _open_source(source: str, index: int, path: Optional[str]) -> cv2.VideoCapture:
    if source == "webcam":
        backend = CAP_MAP.get(CAM_BACKEND, cv2.CAP_ANY)
        cap0 = cv2.VideoCapture(index, backend)
        if not cap0.isOpened() and backend != cv2.CAP_ANY:
            cap0 = cv2.VideoCapture(index, cv2.CAP_ANY)
        return cap0

    # video / ipcam -> pakai path/url
    if not path:
        raise ValueError("path video/url kosong")
    return cv2.VideoCapture(path)


# ========= Capture Loop =========
def capture_loop(source="webcam", index=0, path: Optional[str]=None, loop_video=False):
    global cap, running, latest_jpeg, alert_status, last_alert_photo_ts

    try:
        _ensure_model(YOLO_WEIGHTS, YOLO_CONF_DEF, YOLO_IOU_DEF, YOLO_IMG_DEF)
    except Exception as e:
        print("[YOLO] gagal load:", e)
        running = False
        return

    cap = _open_source(source, index, path)
    if not cap.isOpened():
        print(f"[CAM] gagal membuka sumber: {source} | index={index} | path={path}")
        running = False
        return

    if source == "webcam":
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    absent_hist = []
    missing_streak = 0
    counter = 0

    roi_rect = None
    roi_mtime = ROI_PATH.stat().st_mtime if ROI_PATH.exists() else 0.0

    ok_first, frame0 = cap.read()
    if ok_first:
        roi_rect = get_roi_rect_pixels(frame0.shape)
        if roi_rect:
            print("[ROI] aktif:", roi_rect)
    else:
        print("[CAM] frame pertama gagal")
        running = False
        cap.release()
        return

    while running:
        ok, frame = cap.read()
        if not ok:
            if source == "video" and loop_video:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            time.sleep(0.02)
            continue

        counter += 1

        # reload ROI jika file berubah
        if counter % 30 == 0:
            new_mtime = ROI_PATH.stat().st_mtime if ROI_PATH.exists() else 0.0
            if new_mtime != roi_mtime:
                roi_mtime = new_mtime
                roi_rect = get_roi_rect_pixels(frame.shape)
                print("[ROI] reload:", roi_rect)

        dets = []
        try:
            dets = _infer_and_draw(
                frame=frame,
                counter=counter,
                conf=YOLO_CONF_DEF,
                iou=YOLO_IOU_DEF,
                imgsz=YOLO_IMG_DEF,
                min_area_ratio=MIN_AREA_RATIO,
                roi_rect=roi_rect,
            ) or []
        except Exception as e:
            print("[YOLO] inference error:", e)
            dets = []

        if REQUIRE_ROI and (roi_rect is None):
            dets = []

        present_raw = len(dets) > 0
        missing_streak = 0 if present_raw else (missing_streak + 1)
        present = True if present_raw or missing_streak <= PRESENT_GRACE else False

        absent_hist.append(0 if present else 1)
        if len(absent_hist) > MISSING_WINDOW:
            absent_hist.pop(0)
        avg_absent = float(np.mean(absent_hist)) if absent_hist else (0.0 if present else 1.0)

        status_str = "NORMAL"
        if avg_absent >= ALERT_THRESHOLD:
            status_str = "ALERT"
        elif avg_absent >= WARN_THRESHOLD:
            status_str = "WARN"

        old_alert = alert_status
        alert_status = "missing" if status_str == "ALERT" else "present"

        # kirim foto saat transisi ke ALERT
        if TG_TOKEN and TG_CHAT_ID and status_str == "ALERT" and old_alert != "missing":
            now = time.time()
            if now - last_alert_photo_ts > TG_COOLDOWN_S:
                last_alert_photo_ts = now
                ok_jpg, jpg_buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                if ok_jpg:
                    send_telegram_photo(jpg_buf.tobytes(), "⚠️ ALERT: Kotak infaq tidak terdeteksi!")

        # gambar ROI
        if roi_rect:
            cv2.rectangle(frame, (roi_rect[0], roi_rect[1]), (roi_rect[2], roi_rect[3]), (255, 165, 0), 2)

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
            yield (
                b"--" + boundary.encode() + b"\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buf + b"\r\n"
            )
        time.sleep(0.02)


# ========= API kamera =========
@app.get("/camera/status")
def get_camera_status():
    return {
        "running": running,
        "alert_status": alert_status,
        "source": CUR_SOURCE,
        "index": CUR_INDEX,
        "path": CUR_PATH,
        "loop": CUR_LOOP,
        "weights": YOLO_WEIGHTS,
        "conf": YOLO_CONF_DEF,
        "iou": YOLO_IOU_DEF,
        "imgsz": YOLO_IMG_DEF,
        "infer_every": INFER_EVERY,
        "roi_file": str(ROI_PATH),
    }


@app.post("/camera/start")
def start(
    source: str = Query("webcam", pattern="^(webcam|video|ipcam)$"),
    index: int = 0,
    path: Optional[str] = None,
    loop: bool = True,
):
    global running, CUR_SOURCE, CUR_INDEX, CUR_PATH, CUR_LOOP

    if running:
        return {"ok": True, "msg": "already running"}

    # validasi minimal
    if source in ("video", "ipcam") and not path:
        raise HTTPException(400, "path wajib diisi untuk video/ipcam")

    CUR_SOURCE, CUR_INDEX, CUR_PATH, CUR_LOOP = source, index, path, loop
    running = True

    threading.Thread(
        target=capture_loop,
        kwargs={"source": source, "index": index, "path": path, "loop_video": loop},
        daemon=True,
    ).start()

    return {"ok": True, "source": source, "index": index, "path": path, "loop": loop}


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
