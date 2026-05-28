from sql.executor import normalize_gender_share_sql


def test_normalizes_grouped_gender_share_case_numerator() -> None:
    sql = """
SELECT
  gender,
  ROUND(
    100.0 * SUM(CASE WHEN gender = '女' THEN ppl_cnt ELSE 0 END)
    / NULLIF(SUM(CASE WHEN gender IN ('男', '女') THEN ppl_cnt ELSE 0 END), 0),
    2
  ) AS percentage
FROM app_data
WHERE province = '湖南省'
  AND income = '20K+'
  AND gender IN ('男', '女')
GROUP BY gender
ORDER BY gender;
"""

    normalized, warning = normalize_gender_share_sql(sql)

    assert warning
    assert "CASE WHEN gender = '女'" not in normalized
    assert "SUM(SUM(ppl_cnt)) OVER ()" in normalized
    assert "GROUP BY gender" in normalized


def test_keeps_single_female_share_query_unchanged() -> None:
    sql = """
SELECT
  ROUND(
    100.0 * SUM(CASE WHEN gender = '女' THEN ppl_cnt ELSE 0 END)
    / NULLIF(SUM(CASE WHEN gender IN ('男', '女') THEN ppl_cnt ELSE 0 END), 0),
    2
  ) AS female_percent
FROM app_data
WHERE gender IN ('男', '女');
"""

    normalized, warning = normalize_gender_share_sql(sql)

    assert warning is None
    assert normalized == sql
