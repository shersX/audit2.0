#deepseek-v4-pro 	TPM:1000000 / QPM:60
#	hy3-preview 	TPM:1000000 / QPM:60
import asyncio
import logging
import os

from openai import AsyncOpenAI

from model.common import api_semaphore
from model.schemas import REVIEW_RESPONSE_FORMAT

logger = logging.getLogger("PDF-Audit-API")

_hunyuan_client = None


def get_hunyuan_client() -> AsyncOpenAI:
    global _hunyuan_client
    if _hunyuan_client is None:
        _hunyuan_client = AsyncOpenAI(
            api_key=os.environ.get("chenlei-yanfa200"),
            base_url="https://tokenhub.tencentmaas.com/v1",
        )
    return _hunyuan_client


async def hunyuanAPI(prompt, priority=0, retry_count=3):
    """异步调用混元 API，带重试机制。

    priority: 优先级（数值越小越优先，按 PDF 提交顺序传入）。
    """
    client = get_hunyuan_client()
    for attempt in range(retry_count):
        try:
            async with api_semaphore.context(priority):
                completion = await client.chat.completions.create(
                    model="glm-5.2",
                    messages=[{"role": "user", "content": prompt}]
                )
                return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"API调用失败 (尝试 {attempt+1}/{retry_count}): {e}")
            if attempt < retry_count - 1:
                logger.info("等待3秒后重试...")
                await asyncio.sleep(3)
            else:
                logger.critical(f"API调用彻底失败，已达到最大重试次数 {retry_count}")
                return ""
    return ""
