"""跨请求累计 LLM token 用量（供 eval run_batch 统计）。"""
import asyncio
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class TokenUsage:
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    request_count: int = 0

    def add(self, usage, *, provider: str = "", model: str = "") -> None:
        if not usage:
            return
        if provider:
            self.provider = provider
        if model:
            self.model = model
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        total = int(getattr(usage, "total_tokens", 0) or 0)
        if not total:
            total = prompt + completion
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += total
        self.request_count += 1

    def summary_line(self) -> str:
        return (
            f"Token 累计: 输入 {self.prompt_tokens:,} + 输出 {self.completion_tokens:,} "
            f"= 合计 {self.total_tokens:,}（{self.request_count} 次请求）"
        )


_tracker = TokenUsage()
_lock = asyncio.Lock()


def get_token_usage() -> TokenUsage:
    return _tracker


def reset_token_usage() -> None:
    global _tracker
    _tracker = TokenUsage()


def load_token_usage(path: Path) -> None:
    global _tracker
    if not path.exists():
        reset_token_usage()
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    _tracker = TokenUsage(**{k: data[k] for k in asdict(TokenUsage()) if k in data})


async def record_token_usage(usage, *, provider: str = "", model: str = "") -> None:
    async with _lock:
        _tracker.add(usage, provider=provider, model=model)


def save_token_usage(path: Path) -> TokenUsage:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(_tracker), ensure_ascii=False, indent=2), encoding="utf-8")
    return _tracker
