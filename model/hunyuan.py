#deepseek-v4-pro 	TPM:1000000 / QPM:60
#	hy3-preview 	TPM:1000000 / QPM:60
import asyncio
import logging
import os

from openai import AsyncOpenAI

from model.common import api_semaphore
from model.schemas import REVIEW_RESPONSE_FORMAT

logger = logging.getLogger("PDF-Audit-API")

hunyuan_client = AsyncOpenAI(
    api_key=os.environ.get("HUNYUAN_API_KEY"),
    base_url="https://tokenhub.tencentmaas.com/v1",
)


async def hunyuanAPI(prompt, retry_count=3):
    """异步调用混元 API，带重试机制。"""
    for attempt in range(retry_count):
        try:
            async with api_semaphore:
                completion = await hunyuan_client.chat.completions.create(
                    model="kimi-k2.6",
                    messages=[{"role": "user", "content": prompt}],
                    response_format=REVIEW_RESPONSE_FORMAT,
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
