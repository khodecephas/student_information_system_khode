from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3, os, math
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"  # change this for production

DB_NAME = "sis.db"


# ---------- DB Setup ----------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Users
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin',
        avatar TEXT
    )''')

    # Students
    c.execute('''CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        matric_no TEXT UNIQUE NOT NULL,
        department TEXT,
        faculty TEXT,
        gender TEXT,
        level TEXT,
        dob TEXT,
        phone TEXT
    )''')

    conn.commit()
    conn.close()


init_db()


# ---------- Helpers ----------
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# ---------- Routes ----------
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            flash("Username and password required", "error")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                         (username, hashed_password, "admin"))
            conn.commit()
            conn.close()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already exists!", "error")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["avatar"] = user["avatar"]  # may be None
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password!", "error")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    # Dashboard is the single control panel (view/add/edit/delete/search/filter/paginate)
    if "user_id" not in session:
        return redirect(url_for("login"))

    # Handle Add/Edit (modal posts here)
    if request.method == "POST":
        student_id = request.form.get("id")  # present for edit
        name = request.form.get("name", "").strip()
        matric_no = request.form.get("matric_no", "").strip()
        gender = request.form.get("gender", "").strip()
        department = request.form.get("department", "").strip()
        faculty = request.form.get("faculty", "").strip()
        level = request.form.get("level", "").strip()
        dob = request.form.get("dob", "").strip()
        phone = request.form.get("phone", "").strip()

        if not name or not matric_no:
            flash("Name and Matric No are required", "error")
            return redirect(url_for("dashboard"))

        conn = get_db_connection()
        try:
            if student_id:  # update existing
                conn.execute(
                    """UPDATE students SET name=?, matric_no=?, gender=?, department=?, faculty=?, level=?, dob=?, phone=? WHERE id=?""",
                    (name, matric_no, gender, department, faculty, level, dob, phone, student_id)
                )
                flash("Student updated successfully!", "success")
            else:  # insert new
                conn.execute(
                    """INSERT INTO students (name, matric_no, gender, department, faculty, level, dob, phone) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (name, matric_no, gender, department, faculty, level, dob, phone)
                )
                flash("Student added successfully!", "success")
            conn.commit()
        except sqlite3.IntegrityError:
            flash("Matric No already exists!", "error")
        finally:
            conn.close()

        # Post-Redirect-Get to avoid duplicate form submission
        return redirect(url_for("dashboard"))

    # GET: list / search / paginate
    search_query = request.args.get("q", "").strip()
    gender_filter = request.args.get("gender", "").strip()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 10))
    offset = (page - 1) * per_page

    # Build base WHERE clause and params
    where_clauses = []
    params = []
    if search_query:
        where_clauses.append("(name LIKE ? OR matric_no LIKE ? OR department LIKE ? OR faculty LIKE ?)")
        like_term = f"%{search_query}%"
        params.extend([like_term, like_term, like_term, like_term])
    if gender_filter:
        where_clauses.append("gender = ?")
        params.append(gender_filter)

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    conn = get_db_connection()
    # Total count for pagination & top stat
    count_sql = f"SELECT COUNT(*) FROM students{where_sql}"
    total_students = conn.execute(count_sql, params).fetchone()[0]

    # Fetch page
    fetch_sql = f"SELECT * FROM students{where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"
    rows = conn.execute(fetch_sql, params + [per_page, offset]).fetchall()

    # Stats (global, not filtered)
    total_departments = conn.execute("SELECT COUNT(DISTINCT department) FROM students").fetchone()[0]
    total_faculties = conn.execute("SELECT COUNT(DISTINCT faculty) FROM students").fetchone()[0]
    male_students = conn.execute("SELECT COUNT(*) FROM students WHERE gender='Male'").fetchone()[0]
    female_students = conn.execute("SELECT COUNT(*) FROM students WHERE gender='Female'").fetchone()[0]

    conn.close()

    total_pages = math.ceil(total_students / per_page) if per_page else 1

    return render_template(
        "dashboard.html",
        students=rows,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_students=total_students,
        total_departments=total_departments,
        total_faculties=total_faculties,
        male_students=male_students,
        female_students=female_students,
        search_query=search_query,
        gender_filter=gender_filter,
        admin_username=session.get("username", "Admin"),
        admin_avatar=session.get("avatar") or url_for("static", filename="images/admin-avatar.png")
    )


# Keep /students endpoint for compatibility (redirects to dashboard)
@app.route("/students")
def students_redirect():
    return redirect(url_for("dashboard"))


@app.route("/delete_student/<int:id>", methods=["POST", "GET"])
def delete_student(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    conn.execute("DELETE FROM students WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash("Student deleted successfully!", "info")

    # If AJAX/fetch POST call — return JSON
    if request.method == "POST":
        return jsonify({"success": True})

    # Otherwise redirect (GET or direct link)
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully!", "info")
    return redirect(url_for("login"))


# ---------- Run ----------
if __name__ == "__main__":
    app.run(debug=True)
