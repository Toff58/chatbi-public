# 代码精简说明

更新时间：2026-05-19

## 结论

代码可以精简，且本次已经做了安全范围内的精简。没有改动核心业务规则，只清理旧流程、临时入口和已经无引用的直连模型函数。

## 改了哪里

| 文件 | 改动 | 原因 |
| --- | --- | --- |
| `graph/nodes.py` | 删除旧的 `generate_sql`、`validate_sql`、`execute_sql`、`generate_answer` 节点，只保留 `build_local_summary()` | 当前入口已经由 `graph/agent.py` 的 LangChain Agent 接管，旧节点不再被调用。 |
| `deepseek_client.py` | 删除旧的 `get_api_key()`、`chat_completion()`、`extract_sql()`、`generate_sql()`、`generate_summary()` | 模型调用统一走 `deepseek_langchain.py#ChatDeepSeek`，保留两套 HTTP 客户端会增加维护成本。 |
| `check_env.py` | 删除 | 只打印 Python 解释器路径，属于临时检查脚本。 |
| `check_query.py` | 删除 | 只查询 category 枚举，功能已被 `sql/executor.py#get_schema_profile()` 覆盖。 |
| `test_graph.py` | 删除 | 根目录临时手动测试入口，已由 `tests/run_agent_tests.py` 替代。 |
| `create_db.py` | 删除 | 会用 11 行样例数据覆盖真实业务库，当前正式链路应使用 `data/import_csv_to_db.py` 从 CSV 导入。 |

## 顺手修复

| 文件 | 改动 | 价值 |
| --- | --- | --- |
| `sql/executor.py` | 表校验从“字符串包含 app_data”改为必须真实出现 `FROM/JOIN app_data` | 防止 `SELECT 'app_data'` 这类无表查询被误判合法。 |
| `graph/agent.py` | 增加未知字段 schema guard | 遇到 `device_brand` 这类不在表里的字段，直接返回可见错误，不生成假成功空结果。 |
| `graph/sql_examples.py` | 增加非法枚举空结果 few-shot | 让“火星省”这类不存在枚举稳定生成 `WHERE 1 = 0`。 |
| `tests/run_agent_tests.py` | 增加分段耗时字段和时间戳日志 | 便于定位模型耗时、SQL 工具耗时和总耗时。 |

## 没动的地方

| 范围 | 原因 |
| --- | --- |
| `graph/rag.py` 规则结构 | 当前规则数量少，本地关键词检索足够；暂不引入向量库。 |
| `sql/executor.py` 的二次基础校验 | 工具层和执行层都保留基础 SQL 校验，属于安全冗余，不删。 |
| 历史 `query_log.csv`、`query_debug.jsonl` | 工作区开始时已经有改动，未回滚也未清理。 |
| 既有 `logs/generated_questions_test_results*` | 这些是已有探索测试结果，未删除。 |

## 验证结果

最终执行：

```powershell
.\.venv\Scripts\python.exe tests\run_agent_tests.py
```

结果：
- 12 条样例全部通过。
- 最新日志：`logs/agent_test_results.csv`
- 本次最终时间戳日志：`logs/agent_test_results_20260519_183409.csv`

