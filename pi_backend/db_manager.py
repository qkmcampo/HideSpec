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

DEFECT_TYPE_ALIASES = {
    "color_defect": "paint_stain",
}

BAD_DEFECT_THRESHOLD_PERCENT = 20.0


def normalize_defect_type(defect_type):
    return DEFECT_TYPE_ALIASES.get(defect_type, defect_type)


def normalize_defects(defects):
    return [
        {**defect, "type": normalize_defect_type(defect.get("type", "unknown"))}
        for defect in defects
    ]


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
                defect_area_percent REAL NOT NULL DEFAULT 0,
                leather_area REAL NOT NULL DEFAULT 0,
                defect_area REAL NOT NULL DEFAULT 0,
                defects_json TEXT NOT NULL DEFAULT '[]',
                snapshot_path TEXT,
                machine_status TEXT,
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

        self._migrate_defect_types(conn)
        conn.commit()
        conn.close()

    def _migrate_defect_types(self, conn):
        for old_type, new_type in DEFECT_TYPE_ALIASES.items():
            conn.execute(
                "UPDATE defect_log SET defect_type = ? WHERE defect_type = ?",
                (new_type, old_type),
            )

        rows = conn.execute("SELECT id, defects_json FROM inspections").fetchall()
        for row in rows:
            try:
                defects = json.loads(row["defects_json"] or "[]")
            except json.JSONDecodeError:
                continue

            normalized = normalize_defects(defects)
            if normalized != defects:
                conn.execute(
                    "UPDATE inspections SET defects_json = ? WHERE id = ?",
                    (json.dumps(normalized), row["id"]),
                )

    def save_inspection(
        self,
        hide_id,
        classification,
        defects,
        total_defects,
        defect_area_percent=0,
        leather_area=0,
        defect_area=0,
        image_path=None,
        machine_status=None,
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

        defects = normalize_defects(defects)
        conn = self._get_conn()

        cursor = conn.execute(
            """
            INSERT INTO inspections (
                hide_id,
                classification,
                total_defects,
                defect_area_percent,
                leather_area,
                defect_area,
                defects_json,
                snapshot_path,
                machine_status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hide_id,
                classification,
                total_defects,
                float(defect_area_percent or 0),
                float(leather_area or 0),
                float(defect_area or 0),
                json.dumps(defects),
                image_path,
                machine_status,
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
                AVG(total_defects) AS avg_defects,
                AVG(defect_area_percent) AS avg_defect_area_percent,
                SUM(total_defects) AS total_defects,
                SUM(CASE WHEN defect_area_percent >= ? THEN 1 ELSE 0 END) AS over_threshold
            FROM inspections
            {where_clause}
            """,
            [BAD_DEFECT_THRESHOLD_PERCENT, *params],
        ).fetchone()

        total = row["total"] or 0
        good = row["good"] or 0
        bad = row["bad"] or 0
        avg = round(row["avg_defects"] or 0, 2)
        avg_area = round(row["avg_defect_area_percent"] or 0, 2)
        total_defects = row["total_defects"] or 0
        over_threshold = row["over_threshold"] or 0

        conn.close()

        return {
            "total_inspections": total,
            "good_count": good,
            "bad_count": bad,
            "pass_rate": round((good / total) * 100, 1) if total > 0 else 0,
            "defect_rate": round((bad / total) * 100, 1) if total > 0 else 0,
            "avg_defects_per_hide": avg,
            "avg_defect_area_percent": avg_area,
            "total_defects": total_defects,
            "over_threshold_count": over_threshold,
            "threshold_percent": BAD_DEFECT_THRESHOLD_PERCENT,
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

    def get_quality_distribution(self, period="today"):
        conn = self._get_conn()
        where_clause, params = self._period_filter(period)

        row = conn.execute(
            f"""
            SELECT
                SUM(CASE WHEN defect_area_percent <= ? THEN 1 ELSE 0 END) AS good_by_threshold,
                SUM(CASE WHEN defect_area_percent > ? THEN 1 ELSE 0 END) AS bad_by_threshold
            FROM inspections
            {where_clause}
            """,
            [BAD_DEFECT_THRESHOLD_PERCENT, BAD_DEFECT_THRESHOLD_PERCENT, *params],
        ).fetchone()

        conn.close()
        good = row["good_by_threshold"] or 0
        bad = row["bad_by_threshold"] or 0
        total = good + bad
        return {
            "period": period,
            "threshold_percent": BAD_DEFECT_THRESHOLD_PERCENT,
            "good": good,
            "bad": bad,
            "total": total,
            "good_rate": round((good / total) * 100, 1) if total else 0,
            "bad_rate": round((bad / total) * 100, 1) if total else 0,
        }

    def get_defect_area_distribution(self, period="today"):
        conn = self._get_conn()
        where_clause, params = self._period_filter(period)

        row = conn.execute(
            f"""
            SELECT
                MIN(defect_area_percent) AS min_percent,
                MAX(defect_area_percent) AS max_percent,
                AVG(defect_area_percent) AS avg_percent
            FROM inspections
            {where_clause}
            """,
            params,
        ).fetchone()

        conn.close()
        return {
            "period": period,
            "min_percent": round(row["min_percent"] or 0, 2),
            "max_percent": round(row["max_percent"] or 0, 2),
            "avg_percent": round(row["avg_percent"] or 0, 2),
            "threshold_percent": BAD_DEFECT_THRESHOLD_PERCENT,
        }

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


