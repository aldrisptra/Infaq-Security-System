import os
import time
import json
import threading
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
from pydantic import BaseModel, confloat
import requests


# ============================================================
# MODE SWITCH (biar Railway aman, Edge tetap full)
# ============================================================
# Railway (dashboard saja): set ENABLE_CAPTURE=0, ENABLE_YOLO=0
# Edge/laptop (deteksi beneran): set ENABLE_CAPTURE=1, ENABLE_YOLO=1
ENABLE_CAPTURE = os.getenv("ENABLE_CAPTURE", "1") == "1"
ENABLE_YOLO = os.getenv("ENABLE_YOLO", "1") == "1"

# Try import cv2/numpy (kalau tidak ada di cloud, jangan crash)
try:
    import cv2
except Exception:
    cv2 = None

try:
    import numpy as np
except Exception:
    np = None

# Try import ultralytics (kalau tidak ada di cloud, jangan crash)
try:
    from ultralytics import YOLO
except Exception:
    YOLO = None


# ============================================================
# Optional imports (auth/db/models)
# ============================================================
BASE_DIR = Path(__file__).resolve().parent

# dotenv optional
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env", override=True)
except Exception:
    pass

# DB + Models optional
Session = Any
Camera = Any
Masjid = Any
get_db = None

try:
    from sqlalchemy.orm import Session as _Session
    Session = _Session
    from database import get_db as _get_db
    get_db = _get_db
    from models import Camera as _Camera, Masjid as _Masjid
    Camera, Masjid = _Camera, _Masjid
except Exception:
    # biar cloud tetap bisa jalan tanpa DB
    pass

# Auth optional
auth_router = None
CurrentUser = Any
def _dummy_user():
    class U:
        id_masjid = 1
        role = "demo"
    return U()

def get_current_user():
    return _dummy_user()

try:
    from auth import router as _auth_router
    from auth import get_current_user as _get_current_user, CurrentUser as _CurrentUser
    auth_router = _auth_router
    get_current_user = _get_current_user
    CurrentUser = _CurrentUser
except Exception:
    # fallback no-auth
    pass


# ============================================================
# ENV
# ============================================================
TG_TOKEN = os.getenv("TG_TOKEN", "").strip()

MISSING_WINDOW   = int(os.getenv("MISSING_WINDOW",  "24"))
WARN_THRESHOLD   = float(os.getenv("WARN_THRESHOLD",  "0.40"))
ALERT_THRESHOLD  = float(os.getenv("ALERT_THRESHOLD", "0.70"))
PRESENT_GRACE    = int(os.getenv("PRESENT_GRACE", "10"))

YOLO_CONF_DEF   = float(os.getenv("YOLO_CONF", "0.50"))
YOLO_IOU_DEF    = float(os.getenv("YOLO_IOU", "0.90"))
YOLO_IMG_DEF    = int(os.getenv("YOLO_IMG",  "800"))
MIN_AREA_RATIO  = float(os.getenv("MIN_AREA_RATIO", "0.01"))
INFER_EVERY     = int(os.getenv("INFER_EVERY", "1"))

ROI_STRATEGY = os.getenv("ROI_STRATEGY", "crop").lower()   # crop | full
CENTER_IN_ROI = os.getenv("CENTER_IN_ROI", "1") == "1"
REQUIRE_ROI = os.getenv("REQUIRE_ROI", "0") == "1"
DEBUG_LOG = os.getenv("DEBUG_LOG", "1") == "1"

# CORS
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").strip()
allow_origins = ["*"] if CORS_ORIGINS == "*" else [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

# YOLO weights (edge biasanya lokal, cloud biasanya off)
DEFAULT_WEIGHT = BASE_DIR / "best.pt"
ALT_WEIGHT = BASE_DIR / "runs" / "detect" / "train_box" / "weights" / "best.pt"
if (not DEFAULT_WEIGHT.is_file()) and ALT_WEIGHT.is_file():
    DEFAULT_WEIGHT = ALT_WEIGHT
YOLO_WEIGHTS = os.getenv("YOLO_WEIGHTS", str(DEFAULT_WEIGHT))

# Target class filter (opsional)
TARGET_CLASS_IDS = {int(s) for s in os.getenv("TARGET_CLASS_IDS", "").split(",") if s.strip().isdigit()}
TARGET_LABELS = {s.strip().lower() for s in os.getenv("TARGET_LABELS", "").split(",") if s.strip()}

LABEL_DISPLAY = {
    "box": "Kotak Infaq",
    "donation_box": "Kotak Amal",
}


# ============================================================
# FastAPI
# ============================================================
app = FastAPI(docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if auth_router is not None:
    app.include_router(auth_router)


@app.get("/")
def root():
    return {
        "ok": True,
        "msg": "camera_server up",
        "enable_capture": ENABLE_CAPTURE,
        "enable_yolo": ENABLE_YOLO,
        "cv2": bool(cv2),
        "ultralytics": bool(YOLO),
        "token_loaded": bool(TG_TOKEN),
    }


# ============================================================
# ROI (file-based)
# ============================================================
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
        return ROISchema(**data)
    except Exception as e:
        print("[ROI] load error:", e)
        return None

def save_roi_rel(roi: ROISchema) -> None:
    try:
        if hasattr(roi, "model_dump_json"):
            ROI_PATH.write_text(roi.model_dump_json(), encoding="utf-8")
        else:
            ROI_PATH.write_text(roi.json(), encoding="utf-8")
    except Exception as e:
        print("[ROI] save error:", e)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def roi_rect_px(frame_shape) -> Optional[Tuple[int, int, int, int]]:
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
def set_roi(roi: ROISchema, current_user: CurrentUser = Depends(get_current_user)):
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
        print("[ROI] delete error:", e)
    return {"ok": True}


# ============================================================
# Telegram
# ============================================================
def tg_send_text(chat_id: str, text: str):
    if not TG_TOKEN or not chat_id:
        return {"ok": False, "reason": "token/chat_id kosong"}

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=20)
    if r.status_code != 200:
        print("[TG] sendMessage ERROR", r.status_code, r.text)
        return {"ok": False, "status": r.status_code, "text": r.text}
    return {"ok": True}

def tg_send_photo(chat_id: str, jpg_bytes: bytes, caption: str):
    if not TG_TOKEN or not chat_id:
        print("[TG] skip: token/chat_id kosong")
        return {"ok": False, "reason": "token/chat_id kosong"}

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    files = {"photo": ("capture.jpg", jpg_bytes, "image/jpeg")}
    data = {"chat_id": chat_id, "caption": caption}
    r = requests.post(url, data=data, files=files, timeout=20)

    if r.status_code != 200:
        print("[TG] sendPhoto ERROR", r.status_code, r.text)
        return {"ok": False, "status": r.status_code, "text": r.text}

    print("[TG] OK sendPhoto to", chat_id)
    return {"ok": True}


# ============================================================
# DB Helpers (optional)
# ============================================================
def _open_thread_db_session():
    if get_db is None:
        return None, None
    gen = get_db()
    db = next(gen)
    return db, gen

def _close_thread_db_session(gen):
    try:
        if gen:
            gen.close()
    except Exception:
        pass

def get_latest_camera_for_masjid(db: Session, masjid_id: int):
    if db is None:
        return None
    return (
        db.query(Camera)
        .filter(Camera.id_masjid == masjid_id, Camera.status == "aktif")
        .order_by(Camera.id_camera.desc())
        .first()
    )

def get_tg_target_by_camera_id(db: Session, camera_id: int):
    if db is None:
        return None
    row = (
        db.query(Masjid.id_masjid, Masjid.tg_chat_id, Masjid.tg_cooldown)
        .join(Camera, Camera.id_masjid == Masjid.id_masjid)
        .filter(Camera.id_camera == camera_id)
        .first()
    )
    if not row:
        return None
    id_masjid, chat_id, cooldown = row
    chat_id = (str(chat_id).strip() if chat_id is not None else "")
    if not chat_id:
        return None
    cooldown = int(cooldown) if cooldown is not None else 10
    return {"id_masjid": int(id_masjid), "chat_id": chat_id, "cooldown": cooldown}

def get_tg_target_by_masjid_id(db: Session, masjid_id: int):
    if db is None:
        return None
    m = db.query(Masjid).filter(Masjid.id_masjid == masjid_id).first()
    if not m:
        return None
    chat_id = (str(m.tg_chat_id).strip() if m.tg_chat_id is not None else "")
    if not chat_id:
        return None
    cooldown = int(m.tg_cooldown) if m.tg_cooldown is not None else 10
    return {"id_masjid": int(m.id_masjid), "chat_id": chat_id, "cooldown": cooldown}


# cooldown per masjid (in-memory)
last_alert_ts_by_masjid: Dict[int, float] = {}

def maybe_send_alert_photo(db: Session, camera_id: Optional[int], masjid_id: Optional[int], frame):
    if cv2 is None:
        return

    target = None
    if camera_id:
        target = get_tg_target_by_camera_id(db, camera_id)
    if (not target) and masjid_id:
        target = get_tg_target_by_masjid_id(db, masjid_id)

    if not target:
        return

    mid = target["id_masjid"]
    chat_id = target["chat_id"]
    cooldown = target["cooldown"]

    now = time.time()
    last_ts = last_alert_ts_by_masjid.get(mid, 0.0)
    if cooldown > 0 and (now - last_ts) < cooldown:
        return

    ok_jpg, jpg_buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok_jpg:
        return

    res = tg_send_photo(chat_id, jpg_buf.tobytes(), "⚠️ ALERT: Kotak infaq tidak terdeteksi!")
    if res.get("ok"):
        last_alert_ts_by_masjid[mid] = now


# Debug TG endpoints (biar cepat cek)
@app.get("/debug/tg/me")
def debug_tg_me(current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db) if get_db else None):
    if db is None:
        return {"ok": False, "msg": "DB belum tersedia di mode cloud"}
    target = get_tg_target_by_masjid_id(db, current_user.id_masjid)
    return {"masjid_id": current_user.id_masjid, "target": target, "token_loaded": bool(TG_TOKEN)}

@app.post("/debug/tg/test")
def debug_tg_test(current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db) if get_db else None):
    if db is None:
        return {"ok": False, "msg": "DB belum tersedia di mode cloud"}
    target = get_tg_target_by_masjid_id(db, current_user.id_masjid)
    if not target:
        return {"ok": False, "msg": "tg_chat_id kosong / masjid tidak ditemukan"}

    res = tg_send_text(target["chat_id"], f"✅ TEST NOTIF untuk masjid_id={target['id_masjid']}")
    return {"target": target, "send_result": res}


# ============================================================
# YOLO (lazy init)
# ============================================================
_yolo_model = None
_model_names = None

def matches_target(cls_id: int, label: str) -> bool:
    if TARGET_CLASS_IDS:
        return cls_id in TARGET_CLASS_IDS
    if TARGET_LABELS:
        return (label or "").lower() in TARGET_LABELS
    return True

def ensure_model():
    global _yolo_model, _model_names

    if not ENABLE_YOLO:
        return
    if YOLO is None:
        raise RuntimeError("ultralytics belum terpasang")
    if _yolo_model is not None:
        return

    wp = Path(YOLO_WEIGHTS)
    if not wp.is_file():
        raise FileNotFoundError(f"YOLO_WEIGHTS tidak ditemukan: {wp} (karena best.pt gitignore, ini normal di cloud)")

    _yolo_model = YOLO(str(wp))
    # paksa CPU (stabil untuk edge demo)
    try:
        _yolo_model.to("cpu")
    except Exception:
        pass
    _model_names = getattr(_yolo_model, "names", None)
    print("[YOLO] loaded:", wp)

def infer_and_draw(frame, counter: int, roi_rect):
    if not ENABLE_YOLO:
        return []
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
            source=crop,
            imgsz=YOLO_IMG_DEF,
            conf=YOLO_CONF_DEF,
            iou=YOLO_IOU_DEF,
            max_det=50,
            device="cpu",
            verbose=False,
        )[0]
    else:
        base_area = max(1, H * W) if roi_rect is None else max(1, (roi_rect[3]-roi_rect[1])*(roi_rect[2]-roi_rect[0]))
        res = _yolo_model.predict(
            source=frame,
            imgsz=YOLO_IMG_DEF,
            conf=YOLO_CONF_DEF,
            iou=YOLO_IOU_DEF,
            max_det=50,
            device="cpu",
            verbose=False,
        )[0]

    dets = []
    if getattr(res, "boxes", None) is None:
        return dets

    if roi_rect:
        rx1, ry1, rx2, ry2 = roi_rect

    for b in res.boxes:
        conf_b = float(b.conf[0])
        x1, y1, x2, y2 = [int(v) for v in b.xyxy[0]]
        cls_id = int(b.cls[0]) if b.cls is not None else -1

        if use_crop:
            x1 += rx1; x2 += rx1
            y1 += ry1; y2 += ry1

        if isinstance(_model_names, dict):
            label = _model_names.get(cls_id, "obj")
        elif isinstance(_model_names, (list, tuple)) and 0 <= cls_id < len(_model_names):
            label = str(_model_names[cls_id])
        else:
            label = "obj"

        if not matches_target(cls_id, label):
            continue

        area = max(1, (x2 - x1) * (y2 - y1))
        if (area / base_area) < MIN_AREA_RATIO:
            continue

        if roi_rect and CENTER_IN_ROI:
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            if not (rx1 <= cx <= rx2 and ry1 <= cy <= ry2):
                continue

        dets.append((x1, y1, x2, y2, conf_b, cls_id, label))

    # draw
    for (x1, y1, x2, y2, conf_b, cls_id, label) in dets[:50]:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 215, 0), 2)
        show = LABEL_DISPLAY.get(label.lower(), label)
        cv2.putText(
            frame,
            f"{show} {conf_b:.2f}",
            (x1, max(12, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 215, 0),
            2,
            cv2.LINE_AA,
        )

    if DEBUG_LOG and counter % 30 == 0:
        print(f"[DEBUG] dets kept={len(dets)}")

    return dets


# ============================================================
# Global State (stream)
# ============================================================
cap: Optional[Any] = None
running: bool = False
latest_jpeg: Optional[bytes] = None
lock = threading.Lock()

alert_status: str = "present"

CUR_SOURCE: str = "webcam"   # webcam | video | ipcam
CUR_INDEX: int = 0
CUR_PATH: Optional[str] = None
CUR_LOOP: bool = False

CUR_CAMERA_ID: Optional[int] = None
CUR_MASJID_ID: Optional[int] = None


# ============================================================
# Open source + reconnect
# ============================================================
def open_source(source: str, index: int, path: Optional[str]):
    if cv2 is None:
        raise RuntimeError("OpenCV belum terpasang. Install opencv-python / opencv-python-headless")

    if source == "webcam":
        # di edge Windows bisa pakai backend DSHOW kalau mau, tapi biarkan default dulu
        cap0 = cv2.VideoCapture(index)
        return cap0

    if not path:
        raise ValueError("path video/url kosong")
    # ipcam/video sama-sama lewat path
    return cv2.VideoCapture(path)

def reopen_capture(source: str, index: int, path: Optional[str], sleep_s: float = 1.0):
    try:
        c = open_source(source, index, path)
        if c is None or not c.isOpened():
            try:
                if c: c.release()
            except Exception:
                pass
            time.sleep(sleep_s)
            return None
        return c
    except Exception:
        time.sleep(sleep_s)
        return None


# ============================================================
# Capture loop (thread)
# ============================================================
def capture_loop(source: str, index: int, path: Optional[str], loop_video: bool,
                 camera_id: Optional[int], masjid_id: Optional[int]):

    global cap, running, latest_jpeg, alert_status

    if not ENABLE_CAPTURE:
        running = False
        return

    if cv2 is None or np is None:
        print("[CAP] cv2/numpy belum ada -> mode cloud/dashboard saja")
        running = False
        return

    db, gen = _open_thread_db_session()
    try:
        # YOLO: jangan bikin cloud crash, tapi di edge wajib ada
        try:
            ensure_model()
        except Exception as e:
            print("[YOLO] ensure_model error:", e)
            # kalau YOLO dimatikan, masih boleh streaming kamera tanpa deteksi
            if ENABLE_YOLO:
                running = False
                return

        # open capture dengan auto-reconnect
        cap = reopen_capture(source, index, path, sleep_s=1.0)
        if cap is None:
            print("[CAM] gagal buka source", source, index, path)
            running = False
            return

        ok0, frame0 = cap.read()
        if not ok0:
            print("[CAM] frame pertama gagal, coba reconnect")
            try:
                cap.release()
            except Exception:
                pass
            cap = reopen_capture(source, index, path, sleep_s=1.0)
            if cap is None:
                running = False
                return
            ok0, frame0 = cap.read()
            if not ok0:
                running = False
                return

        roi = roi_rect_px(frame0.shape)
        absent_hist: List[int] = []
        missing_streak = 0
        counter = 0
        roi_mtime = ROI_PATH.stat().st_mtime if ROI_PATH.exists() else 0.0

        fail_read_streak = 0

        while running:
            ok, frame = cap.read()
            if not ok:
                fail_read_streak += 1

                # video loop
                if source == "video" and loop_video and fail_read_streak >= 2:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    fail_read_streak = 0
                    time.sleep(0.02)
                    continue

                # reconnect untuk ipcam/droidcam
                if fail_read_streak >= 15:
                    print("[CAM] read fail streak -> reconnect", fail_read_streak)
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = reopen_capture(source, index, path, sleep_s=1.0)
                    fail_read_streak = 0
                time.sleep(0.02)
                continue

            fail_read_streak = 0
            counter += 1

            # reload ROI kalau file berubah
            if counter % 30 == 0:
                new_mtime = ROI_PATH.stat().st_mtime if ROI_PATH.exists() else 0.0
                if new_mtime != roi_mtime:
                    roi_mtime = new_mtime
                    roi = roi_rect_px(frame.shape)
                    print("[ROI] reload:", roi)

            dets = []
            if ENABLE_YOLO and _yolo_model is not None:
                dets = infer_and_draw(frame, counter, roi) or []

            if REQUIRE_ROI and roi is None:
                dets = []

            present_raw = len(dets) > 0 if ENABLE_YOLO else True
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

            # send TG only on transition to ALERT
            if TG_TOKEN and status_str == "ALERT" and old_alert != "missing":
                maybe_send_alert_photo(db, camera_id, masjid_id, frame)

            # draw ROI
            if roi:
                cv2.rectangle(frame, (roi[0], roi[1]), (roi[2], roi[3]), (255, 165, 0), 2)

            ok2, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ok2:
                with lock:
                    latest_jpeg = jpg.tobytes()

            time.sleep(0.01)

    finally:
        try:
            if cap:
                cap.release()
        except Exception:
            pass
        _close_thread_db_session(gen)


# ============================================================
# MJPEG stream
# ============================================================
def mjpeg_gen():
    boundary = "frame"
    while True:
        with lock:
            buf = latest_jpeg
        if buf:
            yield (
                b"--" + boundary.encode() + b"\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buf + b"\r\n"
            )
        time.sleep(0.02)


# ============================================================
# Camera API
# ============================================================
@app.get("/camera/status")
def camera_status():
    return {
        "running": running,
        "alert_status": alert_status,
        "camera_id": CUR_CAMERA_ID,
        "masjid_id": CUR_MASJID_ID,
        "source": CUR_SOURCE,
        "index": CUR_INDEX,
        "path": CUR_PATH,
        "loop": CUR_LOOP,
        "enable_capture": ENABLE_CAPTURE,
        "enable_yolo": ENABLE_YOLO,
    }

@app.get("/camera/default")
def camera_default(current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db) if get_db else None):
    if db is None:
        # cloud demo fallback
        return {"source": "ipcam", "index": 0, "path": None, "loop": True, "camera_id": None, "camera_name": None}

    cam = get_latest_camera_for_masjid(db, current_user.id_masjid)
    if not cam:
        return {"source": "webcam", "index": 0, "path": None, "loop": True, "camera_id": None, "camera_name": None}

    return {
        "source": cam.source_type,
        "index": cam.source_index or 0,
        "path": cam.source_path,
        "loop": True,
        "camera_id": cam.id_camera,
        "camera_name": cam.nama,
    }

@app.post("/camera/start-default")
def start_default(current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db) if get_db else None):
    if not ENABLE_CAPTURE:
        raise HTTPException(503, "Capture disabled (cloud mode)")

    if db is None:
        raise HTTPException(503, "DB belum tersedia")

    cam = get_latest_camera_for_masjid(db, current_user.id_masjid)
    if not cam:
        raise HTTPException(404, "Kamera belum ada di database untuk masjid ini")

    if cam.source_type in ("ipcam", "video") and not cam.source_path:
        raise HTTPException(400, "Camera source_path kosong")

    return start_camera(
        source=cam.source_type,
        index=cam.source_index or 0,
        path=cam.source_path,
        loop=True,
        camera_id=cam.id_camera,
        current_user=current_user,
        db=db,
    )

@app.post("/camera/start")
def start_camera(
    source: str = Query("webcam", pattern="^(webcam|video|ipcam)$"),
    index: int = 0,
    path: Optional[str] = None,
    loop: bool = True,
    camera_id: Optional[int] = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db) if get_db else None,
):
    global running, CUR_SOURCE, CUR_INDEX, CUR_PATH, CUR_LOOP, CUR_CAMERA_ID, CUR_MASJID_ID

    if not ENABLE_CAPTURE:
        raise HTTPException(503, "Capture disabled (cloud mode)")

    if cv2 is None:
        raise HTTPException(503, "OpenCV tidak tersedia")

    if running:
        return {"ok": True, "msg": "already running"}

    if source in ("video", "ipcam") and not path:
        raise HTTPException(400, "path wajib diisi untuk video/ipcam")

    # fallback camera_id jika user tidak ngirim
    if camera_id is None and db is not None:
        cam = get_latest_camera_for_masjid(db, getattr(current_user, "id_masjid", 1))
        if cam:
            camera_id = cam.id_camera

    CUR_SOURCE, CUR_INDEX, CUR_PATH, CUR_LOOP = source, index, path, loop
    CUR_CAMERA_ID = camera_id
    CUR_MASJID_ID = getattr(current_user, "id_masjid", None)

    running = True
    threading.Thread(
        target=capture_loop,
        kwargs={
            "source": source,
            "index": index,
            "path": path,
            "loop_video": loop,
            "camera_id": CUR_CAMERA_ID,
            "masjid_id": CUR_MASJID_ID,
        },
        daemon=True,
    ).start()

    return {
        "ok": True,
        "source": source,
        "index": index,
        "path": path,
        "loop": loop,
        "camera_id": CUR_CAMERA_ID,
        "masjid_id": CUR_MASJID_ID,
    }

@app.post("/camera/stop")
def stop_camera(current_user: CurrentUser = Depends(get_current_user)):
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
        raise HTTPException(400, "camera not running")
    return StreamingResponse(mjpeg_gen(), media_type="multipart/x-mixed-replace; boundary=frame")
