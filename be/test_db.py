from database import SessionLocal
from models import Masjid

db = SessionLocal()
try:
    data = db.query(Masjid).all()
    print("OK DB CONNECT. masjid =", data)
finally:
    db.close()
