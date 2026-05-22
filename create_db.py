import argparse

from config import DATA_CSV_PATH, DB_PATH, TABLE_NAME
from data.import_csv_to_db import import_csv_to_sqlite


def main() -> None:
    parser = argparse.ArgumentParser(description="Import ChatBI CSV data into SQLite.")
    parser.add_argument("--csv", default=DATA_CSV_PATH, help="CSV path, default: data/app_data.csv")
    parser.add_argument("--db", default=DB_PATH, help="SQLite database path")
    args = parser.parse_args()

    import_csv_to_sqlite(args.csv, args.db, TABLE_NAME)


if __name__ == "__main__":
    main()
