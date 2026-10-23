# ⚡ StudyBuddy AI

A student dashboard that tracks **attendance, syllabus progress, assignments, tests and exams** in one place, and adds an **AI study assistant** that answers using your real academic data.

Built for a hackathon with Flask, MySQL and the Groq LLM API.

---

## Features

| Area | What it does |
|---|---|
| **Auth** | Register / login / logout with hashed passwords (Werkzeug). Sessions last 7 days. Every page and API route except login/register requires a login. |
| **Dashboard** | Summary cards (subjects, attendance warnings, pending assignments, upcoming tests/exams), the 3 lowest-attendance subjects, and the 5 most urgent items across assignments, tests and exams. |
| **Subjects & Attendance** | Add subjects (with optional code and an initial topic list, one per line). Mark each class *Attended* or *Missed*. Shows attendance %, **how many classes you can still safely miss**, and **how many you must attend to recover** to the 75% threshold. Delete subjects. |
| **Syllabus topics** | Add topics later (one per line) and tick them off with an instant (AJAX) checkbox. Shows completed / total per subject. |
| **Assignments** | Add assignments with optional subject, due date and description. Mark done/undone without a page reload. Shows days remaining. **"AI: What should I review?"** button gives a prioritised review list based on the subject's topics. |
| **Tests** | Create a test for a subject and pick which topics it covers. Shows days remaining and a **readiness %** (completed topics ÷ linked topics). |
| **Exams** | Same as tests, for exams. |
| **AI Study Assistant** | Chat with *StudyBuddyAI*. Each message is sent together with a summary of your subjects, attendance, topics, assignments, tests and exams, so answers are specific to you. Quick-start buttons ("What to study today", "Check test readiness", "Plan this week"), short-term memory (last 4 turns), and a **Clear chat** button. |
| **Global search** | The top-bar search filters the cards/list items on the current page (Ctrl/Cmd + K to focus). |
| **UI** | Glassmorphism theme with animated gradient background and a sidebar layout. |

### How the attendance maths works

The threshold is fixed at **75%**. With `A` classes attended out of `T` total:

- **Attendance %** = `A / T × 100`
- **Safe to miss** = `floor(max(0, A / 0.75 − T))`
- **Need to attend to recover** = `max(0, 3T − 4A)`

Example: 6 attended out of 10 → 60%, need to attend 6 more in a row to get back to 75%.

---

## Tech stack

- **Backend:** Python 3, Flask 3
- **Database:** MySQL (via `mysql-connector-python`, connection pool of 5)
- **AI:** [Groq](https://console.groq.com) chat-completions API (OpenAI-compatible) through `requests`
- **Frontend:** Jinja2 templates, vanilla JavaScript, custom CSS (no frameworks)

---

## Project structure

```
StudyBuddy-hackathon/
├── app.py              # All Flask routes + AI helpers
├── config.py           # Settings loaded from environment / .env
├── db.py               # MySQL connection pool
├── requirements.txt
├── sql/
│   ├── 01_create_database.sql   # CREATE DATABASE studybuddy
│   ├── 02_create_tables.sql     # users, subjects, topics, assignments, tests, exams (+ link tables)
│   └── 03_demo_data.sql         # Optional sample data for one user
├── templates/          # base, login, register, dashboard, subjects, assignments, tests, exams, chat
└── static/
    ├── css/style.css
    └── js/main.js, chat.js
```

### Database schema

`users` → `subjects` → `topics`; `users` → `assignments` (optional subject); `tests` / `exams` belong to a subject and link to topics through `test_topics` / `exam_topics`. All foreign keys cascade on delete (assignments keep existing and just lose their subject).

---

## Getting started

### Prerequisites

- Python 3.9+
- MySQL 8 (or MariaDB 10.5+) running locally
- A free Groq API key from <https://console.groq.com> (the app runs without one, but the AI features will just say they're not configured)

### 1. Clone and install

```bash
git clone https://github.com/syLvester03/StudyBuddy-hackathon.git
cd StudyBuddy-hackathon

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create the database

```bash
mysql -u root -p < sql/01_create_database.sql
mysql -u root -p < sql/02_create_tables.sql
```

### 3. Configure environment

Create a file named `.env` in the project root (it is git-ignored):

```env
SECRET_KEY=change-me-to-a-long-random-string

DB_HOST=localhost
DB_PORT=3306
DB_NAME=studybuddy
DB_USER=root
DB_PASSWORD=your_mysql_password

# NOTE: the key variable is lowercase `api_key` (that's what config.py reads)
api_key=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
```

| Variable | Default | Notes |
|---|---|---|
| `SECRET_KEY` | `dev-secret-change-me` | Signs session cookies. **Always set your own.** |
| `DB_HOST` / `DB_PORT` | `localhost` / `3306` | |
| `DB_NAME` | `studybuddy` | |
| `DB_USER` / `DB_PASSWORD` | `root` / *(empty)* | |
| `api_key` | *(none)* | Your Groq API key. Lowercase on purpose. |
| `GROQ_MODEL` | `llama-3.1-70b-versatile` | Groq retires models over time. If AI calls fail, set this to a currently available model from the Groq console (e.g. `llama-3.3-70b-versatile`). |

### 4. Run

```bash
python app.py
```

Open <http://127.0.0.1:5000>, register an account and you're in.

### 5. (Optional) Load demo data

1. Register an account first.
2. Check your user id: `SELECT id, email FROM users;`
3. If it isn't `1`, edit `SET @USER_ID = 1;` at the top of `sql/03_demo_data.sql`.
4. Run it:

```bash
mysql -u root -p < sql/03_demo_data.sql
```

This adds three subjects (Database Systems, DSA, Calculus II) with topics and attendance, three assignments, two tests and two exams with dates relative to today.

---

## Routes overview

| Route | Method | Purpose |
|---|---|---|
| `/`, `/login`, `/register`, `/logout` | GET/POST | Authentication |
| `/dashboard` | GET | Overview |
| `/subjects` | GET | Subjects, attendance, topics |
| `/subjects/add`, `/subjects/<id>/delete` | POST | Add / delete subject |
| `/subjects/<id>/attendance` | POST | `action=attended` or `missed` |
| `/subjects/<id>/topics/add`, `/topics/<id>/toggle` | POST | Add topics / toggle completion |
| `/assignments`, `/assignments/add`, `/assignments/<id>/toggle`, `/assignments/<id>/delete` | GET/POST | Assignments |
| `/tests`, `/tests/add`, `/tests/<id>/delete` | GET/POST | Tests |
| `/exams`, `/exams/add`, `/exams/<id>/delete` | GET/POST | Exams |
| `/chat` | GET | Chat page |
| `/api/chat`, `/api/chat/clear` | POST | Send message / clear history |
| `/api/assignments/<id>/ai_suggestions` | POST | AI review suggestions |
| `/api/subjects/<id>/topics` | GET | Topic list (used by test/exam forms) |

All data queries are scoped to the logged-in user.

---

## Known limitations

These are worth knowing before a demo or deployment:

- **Chat history lives in the session cookie.** Long conversations can exceed the ~4 KB browser cookie limit, after which the browser may drop the session and log you out. Clear the chat regularly, or move history into the database.
- **Attendance threshold is hard-coded at 75%.**
- **No CSRF protection** on forms, and `app.run(debug=True)` is enabled. Fine for local use, not for production.
- **Foreign subject IDs are not validated** when creating assignments, tests and exams (a user who guesses another user's subject id can attach to it).
- **Invalid dates** posted by hand (bypassing the browser date picker) cause a server error.
- No edit feature for subjects, assignments, tests or exams (add/delete only).
- The AI is only as good as the data you enter; it also needs internet access to reach Groq.

---

## License

*Not specified yet.*

## Authors

Built by **syLvester03** for a hackathon.
