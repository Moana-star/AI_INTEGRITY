"""Tests for secure first-administrator bootstrap policy."""

import os
import sqlite3
import unittest
from unittest.mock import patch

from werkzeug.security import check_password_hash

from database.database import create_tables, provision_initial_administrator


class InitialAdministratorPasswordPolicyTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        create_tables(self.connection.cursor())

    def tearDown(self):
        self.connection.close()

    def test_eight_character_password_is_accepted_and_hashed(self):
        with patch.dict(os.environ, {
            "EIMS_BOOTSTRAP_ADMIN_USERNAME": "admin",
            "EIMS_BOOTSTRAP_ADMIN_PASSWORD": "Abc123!x",
        }, clear=False):
            created = provision_initial_administrator(self.connection.cursor())

        self.assertTrue(created)
        row = self.connection.execute(
            "SELECT password, role FROM users WHERE username = ?", ("admin",)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], "admin")
        self.assertNotEqual(row[0], "Abc123!x")
        self.assertTrue(check_password_hash(row[0], "Abc123!x"))

    def test_seven_character_password_is_rejected(self):
        with patch.dict(os.environ, {
            "EIMS_BOOTSTRAP_ADMIN_USERNAME": "admin",
            "EIMS_BOOTSTRAP_ADMIN_PASSWORD": "Abc12!x",
        }, clear=False):
            with self.assertRaisesRegex(RuntimeError, "at least 8 characters"):
                provision_initial_administrator(self.connection.cursor())


if __name__ == "__main__":
    unittest.main()
