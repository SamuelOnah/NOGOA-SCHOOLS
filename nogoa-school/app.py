import os, sqlite3
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, g, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
                  MAX_CONTENT_LENGTH=5 * 1024 * 1024)
SCHOOL = "Nogoa Private"
UPLOADS = "uploads"
ALLOWED = {"pdf", "png", "jpg", "jpeg"}
os.makedirs(UPLOADS, exist_ok=True)


def db():
    if "db" not in g:
        g.db = sqlite3.connect("school.db")
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_=None):
    d = g.pop("db", None)
    if d:
        d.close()


def init_db():
    c = sqlite3.connect("school.db")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT,
        email TEXT UNIQUE, pw TEXT, role TEXT DEFAULT 'parent');
    CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY, user_id INTEGER,
        child TEXT, dob TEXT, grade TEXT, doc TEXT,
        status TEXT DEFAULT 'Pending', paid INTEGER DEFAULT 0);
    """)
    if not c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        c.execute("INSERT INTO users(name,email,pw,role) VALUES(?,?,?,?)",
                  ("Admin", "admin@nogoa.school", generate_password_hash("admin123"), "admin"))
    c.commit()
    c.close()


init_db()


@app.context_processor
def inject():
    return dict(school=SCHOOL, role=session.get("role"), username=session.get("name"))


def login_required(role=None):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **k):
            if "uid" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                return "Forbidden", 403
            return f(*a, **k)
        return wrapper
    return deco


# ---------- public pages ----------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/admissions")
def admissions():
    steps = [("Create an account", "Register as a parent or guardian."),
             ("Fill the application", "Enter your child's details."),
             ("Upload documents", "Birth certificate and passport photo."),
             ("Pay the fee", "Admission fee: NGN 5,000. The school confirms payment."),
             ("Track your status", "Check progress from your dashboard.")]
    return render_template("admissions.html", steps=steps)


# ---------- accounts ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        if len(f["password"]) < 6:
            flash("Password must be at least 6 characters.")
        else:
            try:
                db().execute("INSERT INTO users(name,email,pw) VALUES(?,?,?)",
                             (f["name"].strip(), f["email"].lower().strip(),
                              generate_password_hash(f["password"])))
                db().commit()
                flash("Account created. You can log in now.")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That email is already registered.")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db().execute("SELECT * FROM users WHERE email=?",
                         (request.form["email"].lower().strip(),)).fetchone()
        if u and check_password_hash(u["pw"], request.form["password"]):
            session.clear()
            session.update(uid=u["id"], name=u["name"], role=u["role"])
            return redirect(url_for("admin" if u["role"] == "admin" else "dashboard"))
        flash("Wrong email or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ---------- parent area ----------
@app.route("/dashboard")
@login_required()
def dashboard():
    apps = db().execute("SELECT * FROM applications WHERE user_id=? ORDER BY id DESC",
                        (session["uid"],)).fetchall()
    return render_template("dashboard.html", apps=apps)


@app.route("/apply", methods=["GET", "POST"])
@login_required()
def apply():
    if request.method == "POST":
        f, file, name = request.form, request.files.get("doc"), ""
        if file and file.filename:
            if file.filename.rsplit(".", 1)[-1].lower() not in ALLOWED:
                flash("Upload a PDF, PNG or JPG file.")
                return redirect(url_for("apply"))
            name = f"{session['uid']}_{secure_filename(file.filename)}"
            file.save(os.path.join(UPLOADS, name))
        db().execute("INSERT INTO applications(user_id,child,dob,grade,doc) VALUES(?,?,?,?,?)",
                     (session["uid"], f["child"].strip(), f["dob"], f["grade"], name))
        db().commit()
        flash("Application submitted.")
        return redirect(url_for("dashboard"))
    return render_template("apply.html")


# ---------- admin area ----------
@app.route("/admin")
@login_required("admin")
def admin():
    rows = db().execute("""SELECT a.*, u.name AS parent, u.email FROM applications a
                           JOIN users u ON u.id=a.user_id ORDER BY a.id DESC""").fetchall()
    return render_template("admin.html", rows=rows)


@app.route("/admin/<int:app_id>", methods=["POST"])
@login_required("admin")
def admin_update(app_id):
    status = request.form["status"]
    if status in ("Pending", "Under review", "Accepted", "Rejected"):
        db().execute("UPDATE applications SET status=?, paid=? WHERE id=?",
                     (status, 1 if request.form.get("paid") else 0, app_id))
        db().commit()
    return redirect(url_for("admin"))


@app.route("/admin/file/<name>")
@login_required("admin")
def admin_file(name):
    return send_from_directory(UPLOADS, name)


if __name__ == "__main__":
    app.run(debug=True)
