"""规则4：固定药品/产品名清单。"""


# 规则4：固定药品/产品名（通用名、商品名须书写正确；可继续追加条目）
FIXED_PRODUCT_TERMS = [
    {
        "generic": "达利雷生",
        "brand": "科唯可",
        "english": "daridorexant",
        "wrong_examples": ["达利雷声"],
    },
    {
        "generic": "注射用苏维西塔单抗",
        "brand": "恩泽舒",
        "aliases": ["苏维西塔单抗", "苏维西塔"],
    },
    {
        "generic": "重组人血管内皮抑制素注射液",
        "brand": "恩度",
    },
    {
        "generic": "注射用盐酸曲拉西利",
        "brand": "科赛拉",
    },
    {
        "generic": "依达拉奉右莰醇注射用浓溶液",
        "brand": "先必新",
    },
    {
        "generic": "依达拉奉右莰醇舌下片",
        "brand": "先必新",
    },
    {
        "generic": "依达拉奉注射液",
        "brand": "必存",
    },
    {
        "generic": "艾拉莫德片",
        "brand": "艾得辛",
    },
    {
        "generic": "先诺特韦片/利托那韦片组合包装",
        "brand": "先诺欣",
    },
]


def format_fixed_product_terms() -> str:
    lines = []
    for i, item in enumerate(FIXED_PRODUCT_TERMS, 1):
        parts = [f"通用名「{item['generic']}」"]
        if item.get("brand"):
            parts.append(f"商品名「{item['brand']}」")
        if item.get("aliases"):
            alias_text = "、".join(f"「{a}」" for a in item["aliases"])
            parts.append(f"可接受简称{alias_text}")
        if item.get("english"):
            parts.append(f"英文名「{item['english']}」")
        wrong = "、".join(f"「{w}」" for w in dict.fromkeys(item.get("wrong_examples", [])))
        line = f"  {i}) {'；'.join(parts)}"
        if wrong:
            line += f"。常见错误写法（出现即判错）：{wrong}"
        lines.append(line)
    return "\n".join(lines)

