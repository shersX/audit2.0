"""SQLite 任务状态存储。"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from config import DB_PATH


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def init_db() -> None:
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_items (
                item_id TEXT PRIMARY KEY,
                pdf_url TEXT,
                status TEXT,
                result TEXT,
                error_message TEXT,
                processing_time REAL,
                create_time TEXT
            )
            """
        )
        conn.commit()


def insert_waiting(item_id: str, pdf_url: str, create_time: str | None = None) -> None:
    if create_time is None:
        create_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO audit_items
            (item_id, pdf_url, status, create_time)
            VALUES (?, ?, ?, ?)
            """,
            (item_id, pdf_url, "waiting", create_time),
        )
        conn.commit()


def insert_waiting_batch(items: list[tuple[str, str]]) -> None:
    """items: [(item_id, pdf_url), ...]"""
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    with _connect() as conn:
        cursor = conn.cursor()
        for item_id, pdf_url in items:
            cursor.execute(
                """
                INSERT OR REPLACE INTO audit_items
                (item_id, pdf_url, status, create_time)
                VALUES (?, ?, ?, ?)
                """,
                (item_id, pdf_url, "waiting", current_time),
            )
        conn.commit()


def set_processing(item_id: str) -> None:
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE audit_items SET status = ? WHERE item_id = ?",
            ("processing", item_id),
        )
        conn.commit()


def set_success(item_id: str, result: Any, processing_time: float) -> None:
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE audit_items
            SET status = 'success', result = ?, error_message = NULL, processing_time = ?
            WHERE item_id = ?
            """,
            (json.dumps(result, ensure_ascii=False), processing_time, item_id),
        )
        conn.commit()


def set_error(
    item_id: str, error_message: str, processing_time: float = 0
) -> None:
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE audit_items
            SET status = 'error', result = NULL, error_message = ?, processing_time = ?
            WHERE item_id = ?
            """,
            (error_message, processing_time, item_id),
        )
        conn.commit()


def list_items_raw() -> list[tuple]:
    """返回 SELECT * 原始元组列表，保持 /audit/all_items 兼容。"""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_items")
        return cursor.fetchall()


def get_item(item_id: str) -> dict | None:
    """返回结构化任务记录；不存在返回 None。"""
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT item_id, pdf_url, status, result, error_message, processing_time, create_time
            FROM audit_items
            WHERE item_id = ?
            """,
            (item_id,),
        )
        row = cursor.fetchone()

    if not row:
        return None

    item_id_, pdf_url, status, result, error_message, processing_time, create_time = row
    return {
        "item_id": item_id_,
        "pdf_url": pdf_url,
        "status": status,
        "result": json.loads(result) if result and status == "success" else None,
        "error_message": error_message,
        "processing_time": processing_time,
        "create_time": create_time,
    }
