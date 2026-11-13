"""
database.py

Creates the SQLite schema for the Examination Integrity Management System and seeds it
with a small set of sample data so the app is demoable immediately.

Run this file directly whenever you need to (re)build the database:
    python database/database.py

To provision demo logins in a new database, set DEMO_ADMIN_PASSWORD and
DEMO_INVIGILATOR_PASSWORD in the environment before running this script.
"""

import sqlite3
import os
from datetime import date, datetime, timedelta
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "exam_integrity.db")


def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'invigilator')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_number TEXT UNIQUE NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            course TEXT,
            year_of_study INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invigilators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            employee_number TEXT UNIQUE NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            phone TEXT,
            status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS examinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT NOT NULL,
            examination_name TEXT NOT NULL,
            examination_date DATE NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            venue TEXT,
            invigilator_id INTEGER,
            status TEXT DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'ongoing', 'completed', 'cancelled')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invigilator_id) REFERENCES invigilators (id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            examination_id INTEGER,
            incident_type TEXT NOT NULL,
            description TEXT,
            severity TEXT DEFAULT 'low' CHECK (severity IN ('low', 'medium', 'high')),
            status TEXT DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
            reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students (id),
            FOREIGN KEY (examination_id) REFERENCES examinations (id)
        )
    """)


def seed_data(cursor):
    # --- Users ---------------------------------------------------------
    # Preserve already-provisioned presentation accounts. Fresh databases can
    # seed them from environment variables without placing plaintext secrets in source.
    admin_password = os.environ.get("DEMO_ADMIN_PASSWORD")
    if admin_password:
        cursor.execute("""
            INSERT OR IGNORE INTO users (username, password, role)
            VALUES (?, ?, 'admin')
        """, ("admin", generate_password_hash(admin_password)))

    invig_password = os.environ.get("DEMO_INVIGILATOR_PASSWORD")
    if invig_password:
        cursor.execute("""
            INSERT OR IGNORE INTO users (username, password, role)
            VALUES (?, ?, 'invigilator')
        """, ("jkamau", generate_password_hash(invig_password)))

    invig_user = cursor.execute("SELECT id FROM users WHERE username = ?", ("jkamau",)).fetchone()
    invig_user_id = invig_user[0] if invig_user else None

    # --- Invigilators ----------------------------------------------------
    cursor.execute("""
        INSERT OR IGNORE INTO invigilators
            (user_id, employee_number, first_name, last_name, phone, status)
        VALUES (?, 'EMP-001', 'James', 'Kamau', '0712345678', 'active')
    """, (invig_user_id,))

    cursor.execute("""
        INSERT OR IGNORE INTO invigilators
            (employee_number, first_name, last_name, phone, status)
        VALUES ('EMP-002', 'Faith', 'Wanjiru', '0723456789', 'active')
    """)

    # --- Students --------------------------------------------------------
    students = [
        ("CS/001/23", "Brian", "Otieno", "Computer Science", 2),
        ("CS/002/23", "Grace", "Njeri", "Computer Science", 2),
        ("BIT/014/22", "Kevin", "Mwangi", "Information Technology", 3),
        ("CS/045/24", "Aisha", "Hassan", "Computer Science", 1),
        ("BBIT/009/22", "Dennis", "Kiplagat", "Business IT", 3),
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO students
            (student_number, first_name, last_name, course, year_of_study)
        VALUES (?, ?, ?, ?, ?)
    """, students)

    # --- Examinations ------------------------------------------------------
    now = datetime.now()
    today = now.date()
    ongoing_start = max(now - timedelta(minutes=30), datetime.combine(today, datetime.min.time())).strftime("%H:%M")
    ongoing_end = min(now + timedelta(minutes=90), datetime.combine(today, datetime.max.time())).strftime("%H:%M")
    exams = [
        ("CS201", "Data Structures & Algorithms", (today + timedelta(days=3)).isoformat(), "09:00", "11:00", "Hall A", 1, "scheduled"),
        ("CS305", "Database Systems", (today + timedelta(days=7)).isoformat(), "09:00", "11:00", "Hall B", 2, "scheduled"),
        ("CS210", "Operating Systems", today.isoformat(), ongoing_start, ongoing_end, "Hall A", 1, "ongoing"),
        ("BIT150", "Web Programming", (today - timedelta(days=7)).isoformat(), "09:00", "11:00", "Hall C", 2, "completed"),
    ]
    for exam in exams:
        exists = cursor.execute("SELECT id FROM examinations WHERE course_code = ? AND examination_name = ? ORDER BY id LIMIT 1", (exam[0], exam[1])).fetchone()
        if not exists:
            cursor.execute("""
                INSERT INTO examinations
                    (course_code, examination_name, examination_date, start_time, end_time, venue, invigilator_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, exam)
        else:
            # Keep known demonstration examinations coherent as presentation dates move.
            cursor.execute("""UPDATE examinations SET examination_date = ?, start_time = ?, end_time = ?,
                venue = ?, invigilator_id = ?, status = ?
                WHERE id = ?""",
                (exam[2], exam[3], exam[4], exam[5], exam[6], exam[7], exists[0]))

    # --- Incidents ---------------------------------------------------------
    cursor.execute("SELECT id FROM students WHERE student_number = 'CS/001/23'")
    s1 = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM students WHERE student_number = 'BIT/014/22'")
    s2 = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM examinations WHERE course_code = 'BIT150'")
    e1 = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM examinations WHERE course_code = 'CS210'")
    e2 = cursor.fetchone()[0]

    incidents = [
        (s1, e1, "Unauthorized material", "Demonstration record only: example notes found in an examination hall.", "high", "open"),
        (s2, e1, "Phone use", "Demonstration record only: example phone use during an examination.", "medium", "resolved"),
        (s1, e2, "Talking", "Demonstration record only: example communication between candidates.", "low", "open"),
    ]
    for incident in incidents:
        exists = cursor.execute("""SELECT 1 FROM incidents
            WHERE student_id = ? AND examination_id = ? AND incident_type = ?""", incident[:3]).fetchone()
        if not exists:
            cursor.execute("""
                INSERT INTO incidents
                    (student_id, examination_id, incident_type, description, severity, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, incident)

    # Clearly synthetic records make the three rule outcomes demonstrable
    # without attaching example allegations to existing student records.
    demo_students = [
        ("DEMO-WATCH", "Demonstration", "Watch", "DEMO", 1),
        ("DEMO-HIGH", "Demonstration", "High", "DEMO", 1),
        ("DEMO-CRITICAL", "Demonstration", "Critical", "DEMO", 1),
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO students (student_number, first_name, last_name, course, year_of_study)
        VALUES (?, ?, ?, ?, ?)
    """, demo_students)
    demo_date = (today + timedelta(days=10)).isoformat()
    demo_exam = cursor.execute("""SELECT id FROM examinations
        WHERE course_code = 'DEMO' AND examination_name = 'Demonstration Examination'""").fetchone()
    if demo_exam is None:
        cursor.execute("""INSERT INTO examinations
            (course_code, examination_name, examination_date, start_time, end_time, venue, invigilator_id, status)
            VALUES ('DEMO', 'Demonstration Examination', ?, '09:00', '11:00', 'Demonstration Hall', 1, 'scheduled')""", (demo_date,))
        demo_exam_id = cursor.lastrowid
    else:
        demo_exam_id = demo_exam[0]
        cursor.execute("UPDATE examinations SET examination_date = ?, status = 'scheduled', invigilator_id = 1 WHERE id = ?",
                       (demo_date, demo_exam_id))
    demo_incidents = [
        ("DEMO-WATCH", "Demonstration observation", "Synthetic demonstration record only; not a real student incident.", "low"),
        ("DEMO-HIGH", "Demonstration observation one", "Synthetic demonstration record only; not a real student incident.", "medium"),
        ("DEMO-HIGH", "Demonstration observation two", "Synthetic demonstration record only; not a real student incident.", "low"),
        ("DEMO-CRITICAL", "Demonstration high-severity observation", "Synthetic demonstration record only; not a real student incident.", "high"),
    ]
    for number, incident_type, description, severity in demo_incidents:
        student_id = cursor.execute("SELECT id FROM students WHERE student_number = ?", (number,)).fetchone()[0]
        exists = cursor.execute("SELECT 1 FROM incidents WHERE student_id = ? AND examination_id = ? AND incident_type = ?", (student_id, demo_exam_id, incident_type)).fetchone()
        if not exists:
            cursor.execute("""INSERT INTO incidents (student_id, examination_id, incident_type, description, severity)
                VALUES (?, ?, ?, ?, ?)""", (student_id, demo_exam_id, incident_type, description, severity))

    device_demo_student_id = cursor.execute(
        "SELECT id FROM students WHERE student_number = ?", ("DEMO-HIGH",)
    ).fetchone()[0]
    seed_connected_device_incidents(cursor, device_demo_student_id, demo_exam_id)


def seed_connected_device_incidents(cursor, student_id, examination_id):
    """Insert the two idempotent, synthetic connected-device demo incidents."""
    device_demo_incidents = [
        (
            "Smartphone / Mobile Phone",
            "Synthetic demonstration record only: example observation involving a smartphone/mobile phone. Not a real student incident.",
            "low",
        ),
        (
            "Smartwatch / Wearable Device",
            "Synthetic demonstration record only: example observation involving a smartwatch/wearable device. Not a real student incident.",
            "medium",
        ),
    ]
    for incident_type, description, severity in device_demo_incidents:
        exists = cursor.execute("""SELECT 1 FROM incidents
            WHERE student_id = ? AND examination_id = ? AND incident_type = ?""",
            (student_id, examination_id, incident_type)).fetchone()
        if not exists:
            cursor.execute("""INSERT INTO incidents
                (student_id, examination_id, incident_type, description, severity, status)
                VALUES (?, ?, ?, ?, ?, 'open')""",
                (student_id, examination_id, incident_type, description, severity))


def build_database():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    create_tables(cursor)
    seed_data(cursor)

    connection.commit()
    connection.close()
    print(f"Database ready at: {DB_PATH}")


if __name__ == "__main__":
    build_database()
