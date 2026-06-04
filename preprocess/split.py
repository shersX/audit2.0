import logging
import re

logger = logging.getLogger("PDF-Audit-API")


def splitpdf(text):
    text = "".join(c for c in text if c.isprintable() or c in "\n\r\t")
    pattern = r"课题名称"
    all_pa = list(re.finditer(pattern, text))
    second_ktmc_start = None
    if len(all_pa) >= 2:
        second_ktmc_start = all_pa[1].start()

    title_info = [
        ("二、立项依据", "立项依据"),
        (
            "三、项目的研究内容、研究目标，以及拟解决的关键科学问题",
            "项目的研究内容、研究目标，以及拟解决的关键科学问题",
        ),
        ("四、拟采取的研究方案及可行性分析", "拟采取的研究方案及可行性分析"),
        ("五、本项目的特色与创新之处", "本项目的特色与创新之处"),
        ("六、年度研究计划及预期研究结果", "年度研究计划及预期研究结果"),
        ("七、研究基础与工作条件", "研究基础与工作条件"),
        ("八、申请人简介", "申请人简介"),
        ("项目预算表", "项目预算表"),
    ]
    titles = [item[0] for item in title_info]
    keywords = [item[1] for item in title_info]

    matches = [re.search(re.escape(t), text) for t in titles]

    for i, (match, keyword) in enumerate(zip(matches, keywords)):
        if not match:
            flexible_pattern = (
                rf"^\s*(?:[一二三四五六七八九十]+|\d+)\s*[、.）]\s*{re.escape(keyword)}"
            )
            flexible_match = re.search(flexible_pattern, text, re.MULTILINE)
            if flexible_match:
                matches[i] = flexible_match
                logger.info(f"使用灵活匹配成功匹配标题：{titles[i]}")

    valid_matches = [(i, match) for i, match in enumerate(matches) if match]
    if valid_matches:
        valid_matches.sort(key=lambda x: x[1].start())
        fixed_matches = matches.copy()
        last_pos = -1
        for idx, match in valid_matches:
            current_start = match.start()
            if current_start < last_pos:
                fixed_matches[idx] = None
            else:
                last_pos = current_start
        matches = fixed_matches

    modules = {}
    if second_ktmc_start is not None:
        modules["封面"] = text[:second_ktmc_start].strip()
        if matches[0]:
            modules["一、课题项目概览"] = text[second_ktmc_start : matches[0].start()].strip()
        else:
            modules["一、课题项目概览"] = text[second_ktmc_start:].strip()
    else:
        modules["封面"] = ""
        if matches[0]:
            modules["一、课题项目概览"] = text[: matches[0].start()].strip()
        else:
            modules["一、课题项目概览"] = text.strip()

    for i, (title, match) in enumerate(zip(titles, matches)):
        if not match:
            modules[title] = ""
            logger.warning(f"未匹配到标题：{title}")
            continue

        next_match = None
        for j in range(i + 1, len(matches)):
            if matches[j]:
                next_match = matches[j]
                break

        start = match.end()
        end = next_match.start() if next_match else len(text)

        if start < end:
            modules[title] = text[start:end].strip()
        else:
            modules[title] = ""
            logger.warning(f"标题 {title} 的结束位置早于或等于开始位置，无法提取内容")

    if not matches[7]:
        modules["项目预算表"] = ""
        logger.info("项目预算表未匹配到，将剩余内容并入八、申请人简介")

        if matches[6]:
            start = matches[6].end()
            modules["八、申请人简介"] = text[start:].strip()
        elif matches[5]:
            modules["八、申请人简介"] = ""
            start = matches[5].end()
            modules["七、研究基础与工作条件"] = text[start:].strip()
    elif not matches[6]:
        modules["八、申请人简介"] = ""
        modules["项目预算表"] = ""
        logger.info("申请人简介未匹配到，将剩余内容并入七、研究基础与工作条件")

        if matches[5]:
            start = matches[5].end()
            modules["七、研究基础与工作条件"] = text[start:].strip()

    return modules
