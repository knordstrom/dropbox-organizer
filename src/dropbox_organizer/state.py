import json
import os
import sqlite3
from datetime import datetime, timezone

from .labeler import LabelResult

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS labels (
    file_id          TEXT PRIMARY KEY,
    path             TEXT NOT NULL,
    content_hash     TEXT NOT NULL,
    labels           TEXT NOT NULL DEFAULT '[]',
    description      TEXT NOT NULL DEFAULT '',
    people_count     INTEGER,
    dominant_colors  TEXT NOT NULL DEFAULT '[]',
    analyzed_at      TEXT NOT NULL DEFAULT '',
    model            TEXT NOT NULL DEFAULT ''
)
"""

# Schema version history:
#   0 → original: path is PK, no file_id column
#   1 → file_id column added (path still PK, file_id nullable)
#   2 → file_id is PK, path is a regular NOT NULL column
_SCHEMA_VERSION = 2


class StateManager:
    def __init__(self, state_path: str):
        self.state_path = state_path
        os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(state_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    # ------------------------------------------------------------------
    # Schema migration
    # ------------------------------------------------------------------

    def _migrate(self):
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]

        if version == 0:
            # Fresh DB or pre-migration: create/upgrade to v1
            tables = [r[0] for r in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='labels'"
            ).fetchall()]
            if not tables:
                # Brand new DB — create at current version directly
                self._conn.execute(_CREATE_TABLE)
                self._conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
                self._conn.commit()
                return
            # Existing table without file_id — add it
            cols = [r[1] for r in self._conn.execute("PRAGMA table_info(labels)").fetchall()]
            if "file_id" not in cols:
                self._conn.execute("ALTER TABLE labels ADD COLUMN file_id TEXT NOT NULL DEFAULT ''")
            self._conn.execute("PRAGMA user_version = 1")
            self._conn.commit()
            version = 1

        if version == 1:
            # file_id column exists but path is still PK; promote file_id after backfill
            # Only promote if every row has a non-empty file_id
            unfilled = self._conn.execute(
                "SELECT COUNT(*) FROM labels WHERE file_id = ''"
            ).fetchone()[0]
            if unfilled == 0:
                self._promote_file_id_to_pk()
                version = 2

        if version < _SCHEMA_VERSION:
            # Nothing else to migrate yet
            pass

    def _promote_file_id_to_pk(self):
        """Recreate the labels table with file_id as primary key."""
        self._conn.executescript("""
            BEGIN;
            ALTER TABLE labels RENAME TO labels_old;
            CREATE TABLE labels (
                file_id          TEXT PRIMARY KEY,
                path             TEXT NOT NULL,
                content_hash     TEXT NOT NULL,
                labels           TEXT NOT NULL DEFAULT '[]',
                description      TEXT NOT NULL DEFAULT '',
                people_count     INTEGER,
                dominant_colors  TEXT NOT NULL DEFAULT '[]',
                analyzed_at      TEXT NOT NULL DEFAULT '',
                model            TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO labels SELECT file_id, path, content_hash, labels, description,
                                       people_count, dominant_colors, analyzed_at, model
                                FROM labels_old;
            DROP TABLE labels_old;
            COMMIT;
        """)
        self._conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
        self._conn.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _row_to_result(self, row: sqlite3.Row) -> LabelResult:
        return LabelResult(
            path=row["path"],
            content_hash=row["content_hash"],
            labels=json.loads(row["labels"]),
            description=row["description"],
            people_count=row["people_count"],
            dominant_colors=json.loads(row["dominant_colors"]),
            analyzed_at=row["analyzed_at"],
            model=row["model"],
            file_id=row["file_id"],
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> dict[str, LabelResult]:
        rows = self._conn.execute("SELECT * FROM labels").fetchall()
        return {row["path"]: self._row_to_result(row) for row in rows}

    def save(self):
        pass  # SQLite writes are immediate; kept for API compatibility

    def is_processed(self, file_id: str, content_hash: str) -> bool:
        if file_id:
            row = self._conn.execute(
                "SELECT content_hash FROM labels WHERE file_id = ?", (file_id,)
            ).fetchone()
        else:
            return False
        return row is not None and row["content_hash"] == content_hash

    def update(self, result: LabelResult):
        self._conn.execute(
            """
            INSERT INTO labels (file_id, path, content_hash, labels, description,
                                people_count, dominant_colors, analyzed_at, model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                path            = excluded.path,
                content_hash    = excluded.content_hash,
                labels          = excluded.labels,
                description     = excluded.description,
                people_count    = excluded.people_count,
                dominant_colors = excluded.dominant_colors,
                analyzed_at     = excluded.analyzed_at,
                model           = excluded.model
            """,
            (
                result.file_id,
                result.path,
                result.content_hash,
                json.dumps(result.labels),
                result.description,
                result.people_count,
                json.dumps(result.dominant_colors),
                result.analyzed_at,
                result.model,
            ),
        )
        self._conn.commit()

    def remove_labels(self, labels_to_remove: set[str], path_prefix: str = "") -> list[tuple[str, list[str]]]:
        prefix = path_prefix.rstrip("/").lower()
        if prefix:
            rows = self._conn.execute(
                "SELECT * FROM labels WHERE lower(path) LIKE ?", (prefix + "%",)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM labels").fetchall()

        changed = []
        for row in rows:
            before = json.loads(row["labels"])
            after = [l for l in before if l not in labels_to_remove]
            removed = [l for l in before if l in labels_to_remove]
            if removed:
                self._conn.execute(
                    "UPDATE labels SET labels = ? WHERE file_id = ?",
                    (json.dumps(after), row["file_id"]),
                )
                changed.append((row["path"], removed))

        if changed:
            self._conn.commit()
        return changed

    def get_all(self) -> list[LabelResult]:
        rows = self._conn.execute("SELECT * FROM labels ORDER BY path").fetchall()
        return [self._row_to_result(row) for row in rows]

    @property
    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]

    def paths_missing_file_id(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT path FROM labels WHERE file_id = '' ORDER BY path"
        ).fetchall()
        return [r[0] for r in rows]

    def set_file_id(self, path: str, file_id: str):
        self._conn.execute(
            "UPDATE labels SET file_id = ? WHERE path = ?", (file_id, path)
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Migration helper
    # ------------------------------------------------------------------

    def import_from_json(self, json_path: str) -> int:
        """Bulk-insert records from a labels.json file. Returns count inserted."""
        with open(json_path) as f:
            data = json.load(f)
        photos = data.get("photos", {})
        inserted = 0
        for path, d in photos.items():
            self._conn.execute(
                """
                INSERT OR IGNORE INTO labels
                    (file_id, path, content_hash, labels, description,
                     people_count, dominant_colors, analyzed_at, model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d.get("file_id", ""),
                    path,
                    d.get("content_hash", ""),
                    json.dumps(d.get("labels", [])),
                    d.get("description", ""),
                    d.get("people_count"),
                    json.dumps(d.get("dominant_colors", [])),
                    d.get("analyzed_at", ""),
                    d.get("model", ""),
                ),
            )
            inserted += self._conn.execute("SELECT changes()").fetchone()[0]
        self._conn.commit()
        return inserted
