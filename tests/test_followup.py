from graph.followup import resolve_followup_question


def test_resolves_province_followup_from_previous_question() -> None:
    memory = {
        "recent_interactions": [
            {
                "question": "广东省高收入人群的性别比例",
                "sql": "SELECT gender FROM app_data WHERE province = '广东省' AND income = '20K+'",
                "filters": {
                    "province": ["广东省"],
                    "income": ["20K+"],
                },
                "result_count": 2,
            }
        ]
    }
    schema_profile = {
        "enum_values": {
            "province": ["广东省", "湖南省"],
            "income": ["20K+"],
            "gender": ["男", "女"],
        }
    }

    resolution = resolve_followup_question("湖南省呢？", memory, schema_profile)

    assert resolution["is_followup"] is True
    assert resolution["resolved_question"] == "湖南省高收入人群的性别比例"
    assert resolution["replacements"][0]["column"] == "province"


def test_resolves_province_followup_without_punctuation() -> None:
    memory = {
        "recent_interactions": [
            {
                "question": "广东省高收入人群的性别比例",
                "sql": "SELECT gender FROM app_data WHERE province = '广东省' AND income = '20K+'",
                "filters": {
                    "province": ["广东省"],
                    "income": ["20K+"],
                },
                "result_count": 2,
            }
        ]
    }
    schema_profile = {
        "enum_values": {
            "province": ["广东省", "湖南省"],
            "income": ["20K+"],
            "gender": ["男", "女"],
        }
    }

    resolution = resolve_followup_question("湖南省呢", memory, schema_profile)

    assert resolution["is_followup"] is True
    assert resolution["resolved_question"] == "湖南省高收入人群的性别比例"


def test_uses_latest_successful_interaction_for_followup() -> None:
    memory = {
        "recent_interactions": [
            {
                "question": "湖南省呢",
                "sql": "",
                "filters": {},
                "result_count": 0,
            },
            {
                "question": "广东省高收入人群的性别比例",
                "sql": "SELECT gender FROM app_data WHERE province = '广东省' AND income = '20K+'",
                "filters": {
                    "province": ["广东省"],
                    "income": ["20K+"],
                },
                "result_count": 2,
            },
        ]
    }
    schema_profile = {
        "enum_values": {
            "province": ["广东省", "湖南省"],
            "income": ["20K+"],
            "gender": ["男", "女"],
        }
    }

    resolution = resolve_followup_question("湖南省呢", memory, schema_profile)

    assert resolution["is_followup"] is True
    assert resolution["previous_question"] == "广东省高收入人群的性别比例"
    assert resolution["resolved_question"] == "湖南省高收入人群的性别比例"


def test_keeps_standalone_question_unchanged() -> None:
    memory = {
        "recent_interactions": [
            {
                "question": "广东省高收入人群的性别比例",
                "sql": "SELECT gender FROM app_data WHERE province = '广东省'",
                "filters": {"province": ["广东省"]},
                "result_count": 2,
            }
        ]
    }
    schema_profile = {"enum_values": {"province": ["广东省", "湖南省"]}}

    resolution = resolve_followup_question("湖南省用户数最多的 App 是哪些？", memory, schema_profile)

    assert resolution["is_followup"] is False
    assert resolution["resolved_question"] == "湖南省用户数最多的 App 是哪些？"


def test_resolves_multiple_followup_slots() -> None:
    memory = {
        "recent_interactions": [
            {
                "question": "广东省高收入人群的性别比例",
                "sql": "SELECT gender FROM app_data WHERE province = '广东省' AND income = '20K+'",
                "filters": {
                    "province": ["广东省"],
                    "income": ["20K+"],
                },
                "result_count": 2,
            }
        ]
    }
    schema_profile = {
        "enum_values": {
            "province": ["广东省", "湖南省"],
            "income": ["20K+", "3000元以下"],
        }
    }

    resolution = resolve_followup_question("湖南省低收入呢？", memory, schema_profile)

    assert resolution["is_followup"] is True
    assert resolution["resolved_question"] == "湖南省低收入人群的性别比例"
