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
    """
    PDF标书统一解析入口函数
    整体能力：
        1. 遍历PDF所有页面，抽取全文文本，匹配指定终止语句做文本截断（只取终止句之前的内容）
        2. 定位【立项依据】【研究内容】【研究方案】等固定章节所在页码
        3. 扫描截断范围内所有页面，判别三类图片标记：全局是否有图、立项依据段是否配图、研究方案段是否配图
    :param file_bytes: 上传PDF文件的二进制字节流，内存读取无需存本地文件
    :return: truncated_text(截断后的正文), has_global_image(全文是否含图片), has_section23_image(立项依据区有无图片), has_tech_route_image(研究方案区有无图片)
    """

    SENTENCES = "对其他来源资金的经费来源、资金具体开支用途做简要说明。"
    FALLBACK = "三、其他来源资金"

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

    # 容器：按页码顺序存放每一页提取出来的原始文本
    page_texts = []
    # 最终对外输出的、截断完毕的PDF全文文本
    truncated_text = ""
    cutoff_page_idx = None
    module2_page_idx = None
    module3_page_idx = None
    module4_page_idx = None
    module5_page_idx = None

    # ========== 编译正则匹配规则（预编译提升循环匹配效率） ==========
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

    # ========== 逐页遍历PDF，提取文本 + 定位章节页码 + 寻找截断点 ==========
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

        # ========== 检测当前页是否包含终止语句 ==========
        terminal_match = pattern_terminal.search(page_text)
        if terminal_match:
            prefix = "".join(p + "\n" for p in page_texts[:-1])
            truncated_text = prefix + page_text[: terminal_match.end()]
            cutoff_page_idx = page_idx
            break
        
    if cutoff_page_idx is None:
        full_text = "".join(p + "\n" for p in page_texts)
        fb_pos = full_text.rfind(FALLBACK)
        if fb_pos != -1:
            truncated_text = full_text[: fb_pos + len(FALLBACK)]
            cum = 0
            cutoff_page_idx = total_pages - 1
            for pi, p in enumerate(page_texts):
                cum += len(p) + 1
                if fb_pos + len(FALLBACK) <= cum:
                    cutoff_page_idx = pi
                    break
        else:
            truncated_text = full_text
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
