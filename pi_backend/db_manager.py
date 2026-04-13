"""
Leather Hide Inspection — Database Manager
Aligned with api_server.py and camera_stream.py
Uses hidespec.db for live analytics + mobile app integration.
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "hidespec.db")


class InspectionDB:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create tables if they do not exist."""
        conn = self._get_conn()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS inspections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hide_id TEXT NOT NULL,
                classification TEXT NOT NULL CHECK(classification IN ('Good', 'Bad')),
                total_defects INTEGER NOT NULL DEFAULT 0,
                defects_json TEXT NOT NULL DEFAULT '[]',
                snapshot_path TEXT,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS defect_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inspection_id INTEGER NOT NULL,
                defect_type TEXT NOT NULL,
                confidence REAL,
                bbox_x INTEGER,
                bbox_y INTEGER,
                bbox_w INTEGER,
                bbox_h INTEGER,
                FOREIGN KEY (inspection_id) REFERENCES inspections(id)
            )
        """)

        conn.commit()
        conn.close()

    def save_inspection(
        self,
        hide_id,
        classification,
        defects,
        total_defects,
        image_path=None,
        created_at=None,
    ):
        """
        Save a completed inspection.

        Args:
            hide_id (str): Unique identifier for the leather hide
            classification (str): 'Good' or 'Bad'
            defects (list): List of dicts with keys like type, confidence, x, y, w, h
            total_defects (int): Total number of defects found
            image_path (str): Saved image path, stored as snapshot_path
            created_at (str): ISO timestamp string
        Returns:
            int: Inserted inspection ID
        """
        if created_at is None:
            created_at = datetime.utcnow().isoformat()

        conn = self._get_conn()

        cursor = conn.execute(
            """
            INSERT INTO inspections (
                hide_id,
                classification,
                total_defects,
                defects_json,
                snapshot_path,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                hide_id,
                classification,
                total_defects,
                json.dumps(defects),
                image_path,
                created_at,
            ),
        )
        inspection_id = cursor.lastrowid

        for defect in defects:
            conn.execute(
                """
                INSERT INTO defect_log (
                    inspection_id,
                    defect_type,
                    confidence,
                    bbox_x,
                    bbox_y,
                    bbox_w,
                    bbox_h
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inspection_id,
                    defect.get("type", "unknown"),
                    defect.get("confidence", 0),
                    defect.get("x", 0),
                    defect.get("y", 0),
                    defect.get("w", 0),
                    defect.get("h", 0),
                ),
            )

        conn.commit()
        conn.close()
        return inspection_id

    def get_inspection(self, inspection_id):
        """Get one inspection by ID."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM inspections WHERE id = ?",
            (inspection_id,),
        ).fetchone()
        conn.close()

        if row:
            return self._row_to_dict(row)
        return None

    def get_inspections(self, limit=50, offset=0, classification=None):
        """Get inspection history with optional filter."""
        conn = self._get_conn()
        query = "SELECT * FROM inspections"
        params = []

        if classification:
            query += " WHERE classification = ?"
            params.append(classification)

        query += " ORDER BY datetime(created_at) DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [self._row_to_dict(r) for r in rows]

    def get_analytics(self, period="today"):
        """Get aggregate analytics for a time period."""
        conn = self._get_conn()
        where_clause, params = self._period_filter(period)

        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN classification = 'Good' THEN 1 ELSE 0 END) AS good,
                SUM(CASE WHEN classification = 'Bad' THEN 1 ELSE 0 END) AS bad,
                AVG(total_defects) AS avg_defects
            FROM inspections
            {where_clause}
            """,
            params,
        ).fetchone()

        total = row["total"] or 0
        good = row["good"] or 0
        bad = row["bad"] or 0
        avg = round(row["avg_defects"] or 0, 2)

        conn.close()

        return {
            "total_inspections": total,
            "good_count": good,
            "bad_count": bad,
            "pass_rate": round((good / total) * 100, 1) if total > 0 else 0,
            "defect_rate": round((bad / total) * 100, 1) if total > 0 else 0,
            "avg_defects_per_hide": avg,
            "period": period,
        }

    def get_defect_distribution(self, period="today"):
        """Get count of each defect type."""
        conn = self._get_conn()

        if period == "all":
            rows = conn.execute(
                """
                SELECT d.defect_type, COUNT(*) AS count
                FROM defect_log d
                JOIN inspections i ON d.inspection_id = i.id
                GROUP BY d.defect_type
                ORDER BY count DESC
                """
            ).fetchall()
        else:
            time_boundary = self._get_time_boundary(period)
            rows = conn.execute(
                """
                SELECT d.defect_type, COUNT(*) AS count
                FROM defect_log d
                JOIN inspections i ON d.inspection_id = i.id
                WHERE datetime(i.created_at) >= datetime(?)
                GROUP BY d.defect_type
                ORDER BY count DESC
                """,
                (time_boundary,),
            ).fetchall()

        conn.close()

        return [{"type": r["defect_type"], "count": r["count"]} for r in rows]

    def get_timeline(self, period="today"):
        """Get inspection timeline data for charts."""
        conn = self._get_conn()

        if period == "today":
            time_boundary = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
            label_fmt = "%H:00"

            rows = conn.execute(
                f"""
                SELECT
                    strftime('{label_fmt}', created_at) AS time_label,
                    COUNT(*) AS total,
                    SUM(CASE WHEN classification = 'Good' THEN 1 ELSE 0 END) AS good,
                    SUM(CASE WHEN classification = 'Bad' THEN 1 ELSE 0 END) AS bad
                FROM inspections
                WHERE datetime(created_at) >= datetime(?)
                GROUP BY time_label
                ORDER BY time_label
                """,
                (time_boundary,),
            ).fetchall()

        elif period == "week":
            time_boundary = (datetime.now() - timedelta(days=7)).isoformat()
            label_fmt = "%m/%d"

            rows = conn.execute(
                f"""
                SELECT
                    strftime('{label_fmt}', created_at) AS time_label,
                    COUNT(*) AS total,
                    SUM(CASE WHEN classification = 'Good' THEN 1 ELSE 0 END) AS good,
                    SUM(CASE WHEN classification = 'Bad' THEN 1 ELSE 0 END) AS bad
                FROM inspections
                WHERE datetime(created_at) >= datetime(?)
                GROUP BY time_label
                ORDER BY time_label
                """,
                (time_boundary,),
            ).fetchall()

        elif period == "month":
            time_boundary = (datetime.now() - timedelta(days=30)).isoformat()
            label_fmt = "%m/%d"

            rows = conn.execute(
                f"""
                SELECT
                    strftime('{label_fmt}', created_at) AS time_label,
                    COUNT(*) AS total,
                    SUM(CASE WHEN classification = 'Good' THEN 1 ELSE 0 END) AS good,
                    SUM(CASE WHEN classification = 'Bad' THEN 1 ELSE 0 END) AS bad
                FROM inspections
                WHERE datetime(created_at) >= datetime(?)
                GROUP BY time_label
                ORDER BY time_label
                """,
                (time_boundary,),
            ).fetchall()

        else:  # all
            rows = conn.execute(
                """
                SELECT
                    strftime('%Y-%m', created_at) AS time_label,
                    COUNT(*) AS total,
                    SUM(CASE WHEN classification = 'Good' THEN 1 ELSE 0 END) AS good,
                    SUM(CASE WHEN classification = 'Bad' THEN 1 ELSE 0 END) AS bad
                FROM inspections
                GROUP BY time_label
                ORDER BY time_label
                """
            ).fetchall()

        conn.close()
        return [dict(r) for r in rows]

    def clear_all(self):
        """Delete all inspections and defect logs."""
        conn = self._get_conn()
        conn.execute("DELETE FROM defect_log")
        conn.execute("DELETE FROM inspections")
        conn.commit()
        conn.close()

    def _row_to_dict(self, row):
        data = dict(row)
        if "defects_json" in data:
            data["defects"] = json.loads(data["defects_json"] or "[]")
            del data["defects_json"]
        return data

    def _period_filter(self, period):
        if period == "all":
            return "", []
        time_boundary = self._get_time_boundary(period)
        return "WHERE datetime(created_at) >= datetime(?)", [time_boundary]

    def _get_time_boundary(self, period):
        now = datetime.now()

        if period == "today":
            return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        if period == "week":
            return (now - timedelta(days=7)).isoformat()
        if period == "month":
            return (now - timedelta(days=30)).isoformat()

        return "2000-01-01T00:00:00"