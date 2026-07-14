import os
from openai import OpenAI

siliconflow_client = OpenAI(
    api_key=os.environ.get("SILICONFLOW_API_KEY"),
    base_url="https://api.siliconflow.cn/v1"
)

response = siliconflow_client.chat.completions.create(
    model="zai-org/GLM-5.2",
    messages=[
        {"role": "system", "content": "你是一个有用的助手"},
        {"role": "user", "content": "你好，请介绍一下你自己"}
    ]
)
print(response.choices[0].message.content)
print(response)
