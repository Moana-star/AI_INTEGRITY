"""Audited venue lifecycle and immutable seating-layout versions.

All reservation-affecting writes share the operations scheduler lock. A venue
cannot be closed while scheduled/active sessions reference it, and capacity
cannot be reduced below existing reservations or allocated seats.
"""
from __future__ import annotations

import json
import sqlite3
from flask import Blueprint, abort, flash, redirect, request, session, url_for

from modules.database import is_postgres
from modules.operations import (
    _audit, _begin_scheduling_write, _require_admin, build_venue_seats, db,
)

venue_management_bp = Blueprint("venue_management", __name__, url_prefix="/venue-management")
SCHEMA_READY = False


def _columns(connection, table):
    if is_postgres():
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name=?",
            (table,),
        ).fetchall()
        return {row["column_name"] for row in rows}
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column(connection, table, name, definition):
    if name not in _columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def ensure_schema():
    """Additive migration; never drops or rewrites existing seat assignments."""
    connection = db()
    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS venue_layout_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_id INTEGER NOT NULL,
                version_number INTEGER NOT NULL,
                row_count INTEGER NOT NULL CHECK(row_count BETWEEN 1 AND 26),
                seats_per_row INTEGER NOT NULL CHECK(seats_per_row BETWEEN 1 AND 100),
                layout_snapshot TEXT NOT NULL,
                reason TEXT NOT NULL CHECK(length(trim(reason)) >= 12),
                created_by INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(venue_id, version_number),
                FOREIGN KEY(venue_id) REFERENCES venues(id),
                FOREIGN KEY(created_by) REFERENCES users(id)
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS venue_operations_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_id INTEGER NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('registered','capacity_changed','closed','reopened','layout_version_created')),
                old_capacity INTEGER,
                new_capacity INTEGER,
                old_active INTEGER,
                new_active INTEGER,
                layout_version_id INTEGER,
                reason TEXT NOT NULL CHECK(length(trim(reason)) >= 12),
                actor_user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(venue_id) REFERENCES venues(id),
                FOREIGN KEY(layout_version_id) REFERENCES venue_layout_versions(id),
                FOREIGN KEY(actor_user_id) REFERENCES users(id)
            )
        """)
        _add_column(connection, "venues", "current_layout_version_id", "INTEGER")
        _add_column(connection, "venue_seats", "layout_version_id", "INTEGER")
        _add_column(connection, "venue_seats", "display_label", "TEXT")
        _add_column(connection, "session_seat_assignments", "layout_version_id", "INTEGER")

        # Preserve pre-version layouts as version 1. Their seat IDs remain stable,
        # so existing allocations continue to reference the exact historical seats.
        legacy_venues = connection.execute("""
            SELECT v.id FROM venues v
            JOIN venue_seats s ON s.venue_id=v.id
            WHERE v.current_layout_version_id IS NULL
            GROUP BY v.id
        """).fetchall()
        for venue_row in legacy_venues:
            venue_id = venue_row["id"]
            seats = connection.execute("""
                SELECT id, seat_label, row_label, seat_number, accessible
                FROM venue_seats WHERE venue_id=? ORDER BY row_label, seat_number
            """, (venue_id,)).fetchall()
            max_row = max((ord(row["row_label"][0].upper()) - ord("A") + 1 for row in seats), default=1)
            max_seat = max((row["seat_number"] for row in seats), default=1)
            snapshot = [{"label": row["seat_label"], "row": row["row_label"],
                         "number": row["seat_number"], "accessible": bool(row["accessible"])}
                        for row in seats]
            version_cursor = connection.execute("""
                INSERT INTO venue_layout_versions
                (venue_id,version_number,row_count,seats_per_row,layout_snapshot,reason)
                VALUES (?,1,?,?,?,'Baseline layout preserved during additive versioning migration.')
                RETURNING id
            """, (venue_id, max_row, max_seat, json.dumps(snapshot, separators=(",", ":"))))
            version_id = version_cursor.fetchone()["id"]
            connection.execute("""
                UPDATE venue_seats SET layout_version_id=?, display_label=seat_label
                WHERE venue_id=?
            """, (version_id, venue_id))
            connection.execute("""
                UPDATE venues SET current_layout_version_id=? WHERE id=?
            """, (version_id, venue_id))

        # Associate existing allocations with the version of the seat they already use.
        connection.execute("""
            UPDATE session_seat_assignments
            SET layout_version_id=(
                SELECT vs.layout_version_id FROM venue_seats vs
                WHERE vs.id=session_seat_assignments.venue_seat_id
            )
            WHERE layout_version_id IS NULL
        """)

        # Enforce immutable layout and venue operation history in both supported DBs.
        if is_postgres():
            connection.execute("""
                CREATE OR REPLACE FUNCTION eims_reject_venue_history_mutation()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Venue history and layout versions are append-only'; END;
                $$
            """)
            connection.execute("""
                DROP TRIGGER IF EXISTS venue_operations_history_immutable ON venue_operations_history
            """)
            connection.execute("""
                CREATE TRIGGER venue_operations_history_immutable
                BEFORE UPDATE OR DELETE ON venue_operations_history
                FOR EACH ROW EXECUTE FUNCTION eims_reject_venue_history_mutation()
            """)
            connection.execute("""
                DROP TRIGGER IF EXISTS venue_layout_versions_immutable ON venue_layout_versions
            """)
            connection.execute("""
                CREATE TRIGGER venue_layout_versions_immutable
                BEFORE UPDATE OR DELETE ON venue_layout_versions
                FOR EACH ROW EXECUTE FUNCTION eims_reject_venue_history_mutation()
            """)
        else:
            connection.execute("""
                CREATE TRIGGER IF NOT EXISTS venue_operations_history_no_update
                BEFORE UPDATE ON venue_operations_history
                BEGIN SELECT RAISE(ABORT, 'Venue operation history is append-only'); END
            """)
            connection.execute("""
                CREATE TRIGGER IF NOT EXISTS venue_operations_history_no_delete
                BEFORE DELETE ON venue_operations_history
                BEGIN SELECT RAISE(ABORT, 'Venue operation history is append-only'); END
            """)
            connection.execute("""
                CREATE TRIGGER IF NOT EXISTS venue_layout_versions_no_update
                BEFORE UPDATE ON venue_layout_versions
                BEGIN SELECT RAISE(ABORT, 'Venue layout versions are append-only'); END
            """)
            connection.execute("""
                CREATE TRIGGER IF NOT EXISTS venue_layout_versions_no_delete
                BEFORE DELETE ON venue_layout_versions
                BEGIN SELECT RAISE(ABORT, 'Venue layout versions are append-only'); END
            """)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@venue_management_bp.before_request
def prepare():
    global SCHEMA_READY
    if not _require_admin():
        abort(403)
    if not SCHEMA_READY:
        from modules.institutional_registry import ensure_schema as ensure_registry_schema
        from modules.operations import ensure_schema as ensure_operations_schema
        from modules.integrity import ensure_schema as ensure_integrity_schema
        ensure_registry_schema()
        ensure_operations_schema()
        ensure_integrity_schema()
        ensure_schema()
        SCHEMA_READY = True


def _reason():
    return " ".join((request.form.get("reason") or "").split())


def _history(connection, venue_id, action, reason, old_capacity=None, new_capacity=None,
             old_active=None, new_active=None, layout_version_id=None):
    connection.execute("""
        INSERT INTO venue_operations_history
        (venue_id,action,old_capacity,new_capacity,old_active,new_active,
         layout_version_id,reason,actor_user_id)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (venue_id, action, old_capacity, new_capacity, old_active, new_active,
          layout_version_id, reason, session["user_id"]))


@venue_management_bp.post("/<int:venue_id>/capacity")
def change_capacity(venue_id):
    reason = _reason()
    try:
        new_capacity = int(request.form.get("capacity", ""))
        if not 1 <= new_capacity <= 10000 or not 12 <= len(reason) <= 500:
            raise ValueError
    except (TypeError, ValueError):
        flash("Enter a capacity from 1 to 10,000 and a reason of 12–500 characters.", "error")
        return redirect(url_for("operations.workspace"))

    connection = db()
    try:
        _begin_scheduling_write(connection)
        venue = connection.execute("SELECT * FROM venues WHERE id=?", (venue_id,)).fetchone()
        if not venue:
            connection.rollback()
            flash("Venue not found.", "error")
            return redirect(url_for("operations.workspace"))
        if not venue["active"]:
            connection.rollback()
            flash("Reopen the venue before changing its capacity.", "error")
            return redirect(url_for("operations.workspace"))
        if new_capacity == venue["capacity"]:
            connection.rollback()
            flash("The new capacity must differ from the current capacity.", "error")
            return redirect(url_for("operations.workspace"))

        reservations = connection.execute("""
            SELECT es.id, es.session_code,
                   (SELECT COUNT(*) FROM session_candidates sc WHERE sc.session_id=es.id) AS candidate_count,
                   (SELECT COUNT(*) FROM session_seat_assignments sa WHERE sa.session_id=es.id) AS allocated_count
            FROM examination_sessions es
            WHERE es.venue_id=? AND es.status IN ('scheduled','active')
        """, (venue_id,)).fetchall()
        if any(row["candidate_count"] > new_capacity or row["allocated_count"] > new_capacity
               for row in reservations):
            connection.rollback()
            flash("Capacity reduction blocked: at least one scheduled/active session has more candidates or allocated seats than the proposed capacity. Reschedule or resolve those sessions first.", "error")
            return redirect(url_for("operations.workspace"))
        if venue["current_layout_version_id"]:
            seat_count = connection.execute("""
                SELECT COUNT(*) FROM venue_seats
                WHERE venue_id=? AND layout_version_id=? AND active=1
            """, (venue_id, venue["current_layout_version_id"])).fetchone()[0]
            if new_capacity > seat_count:
                connection.rollback()
                flash("Capacity cannot exceed the number of seats in the current layout. Create a suitable layout version first.", "error")
                return redirect(url_for("operations.workspace"))
        connection.execute("UPDATE venues SET capacity=? WHERE id=?", (new_capacity, venue_id))
        _history(connection, venue_id, "capacity_changed", reason,
                  old_capacity=venue["capacity"], new_capacity=new_capacity,
                  old_active=venue["active"], new_active=venue["active"])
        _audit(connection, "change_capacity", "venue", venue_id,
               f"Changed venue capacity from {venue['capacity']} to {new_capacity}. Reason: {reason}")
        connection.commit()
        flash("Venue capacity updated and recorded in venue history.", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("Capacity change could not be saved because of a database constraint.", "error")
    finally:
        connection.close()
    return redirect(url_for("operations.workspace"))


@venue_management_bp.post("/<int:venue_id>/status")
def change_status(venue_id):
    reason = _reason()
    requested = (request.form.get("active") or "").strip()
    if requested not in {"0", "1"} or not 12 <= len(reason) <= 500:
        flash("Choose a valid venue status and provide a reason of 12–500 characters.", "error")
        return redirect(url_for("operations.workspace"))
    new_active = int(requested)

    connection = db()
    try:
        _begin_scheduling_write(connection)
        venue = connection.execute("SELECT * FROM venues WHERE id=?", (venue_id,)).fetchone()
        if not venue:
            connection.rollback()
            flash("Venue not found.", "error")
            return redirect(url_for("operations.workspace"))
        if venue["active"] == new_active:
            connection.rollback()
            flash("The venue is already in that status.", "error")
            return redirect(url_for("operations.workspace"))
        if new_active == 0:
            booking = connection.execute("""
                SELECT session_code FROM examination_sessions
                WHERE venue_id=? AND status IN ('scheduled','active') LIMIT 1
            """, (venue_id,)).fetchone()
            if booking:
                connection.rollback()
                flash(f"Venue closure blocked: session {booking['session_code']} still reserves this venue. Reschedule or cancel it first.", "error")
                return redirect(url_for("operations.workspace"))
        connection.execute("UPDATE venues SET active=? WHERE id=?", (new_active, venue_id))
        action = "reopened" if new_active else "closed"
        _history(connection, venue_id, action, reason,
                  old_capacity=venue["capacity"], new_capacity=venue["capacity"],
                  old_active=venue["active"], new_active=new_active)
        _audit(connection, action, "venue", venue_id,
               f"Venue {venue['venue_code']} {action}. Reason: {reason}")
        connection.commit()
        flash(f"Venue {action} and recorded in venue history.", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("Venue status change could not be saved because of a database constraint.", "error")
    finally:
        connection.close()
    return redirect(url_for("operations.workspace"))


@venue_management_bp.post("/<int:venue_id>/layouts")
def create_layout_version(venue_id):
    reason = _reason()
    try:
        rows = int(request.form.get("rows", ""))
        seats_per_row = int(request.form.get("seats_per_row", ""))
        if not 12 <= len(reason) <= 500:
            raise ValueError
    except (TypeError, ValueError):
        flash("Enter valid layout dimensions and a reason of 12–500 characters.", "error")
        return redirect(url_for("operations.workspace"))
    accessible = {item.strip().upper() for item in (request.form.get("accessible_seats") or "").split(",") if item.strip()}
    try:
        seats = build_venue_seats(rows, seats_per_row, accessible)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("operations.workspace"))

    connection = db()
    try:
        _begin_scheduling_write(connection)
        venue = connection.execute("SELECT * FROM venues WHERE id=?", (venue_id,)).fetchone()
        if not venue or not venue["active"]:
            connection.rollback()
            flash("A layout version can only be created for an active venue.", "error")
            return redirect(url_for("operations.workspace"))
        if len(seats) < venue["capacity"]:
            connection.rollback()
            flash("The new layout must contain at least the venue's declared capacity.", "error")
            return redirect(url_for("operations.workspace"))
        accessible_count = sum(1 for seat in seats if seat[3])
        pending_sessions = connection.execute("""
            SELECT es.id, es.academic_year, es.semester
            FROM examination_sessions es
            WHERE es.venue_id=? AND es.status IN ('scheduled','active')
        """, (venue_id,)).fetchall()
        for pending in pending_sessions:
            required_accessible = connection.execute("""
                SELECT COUNT(*) FROM session_candidates sc
                JOIN student_exam_accommodations a
                  ON a.student_id=sc.student_id
                 AND a.academic_year=? AND a.semester=?
                WHERE sc.session_id=? AND a.requires_accessible_seat=1
            """, (pending["academic_year"], pending["semester"], pending["id"])).fetchone()[0]
            if required_accessible > accessible_count:
                connection.rollback()
                flash("Layout version blocked: it would not provide enough accessible seats for an existing scheduled/active session.", "error")
                return redirect(url_for("operations.workspace"))
        version_number = connection.execute("""
            SELECT COALESCE(MAX(version_number),0)+1 FROM venue_layout_versions WHERE venue_id=?
        """, (venue_id,)).fetchone()[0]
        snapshot = [{"label": seat[0], "row": seat[1], "number": seat[2],
                     "accessible": bool(seat[3])} for seat in seats]
        cursor = connection.execute("""
            INSERT INTO venue_layout_versions
            (venue_id,version_number,row_count,seats_per_row,layout_snapshot,reason,created_by)
            VALUES (?,?,?,?,?,?,?) RETURNING id
        """, (venue_id, version_number, rows, seats_per_row,
              json.dumps(snapshot, separators=(",", ":")), reason, session["user_id"]))
        version_id = cursor.fetchone()["id"]

        # Keep old seat rows and their foreign-key identities. Internal seat keys
        # are version-scoped; display labels remain human-readable and may repeat.
        connection.execute("UPDATE venue_seats SET active=0 WHERE venue_id=? AND active=1", (venue_id,))
        connection.executemany("""
            INSERT INTO venue_seats
            (venue_id,seat_label,display_label,row_label,seat_number,accessible,active,layout_version_id)
            VALUES (?,?,?,?,?,?,1,?)
        """, [(venue_id, f"v{version_number}:{seat[0]}", seat[0], seat[1],
               seat[2], seat[3], version_id) for seat in seats])
        connection.execute("UPDATE venues SET current_layout_version_id=? WHERE id=?",
                           (version_id, venue_id))
        _history(connection, venue_id, "layout_version_created", reason,
                  old_capacity=venue["capacity"], new_capacity=venue["capacity"],
                  old_active=venue["active"], new_active=venue["active"],
                  layout_version_id=version_id)
        _audit(connection, "create_layout_version", "venue", venue_id,
               f"Created seating layout version {version_number} with {len(seats)} seats. Reason: {reason}")
        connection.commit()
        flash(f"Seating layout version {version_number} created. Earlier seat records and allocations were preserved.", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("The layout version could not be saved because of a database constraint.", "error")
    finally:
        connection.close()
    return redirect(url_for("operations.workspace"))


@venue_management_bp.get("/<int:venue_id>/history")
def venue_history(venue_id):
    connection = db()
    venue = connection.execute("SELECT * FROM venues WHERE id=?", (venue_id,)).fetchone()
    if not venue:
        connection.close()
        abort(404)
    history = connection.execute("""
        SELECT h.*, v.version_number
        FROM venue_operations_history h
        LEFT JOIN venue_layout_versions v ON v.id=h.layout_version_id
        WHERE h.venue_id=?
        ORDER BY h.id DESC
    """, (venue_id,)).fetchall()
    versions = connection.execute("""
        SELECT version_number,row_count,seats_per_row,reason,created_by,created_at
        FROM venue_layout_versions WHERE venue_id=? ORDER BY version_number DESC
    """, (venue_id,)).fetchall()
    connection.close()
    from flask import render_template
    return render_template("venue_history.html", venue=venue, history=history, versions=versions)
