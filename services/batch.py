"""批量任务编排：下载 → 管线 → 校验 → 写库。"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from config import DEFAULT_MAX_WORKERS, EXPECTED_RULE_COUNT
from pipeline.audit import audit_pdf_bytes
from services.download import download_pdf
from services.errors import build_error_entry, save_errors_json
from services.store import set_error, set_processing, set_success

if TYPE_CHECKING:
    from api.schemas import PDFItem

logger = logging.getLogger("PDF-Audit-API")


async def process_pdf(pdf_url: str, item_id: str, priority: int = 0):
    """下载 PDF 并执行审核，生成评估报告并写入数据库。

    priority: 该 PDF 在 API 阶段的优先级（数值越小越优先，按提交顺序）。
    """
    url_str = str(pdf_url)
    pdf_bytes = await download_pdf(url_str)
    if not pdf_bytes:
        result = {
            "item_id": item_id,
            "pdf_url": url_str,
            "status": "error",
            "processing_time": 0,
            "error_message": "PDF下载失败",
        }
        set_error(item_id, result["error_message"], 0)
        return result

    audit_result = await audit_pdf_bytes(
        pdf_bytes, item_id, url_str, priority=priority
    )
    processing_time = audit_result.get("processing_time", 0)

    if audit_result["status"] == "success":
        rule_count = audit_result.get("rule_count", 0)
        if rule_count != EXPECTED_RULE_COUNT:
            error_message = (
                f"规则条数异常: 期望 {EXPECTED_RULE_COUNT}, 实际 {rule_count}"
            )
            set_error(item_id, error_message, processing_time)
            return {
                "item_id": item_id,
                "pdf_url": url_str,
                "status": "error",
                "processing_time": processing_time,
                "error_message": error_message,
                "rule_count": rule_count,
                "parsed_rows": rule_count,
            }

        set_success(item_id, audit_result["result"], processing_time)
        return {
            "item_id": item_id,
            "pdf_url": url_str,
            "status": "success",
            "processing_time": processing_time,
            "result": audit_result["result"],
        }

    error_message = audit_result.get("error_message", "未知错误")
    set_error(item_id, error_message, processing_time)
    return {
        "item_id": item_id,
        "pdf_url": url_str,
        "status": "error",
        "processing_time": processing_time,
        "error_message": error_message,
    }


async def process_all_items(
    items: list[PDFItem],
    total_items: int,
    max_workers: int = DEFAULT_MAX_WORKERS,
    run_id: str = "",
):
    """使用异步队列控制并发处理"""
    completed_count = 0
    count_lock = asyncio.Lock()
    errors: list[dict] = []
    errors_lock = asyncio.Lock()
    queue: asyncio.Queue = asyncio.Queue()

    for priority, item in enumerate(items):
        await queue.put((priority, item))

    async def record_failure(
        item: PDFItem, error: str, parsed_rows: int | None = None
    ) -> None:
        async with errors_lock:
            errors.append(
                build_error_entry(item.id, str(item.url), error, parsed_rows)
            )
            if run_id:
                try:
                    save_errors_json(run_id, errors)
                except Exception as save_err:
                    logger.warning(f"流式写盘 errors.json 失败: {save_err}")

    async def worker():
        nonlocal completed_count
        while True:
            try:
                priority, item = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                set_processing(item.id)
                result = await process_pdf(item.url, item.id, priority=priority)
                if result.get("status") != "success":
                    await record_failure(
                        item,
                        result.get("error_message", "未知错误"),
                        result.get("parsed_rows"),
                    )
                    async with count_lock:
                        completed_count += 1
                    logger.error(
                        f"任务 {completed_count}/{total_items} 处理失败: {item.id} - "
                        f"{result.get('error_message')}"
                    )
                else:
                    async with count_lock:
                        completed_count += 1
                    logger.info(
                        f"任务 {completed_count}/{total_items} 处理完成: {item.id}"
                    )
            except Exception as e:
                error_message = str(e)
                set_error(item.id, error_message)
                await record_failure(item, error_message)
                async with count_lock:
                    completed_count += 1
                logger.error(
                    f"任务 {completed_count}/{total_items} 处理失败: {item.id} - {e}"
                )
            finally:
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(max_workers)]
    await queue.join()
    await asyncio.gather(*workers)
    if run_id:
        save_errors_json(run_id, errors)
