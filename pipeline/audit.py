"""纯审核管线：PDF 字节入 → 报告出，不写数据库。"""

from __future__ import annotations

import asyncio
import logging
import time

from model import get_llm_api
from postprocess import parse_review_str, process_review_results
from preprocess import clean_text_pageofnum, extract_pdf, splitpdf
from prompt import prompt_rule

logger = logging.getLogger("PDF-Audit-API")


async def build_prompts_from_pdf(pdf_bytes: bytes) -> tuple[list[str], dict]:
    """前处理到 prompt 生成，不调用 LLM。

    返回 (prompts, meta)，meta 含 modules 键列表、last_page_num、图像标记等。
    """
    truncated_text, has_global_image, has_section23_image, has_tech_route_image = (
        await asyncio.to_thread(extract_pdf, pdf_bytes)
    )
    if not truncated_text:
        raise ValueError("PDF内容为空")
    cleaned_text, last_page_num = await asyncio.to_thread(
        clean_text_pageofnum, truncated_text
    )
    modules = await asyncio.to_thread(splitpdf, cleaned_text)
    prompts = prompt_rule(
        modules,
        last_page_num,
        has_global_image,
        has_section23_image,
        has_tech_route_image,
    )
    meta = {
        "module_keys": list(modules.keys()),
        "module_lengths": {k: len(v or "") for k, v in modules.items()},
        "last_page_num": last_page_num,
        "has_global_image": has_global_image,
        "has_section23_image": has_section23_image,
        "has_tech_route_image": has_tech_route_image,
        "prompt_count": len(prompts),
        "prompt_lengths": [len(p) for p in prompts],
    }
    return prompts, meta


async def audit_pdf_bytes(
    pdf_bytes: bytes, item_id: str, pdf_source: str = "", priority: int = 0
) -> dict:
    """从 PDF 字节流执行完整审核管线，不写数据库。

    priority: 该 PDF 在 API 阶段的优先级（数值越小越优先，按提交顺序）。
    """
    start_time = time.time()
    logger.info(f"开始处理PDF: {item_id}")
    try:
        prompts, _meta = await build_prompts_from_pdf(pdf_bytes)
        llm_api = get_llm_api()
        tasks = [llm_api(prompt, priority=priority) for prompt in prompts]
        results = await asyncio.gather(*tasks)
        all_reviews = []
        for result in results:
            parsed = parse_review_str(result)
            if parsed:
                all_reviews.extend(parsed)
        final_report = process_review_results(all_reviews)
        processing_time = round(time.time() - start_time, 2)
        return {
            "item_id": item_id,
            "pdf_source": pdf_source,
            "status": "success",
            "processing_time": processing_time,
            "result": final_report,
            "rule_count": len(all_reviews),
        }
    except Exception as e:
        processing_time = round(time.time() - start_time, 2)
        logger.error(f"处理失败 {item_id}: {e}")
        return {
            "item_id": item_id,
            "pdf_source": pdf_source,
            "status": "error",
            "processing_time": processing_time,
            "error_message": str(e),
        }
