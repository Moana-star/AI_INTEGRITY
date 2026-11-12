import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from modules import institutional_registry as registry


class InstitutionalRegistryTests(unittest.TestCase):
    def setUp(self):
        handle, self.database_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        with sqlite3.connect(self.database_path) as connection:
            connection.executescript("""
                CREATE TABLE users (id INTEGER PRIMARY KEY);
                CREATE TABLE students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_number TEXT UNIQUE NOT NULL,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    course TEXT,
                    year_of_study INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE invigilators (id INTEGER PRIMARY KEY);
                CREATE TABLE examinations (id INTEGER PRIMARY KEY);
            """)
        self.database_patch = patch.object(registry, "DATABASE", self.database_path)
        self.database_patch.start()
        registry.ensure_schema()

    def tearDown(self):
        self.database_patch.stop()
        os.unlink(self.database_path)

    def test_creates_profile_tables_without_replacing_existing_students(self):
        with registry.get_connection() as connection:
            connection.execute("""
                INSERT INTO students (student_number, first_name, last_name, course)
                VALUES ('REG/001', 'Amina', 'Otieno', 'Computer Science')
            """)
            connection.commit()
        registry.ensure_schema()
        with registry.get_connection() as connection:
            student = connection.execute(
                "SELECT student_number FROM students WHERE student_number='REG/001'"
            ).fetchone()
            tables = {row["name"] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        self.assertEqual(student["student_number"], "REG/001")
        self.assertIn("student_profiles", tables)
        self.assertIn("examination_attendance", tables)
        self.assertIn("audit_events", tables)

    def test_student_values_normalize_and_validate(self):
        values = registry._student_values({
            "admission_number": " REG/002 ",
            "first_name": "  Amina ",
            "last_name": " Otieno ",
            "course": " Computer Science ",
            "year_of_study": "2",
            "academic_status": "active",
            "institutional_email": "AMINA@UNIVERSITY.AC.KE",
        })
        self.assertEqual(values[0], "REG/002")
        self.assertEqual(values[1], "Amina")
        self.assertEqual(values[4], 2)
        self.assertEqual(values[7], "amina@university.ac.ke")

    def test_invalid_academic_status_is_rejected(self):
        with self.assertRaises(ValueError):
            registry._student_values({
                "admission_number": "REG/003",
                "first_name": "Amina",
                "last_name": "Otieno",
                "course": "Computer Science",
                "academic_status": "expelled-forever",
            })

    def test_student_and_profile_are_saved_together(self):
        values = registry._student_values({
            "admission_number": "REG/004",
            "first_name": "Brian",
            "last_name": "Kamau",
            "course": "Information Technology",
            "faculty": "School of Computing",
            "department": "Computing",
            "academic_status": "active",
        })
        with registry.get_connection() as connection:
            student_id = registry._save_student(connection, values)
            connection.commit()
            row = connection.execute("""
                SELECT s.student_number, p.faculty, p.department
                FROM students s JOIN student_profiles p ON p.student_id=s.id
                WHERE s.id=?
            """, (student_id,)).fetchone()
        self.assertEqual(row["student_number"], "REG/004")
        self.assertEqual(row["faculty"], "School of Computing")
        self.assertEqual(row["department"], "Computing")


if __name__ == "__main__":
    unittest.main()
