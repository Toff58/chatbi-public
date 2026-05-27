from pathlib import Path


LOG_DIR = Path("logs")
QUERY_LOG_FILE = LOG_DIR / "query_log.csv"
DEBUG_LOG_FILE = LOG_DIR / "query_debug.jsonl"
HIDDEN_DISPLAY_COLUMN_FRAGMENTS = {
    "numerator",
    "denominator",
    "target_sum",
    "source_sum",
    "valid_total",
    "valid_denominator",
    "ratio_raw",
    "base_population",
    "base_count",
    "calc_",
    "_calc",
    "分子",
    "分母",
    "有效分母",
}
RATIO_COLUMN_FRAGMENTS = {"ratio", "rate", "percent", "pct", "share", "占比", "比例"}
MONTH_COLUMN_NAMES = {"active_month", "month", "月份", "活跃月份"}
DISPLAY_COLUMN_LABELS = {
    "app_name": "App",
    "category": "品类",
    "category_new": "细分品类",
    "active_month": "月份",
    "city_tier": "城市等级",
    "income": "收入段",
    "gender": "性别",
    "province": "省份",
    "age": "年龄段",
    "ppl_cnt": "用户数",
    "user_count": "用户数",
    "estimated_user_count": "估算用户数",
    "female_percent": "女性占比",
}
DISPLAY_TOKEN_LABELS = {
    "estimated": "估算",
    "total": "总",
    "avg": "平均",
    "average": "平均",
    "app": "App",
    "user": "用户",
    "users": "用户",
    "count": "数",
    "cnt": "数",
    "number": "数量",
    "female": "女性",
    "male": "男性",
    "percent": "占比",
    "pct": "占比",
    "ratio": "占比",
    "share": "占比",
    "rate": "占比",
}
DICTIONARY_DIMENSION_ORDER = [
    "app_name",
    "category",
    "category_new",
    "city_tier",
    "income",
    "gender",
    "province",
    "age",
    "active_month",
]
METRIC_DICTIONARY_ROWS = [
    {
        "指标": "用户数",
        "适用问题": "某个 App 或带画像筛选的 App 排行、Top、最多等问题",
        "展示口径": "按 App 汇总满足条件的人群规模",
    },
    {
        "指标": "估算用户数",
        "适用问题": "省份、城市等级、性别、年龄、收入等宏观人群规模问题",
        "展示口径": "按有效样本占比估算总体人群规模",
    },
    {
        "指标": "占比",
        "适用问题": "性别、年龄段、收入段、城市等级等分布或比例问题",
        "展示口径": "排除缺失取值后计算有效样本内占比",
    },
]
