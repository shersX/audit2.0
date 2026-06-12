# 30,000 RPM / 5,000,000 TPM
import asyncio
import logging
import os

from openai import AsyncOpenAI

from model.common import api_semaphore
from model.schemas import REVIEW_RESPONSE_FORMAT

logger = logging.getLogger("PDF-Audit-API")

DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DOUBAO_MODEL = os.environ.get("DOUBAO_MODEL", "doubao-seed-2-0-pro-260215")

doubao_client = AsyncOpenAI(
    base_url=DOUBAO_BASE_URL,
    api_key=os.environ.get("DOUBAO_API_KEY"),
)


async def doubaoAPI(prompt, priority=0, retry_count=3):
    """异步调用豆包 API，带重试机制。

    priority: 优先级（数值越小越优先，按 PDF 提交顺序传入）。
    """
    for attempt in range(retry_count):
        try:
            async with api_semaphore.context(priority):
                completion = await doubao_client.chat.completions.create(
                    model=DOUBAO_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    #response_format=REVIEW_RESPONSE_FORMAT,
                )
                return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"豆包 API 调用失败 (尝试 {attempt+1}/{retry_count}): {e}")
            if attempt < retry_count - 1:
                logger.info("等待3秒后重试...")
                await asyncio.sleep(3)
            else:
                logger.critical(f"豆包 API 调用彻底失败，已达到最大重试次数 {retry_count}")
                return ""
    return ""
