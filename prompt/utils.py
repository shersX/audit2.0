"""Prompt 辅助工具。"""

import re


def count_chinese_chars(text: str) -> int:
    """
    统计中文字数（Unicode 范围 \u4e00-\u9fff）
    同时将连续英文/数字视为“一个字”（符合科研写作习惯）
    """
    # 提取所有中文字符
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    # 提取英文单词和数字（避免把 'CRISPR-Cas9' 算成10个字符）
    english_words = re.findall(r'[a-zA-Z]+|\d+', text)
    #print(f"中文字符数: {len(chinese_chars)},英文单词/数字项数: {len(english_words)}")
    # 总“字数” ≈ 中文字符数 + 英文单词/数字项数
    return len(chinese_chars) + len(english_words)

