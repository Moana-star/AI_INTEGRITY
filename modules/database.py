"""Shared SQLite/PostgreSQL DB-API compatibility layer.

SQLite remains the local-development default. When DATABASE_URL points to PostgreSQL,
all application modules use psycopg through this adapter. The adapter deliberately
translates only the documented SQLite constructs used by this codebase; unsupported
SQL fails rather than silently changing semantics.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

SERIAL_TABLE_CACHE: dict[tuple[int, str], bool] = {}


class HybridRow(dict):
    """Mapping row with sqlite3.Row-compatible integer indexing."""
    def __init__(self, values: dict[str, Any]):
        super().__init__(values)
        self._values = tuple(values.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class PostgresCursor:
    def __init__(self, connection: "PostgresConnection"):
        self.connection = connection
        self.cursor = connection.raw.cursor()
        self._lastrowid = None
        self._pending_lastrowid = False

    def execute(self, sql: str, parameters: Iterable[Any] = ()):
        translated, wants_id = self.connection.translate(sql, parameters)
        self._pending_lastrowid = wants_id
        self._lastrowid = None
        try:
            self.cursor.execute(translated, tuple(parameters or ()))
        except Exception as error:
            self.connection.raise_compatible_error(error)
        return self

    def executemany(self, sql: str, seq_of_parameters):
        translated, wants_id = self.connection.translate(sql, ())
        if wants_id:
            translated = re.sub(r"\s+RETURNING\s+id\s*$", "", translated, flags=re.I)
        try:
            self.cursor.executemany(translated, seq_of_parameters)
        except Exception as error:
            self.connection.raise_compatible_error(error)
        return self

    @property
    def lastrowid(self):
        if self._pending_lastrowid:
            row = self.cursor.fetchone()
            self._lastrowid = row["id"] if row else None
            self._pending_lastrowid = False
        return self._lastrowid

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        return HybridRow(row) if row is not None and not isinstance(row, HybridRow) else row

    def fetchall(self):
        return [HybridRow(row) if not isinstance(row, HybridRow) else row for row in self.cursor.fetchall()]

    def __iter__(self):
        for row in self.cursor:
            yield HybridRow(row)


class PostgresConnection:
    def __init__(self, database_url: str):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError("PostgreSQL support requires psycopg 3. Install requirements.txt.") from error
        normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self.raw = psycopg.connect(normalized, row_factory=dict_row)
        self._psycopg = psycopg
        self._row_factory = None

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._row_factory = value

    def _has_id_column(self, table: str) -> bool:
        key = (id(self.raw), table.lower())
        if key not in SERIAL_TABLE_CACHE:
            row = self.raw.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name=%s AND column_name='id' LIMIT 1",
                (table.lower(),),
            ).fetchone()
            SERIAL_TABLE_CACHE[key] = row is not None
        return SERIAL_TABLE_CACHE[key]

    def translate(self, sql: str, parameters=()):
        statement = sql.strip()
        if re.match(r"^PRAGMA\s+foreign_keys\s*=", statement, re.I):
            return "SELECT 1", False
        if "sqlite_master" in statement.lower():
            if re.search(r"SELECT\s+name\s+FROM\s+sqlite_master", statement, re.I):
                statement = (
                    "SELECT table_name AS name FROM information_schema.tables "
                    "WHERE table_schema=current_schema() AND table_type='BASE TABLE'"
                )
            else:
                raise RuntimeError("SQLite sqlite_master SQL-definition queries must be replaced with PostgreSQL schema migrations.")
        statement = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", statement, flags=re.I)
        ignore_insert = bool(re.search(r"\bOR\s+IGNORE\b", sql, re.I))
        statement = statement.replace("?", "%s")
        statement = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "BIGSERIAL PRIMARY KEY", statement, flags=re.I)
        statement = re.sub(r"\bINTEGER\b", "BIGINT", statement, flags=re.I)
        statement = re.sub(r"\bAUTOINCREMENT\b", "", statement, flags=re.I)
        wants_id = False
        insert = re.match(r"INSERT\s+INTO\s+([a-zA-Z_][\w]*)\b", statement, re.I)
        if insert and not re.search(r"\bRETURNING\b", statement, re.I):
            wants_id = self._has_id_column(insert.group(1))
        if ignore_insert and not re.search(r"\bON\s+CONFLICT\b", statement, re.I):
            statement = statement.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        if wants_id:
            statement = statement.rstrip().rstrip(";") + " RETURNING id"
        return statement, wants_id

    def execute(self, sql: str, parameters=()):
        statement = sql.strip()
        if re.match(r"^PRAGMA\s+foreign_keys\s*=", statement, re.I):
            return PostgresCursor(self).execute("SELECT 1")
        pragma = re.match(r"^PRAGMA\s+table_info\(([^)]+)\)", statement, re.I)
        if pragma:
            table = pragma.group(1).strip(" \"'").lower()
            cursor = PostgresCursor(self)
            cursor.execute(
                "SELECT ordinal_position - 1 AS cid, column_name AS name, "
                "data_type AS type, 0 AS notnull, column_default AS dflt_value, "
                "CASE WHEN is_identity='YES' OR column_name='id' THEN 1 ELSE 0 END AS pk "
                "FROM information_schema.columns WHERE table_schema=current_schema() "
                "AND table_name=? ORDER BY ordinal_position",
                (table,),
            )
            return cursor
        cursor = PostgresCursor(self)
        return cursor.execute(sql, parameters)

    def executemany(self, sql: str, parameters):
        cursor = PostgresCursor(self)
        return cursor.executemany(sql, parameters)

    def executescript(self, script: str):
        trigger_pattern = re.compile(
            r"CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>\w+)\s+"
            r"BEFORE\s+(?P<event>UPDATE|DELETE)\s+ON\s+(?P<table>\w+)\s+"
            r"BEGIN\s+SELECT\s+RAISE\(ABORT,\s*'(?P<message>[^']*)'\);\s*END\s*;",
            re.I | re.S,
        )
        token_pattern = re.compile(
            r"(?P<trigger>CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?\w+"
            r".*?BEGIN\s+SELECT\s+RAISE\(ABORT,\s*'[^']*'\);\s*END\s*;)"
            r"|(?P<statement>\\s*[^;]+;)",
            re.I | re.S,
        )
        for token in token_pattern.finditer(script):
            trigger_sql = token.group("trigger")
            if trigger_sql:
                match = trigger_pattern.fullmatch(trigger_sql.strip())
                if not match:
                    raise RuntimeError("Unsupported SQLite trigger definition; add an explicit PostgreSQL migration.")
                name = match.group("name")
                event = match.group("event").upper()
                table = match.group("table")
                message = match.group("message").replace("'", "''")
                function_name = f"eims_guard_{name}"
                try:
                    self.raw.execute(
                        f"CREATE OR REPLACE FUNCTION {function_name}() RETURNS trigger "
                        f"LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION '{message}'; END; $$"
                    )
                    self.raw.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}")
                    self.raw.execute(
                        f"CREATE TRIGGER {name} BEFORE {event} ON {table} "
                        f"FOR EACH ROW EXECUTE FUNCTION {function_name}()"
                    )
                except Exception as error:
                    self.raise_compatible_error(error)
            else:
                statement = token.group("statement").strip().rstrip(";").strip()
                if statement:
                    self.execute(statement)
        return None

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

    def raise_compatible_error(self, error):
        if isinstance(error, self._psycopg.IntegrityError):
            raise sqlite3.IntegrityError(str(error)) from error
        raise error


def is_postgres() -> bool:
    url = os.environ.get("DATABASE_URL", "").lower()
    return url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://"))


def get_connection(sqlite_path: str | Path):
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        if not database_url.lower().startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("DATABASE_URL must use PostgreSQL or be unset for local SQLite.")
        return PostgresConnection(database_url)
    connection = sqlite3.connect(str(sqlite_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
