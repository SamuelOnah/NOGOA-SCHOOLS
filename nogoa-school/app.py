import os, sqlite3, uuid
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, g, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
                  MAX_CONTENT_LENGTH=5 * 1024 * 1024)
# Default site text. The admin can override any of these from /admin/settings.
DEFAULTS = dict(
    school_name="Nogoa Private Nursery, Primary and Secondary Schools",
    short_name="Nogoa Private",
    headline="Where every child is known by name.",
    intro="Nursery, primary and secondary education, with admissions, WAEC/NECO registration and alumni connections all online.",
    about="Write your school's story, mission and values here from the admin settings page.",
    admission_fee="NGN 5,000",
    contact="",
)
UPLOADS = "uploads"
ALLOWED = {"pdf", "png", "jpg", "jpeg"}
PHOTOS = os.path.join(UPLOADS, "photos")  # public photos only; documents stay private
IMG = {"png", "jpg", "jpeg", "webp"}
os.makedirs(PHOTOS, exist_ok=True)

generate_password_hash(os.environ.get("ADMIN_PASSWORD", "admin123"))

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
    CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS people(id INTEGER PRIMARY KEY, name TEXT, role TEXT, bio TEXT, photo TEXT);
    CREATE TABLE IF NOT EXISTS gallery(id INTEGER PRIMARY KEY, caption TEXT, photo TEXT);
    CREATE TABLE IF NOT EXISTS testimonials(id INTEGER PRIMARY KEY, name TEXT, text TEXT, approved INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS exams(id INTEGER PRIMARY KEY, user_id INTEGER, exam TEXT, candidate TEXT,
        dob TEXT, subjects TEXT, status TEXT DEFAULT 'Submitted');
    CREATE TABLE IF NOT EXISTS alumni(user_id INTEGER PRIMARY KEY, grad_year INTEGER, city TEXT,
        bio TEXT, photo TEXT, visible INTEGER DEFAULT 1);
    """)
    if not c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        c.execute("INSERT INTO users(name,email,pw,role) VALUES(?,?,?,?)",
                  ("Admin", "admin@nogoa.school", generate_password_hash("admin123"), "admin"))
    if not c.execute("SELECT 1 FROM people").fetchone():
        c.executemany("INSERT INTO people(name,role,bio) VALUES(?,?,?)", [
            ("Proprietor's Name", "Proprietor", "Replace this with a short welcome message from the proprietor."),
            ("Headmistress's Name", "Headmistress", "Replace this with a short message from the headmistress.")])
        c.execute("INSERT INTO testimonials(name,text,approved) VALUES(?,?,1)",
                  ("Sample parent", "Replace this sample with a real testimonial from the admin page.",))
    c.commit()
    c.close()


init_db()


def q(sql, *a):
    return db().execute(sql, a).fetchall()


def save_image(f):
    if f and f.filename and f.filename.rsplit(".", 1)[-1].lower() in IMG:
        n = uuid.uuid4().hex[:10] + "_" + secure_filename(f.filename)
        f.save(os.path.join(PHOTOS, n))
        return n
    return ""


@app.route("/media/<name>")
def media(name):
    return send_from_directory(PHOTOS, name)


def site():
    return {**DEFAULTS, **{r["k"]: r["v"] for r in q("SELECT k,v FROM settings")}}


@app.context_processor
def inject():
    S = site()
    return dict(s=S, school=S["school_name"], role=session.get("role"), username=session.get("name"))


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
    return render_template("index.html", people=q("SELECT * FROM people ORDER BY id LIMIT 4"),
        quotes=q("SELECT * FROM testimonials WHERE approved=1 ORDER BY id DESC LIMIT 3"),
        photos=q("SELECT * FROM gallery ORDER BY id DESC LIMIT 6"))


@app.route("/about")
def about():
    return render_template("about.html", people=q("SELECT * FROM people ORDER BY id"))


@app.route("/admissions")
def admissions():
    steps = [("Create an account", "Register as a parent or guardian."),
             ("Fill the application", "Enter your child's details."),
             ("Upload documents", "Birth certificate and passport photo."),
             ("Pay the fee", f"Admission fee: {site()['admission_fee']}. The school confirms payment."),
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


# ---------- gallery & testimonials ----------
@app.route("/gallery")
def gallery():
    return render_template("gallery.html", photos=q("SELECT * FROM gallery ORDER BY id DESC"))


@app.route("/testimonials", methods=["GET", "POST"])
def testimonials():
    if request.method == "POST":
        if "uid" not in session:
            return redirect(url_for("login"))
        db().execute("INSERT INTO testimonials(name,text) VALUES(?,?)",
                     (session["name"], request.form["text"].strip()[:500]))
        db().commit()
        flash("Thank you. Your testimonial will show once the school approves it.")
        return redirect(url_for("testimonials"))
    return render_template("testimonials.html",
                           items=q("SELECT * FROM testimonials WHERE approved=1 ORDER BY id DESC"))


# ---------- WAEC / NECO registration ----------
SUBJECTS = ["English Language", "Mathematics", "Civic Education", "Biology", "Chemistry", "Physics",
            "Economics", "Government", "Literature in English", "Commerce", "Financial Accounting",
            "Geography", "Agricultural Science", "Further Mathematics"]


@app.route("/exams", methods=["GET", "POST"])
@login_required()
def exams():
    if request.method == "POST":
        f = request.form
        if f["exam"] in ("WAEC", "NECO") and f.getlist("subjects"):
            db().execute("INSERT INTO exams(user_id,exam,candidate,dob,subjects) VALUES(?,?,?,?,?)",
                         (session["uid"], f["exam"], f["candidate"].strip(), f["dob"],
                          ", ".join(s for s in f.getlist("subjects") if s in SUBJECTS)))
            db().commit()
            flash("Registration submitted. The school will confirm it.")
        else:
            flash("Choose an exam and at least one subject.")
        return redirect(url_for("exams"))
    return render_template("exams.html", subjects=SUBJECTS,
                           mine=q("SELECT * FROM exams WHERE user_id=? ORDER BY id DESC", session["uid"]))


# ---------- classmates ----------
@app.route("/classmates")
@login_required()
def classmates():
    y, name = request.args.get("year", "").strip(), request.args.get("q", "").strip()
    rows = q("""SELECT u.name, a.* FROM alumni a JOIN users u ON u.id=a.user_id
                WHERE a.visible=1 AND (?='' OR a.grad_year=?) AND u.name LIKE ?
                ORDER BY a.grad_year DESC, u.name""", y, y, f"%{name}%")
    return render_template("classmates.html", rows=rows, year=y, name=name)


@app.route("/profile", methods=["GET", "POST"])
@login_required()
def profile():
    me = q("SELECT * FROM alumni WHERE user_id=?", session["uid"])
    if request.method == "POST":
        f = request.form
        photo = save_image(request.files.get("photo")) or (me[0]["photo"] if me else "")
        db().execute("INSERT OR REPLACE INTO alumni VALUES(?,?,?,?,?,?)",
                     (session["uid"], int(f["grad_year"]), f["city"].strip(),
                      f["bio"].strip()[:300], photo, 1 if f.get("visible") else 0))
        db().commit()
        flash("Profile saved.")
        return redirect(url_for("classmates"))
    return render_template("profile.html", me=me[0] if me else None)


# ---------- admin: content ----------
@app.route("/admin/content", methods=["GET", "POST"])
@login_required("admin")
def admin_content():
    if request.method == "POST":
        f, k = request.form, request.form["kind"]
        if k == "person":
            db().execute("INSERT INTO people(name,role,bio,photo) VALUES(?,?,?,?)",
                         (f["name"], f["role"], f["bio"], save_image(request.files.get("photo"))))
        elif k == "photo" and (p := save_image(request.files.get("photo"))):
            db().execute("INSERT INTO gallery(caption,photo) VALUES(?,?)", (f["caption"], p))
        elif k == "approve":
            db().execute("UPDATE testimonials SET approved=1 WHERE id=?", (f["id"],))
        elif k == "exam_status":
            db().execute("UPDATE exams SET status=? WHERE id=?", (f["status"], f["id"]))
        elif k == "delete" and f["table"] in ("people", "gallery", "testimonials"):
            db().execute(f"DELETE FROM {f['table']} WHERE id=?", (f["id"],))
        db().commit()
        return redirect(url_for("admin_content"))
    return render_template("admin_content.html", people=q("SELECT * FROM people ORDER BY id"),
        photos=q("SELECT * FROM gallery ORDER BY id DESC"),
        quotes=q("SELECT * FROM testimonials ORDER BY approved, id DESC"),
        exams=q("SELECT e.*, u.name AS parent FROM exams e JOIN users u ON u.id=e.user_id ORDER BY e.id DESC"))


# ---------- admin: site text, hero/logo images, password ----------
@app.route("/admin/settings", methods=["GET", "POST"])
@login_required("admin")
def admin_settings():
    if request.method == "POST":
        f = request.form
        for k in DEFAULTS:
            if k in f:
                db().execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, f[k].strip()))
        for k in ("hero", "logo"):
            n = save_image(request.files.get(k))
            if n:
                db().execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, n))
            if f.get("remove_" + k):
                db().execute("DELETE FROM settings WHERE k=?", (k,))
        if len(f.get("new_password", "")) >= 6:
            db().execute("UPDATE users SET pw=? WHERE id=?",
                         (generate_password_hash(f["new_password"]), session["uid"]))
        db().commit()
        flash("Saved.")
        return redirect(url_for("admin_settings"))
    return render_template("admin_settings.html")


if __name__ == "__main__":
    app.run(debug=True)
