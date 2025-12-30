# camera_server.py
import os
import time
import json
import hmac
import base64
import hashlib
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

from fastapi import FastAPI, HTTPException, Request, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, confloat
import requests

# ============================================================
# Utils
# ============================================================
BASE_DIR = Path(__file__).resolve().parent

def env_flag(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

# optional dotenv (jangan override env prod)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(BASE_DIR / ".env", override=False)
except Exception:
    pass

IS_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))
ENABLE_CAPTURE = env_flag("ENABLE_CAPTURE", default=(not IS_RAILWAY))
ENABLE_YOLO = env_flag("ENABLE_YOLO", default=(not IS_RAILWAY))

# ============================================================
# Optional heavy imports
# ============================================================
CV2_ERR = None
NP_ERR = None
YOLO_ERR = None

try:
    import cv2  # type: ignore
except Exception as e:
    cv2 = None
    CV2_ERR = repr(e)

try:
    import numpy as np  # type: ignore
except Exception as e:
    np = None
    NP_ERR = repr(e)

try:
    from ultralytics import YOLO  # type: ignore
except Exception as e:
    YOLO = None
    YOLO_ERR = repr(e)

# ============================================================
# ENV CONFIG
# ============================================================
EDGE_API_KEY = os.getenv("EDGE_API_KEY", "").strip()  # FE: VITE_EDGE_KEY
STREAM_TOKEN = os.getenv("STREAM_TOKEN", "").strip()  # FE: VITE_STREAM_TOKEN

TG_TOKEN = os.getenv("TG_TOKEN", "").strip()

JWT_SECRET = (os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY") or "dev-secret-change-me").strip()
JWT_EXPIRE_SECONDS = int(os.getenv("JWT_EXPIRE_SECONDS", "86400"))

# YOLO params
YOLO_WEIGHTS = os.getenv("YOLO_WEIGHTS", str(BASE_DIR / "best.pt"))
YOLO_CONF = float(os.getenv("YOLO_CONF", "0.50"))
YOLO_IOU = float(os.getenv("YOLO_IOU", "0.90"))
YOLO_IMG = int(os.getenv("YOLO_IMG", "800"))
INFER_EVERY = int(os.getenv("INFER_EVERY", "1"))

# target filter (optional)
TARGET_CLASS_IDS = {int(s) for s in os.getenv("TARGET_CLASS_IDS", "").split(",") if s.strip().isdigit()}
TARGET_LABELS = {s.strip().lower() for s in os.getenv("TARGET_LABELS", "").split(",") if s.strip()}

# alert logic (optional)
MISSING_WINDOW = int(os.getenv("MISSING_WINDOW", "24"))
WARN_THRESHOLD = float(os.getenv("WARN_THRESHOLD", "0.40"))
ALERT_THRESHOLD = float(os.getenv("ALERT_THRESHOLD", "0.70"))
PRESENT_GRACE = int(os.getenv("PRESENT_GRACE", "10"))
COOLDOWN_DEFAULT = int(os.getenv("TG_COOLDOWN", "10"))

# ============================================================
# CORS
# ============================================================
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").strip()
allow_origins = ["*"] if CORS_ORIGINS == "*" else [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

app = FastAPI(docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# JWT (simple HS256)
# ============================================================
def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")

def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))

def jwt_encode(payload: Dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h}.{p}".encode("utf-8")
    sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    s = _b64url_encode(sig)
    return f"{h}.{p}.{s}"

def jwt_verify(token: str) -> Dict[str, Any]:
    try:
        h_b64, p_b64, s_b64 = token.split(".", 2)
    except ValueError:
        raise HTTPException(401, "Token tidak valid")

    signing_input = f"{h_b64}.{p_b64}".encode("utf-8")
    exp_sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    exp_b64 = _b64url_encode(exp_sig)

    if not hmac.compare_digest(exp_b64, s_b64):
        raise HTTPException(401, "Token tidak valid")

    payload = json.loads(_b64url_decode(p_b64).decode("utf-8"))
    exp = payload.get("exp")
    if exp is not None and int(time.time()) > int(exp):
        raise HTTPException(401, "Token expired")
    return payload

class EdgeUser(BaseModel):
    id_masjid: int
    role: str = "admin_masjid"
    username: str = ""

def read_bearer_from_header(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None

def get_current_user(request: Request) -> EdgeUser:
    token = read_bearer_from_header(request)
    if not token:
        raise HTTPException(401, "Missing bearer token")

    payload = jwt_verify(token)
    mid = payload.get("id_masjid") or payload.get("masjid_id")
    if mid is None:
        raise HTTPException(401, "Token tidak valid")

    return EdgeUser(
        id_masjid=int(mid),
        role=str(payload.get("role") or "admin_masjid"),
        username=str(payload.get("username") or payload.get("sub") or ""),
    )

# ============================================================
# EDGE KEY guard (header OR query) -> penting utk <img>
# ============================================================
def require_edge_key(request: Request):
    if not EDGE_API_KEY:
        return
    k = request.headers.get("x-edge-key") or request.headers.get("X-Edge-Key")
    if not k:
        k = request.query_params.get("edge_key")  # ✅ untuk <img>
    if k != EDGE_API_KEY:
        raise HTTPException(401, "Invalid edge key")

# ============================================================
# ROI file-based
# ============================================================
class ROISchema(BaseModel):
    x: confloat(ge=0.0, le=1.0)
    y: confloat(ge=0.0, le=1.0)
    w: confloat(ge=0.0, le=1.0)
    h: confloat(ge=0.0, le=1.0)

ROI_PATH = BASE_DIR / "roi_config.json"

def load_roi() -> Optional[ROISchema]:
    if not ROI_PATH.exists():
        return None
    try:
        raw = ROI_PATH.read_text("utf-8").strip()
        if not raw:
            return None
        return ROISchema(**json.loads(raw))
    except Exception:
        return None

def save_roi(roi: ROISchema) -> None:
    ROI_PATH.write_text(roi.model_dump_json(), encoding="utf-8")

def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))

def roi_rect_px(frame_shape) -> Optional[Tuple[int, int, int, int]]:
    roi = load_roi()
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

@app.get("/roi")
def api_get_roi(request: Request):
    require_edge_key(request)
    return {"roi": load_roi()}

@app.post("/roi")
def api_set_roi(request: Request, roi: ROISchema):
    require_edge_key(request)
    if roi.w <= 0 or roi.h <= 0:
        raise HTTPException(400, "w/h harus > 0")
    if roi.x + roi.w > 1 or roi.y + roi.h > 1:
        raise HTTPException(400, "ROI keluar frame")
    save_roi(roi)
    return {"roi": roi}

@app.delete("/roi")
def api_clear_roi(request: Request):
    require_edge_key(request)
    try:
        ROI_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    return {"ok": True}

# ============================================================
# Telegram helpers (optional)
# ============================================================
_last_tg_ts: Dict[int, float] = {}

def tg_send_photo(chat_id: str, jpg_bytes: bytes, caption: str):
    if not TG_TOKEN or not chat_id:
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    files = {"photo": ("capture.jpg", jpg_bytes, "image/jpeg")}
    data = {"chat_id": chat_id, "caption": caption}
    try:
        requests.post(url, data=data, files=files, timeout=20)
    except Exception:
        pass

# ============================================================
# YOLO lazy init (optional)
# ============================================================
_yolo_model = None
_yolo_names = None

def matches_target(cls_id: int, label: str) -> bool:
    if TARGET_CLASS_IDS:
        return cls_id in TARGET_CLASS_IDS
    if TARGET_LABELS:
        return (label or "").lower() in TARGET_LABELS
    return True

def ensure_yolo():
    global _yolo_model, _yolo_names
    if not ENABLE_YOLO:
        return
    if YOLO is None:
        raise RuntimeError(f"ultralytics belum ada: {YOLO_ERR}")
    if _yolo_model is not None:
        return

    wp = Path(YOLO_WEIGHTS)
    if not wp.is_file():
        raise FileNotFoundError(f"YOLO_WEIGHTS tidak ditemukan: {wp}")

    _yolo_model = YOLO(str(wp))
    try:
        _yolo_model.to("cpu")
    except Exception:
        pass
    _yolo_names = getattr(_yolo_model, "names", None)

def infer_boxes(frame, counter: int, roi_rect: Optional[Tuple[int, int, int, int]]):
    if not ENABLE_YOLO or _yolo_model is None:
        return []
    if counter % INFER_EVERY != 0:
        return []

    H, W = frame.shape[:2]
    crop_mode = roi_rect is not None
    if crop_mode:
        x1, y1, x2, y2 = roi_rect
        src = frame[y1:y2, x1:x2]
    else:
        x1 = y1 = 0
        src = frame

    res = _yolo_model.predict(
        source=src, imgsz=YOLO_IMG, conf=YOLO_CONF, iou=YOLO_IOU,
        max_det=50, device="cpu", verbose=False
    )[0]

    dets = []
    if getattr(res, "boxes", None) is None:
        return dets

    for b in res.boxes:
        conf = float(b.conf[0])
        bx1, by1, bx2, by2 = [int(v) for v in b.xyxy[0]]
        cls_id = int(b.cls[0]) if b.cls is not None else -1

        if crop_mode:
            bx1 += x1; bx2 += x1
            by1 += y1; by2 += y1

        if isinstance(_yolo_names, dict):
            label = _yolo_names.get(cls_id, "obj")
        elif isinstance(_yolo_names, (list, tuple)) and 0 <= cls_id < len(_yolo_names):
            label = str(_yolo_names[cls_id])
        else:
            label = "obj"

        if not matches_target(cls_id, label):
            continue

        dets.append((bx1, by1, bx2, by2, conf, cls_id, label))
    return dets

# ============================================================
# Global stream state
# ============================================================
running = False
cap = None
lock = threading.Lock()
latest_jpeg: Optional[bytes] = None
last_frame_ts: float = 0.0
last_cap_error: Optional[str] = None
stream_ready: bool = False
alert_status: str = "present"

CUR_SOURCE = "webcam"   # webcam | video | ipcam
CUR_INDEX = 0
CUR_PATH: Optional[str] = None
CUR_LOOP = True
CUR_MASJID_ID: Optional[int] = None

def open_capture(source: str, index: int, path: Optional[str]):
    if cv2 is None:
        raise RuntimeError("OpenCV belum terpasang")
    if source == "webcam":
        return cv2.VideoCapture(index)
    if not path:
        raise ValueError("path kosong")
    return cv2.VideoCapture(path)

def reopen_capture(source: str, index: int, path: Optional[str], sleep_s: float = 1.0):
    try:
        c = open_capture(source, index, path)
        if c is None or not c.isOpened():
            try:
                if c:
                    c.release()
            except Exception:
                pass
            time.sleep(sleep_s)
            return None
        return c
    except Exception:
        time.sleep(sleep_s)
        return None

def capture_worker(source: str, index: int, path: Optional[str], loop_video: bool, masjid_id: Optional[int]):
    global cap, running, latest_jpeg, last_frame_ts, last_cap_error, stream_ready, alert_status

    stream_ready = False
    last_frame_ts = 0.0
    last_cap_error = None
    alert_status = "present"

    if not ENABLE_CAPTURE:
        running = False
        last_cap_error = "Capture disabled (ENABLE_CAPTURE=false)"
        return
    if cv2 is None or np is None:
        running = False
        last_cap_error = "cv2/numpy tidak tersedia"
        return

    try:
        ensure_yolo()
    except Exception as e:
        if ENABLE_YOLO:
            running = False
            last_cap_error = f"YOLO init gagal: {repr(e)}"
            return

    cap = reopen_capture(source, index, path, sleep_s=1.0)
    if cap is None:
        running = False
        last_cap_error = "Gagal membuka capture"
        return

    # coba baca frame pertama
    ok0, frame0 = cap.read()
    if not ok0:
        try:
            cap.release()
        except Exception:
            pass
        cap = reopen_capture(source, index, path, sleep_s=1.0)
        if cap is None:
            running = False
            last_cap_error = "Gagal membuka capture setelah retry"
            return

    absent_hist: List[int] = []
    missing_streak = 0
    counter = 0
    fail_read_streak = 0
    roi_mtime = ROI_PATH.stat().st_mtime if ROI_PATH.exists() else 0.0
    roi = roi_rect_px(frame0.shape)

    while running:
        ok, frame = cap.read()
        if not ok:
            fail_read_streak += 1

            # looping video
            if source == "video" and loop_video and fail_read_streak >= 2:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                fail_read_streak = 0
                time.sleep(0.02)
                continue

            # reconnect
            if fail_read_streak >= 15:
                try:
                    cap.release()
                except Exception:
                    pass
                cap = reopen_capture(source, index, path, sleep_s=1.0)
                fail_read_streak = 0
                if cap is None:
                    last_cap_error = "Reconnect gagal"
                    time.sleep(0.2)
                    continue

            time.sleep(0.02)
            continue

        fail_read_streak = 0
        counter += 1

        # reload ROI jika berubah
        if counter % 30 == 0:
            new_mtime = ROI_PATH.stat().st_mtime if ROI_PATH.exists() else 0.0
            if new_mtime != roi_mtime:
                roi_mtime = new_mtime
                roi = roi_rect_px(frame.shape)

        dets = infer_boxes(frame, counter, roi) if (ENABLE_YOLO and _yolo_model is not None) else []
        present_raw = (len(dets) > 0) if ENABLE_YOLO else True

        missing_streak = 0 if present_raw else (missing_streak + 1)
        present = True if present_raw or missing_streak <= PRESENT_GRACE else False

        absent_hist.append(0 if present else 1)
        if len(absent_hist) > MISSING_WINDOW:
            absent_hist.pop(0)

        avg_absent = float(np.mean(absent_hist)) if absent_hist else (0.0 if present else 1.0)
        if avg_absent >= ALERT_THRESHOLD:
            alert_status = "missing"
        else:
            alert_status = "present"

        # draw ROI box
        if roi:
            x1, y1, x2, y2 = roi
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 165, 0), 2)

        # draw detections
        for (x1, y1, x2, y2, conf, cls_id, label) in dets[:50]:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 215, 0), 2)
            cv2.putText(frame, f"{label} {conf:.2f}", (x1, max(12, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 215, 0), 2, cv2.LINE_AA)

        ok2, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if ok2:
            with lock:
                latest_jpeg = jpg.tobytes()
                stream_ready = True
                last_frame_ts = time.time()
                last_cap_error = None

        time.sleep(0.01)

    try:
        if cap:
            cap.release()
    except Exception:
        pass

def mjpeg_generator():
    boundary = b"frame"
    # ✅ jangan error kalau belum ada frame: tunggu saja sampai latest_jpeg terisi
    while True:
        with lock:
            buf = latest_jpeg
        if buf:
            yield (b"--" + boundary + b"\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Cache-Control: no-store\r\n\r\n" + buf + b"\r\n")
        time.sleep(0.02)

# ============================================================
# Auth untuk stream: token bisa STREAM_TOKEN atau JWT
# ============================================================
def stream_auth_ok(request: Request) -> bool:
    # 1) Edge key (opsional)
    require_edge_key(request)

    # 2) token dari query/header
    token = request.query_params.get("token") or read_bearer_from_header(request)

    # kalau STREAM_TOKEN diset -> boleh pakai token random itu
    if STREAM_TOKEN:
        if token == STREAM_TOKEN:
            return True
        # kalau token ternyata JWT valid, juga kita terima (biar fleksibel)
        try:
            if token and token.count(".") == 2:
                jwt_verify(token)
                return True
        except Exception:
            pass
        return False

    # kalau STREAM_TOKEN kosong -> wajib JWT valid
    if not token:
        return False
    try:
        jwt_verify(token)
        return True
    except Exception:
        return False

# ============================================================
# Routes
# ============================================================
@app.get("/")
def root():
    return {
        "ok": True,
        "is_railway": IS_RAILWAY,
        "enable_capture": ENABLE_CAPTURE,
        "enable_yolo": ENABLE_YOLO,
        "cv2_ok": bool(cv2),
        "np_ok": bool(np),
        "yolo_ok": bool(YOLO),
        "cv2_err": CV2_ERR,
        "np_err": NP_ERR,
        "yolo_err": YOLO_ERR,
        "edge_key_enabled": bool(EDGE_API_KEY),
        "stream_token_enabled": bool(STREAM_TOKEN),
    }

@app.get("/camera/status")
def camera_status(request: Request):
    require_edge_key(request)
    return {
        "running": running,
        "stream_ready": stream_ready,
        "last_frame_ts": last_frame_ts,
        "last_cap_error": last_cap_error,
        "alert_status": alert_status,
        "source": CUR_SOURCE,
        "index": CUR_INDEX,
        "path": CUR_PATH,
        "loop": CUR_LOOP,
        "masjid_id": CUR_MASJID_ID,
    }

@app.post("/camera/start")
def camera_start(
    request: Request,
    user: EdgeUser = Depends(get_current_user),
    source: str = Query("webcam", pattern="^(webcam|video|ipcam)$"),
    index: int = 0,
    path: Optional[str] = None,
    loop: bool = True,
):
    require_edge_key(request)

    global running, CUR_SOURCE, CUR_INDEX, CUR_PATH, CUR_LOOP, CUR_MASJID_ID, latest_jpeg, stream_ready, last_cap_error

    if not ENABLE_CAPTURE:
        raise HTTPException(503, "Capture disabled (cloud mode)")
    if cv2 is None:
        raise HTTPException(503, "OpenCV tidak tersedia")
    if running:
        return {"ok": True, "msg": "already running"}

    if source in ("video", "ipcam") and not path:
        raise HTTPException(400, "path wajib untuk video/ipcam")

    CUR_SOURCE, CUR_INDEX, CUR_PATH, CUR_LOOP = source, index, path, loop
    CUR_MASJID_ID = user.id_masjid

    with lock:
        latest_jpeg = None
    stream_ready = False
    last_cap_error = None

    running = True
    threading.Thread(
        target=capture_worker,
        kwargs={"source": source, "index": index, "path": path, "loop_video": loop, "masjid_id": CUR_MASJID_ID},
        daemon=True
    ).start()

    return {"ok": True, "masjid_id": CUR_MASJID_ID, "source": CUR_SOURCE}

@app.post("/camera/stop")
def camera_stop(request: Request):
    require_edge_key(request)
    global running
    running = False
    return {"ok": True}

@app.get("/camera/stream")
def camera_stream(request: Request):
    # ✅ auth: edge_key bisa via query, token bisa via query/header
    if not stream_auth_ok(request):
        raise HTTPException(401, "Unauthorized stream")

    if not running:
        raise HTTPException(409, "Camera is not running yet")

    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )

@app.get("/camera/frame.jpg")
def camera_frame(request: Request):
    # snapshot endpoint (fallback, stabil di tunnel)
    if not stream_auth_ok(request):
        raise HTTPException(401, "Unauthorized frame")
    if not running:
        raise HTTPException(409, "Camera is not running yet")

    with lock:
        buf = latest_jpeg

    # kalau belum ada frame, return 204 (bukan error gambar rusak)
    if not buf:
        return Response(status_code=204)

    return Response(content=buf, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

@app.get("/debug/stream-auth")
def debug_stream_auth(request: Request):
    # bantu cek kenapa stream 401
    token_q = request.query_params.get("token")
    ek_q = request.query_params.get("edge_key")
    auth_h = bool(read_bearer_from_header(request))
    ek_h = bool(request.headers.get("x-edge-key") or request.headers.get("X-Edge-Key"))
    return {
        "edge_key_enabled": bool(EDGE_API_KEY),
        "stream_token_enabled": bool(STREAM_TOKEN),
        "has_token_query": bool(token_q),
        "has_edge_key_query": bool(ek_q),
        "has_bearer_header": auth_h,
        "has_edge_key_header": ek_h,
        "stream_auth_ok": stream_auth_ok(request),
    }
