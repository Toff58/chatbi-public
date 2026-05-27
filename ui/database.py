import sqlite3
from pathlib import Path

from config import DATA_CSV_PATH, DB_PATH, IMPORT_METADATA_TABLE, TABLE_NAME
from data.import_csv_to_db import import_csv_to_sqlite


def ensure_database() -> None:
    if not Path(DATA_CSV_PATH).exists():
        raise FileNotFoundError(f"数据库不存在，且未找到可导入的 CSV：{DATA_CSV_PATH}")

    if _database_matches_csv():
        return

    import_csv_to_sqlite(DATA_CSV_PATH, DB_PATH)

def _database_matches_csv() -> bool:
    db_file = Path(DB_PATH)
    if not db_file.exists():
        return False

    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            table_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (TABLE_NAME,),
            ).fetchone()
            if not table_exists:
                return False

            db_rows = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
            csv_rows = _csv_row_count(DATA_CSV_PATH)
            if db_rows != csv_rows:
                return False

            metadata_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (IMPORT_METADATA_TABLE,),
            ).fetchone()
            if not metadata_exists:
                return False

            metadata = conn.execute(
                f"""
                SELECT source_mtime, source_rows
                FROM {IMPORT_METADATA_TABLE}
                WHERE table_name = ?
                """,
                (TABLE_NAME,),
            ).fetchone()
            if not metadata:
                return False

            csv_mtime = Path(DATA_CSV_PATH).stat().st_mtime
            return int(metadata[1]) == csv_rows and float(metadata[0]) >= csv_mtime
        finally:
            conn.close()
    except sqlite3.Error:
        return False

def _csv_row_count(csv_path: str) -> int:
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
        return max(sum(1 for _ in file) - 1, 0)
