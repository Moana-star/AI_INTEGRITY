import os
import sqlite3
import tempfile
import unittest

from modules.access_control import (
    effective_user_role, ensure_role_schema, legacy_role_for,
)


class InstitutionalRoleMigrationTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','invigilator'))
            )
        """)
        self.connection.executemany(
            "INSERT INTO users(username,password,role) VALUES(?,?,?)",
            [("root", "hash-a", "admin"), ("examiner", "hash-b", "invigilator")],
        )
        self.connection.commit()

    def tearDown(self):
        self.connection.close()
        os.unlink(self.path)

    def test_additive_migration_preserves_legacy_accounts_and_maps_roles(self):
        ensure_role_schema(self.connection)
        users = self.connection.execute(
            "SELECT * FROM users ORDER BY id"
        ).fetchall()
        self.assertEqual([effective_user_role(row) for row in users],
                         ["admin", "invigilator"])
        self.assertEqual([row["username"] for row in users],
                         ["root", "examiner"])

    def test_migration_is_idempotent(self):
        ensure_role_schema(self.connection)
        ensure_role_schema(self.connection)
        count = self.connection.execute(
            "SELECT COUNT(*) FROM institutional_staff_profiles"
        ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_new_institutional_roles_map_to_legacy_check_constraint(self):
        ensure_role_schema(self.connection)
        expected = {
            "admin": "admin",
            "registrar": "invigilator",
            "examination_officer": "invigilator",
            "invigilator": "invigilator",
        }
        for role, legacy in expected.items():
            self.assertEqual(legacy_role_for(role), legacy)

    def test_student_cannot_be_assigned_as_a_staff_account(self):
        with self.assertRaises(ValueError):
            legacy_role_for("student")

    def test_unknown_legacy_role_fails_closed_after_migration(self):
        ensure_role_schema(self.connection)
        self.connection.execute(
            "UPDATE users SET institutional_role='unexpected' WHERE username='root'"
        )
        self.connection.commit()
        row = self.connection.execute(
            "SELECT * FROM users WHERE username='root'"
        ).fetchone()
        self.assertIsNone(effective_user_role(row))


if __name__ == "__main__":
    unittest.main()
