"""
Leather Hide Inspection — Database Manager
Handles SQLite storage of inspection records.
Team 10 — TIP QC Capstone Project
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), 'inspections.db')


class InspectionDB:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create tables if they don't exist."""
        conn = self._get_conn()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS inspections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hide_id TEXT NOT NULL,
                classification TEXT NOT NULL CHECK(classification IN ('Good', 'Bad')),
                total_defects INTEGER DEFAULT 0,
                defects_json TEXT DEFAULT '[]',
                image_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
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
        ''')
        conn.commit()
        conn.close()

    def save_inspection(self, hide_id, classification, defects, total_defects, image_path=None):
        """
        Save a completed inspection.

        Args:
            hide_id (str): Unique identifier for the leather hide
            classification (str): 'Good' or 'Bad'
            defects (list): List of dicts with keys: type, confidence, x, y, w, h
            total_defects (int): Total number of defects found
            image_path (str): Path to the saved inspection image

        Returns:
            int: The inspection ID
        """
        conn = self._get_conn()
        cursor = conn.execute(
            '''INSERT INTO inspections (hide_id, classification, total_defects, defects_json, image_path)
               VALUES (?, ?, ?, ?, ?)''',
            (hide_id, classification, total_defects, json.dumps(defects), image_path)
        )
        inspection_id = cursor.lastrowid

        # Also log individual defects
        for defect in defects:
            conn.execute(
                '''INSERT INTO defect_log (inspection_id, defect_type, confidence,
                   bbox_x, bbox_y, bbox_w, bbox_h)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (inspection_id, defect.get('type', 'unknown'),
                 defect.get('confidence', 0),
                 defect.get('x', 0), defect.get('y', 0),
                 defect.get('w', 0), defect.get('h', 0))
            )

        conn.commit()
        conn.close()
        return inspection_id

    def get_inspection(self, inspection_id):
        """Get a single inspection by ID."""
        conn = self._get_conn()
        row = conn.execute(
            'SELECT * FROM inspections WHERE id = ?', (inspection_id,)
        ).fetchone()
        conn.close()
        if row:
            return self._row_to_dict(row)
        return None

    def get_inspections(self, limit=50, offset=0, classification=None):
        """Get inspection history with optional filtering."""
        conn = self._get_conn()
        query = 'SELECT * FROM inspections'
        params = []

        if classification:
            query += ' WHERE classification = ?'
            params.append(classification)

        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [self._row_to_dict(r) for r in rows]

    def get_analytics(self, period='today'):
        """Get aggregated analytics for a time period."""
        conn = self._get_conn()
        where_clause, params = self._period_filter(period)

        # Total counts
        row = conn.execute(
            f'''SELECT
                COUNT(*) as total,
                SUM(CASE WHEN classification = 'Good' THEN 1 ELSE 0 END) as good,
                SUM(CASE WHEN classification = 'Bad' THEN 1 ELSE 0 END) as bad,
                AVG(total_defects) as avg_defects
            FROM inspections {where_clause}''',
            params
        ).fetchone()

        total = row['total'] or 0
        good = row['good'] or 0
        bad = row['bad'] or 0

        conn.close()
        return {
            "total_inspections": total,
            "good_count": good,
            "bad_count": bad,
            "pass_rate": round((good / total * 100), 1) if total > 0 else 0,
            "defect_rate": round((bad / total * 100), 1) if total > 0 else 0,
            "avg_defects_per_hide": round(row['avg_defects'] or 0, 2),
            "period": period
        }

    def get_defect_distribution(self, period='all'):
        """Get count of each defect type."""
        conn = self._get_conn()
        where_clause = ''
        params = []

        if period != 'all':
            time_filter = self._get_time_boundary(period)
            where_clause = 'WHERE i.created_at >= ?'
            params = [time_filter]

        rows = conn.execute(
            f'''SELECT d.defect_type, COUNT(*) as count
            FROM defect_log d
            JOIN inspections i ON d.inspection_id = i.id
            {where_clause}
            GROUP BY d.defect_type
            ORDER BY count DESC''',
            params
        ).fetchall()
        conn.close()
        return [{"type": r['defect_type'], "count": r['count']} for r in rows]

    def get_timeline(self, period='today'):
        """Get inspection counts over time for charts."""
        conn = self._get_conn()

        if period == 'today':
            # Hourly breakdown
            time_boundary = datetime.now().replace(hour=0, minute=0, second=0).isoformat()
            rows = conn.execute(
                '''SELECT strftime('%H:00', created_at) as time_label,
                   COUNT(*) as total,
                   SUM(CASE WHEN classification = 'Good' THEN 1 ELSE 0 END) as good,
                   SUM(CASE WHEN classification = 'Bad' THEN 1 ELSE 0 END) as bad
                FROM inspections
                WHERE created_at >= ?
                GROUP BY time_label
                ORDER BY time_label''',
                (time_boundary,)
            ).fetchall()
        elif period == 'week':
            # Daily breakdown for last 7 days
            time_boundary = (datetime.now() - timedelta(days=7)).isoformat()
            rows = conn.execute(
                '''SELECT strftime('%m/%d', created_at) as time_label,
                   COUNT(*) as total,
                   SUM(CASE WHEN classification = 'Good' THEN 1 ELSE 0 END) as good,
                   SUM(CASE WHEN classification = 'Bad' THEN 1 ELSE 0 END) as bad
                FROM inspections
                WHERE created_at >= ?
                GROUP BY time_label
                ORDER BY created_at''',
                (time_boundary,)
            ).fetchall()
        else:
            # Daily breakdown for last 30 days
            time_boundary = (datetime.now() - timedelta(days=30)).isoformat()
            rows = conn.execute(
                '''SELECT strftime('%m/%d', created_at) as time_label,
                   COUNT(*) as total,
                   SUM(CASE WHEN classification = 'Good' THEN 1 ELSE 0 END) as good,
                   SUM(CASE WHEN classification = 'Bad' THEN 1 ELSE 0 END) as bad
                FROM inspections
                WHERE created_at >= ?
                GROUP BY time_label
                ORDER BY created_at''',
                (time_boundary,)
            ).fetchall()

        conn.close()
        return [dict(r) for r in rows]

    # ─── Helpers ────────────────────────────────────────────────
    def _row_to_dict(self, row):
        d = dict(row)
        if 'defects_json' in d:
            d['defects'] = json.loads(d['defects_json'])
            del d['defects_json']
        return d

    def _period_filter(self, period):
        if period == 'all':
            return '', []
        time_boundary = self._get_time_boundary(period)
        return 'WHERE created_at >= ?', [time_boundary]

    def _get_time_boundary(self, period):
        now = datetime.now()
        if period == 'today':
            return now.replace(hour=0, minute=0, second=0).isoformat()
        elif period == 'week':
            return (now - timedelta(days=7)).isoformat()
        elif period == 'month':
            return (now - timedelta(days=30)).isoformat()
        return '2000-01-01'
