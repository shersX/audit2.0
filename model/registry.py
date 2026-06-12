"""LLM provider 注册表，供 app 与 eval 切换模型。"""
import os
from collections.abc import Awaitable, Callable

from model.doubao import doubaoAPI
from model.hunyuan import hunyuanAPI

LLMCallable = Callable[..., Awaitable[str]]

PROVIDERS: dict[str, LLMCallable] = {
    "hunyuan": hunyuanAPI,
    "doubao": doubaoAPI,
}

DEFAULT_PROVIDER = "hunyuan"


def resolve_provider(provider: str | None = None) -> str:
    return (provider or os.environ.get("AUDIT_LLM_PROVIDER") or DEFAULT_PROVIDER).lower()


def get_llm_api(provider: str | None = None) -> LLMCallable:
    name = resolve_provider(provider)
    if name not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"未知模型 provider: {name}，可选: {available}")
    return PROVIDERS[name]
