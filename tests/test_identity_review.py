import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import app as flask_app
from modules import identity_check, institutional_registry, operations


class SessionIdentityReviewTests(unittest.TestCase):
    def setUp(self):
        handle,self.path=tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        connection=sqlite3.connect(self.path)
        connection.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT);
            CREATE TABLE students(
                id INTEGER PRIMARY KEY,student_number TEXT UNIQUE NOT NULL,
                first_name TEXT NOT NULL,last_name TEXT NOT NULL,course TEXT,
                year_of_study INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE invigilators(
                id INTEGER PRIMARY KEY,user_id INTEGER,employee_number TEXT,
                first_name TEXT,last_name TEXT,phone TEXT,status TEXT DEFAULT 'active'
            );
            CREATE TABLE examinations(
                id INTEGER PRIMARY KEY,course_code TEXT,examination_name TEXT,
                invigilator_id INTEGER
            );
        """)
        connection.executemany("INSERT INTO users(id,username) VALUES(?,?)",[(1,"admin"),(2,"invigilator")])
        connection.executemany("""
            INSERT INTO students(id,student_number,first_name,last_name)
            VALUES(?,?,?,?)
        """,[(1,"KSU/001","Amina","Otieno"),(2,"KSU/002","Brian","Kamau")])
        connection.execute("INSERT INTO invigilators(id,user_id,employee_number,first_name,last_name) VALUES(1,2,'EMP-1','Test','Invigilator')")
        connection.execute("INSERT INTO examinations(id,course_code,examination_name,invigilator_id) VALUES(1,'CSC101','Computing',1)")
        connection.commit()
        connection.close()
        self.patches=[
            patch.object(identity_check,"DATABASE",self.path),
            patch.object(institutional_registry,"DATABASE",self.path),
            patch.object(operations,"DATABASE",self.path),
        ]
        for item in self.patches:item.start()
        institutional_registry.ensure_schema()
        operations.ensure_schema()
        connection=sqlite3.connect(self.path)
        connection.execute("""
            INSERT INTO examination_sessions
                (id,session_code,examination_id,academic_year,semester,session_date,start_time,end_time)
            VALUES(1,'CSC101-S1',1,'2026/2027','Semester 1','2026-11-20','09:00','11:00')
        """)
        connection.execute("INSERT INTO session_invigilators(session_id,invigilator_id) VALUES(1,1)")
        connection.executemany("""
            INSERT INTO session_candidates(session_id,student_id,eligibility_status,seat_label)
            VALUES(1,?,'eligible',?)
        """,[(1,"A-01")])
        connection.commit()
        connection.close()
        flask_app.config.update(TESTING=True,SECRET_KEY="identity-test-secret")
        self.client=flask_app.test_client()

    def tearDown(self):
        for item in self.patches:item.stop()
        operations.SCHEMA_READY=False
        institutional_registry._schema_ready=False
        os.unlink(self.path)

    def set_user(self,role,user_id):
        with self.client.session_transaction() as state:
            state.clear()
            state["role"]=role
            state["user_id"]=user_id

    def test_assigned_invigilator_can_open_identity_station(self):
        self.set_user("invigilator",2)
        response=self.client.get("/identity/sessions/1")
        self.assertEqual(response.status_code,200)
        self.assertIn(b"Camera preview",response.data)
        self.assertIn(b"KSU/001",response.data)
        self.assertNotIn(b"KSU/002",response.data)
        self.assertIn(b"does not capture, upload, compare, template or store",response.data)

    def test_unassigned_invigilator_cannot_open_session_identity_station(self):
        self.set_user("invigilator",99)
        response=self.client.get("/identity/sessions/1")
        self.assertEqual(response.status_code,403)

    def test_registrar_cannot_open_identity_station(self):
        self.set_user("registrar",3)
        response=self.client.get("/identity/sessions/1")
        self.assertEqual(response.status_code,403)


if __name__ == "__main__":
    unittest.main()
