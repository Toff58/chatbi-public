import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import DB_PATH, IMPORT_METADATA_TABLE, TABLE_NAME, REQUIRED_COLUMNS


def import_csv_to_sqlite(csv_path: str, db_path: str = DB_PATH, table_name: str = TABLE_NAME) -> None:
    csv_file = Path(csv_path)

    if not csv_file.exists():
        raise FileNotFoundError(f"CSV 文件不存在：{csv_file}")

    df = pd.read_csv(csv_file)

    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_columns:
        raise ValueError(f"CSV 缺少必要字段：{missing_columns}")

    # 只保留项目需要的字段，避免 CSV 里有多余列影响后续逻辑
    df = df[REQUIRED_COLUMNS].copy()

    # 基础清洗
    df["ppl_cnt"] = pd.to_numeric(df["ppl_cnt"], errors="coerce").fillna(0).astype(int)

    text_columns = [col for col in REQUIRED_COLUMNS if col != "ppl_cnt"]
    for col in text_columns:
        df[col] = df[col].fillna("NA").astype(str).str.strip()

    conn = sqlite3.connect(db_path)

    try:
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        _write_import_metadata(conn, csv_file, table_name, len(df))
        _create_indexes(conn, table_name)
        conn.commit()

        row_count = len(df)
        print(f"CSV 导入完成：{csv_file}")
        print(f"数据库文件：{db_path}")
        print(f"数据表：{table_name}")
        print(f"导入行数：{row_count}")

    finally:
        conn.close()


def _write_import_metadata(
    conn: sqlite3.Connection,
    csv_file: Path,
    table_name: str,
    row_count: int,
) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {IMPORT_METADATA_TABLE} (
            table_name TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            source_mtime REAL NOT NULL,
            source_rows INTEGER NOT NULL,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        f"""
        INSERT INTO {IMPORT_METADATA_TABLE} (
            table_name,
            source_path,
            source_mtime,
            source_rows,
            imported_at
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(table_name) DO UPDATE SET
            source_path = excluded.source_path,
            source_mtime = excluded.source_mtime,
            source_rows = excluded.source_rows,
            imported_at = CURRENT_TIMESTAMP
        """,
        (table_name, str(csv_file.resolve()), csv_file.stat().st_mtime, row_count),
    )


def _create_indexes(conn: sqlite3.Connection, table_name: str) -> None:
    index_columns = [
        "app_name",
        "category",
        "category_new",
        "active_month",
        "gender",
        "age",
        "city_tier",
        "income",
        "province",
    ]
    for column in index_columns:
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{column} ON {table_name} ({column})"
        )


def main():
    parser = argparse.ArgumentParser(description="Import CSV data into SQLite database.")
    parser.add_argument("csv_path", help="CSV 文件路径，例如 data/app_data.csv")
    args = parser.parse_args()

    import_csv_to_sqlite(args.csv_path)


if __name__ == "__main__":
    main()
