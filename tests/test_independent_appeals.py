import os
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import app as flask_app
from modules import appeals, integrity, institutional_registry, operations


class IndependentAppealTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        connection = sqlite3.connect(self.path)
        connection.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT);
            CREATE TABLE students(
                id INTEGER PRIMARY KEY, student_number TEXT UNIQUE NOT NULL,
                first_name TEXT NOT NULL,last_name TEXT NOT NULL,course TEXT,
                year_of_study INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE invigilators(id INTEGER PRIMARY KEY,user_id INTEGER);
            CREATE TABLE examinations(
                id INTEGER PRIMARY KEY,course_code TEXT,examination_name TEXT,
                invigilator_id INTEGER
            );
            CREATE TABLE incidents(
                id INTEGER PRIMARY KEY,student_id INTEGER,examination_id INTEGER,
                incident_type TEXT,description TEXT,severity TEXT,status TEXT,
                reported_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        connection.executemany("INSERT INTO users(id,username) VALUES(?,?)",
            [(1,"reporter"),(2,"original-reviewer"),(3,"independent-reviewer")])
        connection.execute("INSERT INTO students(id,student_number,first_name,last_name) VALUES(1,'KSU/001','Amina','Otieno')")
        connection.execute("INSERT INTO incidents(id,student_id,incident_type,severity,status) VALUES(1,1,'Exam incident','medium','resolved')")
        connection.commit()
        connection.close()
        self.patches = [
            patch.object(appeals,"DATABASE",self.path),
            patch.object(integrity,"DATABASE",self.path),
            patch.object(institutional_registry,"DATABASE",self.path),
            patch.object(operations,"DATABASE",self.path),
        ]
        for item in self.patches:
            item.start()
        integrity.SCHEMA_READY=False
        operations.SCHEMA_READY=False
        institutional_registry._schema_ready=False
        institutional_registry.ensure_schema()
        integrity.ensure_schema()
        appeals.ensure_schema()
        connection=sqlite3.connect(self.path)
        connection.execute("""
            UPDATE incident_case_workflow
            SET case_status='resolved',reported_by=1,updated_by=2
            WHERE incident_id=1
        """)
        connection.commit()
        connection.close()
        flask_app.config.update(TESTING=True,SECRET_KEY="appeal-test-secret")
        self.client=flask_app.test_client()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        integrity.SCHEMA_READY=False
        operations.SCHEMA_READY=False
        institutional_registry._schema_ready=False
        os.unlink(self.path)

    def csrf(self):
        response=self.client.get("/forgot-password")
        return re.search(rb'<meta name="csrf-token" content="([^"]+)"',response.data).group(1).decode()

    def submit(self):
        with self.client.session_transaction() as state:
            state.clear()
            state["role"]="student"
            state["student_id"]=1
        return self.client.post("/appeals/incidents/1",data={
            "appeal_text":"I am submitting this appeal because relevant context and supporting details were not considered in the original review.",
            "csrf_token":self.csrf(),
        })

    def test_student_can_submit_one_appeal_for_own_final_case(self):
        response=self.submit()
        self.assertEqual(response.status_code,302)
        connection=sqlite3.connect(self.path)
        appeal=connection.execute("SELECT appeal_status FROM incident_appeals WHERE incident_id=1").fetchone()
        event=connection.execute("SELECT actor_student_id,to_status FROM incident_appeal_events").fetchone()
        connection.close()
        self.assertEqual(appeal[0],"submitted")
        self.assertEqual(event,(1,"submitted"))

    def test_original_reporter_and_reviewer_cannot_decide_appeal(self):
        self.submit()
        for user_id in (1,2):
            with self.client.session_transaction() as state:
                state.clear()
                state["role"]="examination_officer"
                state["user_id"]=user_id
            response=self.client.post("/appeals/1/decision",data={
                "outcome":"decision_upheld",
                "decision_reason":"The independent appeal review has considered the submitted grounds and evidence.",
                "csrf_token":self.csrf(),
            })
            self.assertEqual(response.status_code,403)

    def test_independent_reviewer_can_decide_without_rewriting_original_case(self):
        self.submit()
        with self.client.session_transaction() as state:
            state.clear()
            state["role"]="examination_officer"
            state["user_id"]=3
        response=self.client.post("/appeals/1/decision",data={
            "outcome":"decision_overturned",
            "decision_reason":"The independent review found that material information was not considered in the original decision.",
            "csrf_token":self.csrf(),
        })
        self.assertEqual(response.status_code,302)
        connection=sqlite3.connect(self.path)
        outcome=connection.execute("SELECT appeal_status,reviewed_by FROM incident_appeals WHERE id=1").fetchone()
        original=connection.execute("SELECT case_status FROM incident_case_workflow WHERE incident_id=1").fetchone()[0]
        connection.close()
        self.assertEqual(outcome,("decision_overturned",3))
        self.assertEqual(original,"resolved")

    def test_student_cannot_appeal_another_students_case(self):
        with self.client.session_transaction() as state:
            state.clear()
            state["role"]="student"
            state["student_id"]=99
        response=self.client.post("/appeals/incidents/1",data={
            "appeal_text":"This appeal text is long enough to satisfy the minimum statement length for this test.",
            "csrf_token":self.csrf(),
        })
        self.assertEqual(response.status_code,403)


if __name__ == "__main__":
    unittest.main()
