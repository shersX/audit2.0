def process_review_results(review_list):
    """
    处理评审结果：合并数据、转换格式、统计不符合规则序号。

    Args:
        review_list: 解析后的评审结果列表（每个元素是符合格式的字典）

    Returns:
        组装好的最终结果（字典格式，可直接转为 JSON）
    """
    final_result = {
        "审查结果": [],
        "统计": "",
    }
    non_compliant_rules = []

    for review in review_list:
        processed_item = {
            "规则内容（需带规则序号）": review.get("规则内容", ""),
            "评估结果": review.get("是否符合", ""),
            "理由": review.get("理由", ""),
        }
        final_result["审查结果"].append(processed_item)

        if review.get("是否符合", "") == "不符合":
            rule_content = review.get("规则内容", "")
            if "." in rule_content:
                rule_number = rule_content.split(".")[0]
                non_compliant_rules.append(rule_number)

    final_result["统计"] = "、".join(non_compliant_rules) + "、" if non_compliant_rules else ""
    return final_result
