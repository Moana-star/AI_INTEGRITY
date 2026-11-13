import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine

from scripts.migrate_sqlite_to_postgres import table_counts, validate_source


class SQLiteToPostgresMigrationPreflightTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        connection = sqlite3.connect(self.path)
        connection.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT UNIQUE);
            CREATE TABLE students(id INTEGER PRIMARY KEY, student_number TEXT UNIQUE);
            CREATE TABLE examinations(id INTEGER PRIMARY KEY, course_code TEXT);
            CREATE TABLE academic_history_events(
                id INTEGER PRIMARY KEY,
                student_id INTEGER NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id)
            );
            INSERT INTO users VALUES(1,'admin');
            INSERT INTO students VALUES(1,'KSU/TEST/001');
            INSERT INTO examinations VALUES(1,'CSC101');
            INSERT INTO academic_history_events VALUES(1,1);
            CREATE TRIGGER academic_history_no_update
            BEFORE UPDATE ON academic_history_events
            BEGIN SELECT RAISE(ABORT, 'Academic history events are append-only'); END;
            CREATE TRIGGER academic_history_no_delete
            BEFORE DELETE ON academic_history_events
            BEGIN SELECT RAISE(ABORT, 'Academic history events are append-only'); END;
        """)
        connection.commit()
        connection.close()

    def tearDown(self):
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass

    def test_preflight_accepts_valid_source_and_known_immutable_triggers(self):
        tables, triggers = validate_source(Path(self.path))
        self.assertIn("academic_history_events", tables)
        self.assertEqual(len(triggers), 2)

    def test_preflight_rejects_unknown_trigger_instead_of_silently_dropping_it(self):
        connection = sqlite3.connect(self.path)
        connection.execute("""
            CREATE TRIGGER unexpected_trigger
            BEFORE UPDATE ON students
            BEGIN SELECT RAISE(ABORT, 'unexpected'); END
        """)
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(RuntimeError, "Unrecognized SQLite triggers"):
            validate_source(Path(self.path))

    def test_preflight_rejects_broken_foreign_key_relationships(self):
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("INSERT INTO academic_history_events VALUES(2,999)")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(RuntimeError, "foreign_key_check"):
            validate_source(Path(self.path))

    def test_preflight_rejects_views_that_have_no_reviewed_postgres_definition(self):
        connection = sqlite3.connect(self.path)
        connection.execute("CREATE VIEW student_numbers AS SELECT student_number FROM students")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(RuntimeError, "SQLite views are not copied"):
            validate_source(Path(self.path))

    def test_preflight_rejects_partial_indexes_without_reviewed_equivalent(self):
        connection = sqlite3.connect(self.path)
        connection.execute("CREATE INDEX partial_student_index ON students(student_number) WHERE student_number <> ''")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(RuntimeError, "Partial or expression indexes"):
            validate_source(Path(self.path))

    def test_table_counts_reflect_all_requested_tables(self):
        engine = create_engine(f"sqlite:///{Path(self.path).resolve().as_posix()}")
        try:
            counts = table_counts(engine, ["users", "students", "examinations"])
        finally:
            engine.dispose()
        self.assertEqual(counts, {"examinations": 1, "students": 1, "users": 1})


if __name__ == "__main__":
    unittest.main()
