#RPM 500 TPM 2000000
import asyncio
import logging
import os

from openai import AsyncOpenAI

from model.common import api_semaphore
from model.usage import record_token_usage

logger = logging.getLogger("PDF-Audit-API")

_ali_client = None


def get_ali_client() -> AsyncOpenAI:
    global _ali_client
    if _ali_client is None:
        _ali_client = AsyncOpenAI(
            api_key=os.environ.get("DASHSCOPE_API_KEY"),
            base_url="https://llm-g1mu7oh8mmt15g0y.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        )
    return _ali_client


async def aliAPI(prompt, priority=0, retry_count=3):
    client = get_ali_client()
    for attempt in range(retry_count):
        try:
            async with api_semaphore.context(priority):
                completion = await client.chat.completions.create(
                    model="glm-5.2",
                    messages=[{"role": "user", "content": prompt}],
                )
                if completion.usage:
                    await record_token_usage(
                        completion.usage, provider="ali", model="glm-5.2"
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


if __name__ == "__main__":
    print(asyncio.run(aliAPI("你好，请介绍一下你自己")))
