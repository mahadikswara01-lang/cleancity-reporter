"""Optional: adds a demo user and 6 dummy complaints so the demo looks full.
Run once:  python seed.py
Demo login:  demo@example.com / demo123
"""
import sqlite3, os, struct, zlib
from werkzeug.security import generate_password_hash
from app import DB, UPLOADS, init_db

init_db()


def make_png(path, rgb):
    w = h = 200
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    open(path, "wb").write(png)


db = sqlite3.connect(DB)
if not db.execute("SELECT 1 FROM users WHERE email='demo@example.com'").fetchone():
    db.execute("INSERT INTO users (name, email, password) VALUES (?,?,?)",
               ("Demo User", "demo@example.com", generate_password_hash("demo123")))
    uid = db.execute("SELECT id FROM users WHERE email='demo@example.com'").fetchone()[0]
    data = [
        ("Toilet", "Kandivali East station, platform 1", "Public toilet is very dirty and has no water.", "Pending", (150, 120, 90)),
        ("Garbage", "Thakur Village main road", "Garbage pile has not been cleared for 3 days.", "In Progress", (90, 130, 90)),
        ("Drainage", "Lokhandwala Circle", "Drain is overflowing near the bus stop.", "Pending", (80, 100, 140)),
        ("Water", "Samta Nagar", "Public water tap is leaking continuously.", "Resolved", (100, 160, 200)),
        ("Lighting", "Poisar Gymkhana road", "Street light not working for a week.", "In Progress", (200, 190, 90)),
        ("Garbage", "Mahavir Nagar market", "Open dumping of waste behind the market.", "Resolved", (120, 120, 120)),
    ]
    for i, (cat, loc, desc, status, rgb) in enumerate(data, 1):
        fname = f"demo_{i}.png"
        make_png(os.path.join(UPLOADS, fname), rgb)
        db.execute("INSERT INTO complaints (user_id, category, location, description, photo, status, date) "
                   "VALUES (?,?,?,?,?,?,?)", (uid, cat, loc, desc, fname, status, f"2{i}-09-2026 10:30"))
    db.commit()
    print("Demo data added. Login: demo@example.com / demo123")
else:
    print("Demo data already exists.")
db.close()
