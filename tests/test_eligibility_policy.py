import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from modules import eligibility


class EligibilityPolicyTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.patch = patch.object(eligibility, "DATABASE", self.path)
        self.patch.start()
        connection = sqlite3.connect(self.path)
        connection.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT);
            CREATE TABLE students(id INTEGER PRIMARY KEY, student_number TEXT);
            CREATE TABLE academic_units(id INTEGER PRIMARY KEY, unit_code TEXT, unit_name TEXT, active INTEGER);
            CREATE TABLE student_profiles(student_id INTEGER PRIMARY KEY, academic_status TEXT);
            CREATE TABLE student_unit_enrolments(
                id INTEGER PRIMARY KEY, student_id INTEGER, unit_id INTEGER,
                academic_year TEXT, semester TEXT, enrolment_status TEXT
            );
        """)
        connection.executemany("INSERT INTO users(id,username) VALUES(?,?)", [(1,"officer"),(2,"approver")])
        connection.execute("INSERT INTO students(id,student_number) VALUES(1,'S/001')")
        connection.execute("INSERT INTO academic_units(id,unit_code,unit_name,active) VALUES(1,'CSC101','Computing',1)")
        connection.execute("INSERT INTO student_profiles(student_id,academic_status) VALUES(1,'active')")
        connection.commit()
        connection.close()
        eligibility.ensure_schema()

    def tearDown(self):
        self.patch.stop()
        os.unlink(self.path)

    def connection(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def add_policy(self):
        from datetime import date
        connection = self.connection()
        cursor = connection.execute("""
            INSERT INTO eligibility_policies
                (policy_code,version,effective_from,rules_json,approval_status,created_by,approved_by)
            VALUES('KSU-EXAM-ELIGIBILITY',1,?,?, 'approved',1,2)
        """, (date.today().isoformat(), json.dumps({
            "require_active_student": True,
            "require_registered_unit": True,
        })))
        connection.commit()
        policy_id = cursor.lastrowid
        connection.close()
        return policy_id

    def test_no_approved_policy_returns_pending_not_clearance(self):
        connection = self.connection()
        _, result, reasons, policy = eligibility.evaluate(
            connection,1,1,"2026/2027","Semester 1",1)
        connection.commit()
        connection.close()
        self.assertEqual(result,"pending")
        self.assertIsNone(policy)
        self.assertIn("No currently effective",reasons[0])

    def test_approved_policy_requires_active_status_and_registered_unit(self):
        self.add_policy()
        connection = self.connection()
        _, result, reasons, _ = eligibility.evaluate(
            connection,1,1,"2026/2027","Semester 1",1)
        connection.close()
        self.assertEqual(result,"ineligible")
        self.assertIn("No registered enrolment",reasons[0])

    def test_approved_policy_marks_registered_active_student_eligible(self):
        self.add_policy()
        connection = self.connection()
        connection.execute("""
            INSERT INTO student_unit_enrolments
                (student_id,unit_id,academic_year,semester,enrolment_status)
            VALUES(1,1,'2026/2027','Semester 1','registered')
        """)
        _, result, reasons, policy = eligibility.evaluate(
            connection,1,1,"2026/2027","Semester 1",1)
        connection.close()
        self.assertEqual(result,"eligible")
        self.assertIsNotNone(policy)
        self.assertIn("All conditions",reasons[0])

    def test_suspended_student_is_not_eligible(self):
        self.add_policy()
        connection = self.connection()
        connection.execute("UPDATE student_profiles SET academic_status='suspended' WHERE student_id=1")
        connection.execute("""
            INSERT INTO student_unit_enrolments
                (student_id,unit_id,academic_year,semester,enrolment_status)
            VALUES(1,1,'2026/2027','Semester 1','registered')
        """)
        _, result, reasons, _ = eligibility.evaluate(
            connection,1,1,"2026/2027","Semester 1",1)
        connection.close()
        self.assertEqual(result,"ineligible")
        self.assertTrue(any("academic status" in reason for reason in reasons))


if __name__ == "__main__":
    unittest.main()
