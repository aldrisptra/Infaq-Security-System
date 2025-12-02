# models.py
from sqlalchemy import (
    Column, Integer, String, Text, Enum, Float, ForeignKey, Boolean
)
from sqlalchemy.orm import relationship

from database import Base


class Masjid(Base):
    __tablename__ = "masjid"

    id = Column(Integer, primary_key=True, index=True)
    nama = Column(String(100), nullable=False)
    alamat = Column(Text)

    users = relationship("User", back_populates="masjid")
    cameras = relationship("Camera", back_populates="masjid")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    id_masjid = Column(Integer, ForeignKey("masjid.id"), nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)  # untuk sekarang plain text dulu
    role = Column(String(20), default="admin")      # 'admin' / 'superadmin'

    masjid = relationship("Masjid", back_populates="users")


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    id_masjid = Column(Integer, ForeignKey("masjid.id"), nullable=False)
    name = Column(String(100), nullable=False)
    source_type = Column(String(20), nullable=False) 
    source_url = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)

    masjid = relationship("Masjid", back_populates="cameras")
    roi = relationship("ROI", back_populates="camera", uselist=False)


class ROI(Base):
    __tablename__ = "rois"

    id = Column(Integer, primary_key=True, index=True)
    id_camera = Column(Integer, ForeignKey("cameras.id"), unique=True, nullable=False)
    x1 = Column(Float, nullable=False)
    y1 = Column(Float, nullable=False)
    x2 = Column(Float, nullable=False)
    y2 = Column(Float, nullable=False)

    camera = relationship("Camera", back_populates="roi")
