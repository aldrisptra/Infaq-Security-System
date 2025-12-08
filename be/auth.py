# auth.py
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from passlib.context import CryptContext

from database import get_db
from models import User, Masjid, Camera

# =========================
# CONFIG
# =========================
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

router = APIRouter(prefix="/auth", tags=["auth"])

# tokenUrl HARUS sesuai endpoint login final
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# =========================
# SCHEMAS
# =========================
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUser(BaseModel):
    id: int
    username: str
    id_masjid: int
    role: str


class RegisterMasjidRequest(BaseModel):
    # Data masjid
    nama_masjid: str = Field(min_length=3, max_length=150)
    alamat: Optional[str] = None
    tg_chat_id: Optional[str] = None

    # Kamera
    camera_nama: str = Field(default="Kamera Utama")
    camera_url: str = Field(min_length=5)

    # Admin
    username: str = Field(min_length=3, max_length=100)
    # batasi aman biar ga ketemu isu 72 bytes
    password: str = Field(min_length=6, max_length=60)


# =========================
# HELPERS
# =========================
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def hash_password(plain: str) -> str:
    # bcrypt hard-limit 72 bytes
    if len(plain.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=400,
            detail="Password terlalu panjang. Maks 72 bytes (aman pakai <= 60 karakter)."
        )
    return pwd_context.hash(plain)


def verify_password(plain: str, stored: str) -> bool:
    # fallback utk akun lama yg masih plaintext
    if stored and not stored.startswith("$2"):
        return plain == stored

    # prevent error bcrypt
    if len(plain.encode("utf-8")) > 72:
        return False

    return pwd_context.verify(plain, stored)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        masjid_id: Optional[int] = payload.get("masjid_id")
        role: Optional[str] = payload.get("role")

        if user_id is None or masjid_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception

    return CurrentUser(
        id=user.id,
        username=user.username,
        id_masjid=user.id_masjid,
        role=user.role,
    )


# =========================
# ENDPOINTS
# =========================
@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = get_user_by_username(db, form_data.username)
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Username atau password salah")

    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "masjid_id": user.id_masjid,
            "role": user.role,
        }
    )
    return Token(access_token=access_token)


@router.post("/register-masjid")
def register_masjid(
    payload: RegisterMasjidRequest,
    db: Session = Depends(get_db),
):
    # username harus unique
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(400, "Username sudah dipakai")

    # validasi url kamera
    if not payload.camera_url.startswith(("http://", "https://", "rtsp://")):
        raise HTTPException(400, "camera_url harus diawali http(s):// atau rtsp://")

    try:
        # 1) MASJID
        masjid = Masjid(nama=payload.nama_masjid, alamat=payload.alamat)
        if hasattr(masjid, "tg_chat_id"):
            masjid.tg_chat_id = payload.tg_chat_id

        db.add(masjid)
        db.flush()  # biar dapat masjid.id

        # 2) ADMIN
        user = User(
            id_masjid=masjid.id,
            username=payload.username,
            password=hash_password(payload.password),
            role="admin_masjid",
        )
        db.add(user)

        # 3) KAMERA (SIMPAN LINK DI DB)
        camera = Camera(
            id_masjid=masjid.id,
            nama=payload.camera_nama,
        )

        # set field kalau ada di model
        if hasattr(camera, "source_type"):
            camera.source_type = "ipcam"
        if hasattr(camera, "source_path"):
            camera.source_path = payload.camera_url
        if hasattr(camera, "source_index"):
            camera.source_index = 0
        if hasattr(camera, "status"):
            camera.status = "aktif"

        db.add(camera)
        db.flush()

        db.commit()

        return {
            "ok": True,
            "masjid_id": masjid.id,
            "admin_username": user.username,
            "camera_id": getattr(camera, "id", None),
            "camera_source_type": getattr(camera, "source_type", None),
            "camera_source_path": getattr(camera, "source_path", None),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Gagal register masjid: {str(e)}")
