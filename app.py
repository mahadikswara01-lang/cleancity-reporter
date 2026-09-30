import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, g, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "cleancity.db")
UPLOADS = os.path.join(BASE, "static", "uploads")
ALLOWED = {"png", "jpg", "jpeg", "gif", "webp"}

ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

CATEGORIES = ["Toilet", "Garbage", "Drainage", "Water", "Lighting", "Other"]
STATUSES = ["Pending", "In Progress", "Resolved"]

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB photo limit
os.makedirs(UPLOADS, exist_ok=True)


# ---------- database ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT NOT NULL,
            photo TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    db.commit()
    db.close()


# ---------- helpers ----------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("auth"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin login required.", "warning")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


# ---------- citizen routes ----------
@app.route("/")
def auth():
    if "user_id" in session:
        return redirect(url_for("report"))
    return render_template("auth.html")


@app.route("/register", methods=["POST"])
def register():
    name = request.form["name"].strip()
    email = request.form["email"].strip().lower()
    password = request.form["password"]
    if not name or not email or len(password) < 4:
        flash("Fill all fields (password: at least 4 characters).", "danger")
        return redirect(url_for("auth"))
    db = get_db()
    try:
        db.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                   (name, email, generate_password_hash(password)))
        db.commit()
    except sqlite3.IntegrityError:
        flash("This email is already registered.", "danger")
        return redirect(url_for("auth"))
    flash("Registration successful. Please log in.", "success")
    return redirect(url_for("auth"))


@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"].strip().lower()
    password = request.form["password"]
    user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user and check_password_hash(user["password"], password):
        session.clear()
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        return redirect(url_for("report"))
    flash("Invalid email or password.", "danger")
    return redirect(url_for("auth"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth"))


@app.route("/report", methods=["GET", "POST"])
@login_required
def report():
    if request.method == "POST":
        category = request.form["category"]
        location = request.form["location"].strip()
        description = request.form["description"].strip()
        photo = request.files.get("photo")

        if category not in CATEGORIES or not location or not description:
            flash("Please fill all the fields.", "danger")
            return redirect(url_for("report"))
        if not photo or photo.filename == "" or not allowed_file(photo.filename):
            flash("Please upload a photo (png, jpg, jpeg, gif, webp).", "danger")
            return redirect(url_for("report"))

        filename = datetime.now().strftime("%Y%m%d%H%M%S_") + secure_filename(photo.filename)
        photo.save(os.path.join(UPLOADS, filename))

        db = get_db()
        db.execute(
            "INSERT INTO complaints (user_id, category, location, description, photo, status, date) "
            "VALUES (?, ?, ?, ?, ?, 'Pending', ?)",
            (session["user_id"], category, location, description, filename,
             datetime.now().strftime("%d-%m-%Y %H:%M")))
        db.commit()
        flash("Complaint submitted successfully!", "success")
        return redirect(url_for("my_complaints"))
    return render_template("report.html", categories=CATEGORIES)


@app.route("/my-complaints")
@login_required
def my_complaints():
    rows = get_db().execute(
        "SELECT * FROM complaints WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],)).fetchall()
    return render_template("my_complaints.html", complaints=rows)


# ---------- admin routes ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if (request.form["username"] == ADMIN_USER and
                request.form["password"] == ADMIN_PASS):
            session.clear()
            session["is_admin"] = True
            return redirect(url_for("admin"))
        flash("Wrong admin username or password.", "danger")
    return render_template("admin_login.html")


@app.route("/admin")
@admin_required
def admin():
    db = get_db()
    rows = db.execute(
        "SELECT complaints.*, users.name AS user_name FROM complaints "
        "JOIN users ON users.id = complaints.user_id ORDER BY complaints.id DESC"
    ).fetchall()
    counts = {
        "total": len(rows),
        "pending": sum(1 for r in rows if r["status"] == "Pending"),
        "progress": sum(1 for r in rows if r["status"] == "In Progress"),
        "resolved": sum(1 for r in rows if r["status"] == "Resolved"),
    }
    return render_template("admin.html", complaints=rows, counts=counts,
                           statuses=STATUSES)


@app.route("/admin/update/<int:cid>", methods=["POST"])
@admin_required
def admin_update(cid):
    status = request.form["status"]
    if status in STATUSES:
        db = get_db()
        db.execute("UPDATE complaints SET status = ? WHERE id = ?", (status, cid))
        db.commit()
        flash(f"Complaint #{cid} marked as {status}.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/sw.js")
def service_worker():
    # service worker must be served from the site root
    return send_from_directory(os.path.join(BASE, "static"), "sw.js",
                               mimetype="application/javascript")


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
