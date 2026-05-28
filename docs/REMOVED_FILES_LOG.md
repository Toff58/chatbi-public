# 删除文件记录

更新时间：2026-05-28

## 已删除

| 文件 | 删除原因 | 替代方式 |
| --- | --- | --- |
| `check_env.py` | 临时环境检查脚本，只打印 Python 路径 | 使用 `.\.venv\Scripts\python.exe --version` 或 `where python`。 |
| `check_query.py` | 临时 SQLite 查询脚本，只列出 category | 使用 `sql/executor.py#get_schema_profile()` 或直接运行正式测试。 |

## 尝试删除但未删除

| 文件 | 状态 | 原因 |
| --- | --- | --- |
| `streamlit.err.log` | 未删除 | 文件被现有 Streamlit 进程占用。 |
| `streamlit.out.log` | 未删除 | 文件被现有 Streamlit 进程占用。 |

## 保留但建议后续整理

| 文件 | 原因 |
| --- | --- |
| `logs/generated_questions_test_results*` | 当前是未跟踪历史批量测试结果，本次未删除，避免误删已有验证记录。 |
| `tests/run_generated_question_tests.py` | 当前是未跟踪批量测试脚本，可在确认纳入正式测试策略后再提交或删除。 |
| `__pycache__/` 系列目录 | 可再生成、已被 `.gitignore` 忽略；本次未做递归清理。 |
| `test_graph.py` | 当前作为不依赖模型 API 的 smoke test 保留，用于验证数据库、SQL 安全校验和 workflow 描述。 |
| `create_db.py` | 当前作为正式数据库导入入口保留，内部调用 `data/import_csv_to_db.py` 从 CSV 导入真实数据。 |
