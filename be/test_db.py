from database import SessionLocal
from models import Masjid

db = SessionLocal()

masjid_list = db.query(Masjid).all()
for m in masjid_list:
    print(m.id, m.nama)

db.close()
