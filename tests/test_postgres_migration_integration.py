import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from scripts.migrate_sqlite_to_postgres import migrate


POSTGRES_TEST_URL = os.environ.get("EIMS_POSTGRES_TEST_URL")


@unittest.skipUnless(POSTGRES_TEST_URL, "PostgreSQL integration service is not configured")
class SQLiteToPostgresIntegrationTests(unittest.TestCase):
    def test_copy_preserves_rows_foreign_keys_sequences_and_append_only_guards(self):
        handle, source_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        source = sqlite3.connect(source_path)
        source.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL);
            CREATE TABLE students(id INTEGER PRIMARY KEY AUTOINCREMENT, student_number TEXT UNIQUE NOT NULL);
            CREATE TABLE examinations(id INTEGER PRIMARY KEY AUTOINCREMENT, course_code TEXT NOT NULL);
            CREATE TABLE academic_history_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                event_reason TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id)
            );
            INSERT INTO users(username) VALUES('admin');
            INSERT INTO students(student_number) VALUES('KSU/TEST/001');
            INSERT INTO examinations(course_code) VALUES('CSC101');
            INSERT INTO academic_history_events(student_id,event_reason)
                VALUES(1,'initial test event');
            CREATE TRIGGER academic_history_no_update
            BEFORE UPDATE ON academic_history_events
            BEGIN SELECT RAISE(ABORT, 'Academic history events are append-only'); END;
            CREATE TRIGGER academic_history_no_delete
            BEFORE DELETE ON academic_history_events
            BEGIN SELECT RAISE(ABORT, 'Academic history events are append-only'); END;
        """)
        source.commit()
        source.close()

        engine = create_engine(POSTGRES_TEST_URL, pool_pre_ping=True)
        try:
            migrate(Path(source_path), POSTGRES_TEST_URL, apply=True, confirm_empty=True)
            inspector = inspect(engine)
            self.assertTrue({"users", "students", "examinations", "academic_history_events"}.issubset(
                set(inspector.get_table_names(schema="public"))
            ))
            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(text("SELECT COUNT(*) FROM academic_history_events")).scalar_one(),
                    1,
                )
                with self.assertRaises(DBAPIError):
                    connection.execute(text("""
                        UPDATE academic_history_events SET event_reason='tampered' WHERE id=1
                    """))
                    connection.rollback()
                connection.rollback()
                with self.assertRaises(DBAPIError):
                    connection.execute(text("DELETE FROM academic_history_events WHERE id=1"))
                    connection.rollback()
                connection.rollback()
                new_id = connection.execute(text("""
                    INSERT INTO academic_history_events(student_id,event_reason)
                    VALUES(1,'second event') RETURNING id
                """)).scalar_one()
                connection.commit()
                self.assertEqual(new_id, 2)
                with self.assertRaises(DBAPIError):
                    connection.execute(text("""
                        INSERT INTO academic_history_events(student_id,event_reason)
                        VALUES(999,'invalid foreign key')
                    """))
                    connection.commit()
                connection.rollback()
        finally:
            engine.dispose()
            os.unlink(source_path)


if __name__ == "__main__":
    unittest.main()
