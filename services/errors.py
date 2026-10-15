"""批次失败记录落盘。"""

from __future__ import annotations

import json
import logging
from urllib.parse import unquote, urlparse

from config import RUNS_DIR

logger = logging.getLogger("PDF-Audit-API")


def pdf_filename_from_url(url: str) -> str:
    name = unquote(urlparse(str(url)).path.split("/")[-1])
    return name or str(url)


def build_error_entry(
    item_id: str, pdf_url: str, error: str, parsed_rows: int | None = None
) -> dict:
    entry = {
        "sample_id": item_id,
        "pdf": pdf_filename_from_url(pdf_url),
        "error": error,
    }
    if parsed_rows is not None:
        entry["parsed_rows"] = parsed_rows
    return entry


def save_errors_json(run_id: str, errors: list[dict]) -> None:
    if not errors:
        return
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    err_path = run_dir / "errors.json"
    with err_path.open("w", encoding="utf-8") as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)
    logger.info(f"失败记录已写入: {err_path} ({len(errors)} 条)")
