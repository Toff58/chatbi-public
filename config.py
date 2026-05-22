import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "app_user_distribution.db")
DATA_CSV_PATH = str(BASE_DIR / "data" / "app_data.csv")
TABLE_NAME = "app_data"
IMPORT_METADATA_TABLE = "chatbi_import_metadata"
POPULATION_BASE = 600_000_000
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

REQUIRED_COLUMNS = [
    "app_name",
    "category",
    "category_new",
    "active_month",
    "city_tier",
    "income",
    "gender",
    "province",
    "age",
    "ppl_cnt",
]

PROFILE_COLUMNS = [
    "city_tier",
    "income",
    "gender",
    "province",
    "age",
]
