import os
import sqlite3
import tempfile
import unittest
import threading
from unittest.mock import patch

from modules import institutional_registry, operations, integrity
from app import app as flask_app


class AcademicOperationsSchemaTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        connection = sqlite3.connect(self.path)
        connection.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT);
            CREATE TABLE students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_number TEXT UNIQUE NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                course TEXT,
                year_of_study INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE invigilators (id INTEGER PRIMARY KEY, user_id INTEGER, status TEXT DEFAULT 'active');
            CREATE TABLE incidents (id INTEGER PRIMARY KEY, status TEXT, student_id INTEGER, examination_id INTEGER, incident_type TEXT, description TEXT, severity TEXT, reported_at TEXT);
            CREATE TABLE examinations (id INTEGER PRIMARY KEY, course_code TEXT, examination_name TEXT, invigilator_id INTEGER);
        """)
        connection.close()
        self.registry_patch = patch.object(institutional_registry, "DATABASE", self.path)
        self.operations_patch = patch.object(operations, "DATABASE", self.path)
        self.integrity_patch = patch.object(integrity, "DATABASE", self.path)
        self.registry_patch.start()
        self.operations_patch.start()
        self.integrity_patch.start()
        institutional_registry.ensure_schema()
        operations.ensure_schema()

    def tearDown(self):
        self.registry_patch.stop()
        self.operations_patch.stop()
        self.integrity_patch.stop()
        operations.SCHEMA_READY = False
        integrity.SCHEMA_READY = False
        os.unlink(self.path)

    def test_venue_layout_builds_sequential_and_accessible_seats(self):
        seats = operations.build_venue_seats(2,3,{"A-01","B-03"})
        self.assertEqual(len(seats),6)
        self.assertEqual(seats[0],("A-01","A",1,1))
        self.assertEqual(seats[-1],("B-03","B",3,1))

    def test_venue_layout_rejects_unknown_accessible_seat(self):
        with self.assertRaises(ValueError):
            operations.build_venue_seats(2,3,{"C-01"})

    def test_venue_layout_rejects_more_than_26_rows(self):
        with self.assertRaises(ValueError):
            operations.build_venue_seats(27,3,set())

    def test_session_activation_requires_venue_capacity_and_two_invigilators(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("INSERT INTO users(id) VALUES(1)")
        connection.execute("INSERT INTO examinations(id,course_code,examination_name) VALUES(1,'CSC201','Data Structures')")
        connection.execute("INSERT INTO venues(id,venue_code,room_name,capacity) VALUES(1,'HALL-A','Hall A',2)")
        connection.execute("""
            INSERT INTO examination_sessions
                (id,session_code,examination_id,academic_year,semester,venue_id,session_date,start_time,end_time)
            VALUES(1,'CSC201-S1-A',1,'2026/2027','Semester 1',1,'2026-11-20','09:00','11:00')
        """)
        connection.commit()
        blockers = operations.session_activation_blockers(connection,1)
        self.assertTrue(any("two active invigilators" in item for item in blockers))
        connection.execute("INSERT INTO invigilators(id,user_id,status) VALUES(1,1,'active'),(2,2,'active')")
        connection.execute("INSERT INTO session_invigilators(session_id,invigilator_id) VALUES(1,1),(1,2)")
        connection.commit()
        self.assertEqual(operations.session_activation_blockers(connection,1),[])
        connection.close()

    def test_admin_can_export_session_attendance_csv(self):
        connection = sqlite3.connect(self.path)
        connection.execute("INSERT INTO users(id) VALUES(1)")
        connection.execute("INSERT INTO students(student_number,first_name,last_name) VALUES('REG/001','Amina','Otieno')")
        connection.execute("INSERT INTO examinations(id,course_code,examination_name) VALUES(1,'CSC201','Data Structures')")
        connection.execute("""
            INSERT INTO examination_sessions
            (id,session_code,examination_id,academic_year,semester,session_date,start_time,end_time)
            VALUES(1,'CSC201-S1-A',1,'2026/2027','Semester 1','2026-11-20','09:00','11:00')
        """)
        connection.execute("INSERT INTO session_candidates(session_id,student_id,eligibility_status,eligibility_note,seat_label) VALUES(1,1,'eligible','Approved test policy evaluation','SEAT-001')")
        connection.commit()
        connection.close()
        flask_app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        client = flask_app.test_client()
        with client.session_transaction() as browser_session:
            browser_session["user_id"] = 1
            browser_session["role"] = "admin"
        response = client.get("/operations/sessions/1/attendance.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers.get("Content-Type", ""))
        self.assertIn(b"REG/001", response.data)
        self.assertIn(b"not_recorded", response.data)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store, private")

    def test_registrar_cannot_view_or_record_exam_attendance(self):
        previous_csrf = flask_app.config.get("WTF_CSRF_ENABLED", True)
        try:
            flask_app.config.update(TESTING=True, SECRET_KEY="test-only-secret", WTF_CSRF_ENABLED=False)
            client = flask_app.test_client()
            with client.session_transaction() as browser_session:
                browser_session["user_id"] = 1
                browser_session["role"] = "registrar"
            view = client.get("/operations/sessions/999/attendance")
            record = client.post("/operations/sessions/999/attendance/999", data={
                "event_type":"check_in","verification_method":"manual"
            })
            self.assertEqual(view.status_code,403)
            self.assertEqual(record.status_code,403)
        finally:
            flask_app.config["WTF_CSRF_ENABLED"] = previous_csrf

    def test_registrar_cannot_report_incidents_from_exam_session_workspace(self):
        previous_csrf = flask_app.config.get("WTF_CSRF_ENABLED", True)
        try:
            flask_app.config.update(TESTING=True, SECRET_KEY="test-only-secret", WTF_CSRF_ENABLED=False)
            client = flask_app.test_client()
            with client.session_transaction() as browser_session:
                browser_session["user_id"] = 1
                browser_session["role"] = "registrar"
            response = client.post(
                "/operations/sessions/1/candidates/1/incidents",
                data={
                    "incident_type": "Unauthorized registrar report",
                    "description": "This request must be denied before it can create an incident.",
                    "severity": "low",
                },
            )
            self.assertEqual(response.status_code, 403)
        finally:
            flask_app.config["WTF_CSRF_ENABLED"] = previous_csrf

    def test_invigilator_cannot_export_attendance_csv(self):
        flask_app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        client = flask_app.test_client()
        with client.session_transaction() as browser_session:
            browser_session["user_id"] = 1
            browser_session["role"] = "invigilator"
        response = client.get("/operations/sessions/1/attendance.csv")
        self.assertEqual(response.status_code, 403)

    def test_invigilator_workspace_only_discloses_assigned_candidates_and_sessions(self):
        connection = sqlite3.connect(self.path)
        connection.execute("ALTER TABLE examinations ADD COLUMN examination_date TEXT")
        connection.execute("INSERT INTO users(id) VALUES(1)")
        connection.execute("""
            INSERT INTO students(id,student_number,first_name,last_name,course)
            VALUES(1,'KSU/ASSIGNED/001','Assigned','Student','Computer Science'),
                  (2,'KSU/OTHER/002','Other','Student','Mathematics')
        """)
        connection.execute("INSERT INTO invigilators(id,user_id,status) VALUES(1,1,'active')")
        connection.execute("""
            INSERT INTO examinations(id,course_code,examination_name,invigilator_id,examination_date)
            VALUES(1,'CSC101','Assigned Examination',1,'2026-11-20'),
                  (2,'MAT101','Other Examination',NULL,'2026-11-21')
        """)
        connection.execute("""
            INSERT INTO examination_sessions
            (id,session_code,examination_id,academic_year,semester,session_date,start_time,end_time)
            VALUES(1,'ASSIGNED-SESSION',1,'2026/2027','Semester 1','2026-11-20','09:00','11:00'),
                  (2,'UNASSIGNED-SESSION',2,'2026/2027','Semester 1','2026-11-21','09:00','11:00')
        """)
        connection.execute("INSERT INTO session_invigilators(session_id,invigilator_id) VALUES(1,1)")
        connection.execute("""
            INSERT INTO session_candidates(session_id,student_id,eligibility_status)
            VALUES(1,1,'eligible'),(2,2,'eligible')
        """)
        connection.commit()
        connection.close()
        operations.SCHEMA_READY = False
        flask_app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        client = flask_app.test_client()
        with client.session_transaction() as browser_session:
            browser_session["user_id"] = 1
            browser_session["role"] = "invigilator"
        with patch("modules.operations.render_template", return_value="workspace") as rendered:
            response = client.get("/operations/")
        self.assertEqual(response.status_code, 200)
        context = rendered.call_args.kwargs
        self.assertEqual([row["session_code"] for row in context["sessions"]], ["ASSIGNED-SESSION"])
        self.assertEqual([row["student_number"] for row in context["students"]], ["KSU/ASSIGNED/001"])
        self.assertEqual([row["examination_name"] for row in context["exams"]], ["Assigned Examination"])

    def test_invigilator_cannot_record_attendance_for_an_unassigned_session(self):
        connection = sqlite3.connect(self.path)
        connection.execute("INSERT INTO users(id) VALUES(1)")
        connection.executemany("""
            INSERT INTO students(id,student_number,first_name,last_name)
            VALUES(?,?,?,?)
        """, [
            (1, "KSU/ASSIGNED/001", "Assigned", "Candidate"),
            (2, "KSU/OTHER/002", "Other", "Candidate"),
        ])
        connection.execute("INSERT INTO invigilators(id,user_id,status) VALUES(1,1,'active')")
        connection.executemany("""
            INSERT INTO examinations(id,course_code,examination_name)
            VALUES(?,?,?)
        """, [(1, "CSC101", "Assigned exam"), (2, "MAT101", "Unassigned exam")])
        connection.executemany("""
            INSERT INTO examination_sessions
            (id,session_code,examination_id,academic_year,semester,session_date,start_time,end_time,status)
            VALUES(?,?,?,'2026/2027','Semester 1','2026-11-20','09:00','11:00','active')
        """, [(1, "ASSIGNED-SESSION", 1), (2, "OTHER-SESSION", 2)])
        connection.execute("INSERT INTO session_invigilators(session_id,invigilator_id) VALUES(1,1)")
        connection.executemany("""
            INSERT INTO session_candidates(session_id,student_id,eligibility_status)
            VALUES(?,?,'eligible')
        """, [(1,1),(2,2)])
        connection.commit()
        connection.close()

        previous_csrf = flask_app.config.get("WTF_CSRF_ENABLED", True)
        try:
            flask_app.config.update(TESTING=True, SECRET_KEY="test-only-secret", WTF_CSRF_ENABLED=False)
            client = flask_app.test_client()
            with client.session_transaction() as browser_session:
                browser_session["user_id"] = 1
                browser_session["role"] = "invigilator"
            response = client.post(
                "/operations/sessions/2/attendance/2",
                data={"event_type": "check_in", "verification_method": "manual"},
            )
            self.assertEqual(response.status_code, 302)
            connection = sqlite3.connect(self.path)
            attendance_count = connection.execute(
                "SELECT COUNT(*) FROM session_attendance WHERE session_id=2 AND student_id=2"
            ).fetchone()[0]
            event_count = connection.execute(
                "SELECT COUNT(*) FROM attendance_events WHERE session_id=2 AND student_id=2"
            ).fetchone()[0]
            connection.close()
            self.assertEqual(attendance_count, 0)
            self.assertEqual(event_count, 0)
        finally:
            flask_app.config["WTF_CSRF_ENABLED"] = previous_csrf

    def test_reconciliation_flags_missing_checkin_for_review_not_absence(self):
        connection = sqlite3.connect(self.path)
        connection.execute("INSERT INTO users(id) VALUES(1)")
        connection.execute("INSERT INTO students(student_number,first_name,last_name) VALUES('REG/002','Brian','Kiptoo')")
        connection.execute("INSERT INTO examinations(id,course_code,examination_name) VALUES(1,'MAT101','Calculus')")
        connection.execute("""
            INSERT INTO examination_sessions
            (id,session_code,examination_id,academic_year,semester,session_date,start_time,end_time,status)
            VALUES(1,'MAT101-S1-A',1,'2026/2027','Semester 1','2020-01-01','09:00','11:00','completed')
        """)
        connection.execute("INSERT INTO session_candidates(session_id,student_id,eligibility_status,eligibility_note,seat_label) VALUES(1,1,'eligible','Approved test policy evaluation','SEAT-001')")
        connection.commit()
        connection.close()
        flask_app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        client = flask_app.test_client()
        with client.session_transaction() as browser_session:
            browser_session["user_id"] = 1
            browser_session["role"] = "admin"
        page = client.get("/operations/sessions/1/attendance")
        import re
        token = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
        response = client.post("/operations/sessions/1/reconcile-attendance", data={"csrf_token": token})
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        result = connection.execute("SELECT status, verification_status FROM session_attendance WHERE session_id=1 AND student_id=1").fetchone()
        connection.close()
        self.assertEqual(result, ("disputed", "manual_review"))

    def test_operational_tables_are_created(self):
        connection = sqlite3.connect(self.path)
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        connection.close()
        self.assertTrue({
            "venues", "examination_sessions", "session_invigilators",
            "session_candidates", "attendance_events", "session_attendance",
            "academic_units", "student_unit_enrolments", "audit_events"
        }.issubset(tables))

    def test_legacy_candidate_without_policy_evaluation_is_reset_to_pending(self):
        connection = sqlite3.connect(self.path)
        connection.execute("INSERT INTO students(student_number,first_name,last_name) VALUES('LEGACY/1','Legacy','Candidate')")
        connection.execute("INSERT INTO examinations(id,course_code,examination_name) VALUES(1,'LEG','Legacy Exam')")
        connection.execute("""
            INSERT INTO examination_sessions
                (id,session_code,examination_id,academic_year,semester,session_date,start_time,end_time)
            VALUES(1,'LEG-SESSION',1,'2026/2027','Semester 1','2026-11-20','09:00','11:00')
        """)
        connection.execute("""
            INSERT INTO session_candidates(session_id,student_id,eligibility_status,eligibility_note)
            VALUES(1,1,'eligible',NULL)
        """)
        connection.commit()
        connection.close()
        operations.ensure_schema()
        connection = sqlite3.connect(self.path)
        status = connection.execute("""
            SELECT eligibility_status,eligibility_note FROM session_candidates
            WHERE session_id=1 AND student_id=1
        """).fetchone()
        connection.close()
        self.assertEqual(status[0], "pending")
        self.assertIn("approved institutional eligibility policy", status[1])

    def test_duplicate_candidate_is_rejected(self):
        connection = sqlite3.connect(self.path)
        connection.execute("INSERT INTO students(student_number,first_name,last_name) VALUES('A/1','A','One')")
        connection.execute("INSERT INTO examinations DEFAULT VALUES")
        connection.execute("INSERT INTO examination_sessions(session_code,examination_id,academic_year,semester,session_date,start_time,end_time) VALUES('S-1',1,'2026/27','S1','2026-11-20','09:00','11:00')")
        connection.execute("INSERT INTO session_candidates(session_id,student_id) VALUES(1,1)")
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO session_candidates(session_id,student_id) VALUES(1,1)")
        connection.close()

    def test_duplicate_attendance_per_session_student_is_rejected(self):
        connection = sqlite3.connect(self.path)
        connection.execute("INSERT INTO students(student_number,first_name,last_name) VALUES('A/1','A','One')")
        connection.execute("INSERT INTO examinations DEFAULT VALUES")
        connection.execute("INSERT INTO examination_sessions(session_code,examination_id,academic_year,semester,session_date,start_time,end_time) VALUES('S-1',1,'2026/27','S1','2026-11-20','09:00','11:00')")
        connection.execute("INSERT INTO session_attendance(session_id,student_id) VALUES(1,1)")
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO session_attendance(session_id,student_id) VALUES(1,1)")
        connection.close()


    def _seed_schedule_fixture(self, conflicting=False, candidate_conflicting=False):
        connection = sqlite3.connect(self.path)
        connection.execute("INSERT INTO users(id) VALUES(1),(2)")
        connection.execute("""
            INSERT INTO students(id,student_number,first_name,last_name)
            VALUES(1,'TEST/001','Test','Candidate One'),
                  (2,'TEST/002','Test','Candidate Two')
        """)
        connection.execute("""
            INSERT INTO examinations(id,course_code,examination_name)
            VALUES(1,'CSC201','Data Structures'),
                  (2,'MAT201','Calculus')
        """)
        connection.execute("""
            INSERT INTO venues(id,venue_code,room_name,capacity,active)
            VALUES(1,'HALL-A','Hall A',100,1),
                  (2,'HALL-B','Hall B',100,1)
        """)
        connection.execute("""
            INSERT INTO invigilators(id,user_id,employee_number,first_name,last_name,status)
            VALUES(1,1,'EMP-001','Alex','One','active'),
                  (2,2,'EMP-002','Taylor','Two','active')
        """)
        second_date = '2026-11-22' if (conflicting or candidate_conflicting) else '2026-11-21'
        second_start = '10:00' if (conflicting or candidate_conflicting) else '09:00'
        second_end = '12:00' if (conflicting or candidate_conflicting) else '11:00'
        connection.execute("""
            INSERT INTO examination_sessions
            (id,session_code,examination_id,academic_year,semester,venue_id,
             session_date,start_time,end_time,status)
            VALUES
            (1,'SESSION-A',1,'2026/2027','Semester 1',1,'2026-11-20','09:00','11:00','scheduled'),
            (2,'SESSION-B',2,'2026/2027','Semester 1',2,?,?,?,'scheduled')
        """, (second_date, second_start, second_end))
        connection.execute("""
            INSERT INTO session_candidates(session_id,student_id,eligibility_status)
            VALUES(1,1,'pending'),(2,2,'pending')
        """)
        if candidate_conflicting:
            connection.execute("INSERT INTO session_candidates(session_id,student_id,eligibility_status) VALUES(2,1,'pending')")
        connection.execute("INSERT INTO session_invigilators(session_id,invigilator_id) VALUES(1,1)")
        if conflicting:
            connection.execute("INSERT INTO session_invigilators(session_id,invigilator_id) VALUES(2,1)")
        else:
            connection.execute("INSERT INTO session_invigilators(session_id,invigilator_id) VALUES(2,2)")
        connection.commit()
        connection.close()
        operations.SCHEMA_READY = False
        integrity.SCHEMA_READY = False
        flask_app.config.update(
            TESTING=True,
            SECRET_KEY="scheduling-test-secret",
            WTF_CSRF_ENABLED=False,
        )
        client = flask_app.test_client()
        with client.session_transaction() as browser_session:
            browser_session["user_id"] = 1
            browser_session["role"] = "admin"
        return client

    def test_scheduling_write_lock_serializes_competing_sqlite_writers(self):
        first = operations.db()
        operations._begin_scheduling_write(first)
        attempted = threading.Event()
        acquired = threading.Event()
        errors = []

        def competing_writer():
            second = operations.db()
            try:
                attempted.set()
                operations._begin_scheduling_write(second)
                acquired.set()
                second.rollback()
            except Exception as error:
                errors.append(error)
            finally:
                second.close()

        worker = threading.Thread(target=competing_writer)
        worker.start()
        self.assertTrue(attempted.wait(1))
        self.assertFalse(acquired.wait(0.15), "second scheduler must wait for the active reservation transaction")
        first.commit()
        self.assertTrue(acquired.wait(2), "second scheduler should acquire the lock after the first commits")
        worker.join(2)
        first.close()
        self.assertFalse(errors)

    def test_reschedule_records_old_and_new_schedule_and_audit_reason(self):
        client = self._seed_schedule_fixture()
        response = client.post("/operations/sessions/1/reschedule", data={
            "session_date": "2026-11-22",
            "start_time": "12:00",
            "end_time": "14:00",
            "venue_id": "2",
            "reason": "Venue maintenance required a timetable adjustment.",
        })
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        current = connection.execute("""
            SELECT session_date,start_time,end_time,venue_id
            FROM examination_sessions WHERE id=1
        """).fetchone()
        history = connection.execute("""
            SELECT action,old_session_date,old_start_time,old_end_time,old_venue_id,
                   new_session_date,new_start_time,new_end_time,new_venue_id,reason,actor_user_id
            FROM examination_session_schedule_history WHERE session_id=1
        """).fetchone()
        audit = connection.execute("""
            SELECT action,entity_type,entity_id,summary FROM audit_events
            WHERE entity_type='examination_session' AND entity_id='1' AND action='reschedule'
        """).fetchone()
        connection.close()
        self.assertEqual(current, ("2026-11-22","12:00","14:00",2))
        self.assertEqual(history[:10], (
            "rescheduled","2026-11-20","09:00","11:00",1,
            "2026-11-22","12:00","14:00",2,
            "Venue maintenance required a timetable adjustment."
        ))
        self.assertEqual(history[10], 1)
        self.assertIsNotNone(audit)
        self.assertIn("Venue maintenance required", audit[3])
        page = client.get("/operations/sessions/1/history")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Venue maintenance required", page.data)

    def test_reschedule_rejects_venue_and_invigilator_conflicts_without_mutation(self):
        client = self._seed_schedule_fixture(conflicting=True)
        response = client.post("/operations/sessions/1/reschedule", data={
            "session_date": "2026-11-22",
            "start_time": "11:00",
            "end_time": "13:00",
            "venue_id": "2",
            "reason": "Move this session after a timetable review.",
        })
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        current = connection.execute(
            "SELECT session_date,start_time,end_time,venue_id FROM examination_sessions WHERE id=1"
        ).fetchone()
        history_count = connection.execute(
            "SELECT COUNT(*) FROM examination_session_schedule_history WHERE session_id=1"
        ).fetchone()[0]
        connection.close()
        self.assertEqual(current, ("2026-11-20","09:00","11:00",1))
        self.assertEqual(history_count, 0)

    def test_reschedule_requires_reason_and_future_date(self):
        client = self._seed_schedule_fixture()
        response = client.post("/operations/sessions/1/reschedule", data={
            "session_date": "2026-11-12",
            "start_time": "12:00",
            "end_time": "14:00",
            "venue_id": "2",
            "reason": "Too short",
        })
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        current = connection.execute(
            "SELECT session_date,start_time,end_time,venue_id FROM examination_sessions WHERE id=1"
        ).fetchone()
        count = connection.execute(
            "SELECT COUNT(*) FROM examination_session_schedule_history"
        ).fetchone()[0]
        connection.close()
        self.assertEqual(current, ("2026-11-20","09:00","11:00",1))
        self.assertEqual(count, 0)

    def test_completed_session_cannot_be_rescheduled(self):
        client = self._seed_schedule_fixture()
        connection = sqlite3.connect(self.path)
        connection.execute("UPDATE examination_sessions SET status='completed' WHERE id=1")
        connection.commit()
        connection.close()
        response = client.post("/operations/sessions/1/reschedule", data={
            "session_date": "2026-11-22",
            "start_time": "12:00",
            "end_time": "14:00",
            "venue_id": "2",
            "reason": "A completed session must remain immutable.",
        })
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        current = connection.execute(
            "SELECT status,session_date,start_time,end_time FROM examination_sessions WHERE id=1"
        ).fetchone()
        connection.close()
        self.assertEqual(current, ("completed","2026-11-20","09:00","11:00"))

    def test_cancellation_requires_reason_and_preserves_schedule_history(self):
        client = self._seed_schedule_fixture()
        short = client.post("/operations/sessions/1/status", data={
            "status": "cancelled", "reason": "No reason"
        })
        self.assertEqual(short.status_code, 302)
        connection = sqlite3.connect(self.path)
        self.assertEqual(connection.execute(
            "SELECT status FROM examination_sessions WHERE id=1"
        ).fetchone()[0], "scheduled")
        connection.close()

        response = client.post("/operations/sessions/1/status", data={
            "status": "cancelled",
            "reason": "Institutional timetable change approved by the examination office.",
        })
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        status = connection.execute(
            "SELECT status FROM examination_sessions WHERE id=1"
        ).fetchone()[0]
        history = connection.execute("""
            SELECT action,old_session_date,new_session_date,reason,actor_user_id
            FROM examination_session_schedule_history WHERE session_id=1
        """).fetchone()
        connection.close()
        self.assertEqual(status, "cancelled")
        self.assertEqual(history[0], "cancelled")
        self.assertEqual(history[1], history[2])
        self.assertIn("Institutional timetable change", history[3])
        self.assertEqual(history[4], 1)

    def test_schedule_history_is_append_only(self):
        client = self._seed_schedule_fixture()
        response = client.post("/operations/sessions/1/reschedule", data={
            "session_date": "2026-11-22",
            "start_time": "12:00",
            "end_time": "14:00",
            "venue_id": "2",
            "reason": "Venue maintenance required a timetable adjustment.",
        })
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE examination_session_schedule_history SET reason='rewritten' WHERE session_id=1"
            )
        connection.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM examination_session_schedule_history WHERE session_id=1"
            )
        connection.rollback()
        connection.close()


    def test_reschedule_rejects_candidate_overlap(self):
        client = self._seed_schedule_fixture(candidate_conflicting=True)
        response = client.post("/operations/sessions/1/reschedule", data={
            "session_date": "2026-11-22",
            "start_time": "10:00",
            "end_time": "12:00",
            "venue_id": "",
            "reason": "Candidate timetable conflict requires another sitting.",
        })
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        current = connection.execute(
            "SELECT session_date,start_time,end_time,venue_id FROM examination_sessions WHERE id=1"
        ).fetchone()
        history_count = connection.execute(
            "SELECT COUNT(*) FROM examination_session_schedule_history WHERE session_id=1"
        ).fetchone()[0]
        connection.close()
        self.assertEqual(current, ("2026-11-20","09:00","11:00",1))
        self.assertEqual(history_count, 0)

    def test_reschedule_is_blocked_after_attendance_is_recorded(self):
        client = self._seed_schedule_fixture()
        connection = sqlite3.connect(self.path)
        connection.execute("""
            INSERT INTO attendance_events
                (session_id,student_id,event_type,verification_method,verification_status,recorded_by)
            VALUES(1,1,'check_in','manual','verified',1)
        """)
        connection.commit()
        connection.close()
        response = client.post("/operations/sessions/1/reschedule", data={
            "session_date": "2026-11-22",
            "start_time": "12:00",
            "end_time": "14:00",
            "venue_id": "2",
            "reason": "An attendance record must not be detached from its sitting.",
        })
        self.assertEqual(response.status_code, 302)
        connection = sqlite3.connect(self.path)
        current = connection.execute(
            "SELECT session_date,start_time,end_time,venue_id FROM examination_sessions WHERE id=1"
        ).fetchone()
        history_count = connection.execute(
            "SELECT COUNT(*) FROM examination_session_schedule_history WHERE session_id=1"
        ).fetchone()[0]
        connection.close()
        self.assertEqual(current, ("2026-11-20","09:00","11:00",1))
        self.assertEqual(history_count, 0)


if __name__ == "__main__":
    unittest.main()
