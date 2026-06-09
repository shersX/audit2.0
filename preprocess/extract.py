import io
import re

import fitz
from pypdf import PdfReader


def _extract_page_text(reader: PdfReader, fitz_doc: fitz.Document, page_idx: int) -> str:
    """优先 pypdf 抽文本；单页失败时降级 fitz。"""
    try:
        return reader.pages[page_idx].extract_text() or ""
    except Exception:
        return fitz_doc[page_idx].get_text() or ""


def extract_pdf(file_bytes: bytes):
    SENTENCES = "对其他来源资金的经费来源、资金具体开支用途做简要说明。"

    MODULE2_FULL = "二、立项依据"
    MODULE2_CORE = "立项依据"
    MODULE3_FULL = "三、项目的研究内容、研究目标，以及拟解决的关键科学问题"
    MODULE3_CORE = "项目的研究内容、研究目标，以及拟解决的关键科学问题"
    MODULE4_FULL = "四、拟采取的研究方案及可行性分析"
    MODULE4_CORE = "拟采取的研究方案及可行性分析"
    MODULE5_FULL = "五、本项目的特色与创新之处"
    MODULE5_CORE = "本项目的特色与创新之处"

    reader = PdfReader(io.BytesIO(file_bytes))
    fitz_doc = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
    total_pages = len(reader.pages)

    page_texts = []
    truncated_text = ""
    cutoff_page_idx = None
    module2_page_idx = None
    module3_page_idx = None
    module4_page_idx = None
    module5_page_idx = None

    pattern_module2 = re.compile(
        f"{re.escape(MODULE2_FULL)}|{re.escape(MODULE2_CORE)}", flags=re.UNICODE
    )
    pattern_module3 = re.compile(
        f"{re.escape(MODULE3_FULL)}|{re.escape(MODULE3_CORE)}", flags=re.UNICODE
    )
    pattern_module4 = re.compile(
        f"{re.escape(MODULE4_FULL)}|{re.escape(MODULE4_CORE)}", flags=re.UNICODE
    )
    pattern_module5 = re.compile(
        f"{re.escape(MODULE5_FULL)}|{re.escape(MODULE5_CORE)}", flags=re.UNICODE
    )
    pattern_terminal = re.compile(re.escape(SENTENCES))

    for page_idx in range(total_pages):
        page_text = _extract_page_text(reader, fitz_doc, page_idx)
        page_texts.append(page_text)

        if module2_page_idx is None and pattern_module2.search(page_text):
            module2_page_idx = page_idx
        if module3_page_idx is None and pattern_module3.search(page_text):
            module3_page_idx = page_idx
        if module4_page_idx is None and pattern_module4.search(page_text):
            module4_page_idx = page_idx
        if module5_page_idx is None and pattern_module5.search(page_text):
            module5_page_idx = page_idx

        terminal_match = pattern_terminal.search(page_text)
        if terminal_match:
            prefix = "".join(p + "\n" for p in page_texts[:-1])
            truncated_text = prefix + page_text[: terminal_match.end()]
            cutoff_page_idx = page_idx
            break
    if cutoff_page_idx is None:
        truncated_text = "".join(p + "\n" for p in page_texts)
        cutoff_page_idx = total_pages - 1

    has_global_image = False
    has_section23_image = False
    has_tech_route_image = False

    for page_idx in range(cutoff_page_idx + 1):
        page = fitz_doc[page_idx]
        current_page_has_img = len(page.get_images(full=True)) > 0

        if current_page_has_img:
            has_global_image = True

        in_section23 = False
        if module2_page_idx is not None and module3_page_idx is not None:
            if module2_page_idx <= page_idx <= module3_page_idx:
                in_section23 = True
        if in_section23 and current_page_has_img and not has_section23_image:
            has_section23_image = True

        in_target_section = False
        if module4_page_idx is not None and module5_page_idx is not None:
            if module4_page_idx <= page_idx <= module5_page_idx:
                in_target_section = True
        if in_target_section and current_page_has_img:
            has_tech_route_image = True

    fitz_doc.close()
    return truncated_text, has_global_image, has_section23_image, has_tech_route_image
