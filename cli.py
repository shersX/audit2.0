"""本地联调入口：不经 FastAPI / 下载 / DB，直接跑管线。

用法:
  python -m cli --pdf path/to/file.pdf --item-id local_001
  python -m cli --pdf path/to/file.pdf --dry-prompt --module 1
  python -m cli --pdf path/to/file.pdf --out out.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from config import EXPECTED_RULE_COUNT
from pipeline.audit import audit_pdf_bytes, build_prompts_from_pdf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("PDF-Audit-CLI")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地 PDF 审核联调（跳过下载与 DB）")
    parser.add_argument("--pdf", required=True, help="本地 PDF 路径")
    parser.add_argument("--item-id", default="local_001", help="任务标识")
    parser.add_argument(
        "--dry-prompt",
        action="store_true",
        help="只跑前处理与 prompt 生成，不调用 LLM",
    )
    parser.add_argument(
        "--module",
        type=int,
        default=None,
        help="配合 --dry-prompt：落盘第 N 个模块 prompt（1-based）",
    )
    parser.add_argument("--out", default=None, help="将结果写入 JSON 文件")
    parser.add_argument(
        "--no-rule-count-check",
        action="store_true",
        help="跳过规则条数 == 49 校验（便于排查解析问题）",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        logger.error(f"PDF 不存在: {pdf_path}")
        return 1

    pdf_bytes = pdf_path.read_bytes()
    pdf_source = str(pdf_path.resolve())

    if args.dry_prompt:
        prompts, meta = await build_prompts_from_pdf(pdf_bytes)
        payload = {
            "item_id": args.item_id,
            "pdf_source": pdf_source,
            "mode": "dry-prompt",
            "meta": meta,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if args.module is not None:
            idx = args.module - 1
            if idx < 0 or idx >= len(prompts):
                logger.error(
                    f"--module 超出范围: {args.module}（共 {len(prompts)} 个）"
                )
                return 1
            out_prompt = Path(args.out) if args.out else Path(f"module_{args.module}.txt")
            out_prompt.write_text(prompts[idx], encoding="utf-8")
            logger.info(f"已写入模块 prompt: {out_prompt}")
        elif args.out:
            Path(args.out).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return 0

    result = await audit_pdf_bytes(
        pdf_bytes, args.item_id, pdf_source=pdf_source, priority=0
    )

    if (
        result.get("status") == "success"
        and not args.no_rule_count_check
        and result.get("rule_count") != EXPECTED_RULE_COUNT
    ):
        rule_count = result.get("rule_count", 0)
        result = {
            **result,
            "status": "error",
            "error_message": (
                f"规则条数异常: 期望 {EXPECTED_RULE_COUNT}, 实际 {rule_count}"
            ),
            "parsed_rows": rule_count,
        }

    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        logger.info(f"结果已写入: {args.out}")

    return 0 if result.get("status") == "success" else 1


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
