from typing import TypedDict


class BusinessScope(TypedDict):
    id: str
    name: str
    field: str
    values: list[str]
    keywords: list[str]
    description: str


BUSINESS_SCOPES: list[BusinessScope] = [
    {
        "id": "leisure_entertainment",
        "name": "休闲娱乐",
        "field": "category",
        "values": ["娱乐休闲"],
        "keywords": ["休闲娱乐", "娱乐休闲", "泛娱乐", "娱乐", "休闲"],
        "description": "休闲娱乐固定映射到现有 category 中的娱乐休闲。",
    },
    {
        "id": "social",
        "name": "社交",
        "field": "category",
        "values": ["社交沟通"],
        "keywords": ["社交", "社交沟通", "聊天", "沟通", "互动"],
        "description": "社交固定映射到现有 category 中的社交沟通。",
    },
    {
        "id": "local_life",
        "name": "本地生活",
        "field": "category",
        "values": ["生活类", "美食外卖"],
        "keywords": ["本地生活", "生活服务", "生活类", "到店", "到家", "外卖"],
        "description": "本地生活固定映射到现有 category 中的生活类、美食外卖。",
    },
    {
        "id": "young_users",
        "name": "年轻用户",
        "field": "age",
        "values": ["小于20岁", "20-24岁", "25-29岁"],
        "keywords": ["年轻", "青年", "年轻人", "低龄"],
        "description": "年轻用户默认映射到小于20岁、20-24岁、25-29岁三个年龄段。",
    },
    {
        "id": "lower_tier_city",
        "name": "下沉城市",
        "field": "city_tier",
        "values": ["三线城市", "四线城市", "五线城市"],
        "keywords": ["下沉", "低线", "三线及以下"],
        "description": "下沉城市默认映射到三线城市、四线城市、五线城市。",
    },
    {
        "id": "high_income",
        "name": "高收入",
        "field": "income",
        "values": ["20K+"],
        "keywords": ["高收入", "高薪", "高净值"],
        "description": "高收入默认映射到现有收入段中的 20K+。",
    },
    {
        "id": "low_income",
        "name": "低收入",
        "field": "income",
        "values": ["3000元以下", "3000到5000"],
        "keywords": ["低收入", "低薪"],
        "description": "低收入默认映射到 3000元以下、3000到5000 两个收入段。",
    },
]


def match_business_scopes(question: str) -> list[BusinessScope]:
    lowered = question.lower()
    matches = []
    for scope in BUSINESS_SCOPES:
        if any(keyword.lower() in lowered for keyword in scope["keywords"]):
            matches.append(scope)
    return matches


def format_scope_context(scopes: list[BusinessScope]) -> str:
    if not scopes:
        return "无固定业务范围映射。"

    lines = []
    for scope in scopes:
        values = "', '".join(scope["values"])
        lines.append(
            f"- 用户提到“{scope['name']}”时，必须按固定映射处理："
            f"{scope['field']} IN ('{values}')。{scope['description']}"
        )
    return "\n".join(lines)


def build_scope_clarifications(scopes: list[BusinessScope]) -> list[str]:
    clarifications = []
    for scope in scopes:
        values = "、".join(scope["values"])
        clarifications.append(f"口径说明：已按默认口径将“{scope['name']}”理解为：{values}。")
    return clarifications
