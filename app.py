from datetime import date, datetime
from functools import wraps

import requests
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from db import get_db


app = Flask(__name__)
app.config.from_object(Config)


# -----------------------
# Helpers
# -----------------------


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapper


def compute_attendance_metrics(attended, total):
    if total <= 0:
        return {
            "attendance_pct": None,
            "safe_to_miss": 0,
            "need_to_recover": 0,
        }

    pct = round((attended / total) * 100, 1)

    # safe_to_miss: maximum k such that (attended / (total + k)) >= 0.75
    # Derived: k = floor(max(0, A/0.75 - T))
    safe_to_miss = int(max(0, (attended / 0.75) - total))
    safe_to_miss = int(safe_to_miss)

    # need_to_recover: min n s.t. (A + n) / (T + n) >= 0.75
    # inequality => n >= 3T - 4A
    needed = max(0, (3 * total) - (4 * attended))

    return {
        "attendance_pct": pct,
        "safe_to_miss": safe_to_miss,
        "need_to_recover": needed,
    }

# -----------------------
# Topics API (for forms)
# -----------------------


@app.route("/api/subjects/<int:subject_id>/topics", methods=["GET"])
@login_required
def api_subject_topics(subject_id):
    user_id = session["user_id"]
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)

    cur.execute(
        """
        SELECT t.id, t.name, t.is_completed
        FROM topics t
        JOIN subjects s ON t.subject_id = s.id
        WHERE t.subject_id = %s AND s.user_id = %s
        ORDER BY t.order_index, t.id
        """,
        (subject_id, user_id),
    )
    topics = cur.fetchall()
    cur.close()
    cnx.close()
    return jsonify(topics)

def call_groq_chat(messages, max_tokens=600):
    """Call Groq Cloud via requests."""
    api_key = app.config.get("GROQ_API_KEY")
    model = app.config.get("GROQ_MODEL")

    if not api_key:
        return "AI Study Buddy is not configured yet. Please add your API key."

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "top_p": 1.0,
        "stream": False,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("Groq API error:", e)
        return "Sorry, the AI Study Buddy is currently unavailable. Please try again later."


def build_student_context(user_id):
    """Return a concise text summary of the student's status for the AI."""
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    today = date.today()

    # Subjects + attendance
    cur.execute(
        """
        SELECT id, name, attended_classes, total_classes
        FROM subjects
        WHERE user_id = %s
        ORDER BY name
        """,
        (user_id,),
    )
    subjects = cur.fetchall()

    subject_ids = [s["id"] for s in subjects]
    topics_by_subject = {sid: [] for sid in subject_ids}

    if subject_ids:
        placeholders = ",".join(["%s"] * len(subject_ids))
        cur.execute(
            f"""
            SELECT subject_id, name, is_completed
            FROM topics
            WHERE subject_id IN ({placeholders})
            ORDER BY subject_id, order_index, id
            """,
            subject_ids,
        )
        for row in cur:
            topics_by_subject[row["subject_id"]].append(row)

    # Assignments
    cur.execute(
        """
        SELECT a.title, a.due_date, a.is_completed, s.name AS subject_name
        FROM assignments a
        LEFT JOIN subjects s ON a.subject_id = s.id
        WHERE a.user_id = %s
        ORDER BY a.due_date
        """,
        (user_id,),
    )
    assignments = cur.fetchall()

    # Tests
    cur.execute(
        """
        SELECT t.id, t.title, t.test_date, s.name AS subject_name
        FROM tests t
        JOIN subjects s ON t.subject_id = s.id
        WHERE t.user_id = %s
        ORDER BY t.test_date
        """,
        (user_id,),
    )
    tests = cur.fetchall()

    # Test readiness
    tests_readiness = []
    for t in tests:
        cur2 = cnx.cursor(dictionary=True)
        cur2.execute(
            """
            SELECT COUNT(tt.id) AS total_topics,
                   SUM(CASE WHEN tp.is_completed = 1 THEN 1 ELSE 0 END) AS completed_topics
            FROM test_topics tt
            JOIN topics tp ON tt.topic_id = tp.id
            WHERE tt.test_id = %s
            """,
            (t["id"],),
        )
        row = cur2.fetchone()
        cur2.close()
        total_topics = row["total_topics"] or 0
        completed_topics = row["completed_topics"] or 0
        readiness = (
            round((completed_topics / total_topics) * 100, 1)
            if total_topics > 0
            else None
        )
        days_remaining = (t["test_date"] - today).days
        tests_readiness.append(
            {
                "title": t["title"],
                "subject_name": t["subject_name"],
                "days_remaining": days_remaining,
                "readiness": readiness,
            }
        )

    # Exams
    cur.execute(
        """
        SELECT e.id, e.title, e.exam_date, s.name AS subject_name
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        WHERE e.user_id = %s
        ORDER BY e.exam_date
        """,
        (user_id,),
    )
    exams = cur.fetchall()

    exams_readiness = []
    for e in exams:
        cur2 = cnx.cursor(dictionary=True)
        cur2.execute(
            """
            SELECT COUNT(et.id) AS total_topics,
                   SUM(CASE WHEN tp.is_completed = 1 THEN 1 ELSE 0 END) AS completed_topics
            FROM exam_topics et
            JOIN topics tp ON et.topic_id = tp.id
            WHERE et.exam_id = %s
            """,
            (e["id"],),
        )
        row = cur2.fetchone()
        cur2.close()
        total_topics = row["total_topics"] or 0
        completed_topics = row["completed_topics"] or 0
        readiness = (
            round((completed_topics / total_topics) * 100, 1)
            if total_topics > 0
            else None
        )
        days_remaining = (e["exam_date"] - today).days
        exams_readiness.append(
            {
                "title": e["title"],
                "subject_name": e["subject_name"],
                "days_remaining": days_remaining,
                "readiness": readiness,
            }
        )

    cur.close()
    cnx.close()

    # Build concise text
    lines = [f"Today: {today.isoformat()}"]

    if subjects:
        lines.append("Subjects and progress:")
        for s in subjects:
            metrics = compute_attendance_metrics(
                s["attended_classes"], s["total_classes"]
            )
            pct = metrics["attendance_pct"]
            pct_text = "N/A" if pct is None else f"{pct}%"
            topics = topics_by_subject.get(s["id"], [])
            completed = sum(1 for t in topics if t["is_completed"])
            total = len(topics)
            lines.append(
                f"- {s['name']}: attendance {pct_text}, topics {completed}/{total} completed."
            )
    else:
        lines.append("Student has not added any subjects yet.")

    if assignments:
        lines.append("Assignments:")
        for a in assignments[:6]:
            status = "done" if a["is_completed"] else "pending"
            subj = a["subject_name"] or "General"
            due = a["due_date"].isoformat() if a["due_date"] else "no due date"
            lines.append(f"- {subj} — {a['title']} (due {due}, {status}).")
    else:
        lines.append("No assignments recorded.")

    if tests_readiness:
        lines.append("Upcoming tests:")
        for t in tests_readiness[:6]:
            r = "N/A" if t["readiness"] is None else f"{t['readiness']}%"
            lines.append(
                f"- {t['subject_name']} — {t['title']} in {t['days_remaining']} days, readiness {r}."
            )

    if exams_readiness:
        lines.append("Upcoming exams:")
        for e in exams_readiness[:6]:
            r = "N/A" if e["readiness"] is None else f"{e['readiness']}%"
            lines.append(
                f"- {e['subject_name']} — {e['title']} in {e['days_remaining']} days, readiness {r}."
            )

    return "\n".join(lines)


# -----------------------
# Auth routes
# -----------------------


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not name or not email or not password:
            flash("Please fill in all required fields.", "error")
            return redirect(url_for("register"))
        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        cnx = get_db()
        cur = cnx.cursor(dictionary=True)

        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            flash("Email already registered. Please log in.", "error")
            cur.close()
            cnx.close()
            return redirect(url_for("login"))

        password_hash = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
            (name, email, password_hash),
        )
        user_id = cur.lastrowid
        cur.close()
        cnx.close()

        session["user_id"] = user_id
        session["user_name"] = name
        session.permanent = True

        flash("Account created successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        cnx = get_db()
        cur = cnx.cursor(dictionary=True)
        cur.execute(
            "SELECT id, name, password_hash FROM users WHERE email = %s", (email,)
        )
        user = cur.fetchone()
        cur.close()
        cnx.close()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        session.permanent = True

        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -----------------------
# Dashboard
# -----------------------


@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    today = date.today()

    cnx = get_db()
    cur = cnx.cursor(dictionary=True)

    # Subjects & attendance
    cur.execute(
        """
        SELECT s.*
        FROM subjects s
        WHERE s.user_id = %s
        ORDER BY s.name
        """,
        (user_id,),
    )
    subjects = cur.fetchall()

    for s in subjects:
        metrics = compute_attendance_metrics(
            s["attended_classes"], s["total_classes"]
        )
        s.update(metrics)

    total_subjects = len(subjects)
    attendance_warnings = sum(
        1
        for s in subjects
        if s["attendance_pct"] is not None and s["attendance_pct"] < 75
    )

    # Low attendance section (subjects <90% or top 3 lowest)
    subjects_with_pct = [
        s for s in subjects if s["attendance_pct"] is not None
    ]
    low_attendance = [
        s for s in subjects_with_pct if s["attendance_pct"] < 90
    ]
    low_attendance.sort(key=lambda x: x["attendance_pct"])

    if not low_attendance:
        low_attendance = sorted(
            subjects_with_pct, key=lambda x: x["attendance_pct"]
        )[:3]
    else:
        low_attendance = low_attendance[:3]

    # Assignments
    cur.execute(
        """
        SELECT a.*, s.name AS subject_name
        FROM assignments a
        LEFT JOIN subjects s ON a.subject_id = s.id
        WHERE a.user_id = %s
        ORDER BY a.is_completed, a.due_date
        """,
        (user_id,),
    )
    assignments = cur.fetchall()
    pending_assignments_count = sum(1 for a in assignments if not a["is_completed"])

    # Upcoming tests
    cur.execute(
        """
        SELECT t.*, s.name AS subject_name
        FROM tests t
        JOIN subjects s ON t.subject_id = s.id
        WHERE t.user_id = %s AND t.test_date >= %s
        ORDER BY t.test_date
        """,
        (user_id, today),
    )
    tests = cur.fetchall()
    upcoming_tests_count = len(tests)

    # Upcoming exams
    cur.execute(
        """
        SELECT e.*, s.name AS subject_name
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        WHERE e.user_id = %s AND e.exam_date >= %s
        ORDER BY e.exam_date
        """,
        (user_id, today),
    )
    exams = cur.fetchall()
    upcoming_exams_count = len(exams)

    # Urgent tasks: nearest assignments/tests/exams
    urgent_items = []

    for a in assignments:
        if a["is_completed"]:
            continue
        due = a["due_date"]
        if due:
            days = (due - today).days
        else:
            days = None
        urgent_items.append(
            {
                "type": "Assignment",
                "title": a["title"],
                "subject_name": a["subject_name"] or "General",
                "date": due,
                "days_remaining": days,
            }
        )

    for t in tests:
        days = (t["test_date"] - today).days
        urgent_items.append(
            {
                "type": "Test",
                "title": t["title"],
                "subject_name": t["subject_name"],
                "date": t["test_date"],
                "days_remaining": days,
            }
        )

    for e in exams:
        days = (e["exam_date"] - today).days
        urgent_items.append(
            {
                "type": "Exam",
                "title": e["title"],
                "subject_name": e["subject_name"],
                "date": e["exam_date"],
                "days_remaining": days,
            }
        )

    urgent_items = sorted(
        urgent_items,
        key=lambda x: (x["date"] is None, x["date"] or date.max),
    )[:5]

    cur.close()
    cnx.close()

    return render_template(
        "dashboard.html",
        active_page="dashboard",
        subjects=subjects,
        low_attendance=low_attendance,
        total_subjects=total_subjects,
        attendance_warnings=attendance_warnings,
        pending_assignments_count=pending_assignments_count,
        upcoming_tests_count=upcoming_tests_count,
        upcoming_exams_count=upcoming_exams_count,
        urgent_items=urgent_items,
        today=today,
    )


# -----------------------
# Subjects & Attendance
# -----------------------


@app.route("/subjects", methods=["GET"])
@login_required
def subjects():
    user_id = session["user_id"]
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)

    # Subjects with topic counts
    cur.execute(
        """
        SELECT s.*,
               COUNT(t.id) AS total_topics,
               SUM(CASE WHEN t.is_completed = 1 THEN 1 ELSE 0 END) AS completed_topics
        FROM subjects s
        LEFT JOIN topics t ON t.subject_id = s.id
        WHERE s.user_id = %s
        GROUP BY s.id
        ORDER BY s.name
        """,
        (user_id,),
    )
    subjects = cur.fetchall()
    for s in subjects:
        metrics = compute_attendance_metrics(
            s["attended_classes"], s["total_classes"]
        )
        s.update(metrics)
        s["completed_topics"] = s["completed_topics"] or 0
        s["total_topics"] = s["total_topics"] or 0

    # Load topics per subject
    subject_ids = [s["id"] for s in subjects]
    topics_by_subject = {sid: [] for sid in subject_ids}
    if subject_ids:
        placeholders = ",".join(["%s"] * len(subject_ids))
        cur.execute(
            f"""
            SELECT id, subject_id, name, is_completed
            FROM topics
            WHERE subject_id IN ({placeholders})
            ORDER BY subject_id, order_index, id
            """,
            subject_ids,
        )
        for row in cur:
            topics_by_subject[row["subject_id"]].append(row)

    cur.close()
    cnx.close()

    return render_template(
        "subjects.html",
        active_page="subjects",
        subjects=subjects,
        topics_by_subject=topics_by_subject,
    )


@app.route("/subjects/add", methods=["POST"])
@login_required
def add_subject():
    user_id = session["user_id"]
    name = request.form.get("name", "").strip()
    code = request.form.get("code", "").strip()
    topics_text = request.form.get("topics", "").strip()

    if not name:
        flash("Subject name is required.", "error")
        return redirect(url_for("subjects"))

    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    cur.execute(
        "INSERT INTO subjects (user_id, name, code) VALUES (%s, %s, %s)",
        (user_id, name, code or None),
    )
    subject_id = cur.lastrowid

    # Initial topics, one per line
    if topics_text:
        lines = [l.strip() for l in topics_text.splitlines() if l.strip()]
        for idx, topic_name in enumerate(lines, start=1):
            cur.execute(
                "INSERT INTO topics (subject_id, name, order_index) VALUES (%s, %s, %s)",
                (subject_id, topic_name, idx),
            )

    cur.close()
    cnx.close()

    flash("Subject added.", "success")
    return redirect(url_for("subjects"))


@app.route("/subjects/<int:subject_id>/delete", methods=["POST"])
@login_required
def delete_subject(subject_id):
    user_id = session["user_id"]
    cnx = get_db()
    cur = cnx.cursor()
    cur.execute(
        "DELETE FROM subjects WHERE id = %s AND user_id = %s",
        (subject_id, user_id),
    )
    cur.close()
    cnx.close()
    flash("Subject deleted.", "success")
    return redirect(url_for("subjects"))


@app.route("/subjects/<int:subject_id>/attendance", methods=["POST"])
@login_required
def update_attendance(subject_id):
    user_id = session["user_id"]
    action = request.form.get("action")

    cnx = get_db()
    cur = cnx.cursor()
    if action == "attended":
        cur.execute(
            """
            UPDATE subjects
            SET attended_classes = attended_classes + 1,
                total_classes = total_classes + 1
            WHERE id = %s AND user_id = %s
            """,
            (subject_id, user_id),
        )
    elif action == "missed":
        cur.execute(
            """
            UPDATE subjects
            SET total_classes = total_classes + 1
            WHERE id = %s AND user_id = %s
            """,
            (subject_id, user_id),
        )
    cur.close()
    cnx.close()

    return redirect(url_for("subjects"))


@app.route("/subjects/<int:subject_id>/topics/add", methods=["POST"])
@login_required
def add_topics(subject_id):
    user_id = session["user_id"]
    topics_text = request.form.get("topics", "").strip()
    if not topics_text:
        return redirect(url_for("subjects"))

    cnx = get_db()
    cur = cnx.cursor(dictionary=True)

    # Ensure subject belongs to user
    cur.execute(
        "SELECT id FROM subjects WHERE id = %s AND user_id = %s",
        (subject_id, user_id),
    )
    if not cur.fetchone():
        cur.close()
        cnx.close()
        flash("Subject not found.", "error")
        return redirect(url_for("subjects"))

    # Find current max order
    cur.execute(
        "SELECT COALESCE(MAX(order_index), 0) AS max_idx FROM topics WHERE subject_id = %s",
        (subject_id,),
    )
    max_idx = cur.fetchone()["max_idx"]

    lines = [l.strip() for l in topics_text.splitlines() if l.strip()]
    for offset, topic_name in enumerate(lines, start=1):
        cur.execute(
            "INSERT INTO topics (subject_id, name, order_index) VALUES (%s, %s, %s)",
            (subject_id, topic_name, max_idx + offset),
        )

    cur.close()
    cnx.close()
    flash("Topics added.", "success")
    return redirect(url_for("subjects"))


@app.route("/topics/<int:topic_id>/toggle", methods=["POST"])
@login_required
def toggle_topic(topic_id):
    user_id = session["user_id"]
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    # ensure the topic belongs to this user
    cur.execute(
        """
        SELECT t.id
        FROM topics t
        JOIN subjects s ON t.subject_id = s.id
        WHERE t.id = %s AND s.user_id = %s
        """,
        (topic_id, user_id),
    )
    if not cur.fetchone():
        cur.close()
        cnx.close()
        flash("Topic not found.", "error")
        return redirect(url_for("subjects"))

    cur.execute(
        "UPDATE topics SET is_completed = 1 - is_completed WHERE id = %s",
        (topic_id,),
    )
    cur.close()
    cnx.close()
    return redirect(url_for("subjects"))


# -----------------------
# Assignments
# -----------------------


@app.route("/assignments", methods=["GET"])
@login_required
def assignments():
    user_id = session["user_id"]
    today = date.today()

    cnx = get_db()
    cur = cnx.cursor(dictionary=True)

    # subjects for dropdown
    cur.execute(
        "SELECT id, name FROM subjects WHERE user_id = %s ORDER BY name",
        (user_id,),
    )
    subjects = cur.fetchall()

    cur.execute(
        """
        SELECT a.*, s.name AS subject_name
        FROM assignments a
        LEFT JOIN subjects s ON a.subject_id = s.id
        WHERE a.user_id = %s
        ORDER BY a.is_completed, a.due_date
        """,
        (user_id,),
    )
    assignments = cur.fetchall()

    for a in assignments:
        if a["due_date"]:
            a["days_remaining"] = (a["due_date"] - today).days
        else:
            a["days_remaining"] = None

    cur.close()
    cnx.close()

    return render_template(
        "assignments.html",
        active_page="assignments",
        subjects=subjects,
        assignments=assignments,
        today=today,
    )


@app.route("/assignments/add", methods=["POST"])
@login_required
def add_assignment():
    user_id = session["user_id"]
    title = request.form.get("title", "").strip()
    subject_id = request.form.get("subject_id")
    due_date_str = request.form.get("due_date")
    description = request.form.get("description", "").strip()

    if not title:
        flash("Assignment title is required.", "error")
        return redirect(url_for("assignments"))

    subject_id = int(subject_id) if subject_id else None
    due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else None

    cnx = get_db()
    cur = cnx.cursor()
    cur.execute(
        """
        INSERT INTO assignments (user_id, subject_id, title, description, due_date)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, subject_id, title, description or None, due_date),
    )
    cur.close()
    cnx.close()

    flash("Assignment added.", "success")
    return redirect(url_for("assignments"))


@app.route("/assignments/<int:assignment_id>/toggle", methods=["POST"])
@login_required
def toggle_assignment(assignment_id):
    user_id = session["user_id"]
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)
    cur.execute(
        "SELECT id FROM assignments WHERE id = %s AND user_id = %s",
        (assignment_id, user_id),
    )
    if not cur.fetchone():
        cur.close()
        cnx.close()
        flash("Assignment not found.", "error")
        return redirect(url_for("assignments"))

    cur.execute(
        "UPDATE assignments SET is_completed = 1 - is_completed WHERE id = %s",
        (assignment_id,),
    )
    cur.close()
    cnx.close()
    return redirect(url_for("assignments"))


@app.route("/assignments/<int:assignment_id>/delete", methods=["POST"])
@login_required
def delete_assignment(assignment_id):
    user_id = session["user_id"]
    cnx = get_db()
    cur = cnx.cursor()
    cur.execute(
        "DELETE FROM assignments WHERE id = %s AND user_id = %s",
        (assignment_id, user_id),
    )
    cur.close()
    cnx.close()
    return redirect(url_for("assignments"))


@app.route("/api/assignments/<int:assignment_id>/ai_suggestions", methods=["POST"])
@login_required
def assignment_ai_suggestions(assignment_id):
    user_id = session["user_id"]
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)

    cur.execute(
        """
        SELECT a.*, s.name AS subject_name, s.id AS subject_id
        FROM assignments a
        LEFT JOIN subjects s ON a.subject_id = s.id
        WHERE a.id = %s AND a.user_id = %s
        """,
        (assignment_id, user_id),
    )
    assignment = cur.fetchone()
    if not assignment:
        cur.close()
        cnx.close()
        return jsonify({"error": "Assignment not found"}), 404

    topics = []
    if assignment["subject_id"]:
        cur.execute(
            """
            SELECT name, is_completed
            FROM topics
            WHERE subject_id = %s
            ORDER BY order_index, id
            """,
            (assignment["subject_id"],),
        )
        topics = cur.fetchall()

    cur.close()
    cnx.close()

    topics_text = "\n".join(
        f"- {t['name']} ({'completed' if t['is_completed'] else 'not completed'})"
        for t in topics
    )

    system_msg = {
    "role": "system",
    "content": (
        "You are a concise study assistant. "
        "Given an assignment and a list of course topics with completion status, "
        "identify the most relevant topics and what the student should review first. "
        "Be direct, practical, and avoid any fluff or self-reference. "
        "Format the response as a short numbered list of review steps in markdown. "
        "Each step on its own line with the key topic in **bold** at the start. "
        "Do not write long paragraphs or introductions."
    ),
}

    user_text = f"""
Assignment:
Title: {assignment['title']}
Subject: {assignment['subject_name'] or 'General'}
Description: {assignment['description'] or 'N/A'}
Due date: {assignment['due_date']}

Course topics and completion:
{topics_text or 'No topics available.'}

Based on this, list the 3-7 most relevant topics for this assignment and what the student should review in order of priority.
"""
    user_msg = {"role": "user", "content": user_text}

    reply = call_groq_chat([system_msg, user_msg], max_tokens=400)

    return jsonify({"suggestions": reply})


# -----------------------
# Tests
# -----------------------


@app.route("/tests", methods=["GET"])
@login_required
def tests():
    user_id = session["user_id"]
    today = date.today()
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)

    # subjects for dropdown
    cur.execute(
        "SELECT id, name FROM subjects WHERE user_id = %s ORDER BY name",
        (user_id,),
    )
    subjects = cur.fetchall()

    # tests with readiness
    cur.execute(
        """
        SELECT t.*, s.name AS subject_name
        FROM tests t
        JOIN subjects s ON t.subject_id = s.id
        WHERE t.user_id = %s
        ORDER BY t.test_date
        """,
        (user_id,),
    )
    tests = cur.fetchall()

    test_ids = [t["id"] for t in tests]
    topics_by_test = {tid: [] for tid in test_ids}

    if test_ids:
        placeholders = ",".join(["%s"] * len(test_ids))
        cur.execute(
            f"""
            SELECT tt.test_id, tp.name, tp.is_completed
            FROM test_topics tt
            JOIN topics tp ON tt.topic_id = tp.id
            WHERE tt.test_id IN ({placeholders})
            ORDER BY tt.test_id, tp.order_index, tp.id
            """,
            test_ids,
        )
        for row in cur:
            topics_by_test[row["test_id"]].append(row)

    for t in tests:
        topics = topics_by_test.get(t["id"], [])
        total = len(topics)
        completed = sum(1 for x in topics if x["is_completed"])
        t["total_topics"] = total
        t["completed_topics"] = completed
        t["readiness"] = (
            round((completed / total) * 100, 1) if total > 0 else None
        )
        t["days_remaining"] = (t["test_date"] - today).days
        t["topics"] = topics

    cur.close()
    cnx.close()

    return render_template(
        "tests.html",
        active_page="tests",
        subjects=subjects,
        tests=tests,
        today=today,
    )


@app.route("/tests/add", methods=["POST"])
@login_required
def add_test():
    user_id = session["user_id"]
    title = request.form.get("title", "").strip()
    subject_id = request.form.get("subject_id")
    date_str = request.form.get("test_date")
    topic_ids = request.form.getlist("topic_ids")

    if not title or not subject_id or not date_str:
        flash("Please fill in title, subject, and date.", "error")
        return redirect(url_for("tests"))

    subject_id = int(subject_id)
    test_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    cnx = get_db()
    cur = cnx.cursor()

    cur.execute(
        """
        INSERT INTO tests (user_id, subject_id, title, test_date)
        VALUES (%s, %s, %s, %s)
        """,
        (user_id, subject_id, title, test_date),
    )
    test_id = cur.lastrowid

    for tid in topic_ids:
        if tid:
            cur.execute(
                "INSERT INTO test_topics (test_id, topic_id) VALUES (%s, %s)",
                (test_id, int(tid)),
            )

    cur.close()
    cnx.close()

    flash("Test added.", "success")
    return redirect(url_for("tests"))


@app.route("/tests/<int:test_id>/delete", methods=["POST"])
@login_required
def delete_test(test_id):
    user_id = session["user_id"]
    cnx = get_db()
    cur = cnx.cursor()
    cur.execute(
        "DELETE FROM tests WHERE id = %s AND user_id = %s",
        (test_id, user_id),
    )
    cur.close()
    cnx.close()
    return redirect(url_for("tests"))


# -----------------------
# Exams
# -----------------------


@app.route("/exams", methods=["GET"])
@login_required
def exams():
    user_id = session["user_id"]
    today = date.today()
    cnx = get_db()
    cur = cnx.cursor(dictionary=True)

    cur.execute(
        "SELECT id, name FROM subjects WHERE user_id = %s ORDER BY name",
        (user_id,),
    )
    subjects = cur.fetchall()

    cur.execute(
        """
        SELECT e.*, s.name AS subject_name
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        WHERE e.user_id = %s
        ORDER BY e.exam_date
        """,
        (user_id,),
    )
    exams = cur.fetchall()

    exam_ids = [e["id"] for e in exams]
    topics_by_exam = {eid: [] for eid in exam_ids}

    if exam_ids:
        placeholders = ",".join(["%s"] * len(exam_ids))
        cur.execute(
            f"""
            SELECT et.exam_id, tp.name, tp.is_completed
            FROM exam_topics et
            JOIN topics tp ON et.topic_id = tp.id
            WHERE et.exam_id IN ({placeholders})
            ORDER BY et.exam_id, tp.order_index, tp.id
            """,
            exam_ids,
        )
        for row in cur:
            topics_by_exam[row["exam_id"]].append(row)

    for e in exams:
        topics = topics_by_exam.get(e["id"], [])
        total = len(topics)
        completed = sum(1 for x in topics if x["is_completed"])
        e["total_topics"] = total
        e["completed_topics"] = completed
        e["readiness"] = (
            round((completed / total) * 100, 1) if total > 0 else None
        )
        e["days_remaining"] = (e["exam_date"] - today).days
        e["topics"] = topics

    cur.close()
    cnx.close()

    return render_template(
        "exams.html",
        active_page="exams",
        subjects=subjects,
        exams=exams,
        today=today,
    )

@app.route("/exams/add", methods=["POST"])
@login_required
def add_exam():
    user_id = session["user_id"]
    title = request.form.get("title", "").strip()
    subject_id = request.form.get("subject_id")
    date_str = request.form.get("exam_date")
    topic_ids = request.form.getlist("topic_ids")

    if not title or not subject_id or not date_str:
        flash("Please fill in title, subject, and date.", "error")
        return redirect(url_for("exams"))

    subject_id = int(subject_id)
    exam_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    cnx = get_db()
    cur = cnx.cursor()

    cur.execute(
        """
        INSERT INTO exams (user_id, subject_id, title, exam_date)
        VALUES (%s, %s, %s, %s)
        """,
        (user_id, subject_id, title, exam_date),
    )
    exam_id = cur.lastrowid

    for tid in topic_ids:
        if tid:
            cur.execute(
                "INSERT INTO exam_topics (exam_id, topic_id) VALUES (%s, %s)",
                (exam_id, int(tid)),
            )

    cur.close()
    cnx.close()

    flash("Exam added.", "success")
    return redirect(url_for("exams"))


@app.route("/exams/<int:exam_id>/delete", methods=["POST"])
@login_required
def delete_exam(exam_id):
    user_id = session["user_id"]
    cnx = get_db()
    cur = cnx.cursor()
    cur.execute(
        "DELETE FROM exams WHERE id = %s AND user_id = %s",
        (exam_id, user_id),
    )
    cur.close()
    cnx.close()
    return redirect(url_for("exams"))

# -----------------------
# AI Study Buddy / Chat
# -----------------------


@app.route("/chat", methods=["GET"])
@login_required
def chat():
    history = session.get("chat_history", [])
    return render_template(
        "chat.html", active_page="chat", history=history
    )


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    user_id = session["user_id"]
    data = request.get_json() or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    # Load or init history in session (simple text-based)
    history = session.get("chat_history", [])

    student_context = build_student_context(user_id)

    system_msg = {
    "role": "system",
    "content": (
        "You are 'StudyBuddyAI', a concise academic assistant for a single university student. "
        "You always base your answers on the student's current subjects, attendance, topics, "
        "assignments, tests, and exams, which are provided as context. "
        "Give direct, practical answers only. Do not add motivational fluff, apologies, or "
        "self-promotion. If you recommend what to study, be specific about subjects, topics, "
        "and upcoming dates from the context.\n\n"
        "Formatting rules (important):\n"
        "- Use plain markdown only: numbered lists (1., 2., 3.) and bullet lists (- item).\n"
        "- Put each step or recommendation on its own line.\n"
        "- Do NOT use HTML tags such as <br>, <p>, <table>, or <tr>.\n"
        "- Do NOT draw ASCII tables or use '|' characters to make columns.\n"
        "- Do NOT wrap the entire answer in a code block.\n"
        "- Avoid giant paragraphs; keep sentences short and to the point."
    ),
}

    context_msg = {
        "role": "user",
        "content": f"Here is the student's current academic context:\n{student_context}",
    }

    user_msg = {"role": "user", "content": user_message}

    # Optionally include last few turns from history, but keep prompt small
    past_msgs = []
    for turn in history[-4:]:
        past_msgs.append({"role": "user", "content": turn["user"]})
        past_msgs.append({"role": "assistant", "content": turn["assistant"]})

    messages = [system_msg, context_msg] + past_msgs + [user_msg]

    reply = call_groq_chat(messages, max_tokens=1500)

    # Store in session history
    history.append({"user": user_message, "assistant": reply})
    # prevent unlimited growth
    history = history[-20:]
    session["chat_history"] = history

    return jsonify({"reply": reply})

@app.route("/api/chat/clear", methods=["POST"])
@login_required
def api_chat_clear():
    """Clear the chat history stored in the session."""
    session["chat_history"] = []
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(debug=True)