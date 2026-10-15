"""PDF 下载（带重试）。"""

from __future__ import annotations

import asyncio
import logging

import httpx

from config import DOWNLOAD_RETRY_COUNT, DOWNLOAD_RETRY_DELAY, DOWNLOAD_TIMEOUT

logger = logging.getLogger("PDF-Audit-API")


async def download_pdf(
    url: str,
    retry_count: int = DOWNLOAD_RETRY_COUNT,
    retry_delay: int = DOWNLOAD_RETRY_DELAY,
):
    """下载PDF文件，带重试机制"""
    url_str = str(url)
    if not url_str.startswith(("http://", "https://")):
        raise ValueError("无效的URL协议")

    for attempt in range(retry_count):
        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
                response = await client.get(url_str)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "").lower()
                if "pdf" not in content_type:
                    if "text/html" in content_type:
                        raise ValueError("URL指向的是一个HTML页面，而不是PDF文件")
                    raise ValueError(
                        f"URL指向的文件不是PDF格式 (Content-Type: {content_type})"
                    )
                return response.content
        except Exception as e:
            logger.warning(f"下载PDF失败 (尝试 {attempt + 1}/{retry_count}): {e}")
            if attempt < retry_count - 1:
                await asyncio.sleep(retry_delay)
            else:
                logger.error(
                    f"下载PDF彻底失败，已达到最大重试次数 {retry_count}: {e}"
                )
                return None
    return None
