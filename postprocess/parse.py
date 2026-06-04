import json
import logging

logger = logging.getLogger("PDF-Audit-API")


def parse_review_str(review_str):
    """
    将 JSON 字符串解析为 Python 列表。
    优先直接解析；失败时从文本中提取 [...] 片段再解析。
    """
    if not review_str:
        logger.warning("警告：输入字符串为空，无法解析")
        return []

    if not isinstance(review_str, str):
        logger.warning(f"警告：输入不是字符串格式，类型为 {type(review_str)}，无法解析")
        return []

    processed_str = review_str.strip()
    if processed_str.startswith("\ufeff"):
        processed_str = processed_str[1:]
    if (processed_str.startswith('"') and processed_str.endswith('"')) or (
        processed_str.startswith("'") and processed_str.endswith("'")
    ):
        processed_str = processed_str[1:-1]

    if not processed_str:
        logger.warning("警告：预处理后字符串为空，无法解析")
        return []

    try:
        parsed_data = json.loads(processed_str)
        if not isinstance(parsed_data, list):
            parsed_data = [parsed_data]
        return parsed_data
    except json.JSONDecodeError as e:
        logger.error(f"JSON 直接解析失败: {e}")

    logger.critical("JSON 直接解析失败，尝试从文本中提取数组片段")
    try:
        start_idx = processed_str.find("[")
        end_idx = processed_str.rfind("]")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_fragment = processed_str[start_idx : end_idx + 1]
            parsed_data = json.loads(json_fragment)
            if not isinstance(parsed_data, list):
                parsed_data = [parsed_data]
            logger.info(f"从片段中解析成功，包含 {len(parsed_data)} 个评审项")
            return parsed_data
    except Exception as e:
        logger.error(f"片段提取和解析也失败：{e}")

    logger.critical("JSON 解析彻底失败，返回空列表")
    return []
