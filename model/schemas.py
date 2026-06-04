"""审核结果 JSON Schema，供各模型 provider 共用。"""

REVIEW_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "json_schema",
        "schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "规则内容": {"type": "string"},
                    "理由": {"type": "string"},
                    "是否符合": {"type": "string", "enum": ["符合", "不符合"]},
                },
                "required": ["规则内容", "理由", "是否符合"],
            },
        },
    },
}
