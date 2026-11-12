import os
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash
import app as application
from modules.access_control import ensure_role_schema


class StaffAuthenticationTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        connection = sqlite3.connect(self.path)
        connection.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','invigilator'))
            );
            CREATE TABLE invigilators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                employee_number TEXT UNIQUE NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                phone TEXT,
                status TEXT DEFAULT 'active'
            );
        """)
        ensure_role_schema(connection)
        connection.execute(
            "INSERT INTO users(username,password,role,institutional_role) VALUES(?,?,?,?)",
            ("admin",generate_password_hash("Administrator-Password-123!"),"admin","admin"))
        connection.commit()
        connection.close()
        self.db_patch = patch.object(application, "DATABASE", self.path)
        self.db_patch.start()
        application.app.config.update(TESTING=True, SECRET_KEY="auth-test-secret")
        self.client = application.app.test_client()

    def tearDown(self):
        self.db_patch.stop()
        os.unlink(self.path)

    def token(self, path="/login"):
        response = self.client.get(path)
        match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def test_registrar_account_can_sign_in_to_registry_workspace(self):
        connection = sqlite3.connect(self.path)
        connection.execute(
            "INSERT INTO users(username,password,role,institutional_role) VALUES(?,?,?,?)",
            ("registrar",generate_password_hash("Registrar-Password-123!"),"invigilator","registrar"))
        connection.commit()
        connection.close()
        response = self.client.post("/login", data={
            "username":"registrar",
            "password":"Registrar-Password-123!",
            "role":"registrar",
            "csrf_token":self.token(),
        })
        self.assertEqual(response.status_code,302)
        self.assertTrue(response.headers["Location"].endswith("/admin/registry/students"))
        with self.client.session_transaction() as state:
            self.assertEqual(state["role"],"registrar")

    def test_role_mismatch_does_not_authenticate(self):
        response = self.client.post("/login", data={
            "username":"admin",
            "password":"Administrator-Password-123!",
            "role":"registrar",
            "csrf_token":self.token(),
        })
        self.assertEqual(response.status_code,200)
        with self.client.session_transaction() as state:
            self.assertNotIn("user_id",state)

    def test_admin_can_provision_registrar_account_with_audit_reason(self):
        with self.client.session_transaction() as state:
            state["user_id"]=1
            state["username"]="admin"
            state["role"]="admin"
        token=self.token("/admin/institutional-users")
        response=self.client.post("/admin/institutional-users",data={
            "full_name":"Registrar Test",
            "username":"registrar1",
            "password":"Registrar-Password-123!",
            "role":"registrar",
            "employee_number":"KSU-REG-001",
            "department":"Academic Registry",
            "reason":"Approved institutional test account request.",
            "csrf_token":token,
        })
        self.assertEqual(response.status_code,302)
        connection=sqlite3.connect(self.path)
        role=connection.execute("SELECT institutional_role FROM users WHERE username='registrar1'").fetchone()[0]
        audit=connection.execute("SELECT new_role,reason FROM institutional_role_audit WHERE target_user_id=2").fetchone()
        connection.close()
        self.assertEqual(role,"registrar")
        self.assertEqual(audit[0],"registrar")
        self.assertIn("Approved institutional",audit[1])

    def test_public_staff_registration_is_disabled(self):
        response=self.client.post("/register",data={
            "full_name":"Unverified Person","username":"unverified",
            "password":"Password-123456!","confirm_password":"Password-123456!",
            "role":"invigilator","csrf_token":self.token("/register"),
        })
        self.assertEqual(response.status_code,200)
        connection=sqlite3.connect(self.path)
        count=connection.execute("SELECT COUNT(*) FROM users WHERE username='unverified'").fetchone()[0]
        connection.close()
        self.assertEqual(count,0)


if __name__ == "__main__":
    unittest.main()
