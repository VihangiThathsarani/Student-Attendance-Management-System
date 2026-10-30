from flask import Flask, request, redirect, url_for, render_template_string, render_template, session, abort
import sqlite3
import secrets
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = secrets.token_hex(32)
DATABASE = "students.db"

@app.before_request
def require_login():
    public_endpoints = {"login", "static"}

    if request.endpoint in public_endpoints:
        return None

    if "user_id" not in session:
        return redirect(url_for("login"))

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db

# ---------- USER ACCOUNTS ----------

def create_users_table():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL
                    CHECK(role IN (
                        'Admin',
                        'Student',
                        'Advisor',
                        'Coordinator'
                    )),
                student_id INTEGER,
                FOREIGN KEY (student_id)
                    REFERENCES students(id) ON DELETE CASCADE
            )
        """)

def create_sample_accounts():
    accounts = [
        ("admin", "Admin"),
        ("student", "Student"),
        
    ]

    with get_db() as db:
        for username, role in accounts:
            existing = db.execute(
                "SELECT id FROM users WHERE username = ?",
                (username,)
            ).fetchone()

            if existing is None:
                password = input(
                    f"Enter a password for {username}: "
                )

                if len(password) < 8:
                    raise ValueError(
                        "Password must contain at least 8 characters."
                    )

                db.execute("""
                    INSERT INTO users
                    (username, password_hash, role)
                    VALUES (?, ?, ?)
                """, (
                    username,
                    generate_password_hash(password),
                    role
                ))

def link_sample_student_account():
    with get_db() as db:
        student = db.execute(
            "SELECT id FROM students WHERE student_id = ?",
            ("EG/2023/5677",)
        ).fetchone()

        if student:
            db.execute("""
                UPDATE users
                SET student_id = ?
                WHERE username = ?
                  AND role = ?
            """, (
                student["id"],
                "student",
                "Student"
            ))

# Login and logout

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,)
            ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["student_id"] = user["student_id"]

            if user["role"] == "Admin":
                return redirect(url_for("dashboard"))

            elif user["role"] == "Student":
                return redirect(url_for("leave_management"))

            else:
                session.clear()
                return "Access Denied: Invalid user role.", 403

        error = "Invalid username or password."

    return render_template("login.html", error=error)

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

def create_database():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                email TEXT,
                department TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK(status IN ('Present', 'Absent', 'Late')),
                FOREIGN KEY (student_id)
                    REFERENCES students(id)
                    ON DELETE CASCADE,
                UNIQUE(student_id, date)
            )
        """)

# Add batch and semester to existing students
        columns = [
            row["name"]
            for row in db.execute("PRAGMA table_info(students)")
        ]

        if "batch" not in columns:
            db.execute(
                "ALTER TABLE students ADD COLUMN batch TEXT"
            )

        if "semester" not in columns:
            db.execute(
                "ALTER TABLE students ADD COLUMN semester INTEGER"
            )

# ---------- MODULE-WISE ATTENDANCE ----------

def create_module_attendance_table():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS module_attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                module_id INTEGER NOT NULL,
                attendance_date TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK(status IN ('Present', 'Absent')),
                FOREIGN KEY (student_id)
                    REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (module_id)
                    REFERENCES modules(id),
                UNIQUE(student_id, module_id, attendance_date)
            )
        """)

STYLE = """
<style>
* {box-sizing:border-box}
body{margin:0;background:#f1f5f9;font-family:Arial,sans-serif;color:#1e293b}
header{background:#1e3a8a;color:white;padding:22px 6%}
header h1{margin:0;font-size:25px}
header p{margin:8px 0 0;color:#bfdbfe}
main{max-width:1150px;margin:30px auto;padding:0 16px}
.card{background:white;padding:25px;border-radius:12px;
      margin-bottom:22px;box-shadow:0 3px 12px #0001}
h2{margin-top:0;color:#1e40af}
.form-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}
label{display:block;margin-bottom:6px;font-weight:bold;font-size:14px}
input,select{padding:11px;width:100%;border:1px solid #cbd5e1;
             border-radius:7px;font-size:14px}
button,.btn{display:inline-block;background:#2563eb;color:white;
    border:none;border-radius:7px;padding:11px 17px;
    cursor:pointer;text-decoration:none;font-size:14px}
button:hover,.btn:hover{opacity:.88}
.danger{background:#dc2626}
.green{background:#059669}
.gray{background:#64748b}
.actions{display:flex;gap:7px;align-items:center}
.actions form{margin:0}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:13px;border-bottom:1px solid #e2e8f0}
th{background:#eff6ff;color:#1e40af}
.table-wrap{overflow-x:auto}
.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:15px}
.toolbar input{flex:2;min-width:180px}
.toolbar select{flex:1;min-width:140px}
.empty{text-align:center;color:#64748b;padding:24px}
.error{background:#fee2e2;color:#991b1b;padding:12px;
       border-radius:7px;margin-bottom:16px}
@media(max-width:650px){
    .form-grid{grid-template-columns:1fr}
    header h1{font-size:20px}
    .card{padding:16px}
}
</style>
"""

PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Student Management</title>
""" + STYLE + """
</head>
<body>
<header>
<h1>Student Attendance & Leave Management System</h1>
<p>Student Management Dashboard</p>
</header>

<main>
    <a href="/dashboard" style="display:inline-block; background:#0056b3; color:white; padding:10px 15px; border-radius:5px; text-decoration:none; margin-bottom:15px;">Back to Dashboard</a>

    <section class="card">
<h2>{{ "Edit Student" if editing else "Add New Student" }}</h2>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}

<form method="POST"
 action="{{ url_for('edit_student', id=editing['id']) if editing else url_for('add_student') }}">
<div class="form-grid">
<div>
<label>Student ID</label>
<input name="student_id" maxlength="30" required
 value="{{ editing['student_id'] if editing else '' }}"
 placeholder="EG/20../....">
</div>
<div>
<label>Full Name</label>
<input name="name" maxlength="100" required
 value="{{ editing['name'] if editing else '' }}"
 placeholder="Enter full name">
</div>
<div>
<label>Email</label>
<input type="email" name="email" maxlength="150"
 value="{{ (editing['email'] or '') if editing else '' }}"
 placeholder="student@example.com">
</div>

<div>
<label>Semester</label>
<select name="semester" id="semester" required
        onchange="updateBatches()">
    <option value="">Select Semester</option>
    {% for sem in [3, 4, 5, 6, 7, 8] %}
    <option value="{{ sem }}"
      {% if editing and editing['semester'] == sem %}
      selected
      {% endif %}>
        Semester {{ sem }}
    </option>
    {% endfor %}
</select>
</div>

<div>
<label>Batch</label>
<select name="batch" id="batch" required
        data-selected="{{ editing['batch'] or '' if editing else '' }}">
    <option value="">Select Batch</option>
</select>
</div>
<div id="electives-section" style="grid-column:1/-1;">
    <label>Technical Elective Modules (Optional)</label>
    <p style="font-size:13px;color:#64748b;">
        Select only the elective modules taken by this student.
        Compulsory modules are included automatically.
    </p>

    {% for module in elective_modules %}
    <div class="elective-option"
         data-semester="{{ module['semester'] }}"
         style="display:none;margin:8px 0;">
        <label style="font-weight:normal;">
            <input type="checkbox"
                   name="electives"
                   value="{{ module['id'] }}"
                   style="width:auto;"
                   {% if module['id'] in selected_electives %}
                   checked
                   {% endif %}>
            {{ module['code'] }} - {{ module['name'] }}
        </label>
    </div>
    {% endfor %}
</div>
<br>
<button type="submit">
{{ "Save Changes" if editing else "Add Student" }}
</button>
{% if editing %}
<a class="btn gray" href="{{ url_for('students_page') }}">Cancel</a>
{% endif %}
</form>
</section>

<section class="card">
<h2>Student Records ({{ students|length }})</h2>

<form method="GET" action="{{ url_for('students_page') }}" class="toolbar">
<input name="search" placeholder="Search student ID or name"
 value="{{ search }}">

<select name="sort">
<option value="newest" {% if sort == 'newest' %}selected{% endif %}>Newest First</option>
<option value="name" {% if sort == 'name' %}selected{% endif %}>Name A-Z</option>
<option value="student_id" {% if sort == 'student_id' %}selected{% endif %}>Student ID</option>
</select>
<button type="submit">Search / Filter</button>
<a class="btn gray" href="{{ url_for('students_page') }}">Reset</a>
</form>

<div class="table-wrap">
<table>
<thead>
<tr>
<th>Student ID</th>
<th>Name</th>
<th>Email</th>
<th>Batch</th>
<th>Semester</th>
<th>Actions</th>
</tr>
</thead>
<tbody>
{% for student in students %}
<tr>
<td>{{ student['student_id'] }}</td>
<td>{{ student['name'] }}</td>
<td>{{ student['email'] or '-' }}</td>
<td>{{ student['batch'] or '-' }}</td>
<td>
    {% if student['semester'] %}
        Semester {{ student['semester'] }}
    {% else %}
        -
    {% endif %}
</td>
<td>
<div class="actions">
<a class="btn green"
 href="{{ url_for('edit_student', id=student['id']) }}">Edit</a>
<form method="POST"
 action="{{ url_for('delete_student', id=student['id']) }}"
 onsubmit="return confirm('Delete this student permanently?')">
<button class="danger" type="submit">Delete</button>
</form>
</div>
</td>
</tr>
{% else %}
<tr><td colspan="6" class="empty">No students found.</td></tr>
{% endfor %}
</tbody>
</table>
</div>
</section>
</main>
<script>
const semesterBatches = {
    "3": ["26", "25", "24"],
    "4": ["25", "24"],
    "5": ["25", "24"],
    "6": ["24", "23"],
    "7": ["24", "23"],
    "8": ["23", "22"]
};

function updateBatches() {
    const semester = document.getElementById("semester").value;
    const batchSelect = document.getElementById("batch");
    const selectedBatch = batchSelect.dataset.selected;

    batchSelect.innerHTML =
        '<option value="">Select Batch</option>';

    (semesterBatches[semester] || []).forEach(batch => {
        const option = document.createElement("option");
        option.value = batch;
        option.textContent = "Batch " + batch;

        if (batch === selectedBatch) {
            option.selected = true;
        }

        batchSelect.appendChild(option);
    });

    batchSelect.dataset.selected = "";
}
function updateElectives() {
    const semester = document.getElementById("semester").value;

    document.querySelectorAll(".elective-option").forEach(option => {
        const matches = option.dataset.semester === semester;
        option.style.display = matches ? "block" : "none";

        if (!matches) {
            option.querySelector("input").checked = false;
        }
    });
}
document.addEventListener("DOMContentLoaded", function () {
    updateBatches();
    updateElectives();
});

document.getElementById("semester")
    .addEventListener("change", updateElectives);
</script>
</body>
</html>
"""


def show_page(editing=None, error=None):
    with get_db() as db:
        elective_modules = db.execute("""
            SELECT id, code, name, semester
            FROM modules
            WHERE module_type = 'Elective'
            ORDER BY semester, code, name
        """).fetchall()

        selected_electives = []
        if editing is not None:
            selected_electives = [
                row["module_id"]
                for row in db.execute("""
                    SELECT sm.module_id
                    FROM student_modules sm
                    JOIN modules m ON m.id = sm.module_id
                    WHERE sm.student_id = ?
                      AND m.module_type = 'Elective'
                """, (editing["id"],)).fetchall()
            ]
    search = request.args.get("search", "").strip()
    department = request.args.get("department", "").strip()
    sort = request.args.get("sort", "newest")

    order_options = {
        "newest": "id DESC",
        "name": "name COLLATE NOCASE ASC",
        "student_id": "student_id COLLATE NOCASE ASC"
    }
    order = order_options.get(sort, "id DESC")

    sql = "SELECT * FROM students WHERE 1=1"
    params = []

    if search:
        sql += " AND (student_id LIKE ? OR name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    if department:
        sql += " AND department = ?"
        params.append(department)

    sql += f" ORDER BY {order}"

    with get_db() as db:
        students = db.execute(sql, params).fetchall()
        departments = db.execute(
            "SELECT DISTINCT department FROM students ORDER BY department"
        ).fetchall()

    return render_template_string(
        PAGE,
        elective_modules=elective_modules,
        selected_electives=selected_electives,
        students=students,
        departments=[d["department"] for d in departments],
        search=search,
        department=department,
        sort=sort,
        editing=editing,
        error=error
    )


@app.route("/")
def home():
    return redirect(url_for("dashboard"))

@app.route("/students")
def students_page():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "Admin":
        return "Access Denied: Admin only.", 403

    return show_page()


def student_data():
    return (
        request.form.get("student_id", "").strip(),
        request.form.get("name", "").strip(),
        request.form.get("email", "").strip(),
        "EIE",
        request.form.get("batch", "").strip(),
        request.form.get("semester", "").strip()
    )


def validate_student(data):
    student_id, name, email, department, batch, semester = data

    if not student_id or not name:
        return "Student ID and Name are required."

    if len(student_id) > 30 or len(name) > 100:
        return "Student ID or Name is too long."

    if len(email) > 150:
        return "Email is too long."

    if email and ("@" not in email or "." not in email.split("@")[-1]):
        return "Please enter a valid email address."

    if department != "EIE":
        return "Only EIE students are allowed."

    semester_batches = {
        "3": ["26", "25", "24"],
        "4": ["25", "24"],
        "5": ["25", "24"],
        "6": ["24", "23"],
        "7": ["24", "23"],
        "8": ["23", "22"]
    }

    if semester not in semester_batches:
        return "Please select a valid semester."

    if batch not in semester_batches[semester]:
        return "Invalid batch for the selected semester."

    return None
def save_student_electives(db, student_id, semester):
    selected_ids = request.form.getlist("electives")

    valid_rows = db.execute("""
        SELECT id FROM modules
        WHERE module_type = 'Elective'
          AND semester = ?
    """, (int(semester),)).fetchall()

    valid_ids = {str(row["id"]) for row in valid_rows}

    if any(mid not in valid_ids for mid in selected_ids):
        raise ValueError("Invalid elective module selection.")

    db.execute("""
        DELETE FROM student_modules
        WHERE student_id = ?
          AND module_id IN (
              SELECT id FROM modules
              WHERE module_type = 'Elective'
          )
    """, (student_id,))

    for module_id in set(selected_ids):
        db.execute("""
            INSERT INTO student_modules
            (student_id, module_id)
            VALUES (?, ?)
        """, (student_id, int(module_id)))

@app.route("/add", methods=["POST"])
def add_student():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "Admin":
        return "Access Denied: Admin only.", 403
    data = student_data()
    error = validate_student(data)

    if error:
        return error, 400

    try:
        with get_db() as db:
            cursor = db.execute("""
                INSERT INTO students
                (student_id, name, email, department, batch, semester)
                VALUES (?, ?, ?, ?, ?, ?)
            """, data)

            save_student_electives(db, cursor.lastrowid, data[5])
    except ValueError as error:
        return str(error), 400
    except sqlite3.IntegrityError:
        return "This Student ID already exists.", 400

    return redirect(url_for("students_page"))


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_student(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "Admin":
        return "Access Denied: Admin only.", 403

    with get_db() as db:
        student = db.execute(
            "SELECT * FROM students WHERE id = ?", (id,)
        ).fetchone()

    if student is None:
        return "Student not found.", 404

    if request.method == "POST":
        data = student_data()
        error = validate_student(data)

        if error:
            return error, 400

        try:
            with get_db() as db:
                db.execute("""
                    UPDATE students
                    SET student_id = ?,
                        name = ?,
                        email = ?,
                        department = ?,
                        batch = ?,
                        semester = ?
                    WHERE id = ?
                """, (*data, id))
                save_student_electives(db, id, data[5])
        except sqlite3.IntegrityError:
            return "This Student ID already exists.", 400

        return redirect(url_for("students_page"))

    return show_page(editing=student)


@app.route("/delete/<int:id>", methods=["POST"])
def delete_student(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "Admin":
        return "Access Denied: Admin only.", 403

    with get_db() as db:
        db.execute("DELETE FROM students WHERE id=?", (id,))
    return redirect(url_for("home"))


@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST" and session.get("role") != "Admin":
        return "Access Denied: Admin only.", 403
    role = session.get("role")
    student_id = session.get("student_id")

    if role not in ("Admin", "Student"):
        return "Access Denied.", 403

    if role == "Student" and student_id is None:
        return "Access Denied: Student account not linked.", 403
    error = None
    success = None

    selected_student = request.values.get(
        "student_id", type=int
    )

    if request.method == "POST":
        module_id = request.form.get("module_id", type=int)
        attendance_date = request.form.get("date", "")
        status = request.form.get("status", "")

        try:
            selected_date = date.fromisoformat(attendance_date)

            if selected_date > date.today():
                error = "Future dates are not allowed."
            elif status not in ("Present", "Absent"):
                error = "Please select Present or Absent."
            elif selected_student is None or module_id is None:
                error = "Please select a student and module."
            else:
                with get_db() as db:
                    valid = db.execute("""
                        SELECT s.id
                        FROM students s
                        JOIN modules m
                            ON m.semester = s.semester
                        WHERE s.id = ?
                          AND m.id = ?
                          AND (
                              m.module_type = 'Compulsory'
                              OR EXISTS (
                                  SELECT 1
                                  FROM student_modules sm
                                  WHERE sm.student_id = s.id
                                    AND sm.module_id = m.id
                              )
                          )
                    """, (
                        selected_student,
                        module_id
                    )).fetchone()

                    if valid is None:
                        error = "Module is not valid for this student's semester."
                    else:
                        db.execute("""
                            INSERT INTO module_attendance
                            (student_id, module_id, attendance_date, status)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(student_id, module_id, attendance_date)
                            DO UPDATE SET status = excluded.status
                        """, (
                            selected_student,
                            module_id,
                            attendance_date,
                            status
                        ))
                        success = "Attendance saved successfully."

        except ValueError:
            error = "Please enter a valid date."

    with get_db() as db:
        students = db.execute("""
            SELECT * FROM students
            WHERE semester BETWEEN 3 AND 8
            ORDER BY name
        """).fetchall()

        student = None
        modules = []

        if selected_student:
            student = db.execute(
                "SELECT * FROM students WHERE id = ?",
                (selected_student,)
            ).fetchone()

            if student:
                modules = get_student_modules(selected_student)

        if role == "Admin":
            records = db.execute("""
                SELECT a.id, a.attendance_date,
                       s.student_id,
                       s.name AS student_name,
                       m.code,
                       m.name AS module_name,
                       a.status
                FROM module_attendance a
                JOIN students s ON a.student_id = s.id
                JOIN modules m ON a.module_id = m.id
                ORDER BY a.attendance_date DESC, a.id DESC
            """).fetchall()

        else:
            records = db.execute("""
                SELECT a.id, a.attendance_date,
                       s.student_id,
                       s.name AS student_name,
                       m.code,
                       m.name AS module_name,
                       a.status
                FROM module_attendance a
                JOIN students s ON a.student_id = s.id
                JOIN modules m ON a.module_id = m.id
                WHERE a.student_id = ?
                ORDER BY a.attendance_date DESC, a.id DESC
            """, (student_id,)).fetchall()

        summary = db.execute("""
            SELECT s.student_id,
                   s.name AS student_name,
                   m.code,
                   m.name AS module_name,
                   SUM(CASE WHEN a.status = 'Present'
                       THEN 1 ELSE 0 END) AS present_count,
                   COUNT(*) AS total_count,
                   ROUND(100.0 *
                       SUM(CASE WHEN a.status = 'Present'
                           THEN 1 ELSE 0 END) / COUNT(*), 2
                   ) AS percentage
            FROM module_attendance a
            JOIN students s ON a.student_id = s.id
            JOIN modules m ON a.module_id = m.id
            WHERE (? = 'Admin' OR a.student_id = ?)
            GROUP BY a.student_id, a.module_id
            ORDER BY s.student_id, m.code, m.name
            """, (role, student_id)).fetchall()

    return render_template(
        "attendance.html",
        students=students,
        student=student,
        modules=modules,
        records=records,
        summary=summary,
        today=date.today().isoformat(),
        error=error,
        success=success
    )

    # ---------- EDIT MODULE ATTENDANCE ----------

@app.route("/attendance/edit/<int:record_id>")
def edit_module_attendance(record_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "Admin":
        return "Access Denied: Admin only.", 403

    with get_db() as db:
        record = db.execute("""
            SELECT id, student_id, module_id,
                   attendance_date, status
            FROM module_attendance
            WHERE id = ?
        """, (record_id,)).fetchone()

    if record is None:
        return "Attendance record not found.", 404

    return render_template(
        "edit_attendance.html",
        record=record
    )

# ---------- DELETE MODULE ATTENDANCE ----------

@app.route("/attendance/delete/<int:record_id>", methods=["POST"])
def delete_module_attendance(record_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "Admin":
        return "Access Denied: Admin only.", 403

    with get_db() as db:
        db.execute(
            "DELETE FROM module_attendance WHERE id = ?",
            (record_id,)
        )

    return redirect(url_for("attendance"))


# ---------- UPDATE MODULE ATTENDANCE ----------

@app.route("/attendance/update/<int:record_id>", methods=["POST"])
def update_module_attendance(record_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "Admin":
        return "Access Denied: Admin only.", 403

    attendance_date = request.form.get("date", "")
    status = request.form.get("status", "")

    try:
        selected_date = date.fromisoformat(attendance_date)
    except ValueError:
        return "Invalid attendance date.", 400

    if selected_date > date.today():
        return "Future dates are not allowed.", 400

    if status not in ("Present", "Absent"):
        return "Invalid attendance status.", 400

    with get_db() as db:

        record = db.execute(
            "SELECT id FROM module_attendance WHERE id = ?",
            (record_id,)
        ).fetchone()

        if record is None:
            return "Attendance record not found.", 404

        try:
            db.execute("""
                UPDATE module_attendance
                SET attendance_date = ?, status = ?
                WHERE id = ?
            """, (attendance_date, status, record_id))

        except sqlite3.IntegrityError:
            return "Attendance already exists for this module and date.", 400

    return redirect(url_for("attendance"))
# ---------- MODULE MANAGEMENT ----------

def create_module_tables():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL ,
                name TEXT NOT NULL,
                semester INTEGER NOT NULL
                    CHECK(semester BETWEEN 3 AND 8),
                module_type TEXT NOT NULL
                    CHECK(module_type IN ('Compulsory', 'Elective'))
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS student_modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                module_id INTEGER NOT NULL,
                FOREIGN KEY (student_id)
                    REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (module_id)
                    REFERENCES modules(id) ON DELETE CASCADE,
                UNIQUE(student_id, module_id)
            )
        """)
# Get the modules applicable to a student.
# Compulsory modules are included automatically.
# Electives must be selected for that student.

def get_student_modules(student_id):
    with get_db() as db:
        return db.execute("""
            SELECT m.*
            FROM modules m
            JOIN students s
                ON s.semester = m.semester
            WHERE s.id = ?
              AND (
                  m.module_type = 'Compulsory'
                  OR EXISTS (
                      SELECT 1
                      FROM student_modules sm
                      WHERE sm.student_id = s.id
                        AND sm.module_id = m.id
                  )
              )
            ORDER BY m.module_type, m.code, m.name
        """, (student_id,)).fetchall()
def insert_modules():
    compulsory_modules = [
        # Semester 3
        ("EE3301", "Analog Electronics", 3),
        ("EE3202", "Data Structures and Algorithms", 3),
        ("EE3203", "Electrical and Electronic Measurements", 3),
        ("EE3204", "Engineering Electromagnetism", 3),
        ("EE3205", "Power and Energy", 3),
        ("EE3306", "Signals and Systems", 3),
        ("IS3301", "Complex Analysis and Mathematical Transforms", 3),
        ("IS3321", "Fundamentals of Management for Engineers", 3),
        ("IS3322", "Society and the Engineer", 3),

        # Semester 4
        ("EE4201", "Analog and Digital Communication", 4),
        ("EE4202", "Computer Architecture and Operating Systems", 4),
        ("EE4203", "Database Systems", 4),
        ("EE4304", "Digital Logic Design", 4),
        ("EE4305", "Electric Machines", 4),
        ("EE4206", "Engineering Design Methodology", 4),
        ("EE4207", "Web Application Development", 4),
        ("IS4301", "Probability and Statistics", 4),
        ("IS4322", "Basic Economics", 4),

        # Semester 5
        ("EE5201", "Communication Systems", 5),
        ("EE5102", "Electronic Circuit Design", 5),
        ("EE5203", "Machine Learning", 5),
        ("EE5304", "Power Electronics", 5),
        ("EE5304", "Power Systems", 5),
        ("EE5205", "Software Project", 5),
        ("IS5311", "Discrete Mathematics", 5),

        # Semester 6
        ("EE6301", "Computer Networks", 6),
        ("EE6302", "Control Systems Design", 6),
        ("EE6203", "Digital Signal Processing", 6),
        ("EE6304", "Embedded Systems Design", 6),
        ("EE6105", "Research Methodologies", 6),
        ("IS6101", "Engineering Ethics", 6),
        ("IS6302", "Numerical Methods", 6),

        # Semester 7
        ("EEE7201", "Design and Management of Networks", 7),
        ("EEE7202", "Electrical Installations", 7),
        ("EEE7803", "Undergraduate Project", 7),

        # Semester 8
        ("EEE8202", "Comprehensive Design Project", 8)

    ]



    with get_db() as db:
        for code, name, semester in compulsory_modules:
            existing = db.execute("""
                SELECT id FROM modules
                WHERE code = ?
                  AND name = ?
                  AND semester = ?
            """, (code, name, semester)).fetchone()

            if existing is None:
                db.execute("""
                    INSERT INTO modules
                    (code, name, semester, module_type)
                    VALUES (?, ?, ?, 'Compulsory')
                """, (code, name, semester))

# Technical elective modules
    elective_modules = [
        ("EE4211", "Advanced Data Structures and Algorithms", 4),
        ("EE5211", "Advanced Digital Communications", 5),
        ("EE5212", "DevOps Engineering", 5),
        ("EE5213", "Energy Economics", 5),
        ("EE5214", "Hardware Description Language", 5),
        ("EE5215", "Object Oriented Design Patterns and Principles", 5),
        ("EE5216", "Power System Analysis", 5),

        ("EE6211", "Artificial Intelligence", 6),
        ("EE6212", "Introduction to Biomedical Engineering", 6),
        ("EE6213", "Operating System and Network Programming", 6),
        ("EE6214", "Renewable Energy Systems", 6),
        ("EE6215", "Special Purpose Electric Machines", 6),
        ("EE6216", "Software Architecture", 6),
        ("EE6217", "Wireless and Mobile Communications", 6),

        ("EEE7211", "Advanced Data Communications", 7),
        ("EEE7212", "Computer Vision and Image Processing", 7),
        ("EEE7213", "Electric Motor Drives", 7),
        ("EEE7214", "Information Security", 7),
        ("EEE7215", "Introduction to Robotics and Automation", 7),
        ("EEE7216", "Optical Fibre Communication", 7),
        ("EEE7217", "Optimization Techniques for Engineers", 7),
        ("EEE7218", "Power Electronic Applications", 7),
        ("EEE7219", "Telecommunication Networks", 7),

        ("EEE8211", "Blockchain and Cyber Security", 8),
        ("EEE8212", "Digital Control", 8),
        ("EEE8213", "High Voltage Engineering", 8),
        ("EEE8214", "IC Design", 8),
        ("EEE8215", "Microwave Communications", 8),
        ("EEE8216", "Power System Protection", 8),
        ("EEE8217", "Smart Grid", 8)
    ]

    with get_db() as db:
        for code, name, semester in elective_modules:
            db.execute("""
                INSERT INTO modules
                (code, name, semester, module_type)
                SELECT ?, ?, ?, 'Elective'
                WHERE NOT EXISTS (
                    SELECT 1 FROM modules
                    WHERE code = ?
                      AND name = ?
                      AND semester = ?
                )
            """, (
                code, name, semester,
                code, name, semester
            ))

# ---------- LEAVE MANAGEMENT ----------

def create_leave_table():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS leave_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                leave_type TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending'
                    CHECK(status IN ('Pending', 'Approved', 'Rejected')),
                FOREIGN KEY (student_id)
                    REFERENCES students(id) ON DELETE CASCADE
            )
        """)


def leave_page(editing=None, error=None, success=None):
    with get_db() as db:
        role = session.get("role")
        student_id = session.get("student_id")

        if role == "Admin":
            students = db.execute(
                "SELECT * FROM students ORDER BY name"
            ).fetchall()

            leaves = db.execute("""
                SELECT l.*, s.student_id AS student_code, s.name
                FROM leave_requests l
                JOIN students s ON l.student_id = s.id
                ORDER BY l.id DESC
            """).fetchall()

        elif role == "Student" and student_id is not None:
            students = db.execute(
                "SELECT * FROM students WHERE id = ?",
                (student_id,)
            ).fetchall()

            leaves = db.execute("""
                SELECT l.*, s.student_id AS student_code, s.name
                FROM leave_requests l
                JOIN students s ON l.student_id = s.id
                WHERE l.student_id = ?
                ORDER BY l.id DESC
            """, (student_id,)).fetchall()

        else:
            abort(403)

    return render_template(
        "leave.html",
        students=students,
        leaves=leaves,
        editing=editing,
        error=error,
        success=success
    )


def get_leave_data():
    return (
        request.form.get("student_id", "").strip(),
        request.form.get("leave_type", "").strip(),
        request.form.get("start_date", "").strip(),
        request.form.get("end_date", "").strip(),
        request.form.get("reason", "").strip()
    )


def validate_leave(data):
    student_id, leave_type, start, end, reason = data

    if not student_id.isdigit():
        return "Please select a valid student."

    if leave_type not in (
        "Medical", "Personal", "Family Emergency", "Other"
    ):
        return "Invalid leave type."

    try:
        start_day = date.fromisoformat(start)
        end_day = date.fromisoformat(end)
    except ValueError:
        return "Please enter valid dates."

    if end_day < start_day:
        return "End date cannot be before start date."

    if not reason or len(reason) > 500:
        return "Reason is required (maximum 500 characters)."

    with get_db() as db:
        student = db.execute(
            "SELECT id FROM students WHERE id = ?",
            (student_id,)
        ).fetchone()

    if student is None:
        return "Selected student does not exist."

    return None


@app.route("/leave", methods=["GET", "POST"])
def leave_management():

    role = session.get("role")
    student_id = session.get("student_id")

    if role not in ("Admin", "Student"):
        abort(403)

    if request.method == "POST":

        data = get_leave_data()

        if role == "Student":
            if student_id is None:
                abort(403)

            data = (
                str(student_id),
                data[1],
                data[2],
                data[3],
                data[4]
            )

        error = validate_leave(data)

        if error:
            return leave_page(error=error), 400

        with get_db() as db:
            db.execute("""
                INSERT INTO leave_requests
                (student_id, leave_type, start_date, end_date, reason)
                VALUES (?, ?, ?, ?, ?)
            """, data)

        return redirect(url_for("leave_management"))

    return leave_page()


@app.route("/leave/edit/<int:leave_id>", methods=["GET", "POST"])
def edit_leave(leave_id):

    role = session.get("role")
    student_id = session.get("student_id")

    if role not in ("Admin", "Student"):
        abort(403)

    if role == "Student" and student_id is None:
        abort(403)

    with get_db() as db:
        leave = db.execute(
            "SELECT * FROM leave_requests WHERE id = ?",
            (leave_id,)
        ).fetchone()

    if leave is None:
        abort(404)

    # Students can edit only their own leave requests
    if role == "Student":
        if int(leave["student_id"]) != int(student_id):
            abort(403)

    # Only pending requests can be edited
    if leave["status"] != "Pending":
        abort(403)

    if request.method == "POST":

        data = get_leave_data()

        # Students must use their own ID
        if role == "Student":
            data = (
                str(student_id),
                data[1],
                data[2],
                data[3],
                data[4]
            )

        error = validate_leave(data)

        if error:
            return leave_page(editing=leave, error=error), 400

        with get_db() as db:

            if role == "Admin":
                db.execute("""
                    UPDATE leave_requests
                    SET student_id = ?,
                        leave_type = ?,
                        start_date = ?,
                        end_date = ?,
                        reason = ?
                    WHERE id = ?
                      AND status = 'Pending'
                """, (
                    data[0],
                    data[1],
                    data[2],
                    data[3],
                    data[4],
                    leave_id
                ))

            else:
                db.execute("""
                    UPDATE leave_requests
                    SET leave_type = ?,
                        start_date = ?,
                        end_date = ?,
                        reason = ?
                    WHERE id = ?
                      AND student_id = ?
                      AND status = 'Pending'
                """, (
                    data[1],
                    data[2],
                    data[3],
                    data[4],
                    leave_id,
                    student_id
                ))

        return redirect(url_for("leave_management"))

    return leave_page(editing=leave)

@app.route("/leave/status/<int:leave_id>/<status>", methods=["POST"])
def change_leave_status(leave_id, status):

    if session.get("role") != "Admin":
        abort(403)

    if status not in ("Approved", "Rejected"):
        return "Invalid leave status.", 400

    with get_db() as db:
        db.execute("""
            UPDATE leave_requests SET status=?
            WHERE id=? AND status='Pending'
        """, (status, leave_id))

    return redirect(url_for("leave_management"))


@app.route("/leave/delete/<int:leave_id>", methods=["POST"])
def delete_leave(leave_id):

    role = session.get("role")
    student_id = session.get("student_id")

    if role not in ("Admin", "Student"):
        abort(403)

    with get_db() as db:

        leave = db.execute(
            "SELECT * FROM leave_requests WHERE id = ?",
            (leave_id,)
        ).fetchone()

        if leave is None:
            abort(404)

        if role == "Student":

            if student_id is None:
                abort(403)

            if int(leave["student_id"]) != int(student_id):
                abort(403)

            if leave["status"] != "Pending":
                abort(403)

        if role == "Admin":
            db.execute(
                "DELETE FROM leave_requests WHERE id = ?",
                (leave_id,)
            )
        else:
            db.execute("""
                DELETE FROM leave_requests
                WHERE id = ?
                  AND student_id = ?
                  AND status = 'Pending'
            """, (leave_id, student_id))

    return redirect(url_for("leave_management"))


@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "Admin":
        return "Access Denied: Admin only.", 403

    today = date.today().isoformat()

    with get_db() as db:
        total_students = db.execute(
            "SELECT COUNT(*) FROM students"
        ).fetchone()[0]

        attendance = db.execute("""
            SELECT status, COUNT(*) AS total
            FROM module_attendance
            WHERE attendance_date = ?
            GROUP BY status
        """, (today,)).fetchall()

        leave_counts = db.execute("""
            SELECT status, COUNT(*) AS total
            FROM leave_requests
            GROUP BY status
        """).fetchall()

    attendance_stats = {
        row["status"]: row["total"] for row in attendance
    }

    leave_stats = {
        row["status"]: row["total"] for row in leave_counts
    }

    stats = {
        "students": total_students,
        "present": attendance_stats.get("Present", 0),
        "absent": attendance_stats.get("Absent", 0),
        "pending": leave_stats.get("Pending", 0),
        "approved": leave_stats.get("Approved", 0)
    }

    return render_template(
        "dashboard.html",
        stats=stats
    )

# ---------- MODULE ATTENDANCE OVERVIEW ----------

@app.route("/module-overview")
def module_overview():
    if "user_id" not in session:
        return redirect(url_for("login"))

    role = session.get("role")
    student_id = session.get("student_id")

    if role not in ("Admin", "Student"):
        return "Access Denied.", 403

    if role == "Student" and student_id is None:
        return "Access Denied: Student account not linked.", 403
    semester = request.args.get("semester", type=int)
    selected_batch = request.args.get("batch", "").strip()
    allowed_batches = {
        3: ["26", "25", "24"],
        4: ["25", "24"],
        5: ["25", "24"],
        6: ["24", "23"],
        7: ["24", "23"],
        8: ["23", "22"]
    }
    batches = allowed_batches.get(semester, [])

    if selected_batch not in batches:
        selected_batch = ""

    selected_module = request.args.get("module_id", type=int)
    selected_date = request.args.get(
        "date", date.today().isoformat()
    )

    if semester not in range(3, 9):
        semester = None
        selected_module = None

    try:
        chosen_date = date.fromisoformat(selected_date)
        if chosen_date > date.today():
            selected_date = date.today().isoformat()
    except (ValueError, TypeError):
        selected_date = date.today().isoformat()

    with get_db() as db:
        modules = []
        module = None
        summary = []
        daily = {
            "present": 0,
            "absent": 0,
            "total": 0,
            "not_marked": 0
        }

        if semester is not None:
            modules = db.execute("""
                SELECT * FROM modules
                WHERE semester = ?
                ORDER BY module_type, code, name
            """, (semester,)).fetchall()

        if selected_module is not None and semester is not None:
            module = db.execute("""
                SELECT * FROM modules
                WHERE id = ? AND semester = ?
            """, (selected_module, semester)).fetchone()

        if module is not None:
            counts = db.execute("""
                SELECT a.status, COUNT(*) AS total
                FROM module_attendance a
                JOIN students s
                    ON a.student_id = s.id
                WHERE a.module_id = ?
                  AND a.attendance_date = ?
                  AND s.semester = ?
                  AND (? = '' OR s.batch = ?)
                  AND (? = 'Admin' OR a.student_id = ?)
                  GROUP BY a.status
            """, (
                selected_module,
                selected_date,
                semester,
                selected_batch,
                selected_batch,
                role,
                student_id
            )).fetchall()

            for row in counts:
                if row["status"] == "Present":
                    daily["present"] = row["total"]
                elif row["status"] == "Absent":
                    daily["absent"] = row["total"]

            daily["total"] = daily["present"] + daily["absent"]
            student_count = db.execute("""
                SELECT COUNT(*)
                FROM students s
                JOIN modules m ON m.id = ?
                WHERE s.semester = ?
                    AND (? = '' OR s.batch = ?)
                    AND (? = 'Admin' OR s.id = ?)
                    AND (
                      m.module_type = 'Compulsory'
                      OR EXISTS (
                          SELECT 1
                          FROM student_modules sm
                          WHERE sm.student_id = s.id
                            AND sm.module_id = m.id
                      )
                  )
            """, (
                selected_module,
                semester,
                selected_batch,
                selected_batch,
                role,
                student_id
            )).fetchone()[0]

            daily["not_marked"] = max(
                0, student_count - daily["total"]
            )

        if role == "Admin":
            if module is not None:
                summary = db.execute("""
                    SELECT s.student_id,
                           s.name AS student_name,
                           m.code,
                           m.name AS module_name,
                           SUM(CASE WHEN a.status = 'Present'
                               THEN 1 ELSE 0 END) AS present_count,
                           COUNT(*) AS total_count,
                           ROUND(100.0 *
                               SUM(CASE WHEN a.status = 'Present'
                                   THEN 1 ELSE 0 END) / COUNT(*), 2
                           ) AS percentage
                    FROM module_attendance a
                    JOIN students s ON a.student_id = s.id
                    JOIN modules m ON a.module_id = m.id
                    WHERE a.module_id = ?
                      AND s.semester = ?
                      AND (? = '' OR s.batch = ?)
                    GROUP BY a.student_id, a.module_id
                    ORDER BY s.student_id, m.code, m.name
                """, (
                    selected_module,
                    semester,
                    selected_batch,
                    selected_batch
                )).fetchall()

        else:
            if module is not None:
                summary = db.execute("""
                    SELECT s.student_id,
                           s.name AS student_name,
                           m.code,
                           m.name AS module_name,
                           SUM(CASE WHEN a.status = 'Present'
                               THEN 1 ELSE 0 END) AS present_count,
                           COUNT(*) AS total_count,
                           ROUND(100.0 *
                               SUM(CASE WHEN a.status = 'Present'
                                   THEN 1 ELSE 0 END) / COUNT(*), 2
                           ) AS percentage
                    FROM module_attendance a
                    JOIN students s ON a.student_id = s.id
                    JOIN modules m ON a.module_id = m.id
                    WHERE a.student_id = ?
                      AND a.module_id = ?
                      AND s.semester = ?
                      AND (? = '' OR s.batch = ?)
                    GROUP BY a.student_id, a.module_id
                    ORDER BY s.student_id, m.code, m.name
                """, (
                    student_id,
                    selected_module,
                    semester,
                    selected_batch,
                    selected_batch
                )).fetchall()
    return render_template(
        "module_overview.html",
        batches=batches,
        selected_batch=selected_batch,
        semester=semester,
        modules=modules,
        selected_module=selected_module,
        module=module,
        selected_date=selected_date,
        today=date.today().isoformat(),
        daily=daily,
        summary=summary
    )

if __name__ == "__main__":
    create_database()
    create_leave_table()
    create_module_tables()
    insert_modules()
    create_module_attendance_table()
    create_users_table()
    create_sample_accounts()
    link_sample_student_account()
    app.run(debug=False)