# camera_server.py
import os
import time
import json
import threading
import hashlib
import base64
import hmac
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
from pydantic import BaseModel, confloat
import requests

# ============================================================
# MODE SWITCH (Railway aman, Edge tetap full)
# ============================================================
def env_flag(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip().lower()
    return v in ("1", "true", "yes", "on")

IS_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"))

# Default: Railway OFF, Lokal ON
ENABLE_CAPTURE = env_flag("ENABLE_CAPTURE", default=(not IS_RAILWAY))
ENABLE_YOLO = env_flag("ENABLE_YOLO", default=(not IS_RAILWAY))

# ============================================================
# Optional heavy imports (cv2/numpy/ultralytics)
# ============================================================
CV2_IMPORT_ERROR = None
NP_IMPORT_ERROR = None
YOLO_IMPORT_ERROR = None

try:
    import cv2  # type: ignore
except Exception as e:
    cv2 = None
    CV2_IMPORT_ERROR = repr(e)

try:
    import numpy as np  # type: ignore
except Exception as e:
    np = None
    NP_IMPORT_ERROR = repr(e)

try:
    from ultralytics import YOLO  # type: ignore
except Exception as e:
    YOLO = None
    YOLO_IMPORT_ERROR = repr(e)

# ============================================================
# Optional imports (dotenv/auth/db/models)
# ============================================================
BASE_DIR = Path(__file__).resolve().parent

# dotenv optional (JANGAN override env Railway)
DOTENV_ERROR = None
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(BASE_DIR / ".env", override=False)
except Exception as e:
    DOTENV_ERROR = repr(e)

# DB + Models optional
Session = Any
Camera = Any
Masjid = Any
get_db = None
DB_IMPORT_ERROR = None

try:
    from sqlalchemy.orm import Session as _Session  # type: ignore
    Session = _Session
    from database import get_db as _get_db  # type: ignore
    get_db = _get_db
    from models import Camera as _Camera, Masjid as _Masjid  # type: ignore
    Camera, Masjid = _Camera, _Masjid
except Exception as e:
    DB_IMPORT_ERROR = repr(e)

def _get_db_none():
    # Fallback dependency agar FastAPI tidak bikin "db" jadi query param
    return None

DB_DEP = get_db if get_db else _get_db_none

# ============================================================
# Auth: pakai auth.py kalau bisa, kalau gagal -> fallback auth
# ============================================================
AUTH_IMPORT_ERROR = None
auth_router = None
CurrentUser = Any

def _dummy_user():
    class U:
        id_masjid = 1
        role = "demo"
        username = "demo"
    return U()

def get_current_user():
    return _dummy_user()

try:
    from auth import router as _auth_router  # type: ignore
    from auth import get_current_user as _get_current_user, CurrentUser as _CurrentUser  # type: ignore
    auth_router = _auth_router
    get_current_user = _get_current_user
    CurrentUser = _CurrentUser
except Exception as e:
    AUTH_IMPORT_ERROR = repr(e)
    auth_router = None

# ============================================================
# Fallback auth (biar /auth/login & /auth/register-masjid selalu ada)
# ============================================================
FALLBACK_AUTH_ENABLED = env_flag("FALLBACK_AUTH", default=True)

JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
if not JWT_SECRET:
    # untuk demo saja (WAJIB diganti di production)
    JWT_SECRET = "dev-secret-change-me"

JWT_EXPIRE_SECONDS = int(os.getenv("JWT_EXPIRE_SECONDS", "86400"))

# store user in memory (DEMO ONLY)
_fallback_users: Dict[str, Dict[str, Any]] = {}
_fallback_next_masjid_id = 1

class FallbackUser(BaseModel):
    username: str
    role: str = "admin_masjid"
    id_masjid: int = 1
    masjid_name: Optional[str] = None

def _hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")

def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))

def _jwt_like_encode(payload: Dict[str, Any]) -> str:
    """
    Token mirip JWT (header.payload.signature) tanpa dependency PyJWT.
    HMAC-SHA256.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def _jwt_like_decode(token: str) -> Dict[str, Any]:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".", 2)
    except ValueError:
        raise HTTPException(401, "Invalid token format")

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    expected_sig_b64 = _b64url_encode(expected_sig)

    if not hmac.compare_digest(expected_sig_b64, sig_b64):
        raise HTTPException(401, "Invalid token signature")

    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))

    exp = payload.get("exp")
    if exp is not None:
        try:
            exp_i = int(exp)
            if int(time.time()) > exp_i:
                raise HTTPException(401, "Token expired")
        except Exception:
            raise HTTPException(401, "Invalid token exp")

    return payload

async def _read_body_any(request: Request) -> Dict[str, Any]:
    """
    Terima JSON atau x-www-form-urlencoded agar FE fleksibel.
    """
    ct = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" in ct or "multipart/form-data" in ct:
        form = await request.form()
        return dict(form)
    try:
        return await request.json()
    except Exception:
        return {}

def _fallback_get_current_user(request: Request) -> FallbackUser:
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = auth.split(" ", 1)[1].strip()
    data = _jwt_like_decode(token)

    return FallbackUser(
        username=str(data.get("username") or "demo"),
        role=str(data.get("role") or "admin_masjid"),
        id_masjid=int(data.get("id_masjid") or 1),
        masjid_name=data.get("masjid_name"),
    )

# bikin router fallback kalau auth.py gagal
USING_FALLBACK_AUTH = False
if auth_router is None and FALLBACK_AUTH_ENABLED:
    from fastapi import APIRouter

    fallback_router = APIRouter(prefix="/auth", tags=["auth"])
    USING_FALLBACK_AUTH = True

    @fallback_router.post("/register-masjid")
    async def register_masjid(request: Request):
        """
        Minimal fields (boleh JSON atau form):
        - username
        - password
        - (optional) masjid_name / nama_masjid
        """
        global _fallback_next_masjid_id
        body = await _read_body_any(request)

        username = str(body.get("username") or "").strip()
        password = str(body.get("password") or "").strip()

        if not username or not password:
            raise HTTPException(400, "username dan password wajib diisi")

        if username in _fallback_users:
            raise HTTPException(409, "username sudah terdaftar")

        masjid_name = str(body.get("nama_masjid") or body.get("masjid_name") or "Masjid Demo").strip()

        user = {
            "username": username,
            "pw_hash": _hash_pw(password),
            "role": "admin_masjid",
            "id_masjid": _fallback_next_masjid_id,
            "masjid_name": masjid_name,
        }
        _fallback_users[username] = user
        _fallback_next_masjid_id += 1

        payload = {
            "username": user["username"],
            "role": user["role"],
            "id_masjid": user["id_masjid"],
            "masjid_name": user["masjid_name"],
            "exp": int(time.time()) + JWT_EXPIRE_SECONDS,
        }
        token = _jwt_like_encode(payload)

        # return shape aman untuk banyak FE:
        return {
            "ok": True,
            "token": token,
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "username": user["username"],
                "role": user["role"],
                "id_masjid": user["id_masjid"],
                "masjid_name": user["masjid_name"],
            },
        }

    @fallback_router.post("/login")
    async def login(request: Request):
        """
        Terima JSON / form: username + password
        """
        body = await _read_body_any(request)

        username = str(body.get("username") or "").strip()
        password = str(body.get("password") or "").strip()
        if not username or not password:
            raise HTTPException(400, "username dan password wajib diisi")

        u = _fallback_users.get(username)
        if not u or u["pw_hash"] != _hash_pw(password):
            raise HTTPException(401, "username/password salah")

        payload = {
            "username": u["username"],
            "role": u["role"],
            "id_masjid": u["id_masjid"],
            "masjid_name": u.get("masjid_name"),
            "exp": int(time.time()) + JWT_EXPIRE_SECONDS,
        }
        token = _jwt_like_encode(payload)

        # OAuth-ish style:
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {"username": u["username"], "role": u["role"], "id_masjid": u["id_masjid"], "masjid_name": u.get("masjid_name")},
        }

    @fallback_router.get("/me")
    async def me(user: FallbackUser = Depends(_fallback_get_current_user)):
        return {"ok": True, "user": user.model_dump()}

    auth_router = fallback_router
    get_current_user = _fallback_get_current_user
    CurrentUser = FallbackUser

# ============================================================
# ENV / CONFIG
# ============================================================
TG_TOKEN = os.getenv("TG_TOKEN", "").strip()
EDGE_API_KEY = os.getenv("EDGE_API_KEY", "").strip()
STREAM_TOKEN = os.getenv("STREAM_TOKEN", "").strip()


MISSING_WINDOW = int(os.getenv("MISSING_WINDOW", "24"))
WARN_THRESHOLD = float(os.getenv("WARN_THRESHOLD", "0.40"))
ALERT_THRESHOLD = float(os.getenv("ALERT_THRESHOLD", "0.70"))
PRESENT_GRACE = int(os.getenv("PRESENT_GRACE", "10"))

YOLO_CONF_DEF = float(os.getenv("YOLO_CONF", "0.50"))
YOLO_IOU_DEF = float(os.getenv("YOLO_IOU", "0.90"))
YOLO_IMG_DEF = int(os.getenv("YOLO_IMG", "800"))
MIN_AREA_RATIO = float(os.getenv("MIN_AREA_RATIO", "0.01"))
INFER_EVERY = int(os.getenv("INFER_EVERY", "1"))

ROI_STRATEGY = os.getenv("ROI_STRATEGY", "crop").lower()  # crop | full
CENTER_IN_ROI = os.getenv("CENTER_IN_ROI", "1") == "1"
REQUIRE_ROI = os.getenv("REQUIRE_ROI", "0") == "1"
DEBUG_LOG = os.getenv("DEBUG_LOG", "1") == "1"

# CORS
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").strip()
allow_origins = ["*"] if CORS_ORIGINS == "*" else [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]

# YOLO weights (edge biasanya lokal)
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

@app.get("/debug/bootstrap")
def debug_bootstrap():
    # daftar route biar gampang cek /auth ada atau nggak
    routes = []
    for r in app.routes:
        p = getattr(r, "path", None)
        if p:
            routes.append(p)

    return {
        "is_railway": IS_RAILWAY,
        "ENABLE_CAPTURE_env": os.getenv("ENABLE_CAPTURE"),
        "ENABLE_YOLO_env": os.getenv("ENABLE_YOLO"),
        "computed_enable_capture": ENABLE_CAPTURE,
        "computed_enable_yolo": ENABLE_YOLO,
        "dotenv_error": DOTENV_ERROR,
        "db_import_error": DB_IMPORT_ERROR,
        "auth_import_error": AUTH_IMPORT_ERROR,
        "cv2_import_error": CV2_IMPORT_ERROR,
        "numpy_import_error": NP_IMPORT_ERROR,
        "ultralytics_import_error": YOLO_IMPORT_ERROR,
        "fallback_auth_enabled": FALLBACK_AUTH_ENABLED,
        "using_fallback_auth": USING_FALLBACK_AUTH,
        "db_available": bool(get_db),
        "auth_router_loaded": bool(auth_router),
        "has_auth_routes": any(p.startswith("/auth") for p in routes),
        "sample_routes": routes[:60],
    }

def require_edge_key(request: Request):
    """
    Kalau EDGE_API_KEY di-set, semua request ke endpoint edge harus bawa header:
    X-Edge-Key: <EDGE_API_KEY>
    """
    if not EDGE_API_KEY:
        return
    k = request.headers.get("x-edge-key") or request.headers.get("X-Edge-Key") or ""
    if k != EDGE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid edge key")


@app.get("/debug/env")
def debug_env():
    return {
        "ENABLE_CAPTURE": os.getenv("ENABLE_CAPTURE"),
        "ENABLE_YOLO": os.getenv("ENABLE_YOLO"),
        "computed_enable_capture": ENABLE_CAPTURE,
        "computed_enable_yolo": ENABLE_YOLO,
    }

@app.get("/debug/railway")
def debug_railway():
    return {
        "RAILWAY_ENVIRONMENT": os.getenv("RAILWAY_ENVIRONMENT"),
        "RAILWAY_PROJECT_ID": os.getenv("RAILWAY_PROJECT_ID"),
        "RAILWAY_SERVICE_ID": os.getenv("RAILWAY_SERVICE_ID"),
        "PORT": os.getenv("PORT"),
        "ENABLE_CAPTURE": os.getenv("ENABLE_CAPTURE"),
        "ENABLE_YOLO": os.getenv("ENABLE_YOLO"),
    }

@app.get("/")
def root():
    return {
        "ok": True,
        "msg": "camera_server up",
        "enable_capture": ENABLE_CAPTURE,
        "enable_yolo": ENABLE_YOLO,
        "cv2": bool(cv2),
        "numpy": bool(np),
        "ultralytics": bool(YOLO),
        "token_loaded": bool(TG_TOKEN),
        "db_available": bool(get_db),
        "auth_available": bool(auth_router),
        "is_railway": IS_RAILWAY,
        "using_fallback_auth": USING_FALLBACK_AUTH,
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
        print("[ROI] load error:", repr(e))
        return None

def save_roi_rel(roi: ROISchema) -> None:
    try:
        if hasattr(roi, "model_dump_json"):
            ROI_PATH.write_text(roi.model_dump_json(), encoding="utf-8")
        else:
            ROI_PATH.write_text(roi.json(), encoding="utf-8")
    except Exception as e:
        print("[ROI] save error:", repr(e))

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
        print("[ROI] delete error:", repr(e))
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
        return {"ok": False, "reason": "token/chat_id kosong"}
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    files = {"photo": ("capture.jpg", jpg_bytes, "image/jpeg")}
    data = {"chat_id": chat_id, "caption": caption}
    r = requests.post(url, data=data, files=files, timeout=20)
    if r.status_code != 200:
        print("[TG] sendPhoto ERROR", r.status_code, r.text)
        return {"ok": False, "status": r.status_code, "text": r.text}
    return {"ok": True}

# ============================================================
# DB Helpers
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

@app.get("/debug/tg/me")
def debug_tg_me(current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(DB_DEP)):
    if db is None:
        return {"ok": False, "msg": "DB belum tersedia (mode cloud / fallback)"}
    target = get_tg_target_by_masjid_id(db, current_user.id_masjid)
    return {"ok": True, "masjid_id": current_user.id_masjid, "target": target, "token_loaded": bool(TG_TOKEN)}

@app.post("/debug/tg/test")
def debug_tg_test(current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(DB_DEP)):
    if db is None:
        return {"ok": False, "msg": "DB belum tersedia (mode cloud / fallback)"}
    target = get_tg_target_by_masjid_id(db, current_user.id_masjid)
    if not target:
        return {"ok": False, "msg": "tg_chat_id kosong / masjid tidak ditemukan"}
    res = tg_send_text(target["chat_id"], f"✅ TEST NOTIF untuk masjid_id={target['id_masjid']}")
    return {"ok": True, "target": target, "send_result": res}

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
        raise RuntimeError(f"ultralytics belum terpasang: {YOLO_IMPORT_ERROR}")
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
    _model_names = getattr(_yolo_model, "names", None)
    print("[YOLO] loaded:", wp)

def infer_and_draw(frame, counter: int, roi_rect):
    if not ENABLE_YOLO or _yolo_model is None:
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
            source=crop, imgsz=YOLO_IMG_DEF, conf=YOLO_CONF_DEF, iou=YOLO_IOU_DEF,
            max_det=50, device="cpu", verbose=False
        )[0]
    else:
        base_area = max(1, H * W)
        res = _yolo_model.predict(
            source=frame, imgsz=YOLO_IMG_DEF, conf=YOLO_CONF_DEF, iou=YOLO_IOU_DEF,
            max_det=50, device="cpu", verbose=False
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

        if use_crop and roi_rect:
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

    for (x1, y1, x2, y2, conf_b, cls_id, label) in dets[:50]:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 215, 0), 2)
        show = LABEL_DISPLAY.get(label.lower(), label)
        cv2.putText(frame, f"{show} {conf_b:.2f}", (x1, max(12, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 215, 0), 2, cv2.LINE_AA)

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

stream_ready = False
last_frame_ts = 0.0
last_cap_error = None



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
        raise RuntimeError("OpenCV belum terpasang.")

    if source == "webcam":
        return cv2.VideoCapture(index)

    if not path:
        raise ValueError("path video/url kosong")
    return cv2.VideoCapture(path)

def reopen_capture(source: str, index: int, path: Optional[str], sleep_s: float = 1.0):
    try:
        c = open_source(source, index, path)
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

# ============================================================
# Capture loop (thread)
# ============================================================
def capture_loop(source: str, index: int, path: Optional[str], loop_video: bool,
                 camera_id: Optional[int], masjid_id: Optional[int]):

    global cap, running, latest_jpeg, alert_status, stream_ready, last_frame_ts, last_cap_error

    # reset stream state tiap start
    stream_ready = False
    last_frame_ts = 0.0
    last_cap_error = None

    if not ENABLE_CAPTURE:
        running = False
        last_cap_error = "Capture disabled (ENABLE_CAPTURE=false)"
        return

    if cv2 is None or np is None:
        print("[CAP] cv2/numpy belum ada -> mode cloud/dashboard saja")
        running = False
        last_cap_error = "cv2/numpy tidak tersedia"
        return

    db, gen = _open_thread_db_session()
    try:
        try:
            ensure_model()
        except Exception as e:
            print("[YOLO] ensure_model error:", repr(e))
            if ENABLE_YOLO:
                running = False
                last_cap_error = f"YOLO init gagal: {repr(e)}"
                return

        # === 1) buka capture pertama kali
        cap = reopen_capture(source, index, path, sleep_s=1.0)
        if cap is None:
            running = False
            last_cap_error = "Gagal membuka kamera/capture (cap is None / not opened)"
            return

        # coba baca frame awal
        ok0, frame0 = cap.read()
        if not ok0:
            # release & coba buka lagi
            try:
                cap.release()
            except Exception:
                pass

            # === 2) buka capture ulang kalau frame pertama gagal
            cap = reopen_capture(source, index, path, sleep_s=1.0)
            if cap is None:
                running = False
                last_cap_error = "Gagal membuka kamera/capture setelah retry pertama"
                return

            ok0, frame0 = cap.read()
            if not ok0:
                running = False
                last_cap_error = "Tidak bisa membaca frame pertama dari kamera (ok0 false)"
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

                # untuk video looping
                if source == "video" and loop_video and fail_read_streak >= 2:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    fail_read_streak = 0
                    time.sleep(0.02)
                    continue

                # kalau gagal terlalu sering, coba reconnect
                if fail_read_streak >= 15:
                    try:
                        cap.release()
                    except Exception:
                        pass

                    cap = reopen_capture(source, index, path, sleep_s=1.0)
                    fail_read_streak = 0

                    if cap is None:
                        last_cap_error = "Reconnect gagal: cap is None"
                        time.sleep(0.2)
                        continue

                time.sleep(0.02)
                continue

            fail_read_streak = 0
            counter += 1

            # reload ROI kalau berubah
            if counter % 30 == 0:
                new_mtime = ROI_PATH.stat().st_mtime if ROI_PATH.exists() else 0.0
                if new_mtime != roi_mtime:
                    roi_mtime = new_mtime
                    roi = roi_rect_px(frame.shape)

            dets = []
            if ENABLE_YOLO and _yolo_model is not None:
                dets = infer_and_draw(frame, counter, roi) or []

            if REQUIRE_ROI and roi is None:
                dets = []

            present_raw = (len(dets) > 0) if ENABLE_YOLO else True
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

            if TG_TOKEN and status_str == "ALERT" and old_alert != "missing":
                maybe_send_alert_photo(db, camera_id, masjid_id, frame)

            if roi:
                cv2.rectangle(frame, (roi[0], roi[1]), (roi[2], roi[3]), (255, 165, 0), 2)

            ok2, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ok2:
                with lock:
                    latest_jpeg = jpg.tobytes()
                    stream_ready = True
                    last_frame_ts = time.time()
                    last_cap_error = None

            time.sleep(0.01)

    finally:
        try:
            if cap:
                cap.release()
        except Exception:
            pass
        stream_ready = False
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

def gen_frames():
    yield from mjpeg_gen()
        

# ============================================================
# Camera API
# ============================================================
@app.get("/camera/status")
def camera_status(request: Request):
    require_edge_key(request)
    return {
        "running": running,
        "stream_ready": stream_ready,
        "last_frame_ts": last_frame_ts,
        "last_cap_error": last_cap_error,
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
def camera_default(request: Request):
    require_edge_key(request)
    # kembalikan state terakhir yang tersimpan di server (atau default)
    return {
        "source": CUR_SOURCE or "webcam",
        "index": CUR_INDEX or 0,
        "path": CUR_PATH,
        "loop": CUR_LOOP if CUR_LOOP is not None else True,
        "camera_id": CUR_CAMERA_ID,
        "camera_name": None,
    }

@app.post("/camera/start-default")
def start_default(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(DB_DEP),
):
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
    request: Request,
    source: str = Query("webcam", pattern="^(webcam|video|ipcam)$"),
    index: int = 0,
    path: Optional[str] = None,
    loop: bool = True,
    camera_id: Optional[int] = None,
):
    require_edge_key(request)

    global running, CUR_SOURCE, CUR_INDEX, CUR_PATH, CUR_LOOP, CUR_CAMERA_ID, CUR_MASJID_ID, stream_ready, last_cap_error

    if not ENABLE_CAPTURE:
        raise HTTPException(503, "Capture disabled (cloud mode)")

    if cv2 is None:
        raise HTTPException(503, "OpenCV tidak tersedia")

    if running:
        return {"ok": True, "msg": "already running"}

    if source in ("video", "ipcam") and not path:
        raise HTTPException(400, "path wajib diisi untuk video/ipcam")

    CUR_SOURCE, CUR_INDEX, CUR_PATH, CUR_LOOP = source, index, path, loop
    CUR_CAMERA_ID = camera_id
    CUR_MASJID_ID = None

    stream_ready = False
    last_cap_error = None

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
def stop_camera(request: Request):
    require_edge_key(request)
    global running
    running = False
    return {"ok": True}

@app.get(
    "/camera/stream",
    response_class=StreamingResponse,
    responses={200: {"description": "MJPEG stream", "content": {"multipart/x-mixed-replace; boundary=frame": {}}}},
)
def camera_stream(token: Optional[str] = Query(None)):
    # kalau STREAM_TOKEN diset, wajib benar
    if STREAM_TOKEN and token != STREAM_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid stream token")

    # kalau kamera belum jalan atau belum ada frame, jangan loading kosong
    if not running:
        raise HTTPException(status_code=409, detail="Camera is not running yet")
    if not stream_ready:
        raise HTTPException(status_code=425, detail="Stream not ready yet (waiting first frame)")

    return StreamingResponse(
        mjpeg_gen(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
