def build_local_summary(result: list[dict]) -> str:
    if not result:
        return "\u67e5\u8be2\u6ca1\u6709\u8fd4\u56de\u6570\u636e\u3002"
    return f"\u67e5\u8be2\u6210\u529f\uff0c\u8fd4\u56de {len(result)} \u6761\u7ed3\u679c\u3002"
