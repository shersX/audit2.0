"""HTTP 路由：只负责请求校验与调用 store / batch。"""

from __future__ import annotations

import time
from typing import List

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.schemas import PDFItem
from config import API_VERSION, DEFAULT_MAX_WORKERS
from services.batch import process_all_items
from services.store import get_item, insert_waiting_batch, list_items, list_items_raw

router = APIRouter()


@router.get("/audit/health", tags=["健康检查"])
def health_check():
    return {
        "status": "success",
        "service": "内容审查API",
        "version": API_VERSION,
    }


@router.post("/audit")
async def audit(audit_request: List[PDFItem], background_tasks: BackgroundTasks):
    if not audit_request:
        raise HTTPException(status_code=400, detail="请求体不能为空")
    total_items = len(audit_request)

    insert_waiting_batch(
        [(item.id, str(item.url)) for item in audit_request]
    )

    run_id = time.strftime("%Y%m%d_%H%M%S")
    background_tasks.add_task(
        process_all_items, audit_request, total_items, DEFAULT_MAX_WORKERS, run_id
    )
    return {
        "status": "success",
        "run_id": run_id,
        "message": (
            f"审查任务已创建，共 {total_items} 个任务，run_id={run_id}，"
            f"失败记录见 runs/{run_id}/errors.json，可通过 GET /audit/{{item_id}} 查询状态"
        ),
    }


@router.get("/audit/items", tags=["查询任务列表"])
def get_items():
    """结构化任务列表（前端用，不含完整 result）。"""
    return list_items()


@router.get("/audit/all_items", tags=["查询所有任务"])
def get_all_items():
    return list_items_raw()


@router.get("/audit/{item_id}")
def get_item_result(item_id: str):
    """获取单个项目的处理结果"""
    row = get_item(item_id)
    if not row:
        return {"item_id": item_id, "status": "failure"}
    return row
