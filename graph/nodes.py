def build_local_summary(result: list[dict]) -> str:
    if not result:
        return "本次查询没有返回数据。"
    return f"查询成功，共返回 {len(result)} 条结果。"
