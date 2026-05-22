from config import TABLE_NAME
from graph.workflow import describe_workflow
from sql.executor import execute_query, get_schema_profile, validate_select_sql


def main() -> None:
    print("Workflow steps:")
    for step in describe_workflow():
        print(f"- {step['name']}: {step['description']}")

    schema = get_schema_profile()
    print(f"\nTable: {schema['table']}")
    print(f"Rows: {schema['row_count']}")
    print("Columns:", ", ".join(column["name"] for column in schema["columns"]))

    safe_sql = f"""
    SELECT app_name, SUM(ppl_cnt) AS user_count
    FROM {TABLE_NAME}
    GROUP BY app_name
    ORDER BY user_count DESC
    LIMIT 3
    """.strip()
    is_valid, error = validate_select_sql(safe_sql)
    print(f"\nSafe SQL valid: {is_valid}, error: {error or ''}")
    print("Sample rows:", execute_query(safe_sql))

    dangerous_sql = f"DROP TABLE {TABLE_NAME}"
    is_valid, error = validate_select_sql(dangerous_sql)
    print(f"\nDangerous SQL valid: {is_valid}, error: {error or ''}")


if __name__ == "__main__":
    main()
