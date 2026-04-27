import json
import os
import re
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(__file__)
FRONTEND_DIR = os.path.join(BASE_DIR, "..")

_db_url = os.environ.get("DATABASE_URL", "")
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
DATABASE_URL = _db_url
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
else:
    import sqlite3
    DATA_DIR = os.path.join(BASE_DIR, "data")
    DB_PATH = os.path.join(DATA_DIR, "cliniccare_dev.db")


# ---------------------------------------------------------------------------
# SQLite compatibility shim — makes sqlite3 behave like psycopg2 RealDictCursor
# so all route code is identical regardless of which DB is in use.
# ---------------------------------------------------------------------------
class _SQLiteCursor:
    def __init__(self, cur):
        self._c = cur

    def execute(self, sql, params=()):
        self._c.execute(sql.replace("%s", "?"), params)
        return self

    def executemany(self, sql, seq):
        self._c.executemany(sql.replace("%s", "?"), seq)

    def fetchone(self):
        row = self._c.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(r) for r in self._c.fetchall()]

    @property
    def rowcount(self):
        return self._c.rowcount


class _SQLiteConn:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return _SQLiteCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def db_conn():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return _SQLiteConn(conn)


app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/<path:_unused>", methods=["OPTIONS"])
def handle_options(_unused):
    return ("", 204)


DOCTORS_SEED = [
    {"name": "Dr. Ahmed Rahman", "dept": "General Medicine", "exp": 12, "rating": 4.9, "reviews": 128, "available": 1, "tags": "fever infection hypertension diabetes primary care"},
    {"name": "Dr. Farhana Jamil", "dept": "General Medicine", "exp": 10, "rating": 4.8, "reviews": 101, "available": 1, "tags": "cold flu checkups fatigue primary care"},
    {"name": "Dr. Hasan Imran", "dept": "General Medicine", "exp": 8, "rating": 4.7, "reviews": 84, "available": 1, "tags": "digestive lifestyle headache fever weakness"},
    {"name": "Dr. Nabila Sayeed", "dept": "General Medicine", "exp": 11, "rating": 4.9, "reviews": 139, "available": 0, "tags": "routine care nutrition diabetes blood pressure"},
    {"name": "Dr. Sultana Khan", "dept": "Cardiology", "exp": 18, "rating": 4.8, "reviews": 214, "available": 1, "tags": "heart chest pain arrhythmia ecg cardiology"},
    {"name": "Dr. Mahin Chowdhury", "dept": "Cardiology", "exp": 14, "rating": 4.7, "reviews": 167, "available": 1, "tags": "hypertension cardiac rehab heart failure"},
    {"name": "Dr. Tanzim Alam", "dept": "Cardiology", "exp": 9, "rating": 4.6, "reviews": 98, "available": 1, "tags": "chest pain pressure palpitation monitoring"},
    {"name": "Dr. Rehana Noor", "dept": "Cardiology", "exp": 12, "rating": 4.8, "reviews": 143, "available": 0, "tags": "preventive cardiology lipids heart risk"},
    {"name": "Dr. Mahfuz Islam", "dept": "Neurology", "exp": 9, "rating": 4.6, "reviews": 89, "available": 1, "tags": "migraine epilepsy stroke headache dizziness"},
    {"name": "Dr. Aritri Sen", "dept": "Neurology", "exp": 11, "rating": 4.8, "reviews": 133, "available": 1, "tags": "neuropathy nerve dizziness blurred vision"},
    {"name": "Dr. Kazi Morshed", "dept": "Neurology", "exp": 13, "rating": 4.7, "reviews": 118, "available": 1, "tags": "seizures headache memory sleep issues"},
    {"name": "Dr. Samia Bari", "dept": "Neurology", "exp": 7, "rating": 4.5, "reviews": 71, "available": 0, "tags": "pediatric neuro coordination memory concentration"},
    {"name": "Dr. Nadia Akter", "dept": "Pediatrics", "exp": 7, "rating": 4.9, "reviews": 176, "available": 1, "tags": "child fever vaccination growth pediatric"},
    {"name": "Dr. Laila Tasnim", "dept": "Pediatrics", "exp": 10, "rating": 4.8, "reviews": 152, "available": 1, "tags": "newborn allergy child nutrition immunity"},
    {"name": "Dr. Shoaib Karim", "dept": "Pediatrics", "exp": 8, "rating": 4.7, "reviews": 111, "available": 1, "tags": "pediatric respiratory infection fever cough"},
    {"name": "Dr. Priyanka Das", "dept": "Pediatrics", "exp": 9, "rating": 4.8, "reviews": 127, "available": 0, "tags": "immunization skin child development pediatric"},
    {"name": "Dr. Tanvir Hoque", "dept": "Orthopedics", "exp": 15, "rating": 4.7, "reviews": 102, "available": 1, "tags": "fractures joint pain sports injury orthopedic"},
    {"name": "Dr. Mizan Kabir", "dept": "Orthopedics", "exp": 12, "rating": 4.8, "reviews": 146, "available": 1, "tags": "back pain knee spine orthopedic rehab"},
    {"name": "Dr. Rubayet Hossain", "dept": "Orthopedics", "exp": 9, "rating": 4.6, "reviews": 90, "available": 1, "tags": "trauma shoulder pain fracture mobility"},
    {"name": "Dr. Nigar Sultana", "dept": "Orthopedics", "exp": 11, "rating": 4.7, "reviews": 120, "available": 0, "tags": "arthritis bone health joint stiffness"},
    {"name": "Dr. Rina Begum", "dept": "ENT", "exp": 11, "rating": 4.8, "reviews": 93, "available": 0, "tags": "ear sinus throat ent infection"},
    {"name": "Dr. Fahim Uddin", "dept": "ENT", "exp": 13, "rating": 4.7, "reviews": 124, "available": 1, "tags": "hearing nasal voice ent sinus"},
    {"name": "Dr. Sabiha Anjum", "dept": "ENT", "exp": 8, "rating": 4.6, "reviews": 82, "available": 1, "tags": "allergic rhinitis tonsils ear pain ent"},
    {"name": "Dr. Omar Faruq", "dept": "ENT", "exp": 10, "rating": 4.7, "reviews": 109, "available": 1, "tags": "sinusitis vertigo snoring throat ent"},
]


def score_doctor_breakdown(doc, symptom_text):
    tags = (doc["tags"] or "").lower()
    text = symptom_text.lower()
    words = [x for x in text.split() if x]
    matched = []
    keyword_points = 0
    for key in words:
        if key in tags:
            keyword_points += 8
            if key not in matched:
                matched.append(key)
    experience_points = min(20, int(doc["experience"]))
    rating_points = round(float(doc["rating"]) * 10)
    availability_bonus = 15 if int(doc["available_today"]) == 1 else 0
    match_score = keyword_points + experience_points + rating_points + availability_bonus
    explanation_lines = []
    if matched:
        explanation_lines.append(
            f"Symptom keyword overlap with specialty tags (+{keyword_points} pts): {', '.join(matched[:6])}"
            + ("…" if len(matched) > 6 else "")
        )
    else:
        explanation_lines.append("No direct keyword overlap with tags (0 pts); rank driven by experience & rating.")
    explanation_lines.append(f"Experience cap contribution: +{experience_points} pts (years capped at 20).")
    explanation_lines.append(f"Patient rating signal: +{rating_points} pts (rating × 10).")
    explanation_lines.append(
        f"Availability today: {'+15 pts (slots open)' if availability_bonus else '0 pts (no same-day slot flag)'}"
    )
    return {
        "match_score": match_score,
        "keyword_match_points": keyword_points,
        "experience_points": experience_points,
        "rating_points": rating_points,
        "availability_bonus": availability_bonus,
        "matched_keywords": matched,
        "explanation_lines": explanation_lines,
    }


def infer_condition_and_department(symptoms, severity):
    text = " ".join(symptoms).lower()
    if "chest" in text or "heart" in text or "breath" in text:
        if severity == "Severe":
            return "Acute Cardiac Risk Pattern", "Cardiology"
        return "Possible Cardiac Strain", "Cardiology"
    if "headache" in text or "dizziness" in text or "blurred" in text or "migraine" in text:
        return "Migraine or Neurological Trigger", "Neurology"
    if "ear" in text or "throat" in text or "runny nose" in text or "sinus" in text:
        return "Upper Respiratory / ENT Infection", "ENT"
    if "joint" in text or "back pain" in text or "muscle" in text:
        return "Musculoskeletal Inflammation", "Orthopedics"
    if "child" in text or "infant" in text:
        return "Pediatric General Condition", "Pediatrics"
    return "General Viral/Infectious Pattern", "General Medicine"


def init_db():
    PK = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    conn = db_conn()
    cur = conn.cursor()

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS doctors (
            id {PK},
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            experience INTEGER NOT NULL,
            rating REAL NOT NULL,
            reviews INTEGER NOT NULL,
            available_today INTEGER NOT NULL DEFAULT 0,
            tags TEXT NOT NULL
        )
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS appointments (
            id {PK},
            user_id INTEGER NOT NULL,
            doctor_name TEXT NOT NULL,
            department TEXT NOT NULL,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            time_of_day TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed',
            reason TEXT
        )
        """
    )
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS symptom_checks (
            id {PK},
            user_id INTEGER NOT NULL,
            symptoms_json TEXT NOT NULL,
            severity TEXT NOT NULL,
            duration TEXT NOT NULL,
            predicted_condition TEXT NOT NULL,
            recommended_department TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute("SELECT COUNT(*) AS count FROM doctors")
    if cur.fetchone()["count"] == 0:
        cur.executemany(
            "INSERT INTO doctors (name, department, experience, rating, reviews, available_today, tags) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [(d["name"], d["dept"], d["exp"], d["rating"], d["reviews"], d["available"], d["tags"]) for d in DOCTORS_SEED],
        )

    cur.execute("SELECT COUNT(*) AS count FROM appointments")
    if cur.fetchone()["count"] == 0:
        seed_appointments = [
            (1, "Dr. Ahmed Rahman", "General Medicine", "2026-01-20", "10:00 AM", "Morning", "completed", "Fever & headache"),
            (1, "Dr. Sultana Khan", "Cardiology", "2026-02-08", "2:30 PM", "Afternoon", "completed", "Follow-up"),
            (1, "Dr. Mahfuz Islam", "Neurology", "2026-02-22", "11:00 AM", "Morning", "completed", "Recurring headaches"),
            (1, "Dr. Nadia Akter", "Pediatrics", "2026-03-01", "9:30 AM", "Morning", "completed", "Family consultation"),
            (1, "Dr. Ahmed Rahman", "General Medicine", "2026-03-18", "10:30 AM", "Morning", "completed", "Fatigue"),
            (1, "Dr. Ahmed Rahman", "General Medicine", "2026-04-02", "10:00 AM", "Morning", "upcoming", "General check-up"),
        ]
        cur.executemany(
            "INSERT INTO appointments (user_id, doctor_name, department, appointment_date, appointment_time, time_of_day, status, reason) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            seed_appointments,
        )

    cur.execute("SELECT COUNT(*) AS count FROM symptom_checks")
    if cur.fetchone()["count"] == 0:
        checks = [
            (1, json.dumps(["Headache", "Fever", "Fatigue"]), "Moderate", "1–3 Days", "Viral Flu Syndrome", "General Medicine"),
            (1, json.dumps(["Chest Pain", "Shortness of Breath"]), "Severe", "4–7 Days", "Possible Cardiac Strain", "Cardiology"),
            (1, json.dumps(["Headache", "Dizziness"]), "Moderate", "1–3 Days", "Migraine Pattern", "Neurology"),
        ]
        cur.executemany(
            "INSERT INTO symptom_checks (user_id, symptoms_json, severity, duration, predicted_condition, recommended_department) VALUES (%s, %s, %s, %s, %s, %s)",
            checks,
        )

    conn.commit()
    conn.close()


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "cliniccare-ai-backend-flask"})


@app.post("/api/analyze-symptoms")
def analyze_symptoms():
    try:
        body = request.get_json(silent=True) or {}
        user_id = int(body.get("userId", 1))
        symptoms = body.get("symptoms", [])
        severity = body.get("severity", "Moderate")
        duration = body.get("duration", "1–3 Days")
        notes = body.get("notes", "")

        if not isinstance(symptoms, list) or not symptoms:
            return jsonify({"error": "At least one symptom is required."}), 400

        condition, department = infer_condition_and_department(symptoms, severity)
        symptom_text = f"{' '.join(symptoms)} {notes}".strip()

        conn = db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, department, experience, rating, reviews, available_today, tags FROM doctors WHERE department = %s",
            (department,),
        )
        docs = [dict(r) for r in cur.fetchall()]
        enriched = []
        for d in docs:
            bd = score_doctor_breakdown(d, symptom_text)
            enriched.append({**d, **bd})
        ranked = sorted(enriched, key=lambda x: x["match_score"], reverse=True)[:4]

        cur.execute(
            "INSERT INTO symptom_checks (user_id, symptoms_json, severity, duration, predicted_condition, recommended_department) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, json.dumps(symptoms), severity, duration, condition, department),
        )
        cur.execute(
            "SELECT department, COUNT(*) AS count FROM doctors WHERE department != %s GROUP BY department ORDER BY count DESC LIMIT 2",
            (department,),
        )
        alternatives_raw = cur.fetchall()
        conn.commit()
        conn.close()

        confidence = min(98, 78 + len(symptoms) * 4 + (6 if severity == "Severe" else 0))
        alternatives = [
            {"department": row["department"], "confidence": max(25, confidence - 18 - i * 10)}
            for i, row in enumerate(alternatives_raw)
        ]

        return jsonify(
            {
                "predicted_condition": condition,
                "recommended_department": department,
                "confidence": confidence,
                "top_doctors": [
                    {
                        "id": d["id"],
                        "name": d["name"],
                        "department": d["department"],
                        "experience": d["experience"],
                        "rating": d["rating"],
                        "reviews": d["reviews"],
                        "available_today": bool(d["available_today"]),
                        "match_score": d["match_score"],
                        "match_breakdown": {
                            "keyword_match_points": d["keyword_match_points"],
                            "experience_points": d["experience_points"],
                            "rating_points": d["rating_points"],
                            "availability_bonus": d["availability_bonus"],
                            "matched_keywords": d["matched_keywords"],
                        },
                        "match_explanation": d["explanation_lines"],
                    }
                    for d in ranked
                ],
                "alternatives": alternatives,
            }
        )
    except Exception as exc:
        return jsonify({"error": "Failed to analyze symptoms.", "detail": str(exc)}), 500


@app.get("/api/smart-slots")
def smart_slots():
    try:
        user_id = int(request.args.get("userId", 1))
        conn = db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT time_of_day, appointment_time FROM appointments WHERE user_id = %s ORDER BY appointment_date DESC",
            (user_id,),
        )
        history = [dict(r) for r in cur.fetchall()]
        conn.close()

        prefs = {"Morning": 0, "Afternoon": 0, "Evening": 0}
        for item in history:
            tod = item.get("time_of_day")
            if tod in prefs:
                prefs[tod] += 1

        preferred = sorted(prefs.keys(), key=lambda x: prefs[x], reverse=True)[0] if prefs else "Morning"
        templates = {
            "Morning": ["9:00 AM", "9:30 AM", "10:00 AM", "10:30 AM"],
            "Afternoon": ["1:00 PM", "1:30 PM", "2:00 PM", "2:30 PM"],
            "Evening": ["4:00 PM", "4:30 PM", "5:00 PM", "5:30 PM"],
        }

        now = datetime.now()
        suggestions = []
        for idx, time in enumerate(templates[preferred]):
            date_val = now + timedelta(days=idx + 1)
            suggestions.append(
                {
                    "label": f"{date_val.strftime('%a, %b')} {date_val.day} · {time}",
                    "date_iso": date_val.strftime("%Y-%m-%d"),
                    "time": time,
                    "reason": f"Based on your {preferred.lower()} booking preference",
                }
            )

        return jsonify({"preferred_time_of_day": preferred, "suggestions": suggestions})
    except Exception as exc:
        return jsonify({"error": "Failed to generate smart slots.", "detail": str(exc)}), 500


@app.post("/api/appointments")
def create_appointment():
    try:
        body = request.get_json(silent=True) or {}
        user_id = int(body.get("userId", 1))
        doctor_name = body.get("doctorName", "Dr. Ahmed Rahman")
        department = body.get("department", "General Medicine")
        date_iso = body.get("dateIso", datetime.now().strftime("%Y-%m-%d"))
        time_value = body.get("time", "10:00 AM")
        reason = body.get("reason", "General check-up")

        hour = int(str(time_value).split(":")[0])
        is_pm = "PM" in str(time_value).upper()
        hour24 = hour + 12 if is_pm and hour < 12 else hour
        if hour24 < 12:
            time_of_day = "Morning"
        elif hour24 < 17:
            time_of_day = "Afternoon"
        else:
            time_of_day = "Evening"

        conn = db_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO appointments (user_id, doctor_name, department, appointment_date, appointment_time, time_of_day, status, reason) VALUES (%s, %s, %s, %s, %s, %s, 'upcoming', %s)",
            (user_id, doctor_name, department, date_iso, time_value, time_of_day, reason),
        )
        conn.commit()
        conn.close()

        return jsonify({"ok": True, "message": "Appointment stored successfully."})
    except Exception as exc:
        return jsonify({"error": "Failed to save appointment.", "detail": str(exc)}), 500


@app.get("/api/my-appointments")
def my_appointments():
    try:
        user_id = int(request.args.get("userId", 1))
        conn = db_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, doctor_name, department, appointment_date, appointment_time, status, reason
            FROM appointments
            WHERE user_id = %s
            ORDER BY appointment_date DESC, id DESC
            LIMIT 25
            """,
            (user_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify({"appointments": rows})
    except Exception as exc:
        return jsonify({"error": "Failed to fetch appointments.", "detail": str(exc)}), 500


@app.post("/api/appointments/cancel")
def cancel_appointment():
    try:
        body = request.get_json(silent=True) or {}
        appointment_id = body.get("appointmentId")
        user_id = int(body.get("userId", 1))

        if not appointment_id:
            return jsonify({"error": "appointmentId is required."}), 400

        conn = db_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE appointments SET status = 'cancelled' WHERE id = %s AND user_id = %s",
            (int(appointment_id), user_id),
        )
        conn.commit()
        changed = cur.rowcount
        conn.close()

        if changed == 0:
            return jsonify({"error": "Appointment not found."}), 404
        return jsonify({"ok": True, "message": "Appointment cancelled."})
    except Exception as exc:
        return jsonify({"error": "Failed to cancel appointment.", "detail": str(exc)}), 500


@app.get("/api/risk-assessment")
def risk_assessment():
    try:
        user_id = int(request.args.get("userId", 1))
        conn = db_conn()
        cur = conn.cursor()
        cur.execute("SELECT department, status FROM appointments WHERE user_id = %s", (user_id,))
        appointments = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT symptoms_json, recommended_department FROM symptom_checks WHERE user_id = %s ORDER BY created_at DESC LIMIT 20",
            (user_id,),
        )
        checks = [dict(r) for r in cur.fetchall()]
        conn.close()

        dept_counts = {}
        for ap in appointments:
            dept = ap["department"]
            dept_counts[dept] = dept_counts.get(dept, 0) + 1
        for sc in checks:
            dept = sc["recommended_department"]
            dept_counts[dept] = dept_counts.get(dept, 0) + 1

        symptom_counts = {}
        for row in checks:
            parsed = []
            try:
                parsed = json.loads(row["symptoms_json"])
            except Exception:
                parsed = []
            for s in parsed:
                key = str(s).lower()
                symptom_counts[key] = symptom_counts.get(key, 0) + 1

        top_department = sorted(dept_counts.items(), key=lambda x: x[1], reverse=True)[0] if dept_counts else None
        top_symptom = sorted(symptom_counts.items(), key=lambda x: x[1], reverse=True)[0] if symptom_counts else None

        score = 20
        if top_department and top_department[1] >= 4:
            score += 30
        if top_symptom and top_symptom[1] >= 3:
            score += 25
        if len([a for a in appointments if a["status"] == "upcoming"]) >= 2:
            score += 10

        if score >= 65:
            level = "High"
        elif score >= 40:
            level = "Medium"
        else:
            level = "Low"

        insights = [
            f"Recurring visits detected in {top_department[0]} ({top_department[1]} records)." if top_department else "No strong recurring department trend yet.",
            f'Most repeated symptom is "{top_symptom[0]}" ({top_symptom[1]} checks).' if top_symptom else "No repeated symptom cluster detected.",
            "Recommended: schedule specialist follow-up and keep symptom monitoring active."
            if level == "High"
            else "Recommended: continue regular checkups and monitor symptom frequency."
            if level == "Medium"
            else "Recommended: maintain preventive care and healthy routine.",
        ]

        return jsonify(
            {
                "risk_level": level,
                "risk_score": score,
                "recurring_department": {"department": top_department[0], "count": top_department[1]} if top_department else None,
                "recurring_symptom": {"symptom": top_symptom[0], "count": top_symptom[1]} if top_symptom else None,
                "insights": insights,
            }
        )
    except Exception as exc:
        return jsonify({"error": "Failed to build risk assessment.", "detail": str(exc)}), 500


EMERGENCY_CONTACTS = [
    {"label": "National emergency hotline", "phone": "999", "note": "Life-threatening emergencies — use your country's official number if different."},
    {"label": "ClinicCare 24/7 nurse line (demo)", "phone": "+880-1711-000000", "note": "Triage & facility routing — demo number."},
    {"label": "Mental health crisis line (demo)", "phone": "16263", "note": "Example helpline; verify locally."},
]

EMERGENCY_HOSPITALS = [
    {"name": "ClinicCare Emergency & Trauma Center (demo)", "address": "Dhaka Medical Zone, Plot 12 (sample address)", "phone": "+880-2-00000000", "open_24h": True, "maps_query": "Dhaka Medical College Hospital"},
    {"name": "City General Hospital ER (demo)", "address": "Central City, Ring Road (sample)", "phone": "+880-2-11111111", "open_24h": True, "maps_query": "Square Hospitals Dhaka"},
    {"name": "Women & Children Emergency Wing (demo)", "address": "Pediatric district, Block C (sample)", "phone": "+880-2-22222222", "open_24h": False, "maps_query": "Bangladesh Shishu Hospital"},
]


def pick_nearest_available_doctor():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, department, experience, rating, reviews, available_today
        FROM doctors
        WHERE available_today = 1
        ORDER BY rating DESC, experience DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if row:
        conn.close()
        return {**dict(row), "availability_note": "Same-day availability flag on file — book to confirm a slot."}
    cur.execute(
        """
        SELECT id, name, department, experience, rating, reviews, available_today
        FROM doctors
        ORDER BY rating DESC, experience DESC
        LIMIT 1
        """
    )
    row2 = cur.fetchone()
    conn.close()
    if not row2:
        return None
    return {**dict(row2), "availability_note": "No same-day flag in directory; showing top-rated doctor for fast booking — call ER for urgent care."}


@app.get("/api/emergency-resources")
def emergency_resources():
    try:
        doctor = pick_nearest_available_doctor()
        return jsonify(
            {
                "disclaimer": "For chest pain, stroke symptoms, severe bleeding, or trouble breathing, call your national emergency number immediately. This panel is for navigation and clinic booking only — not a substitute for emergency services.",
                "emergency_contacts": EMERGENCY_CONTACTS,
                "hospitals": EMERGENCY_HOSPITALS,
                "nearest_available_doctor": doctor,
            }
        )
    except Exception as exc:
        return jsonify({"error": "Failed to load emergency resources.", "detail": str(exc)}), 500


def _norm_chat(text: str) -> str:
    t = (text or "").lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t


def health_chat_reply(user_message: str) -> dict:
    t = _norm_chat(user_message)
    suggestions_default = [
        "Which department should I visit for chest pain?",
        "What should I do for a fever?",
        "How do I book an appointment?",
    ]

    if not t:
        return {"reply": "Ask a short question in plain English — for example which department fits your symptoms, or self-care tips for common issues.", "topic": "empty", "suggestions": suggestions_default}

    if any(k in t for k in ["can't breathe", "cannot breathe", "choking", "unconscious", "severe bleeding", "stroke", "suicide", "kill myself"]):
        return {"reply": "That can be an emergency. Call your national emergency number right away (for example 999 or your local equivalent) or go to the nearest ER. This chat cannot assess urgency — use official emergency services.", "topic": "emergency", "suggestions": ["Where is the emergency panel in the app?", "How do I book a routine visit?"]}

    if "department" in t or "which specialist" in t or "which doctor" in t or "where should i go" in t:
        return {"reply": "ClinicCare routes by symptom: heart/chest pressure → Cardiology; headaches, dizziness, numbness → Neurology; ear/nose/throat → ENT; bones/joints/back → Orthopedics; children → Pediatrics; otherwise start with General Medicine.", "topic": "departments", "suggestions": ["I have a headache — which department?", "What about fever in a child?"]}

    if "fever" in t:
        return {"reply": "For fever: rest, fluids, and monitor temperature. Seek same-day care if fever is very high, lasts several days, you have breathing difficulty, confusion, stiff neck, or severe pain. Adults often start with General Medicine; infants and young children → Pediatrics.", "topic": "fever", "suggestions": ["When should I worry about fever?", "Book an appointment"]}

    if any(k in t for k in ["cold", "flu", "cough", "runny nose", "sore throat"]) and not any(k in t for k in ["chest pain", "heart"]):
        return {"reply": "Colds and mild respiratory symptoms often fit General Medicine or ENT if it is mainly throat/sinus. Rest, hydration, and isolation if contagious.", "topic": "respiratory", "suggestions": ["Sore throat for days — who to see?", "Chest pain with cough"]}

    if any(k in t for k in ["chest pain", "heart palpitation", "palpitation", "shortness of breath", "short of breath"]):
        return {"reply": "New or severe chest pain, pain into the arm/jaw, or trouble breathing needs urgent medical assessment — call emergency services if symptoms are severe.", "topic": "cardiac", "suggestions": ["Which department for check-ups?", "What is the Symptom Checker?"]}

    if any(k in t for k in ["headache", "migraine", "dizziness", "numbness", "seizure"]):
        return {"reply": "Persistent or sudden severe headache, weakness on one side, trouble speaking, or seizures need urgent evaluation. For routine headaches or neurological concerns, Neurology is common.", "topic": "neuro", "suggestions": ["Fever with headache", "Book Neurology"]}

    if any(k in t for k in ["stomach", "nausea", "vomit", "diarrhea", "abdomen", "abdominal"]):
        return {"reply": "Mild stomach upset: hydrate and monitor. See a clinician for severe pain, blood in stool/vomit, dehydration signs, or pain that worsens.", "topic": "gi", "suggestions": ["Food poisoning symptoms", "Which department for stomach pain?"]}

    if any(k in t for k in ["joint", "knee", "back pain", "fracture", "bone", "orthopedic"]):
        return {"reply": "Joint or musculoskeletal issues are often seen in Orthopedics; sudden injury with deformity or inability to bear weight may need urgent care or ER.", "topic": "ortho", "suggestions": ["Sports injury — who to see?", "Back pain for weeks"]}

    if any(k in t for k in ["ear", "nose", "throat", "sinus", "hearing"]):
        return {"reply": "Ear, nose, and throat symptoms usually map to ENT. Severe throat swelling or breathing problems are emergencies — call emergency services.", "topic": "ent", "suggestions": ["Sinus infection", "Sore throat only"]}

    if re.search(r"\b(baby|babies|child|children|infant|toddler|kids?|pediatric)\b", t):
        return {"reply": "For children, Pediatrics is the usual first stop for fever, cough, and routine concerns. Seek urgent care if the child is lethargic, breathing hard, dehydrated, or you are worried.", "topic": "peds", "suggestions": ["Fever in a baby", "Child ear pain"]}

    if any(k in t for k in ["book", "appointment", "schedule", "slot"]):
        return {"reply": "Use Book Appointment on the dashboard or menu to pick a department, doctor, and time. The Symptom Checker can suggest a department first if you are unsure.", "topic": "booking", "suggestions": ["Which department for fever?", "Open symptom checker"]}

    if any(k in t for k in ["symptom checker", "analyze symptom"]):
        return {"reply": "The Symptom Checker asks for your symptoms and suggests a likely department and doctors — it is more detailed than this quick chat.", "topic": "symptom_checker", "suggestions": ["Which department should I visit?", "What should I do for fever?"]}

    if any(k in t for k in ["hello", "hi ", "hey", "thanks", "thank you"]):
        return {"reply": "Hello — I am ClinicCare's rule-based health guidance assistant. Ask about departments, common symptoms, or booking. I am not a doctor and cannot diagnose.", "topic": "greeting", "suggestions": suggestions_default}

    return {"reply": "I can help with simple questions like which department might fit your situation, general self-care reminders, or how booking works. Try rephrasing, or use the Symptom Checker for a fuller guided flow.", "topic": "fallback", "suggestions": suggestions_default}


@app.post("/api/health-chat")
def health_chat():
    try:
        body = request.get_json(silent=True) or {}
        message = body.get("message", "")
        if not isinstance(message, str):
            return jsonify({"error": "message must be a string."}), 400
        out = health_chat_reply(message)
        return jsonify(out)
    except Exception as exc:
        return jsonify({"error": "Failed to process chat.", "detail": str(exc)}), 500


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "homepage.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(FRONTEND_DIR, filename)


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print(f"ClinicCare Flask backend running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
