# models.py
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Enum
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from database import Base


class Masjid(Base):
    __tablename__ = "masjid"

    id_masjid = Column(Integer, primary_key=True, autoincrement=True)
    nama = Column(String(150), nullable=False)
    alamat = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)

    tg_chat_id = Column(String(64), nullable=True)
    tg_cooldown = Column(Integer, nullable=False, default=10)

    cameras = relationship("Camera", back_populates="masjid")
    users = relationship("User", back_populates="masjid")

    # alias supaya code lama yang pakai masjid.id tetap jalan
    @property
    def id(self):
        return self.id_masjid


class Camera(Base):
    __tablename__ = "camera"

    id_camera = Column(Integer, primary_key=True, autoincrement=True)

    id_masjid = Column(
        Integer,
        ForeignKey("masjid.id_masjid", ondelete="CASCADE"),
        nullable=False
    )

    nama = Column(String(120), nullable=False)

    source_type = Column(
        Enum("webcam", "video", "ipcam"),
        nullable=False,
        default="webcam"
    )
    source_index = Column(Integer, nullable=True)
    source_path = Column(Text, nullable=True)

    status = Column(
        Enum("aktif", "nonaktif"),
        nullable=False,
        default="aktif"
    )

    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)

    masjid = relationship("Masjid", back_populates="cameras")

    # alias opsional
    @property
    def id(self):
        return self.id_camera


class User(Base):
    __tablename__ = "users"

    # sesuai DESCRIBE kamu: PK-nya namanya "d"
    # kita map attribute "id" ke column DB "d"
    id = Column("id", Integer, primary_key=True, autoincrement=True)

    id_masjid = Column(
        Integer,
        ForeignKey("masjid.id_masjid", ondelete="CASCADE"),
        nullable=False
    )

    username = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False, default="admin_masjid")

    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)

    masjid = relationship("Masjid", back_populates="users")
