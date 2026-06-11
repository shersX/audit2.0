import logging,asyncio,uvicorn,os,httpx
from fastapi import FastAPI,HTTPException,BackgroundTasks
from pydantic import BaseModel,HttpUrl
import json
import time
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse
from prompt import prompt_rule
from model.hunyuan import hunyuanAPI
from preprocess import extract_pdf, clean_text_pageofnum, splitpdf
from postprocess import parse_review_str, process_review_results
from typing import List

EXPECTED_RULE_COUNT = 49
RUNS_DIR = Path("runs")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger=logging.getLogger("PDF-Audit-API")

app=FastAPI(title="PDF-Audit-API",summary="PDF审核API",version="2.0.0")

class PDFItem(BaseModel):
    url: HttpUrl
    id: str


def _pdf_filename_from_url(url: str) -> str:
    name = unquote(urlparse(str(url)).path.split("/")[-1])
    return name or str(url)


def _build_error_entry(item_id: str, pdf_url: str, error: str, parsed_rows: int | None = None) -> dict:
    entry = {
        "sample_id": item_id,
        "pdf": _pdf_filename_from_url(pdf_url),
        "error": error,
    }
    if parsed_rows is not None:
        entry["parsed_rows"] = parsed_rows
    return entry


def _save_errors_json(run_id: str, errors: list[dict]) -> None:
    if not errors:
        return
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    err_path = run_dir / "errors.json"
    with err_path.open("w", encoding="utf-8") as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)
    logger.info(f"失败记录已写入: {err_path} ({len(errors)} 条)")


def _update_item_status(item_id: str, status: str) -> None:
    with sqlite3.connect("audit.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE audit_items SET status = ? WHERE item_id = ?",
            (status, item_id),
        )
        conn.commit()


def _update_item_error(item_id: str, error_message: str, processing_time: float = 0) -> None:
    with sqlite3.connect("audit.db") as conn:
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


async def audit_pdf_bytes(pdf_bytes: bytes, item_id: str, pdf_source: str = "", priority: int = 0) -> dict:
    """从 PDF 字节流执行完整审核管线，不写数据库。

    priority: 该 PDF 在 API 阶段的优先级（数值越小越优先，按提交顺序）。
    """
    start_time = time.time()
    logger.info(f"开始处理PDF: {item_id}")
    try:
        truncated_text, has_global_image, has_section23_image, has_tech_route_image = \
            await asyncio.to_thread(extract_pdf, pdf_bytes)
        if not truncated_text:
            raise ValueError("PDF内容为空")
        cleaned_text, last_page_num = await asyncio.to_thread(clean_text_pageofnum, truncated_text)
        modules = await asyncio.to_thread(splitpdf, cleaned_text)
        prompts = prompt_rule(
            modules, last_page_num, has_global_image, has_section23_image, has_tech_route_image
        )
        tasks = [hunyuanAPI(prompt, priority=priority) for prompt in prompts]
        results = await asyncio.gather(*tasks)
        all_reviews = []
        for result in results:
            parsed = parse_review_str(result)
            if parsed:
                all_reviews.extend(parsed)
        final_report = process_review_results(all_reviews)
        processing_time = round(time.time() - start_time, 2)
        return {
            "item_id": item_id,
            "pdf_source": pdf_source,
            "status": "success",
            "processing_time": processing_time,
            "result": final_report,
            "rule_count": len(all_reviews),
        }
    except Exception as e:
        processing_time = round(time.time() - start_time, 2)
        logger.error(f"处理失败 {item_id}: {e}")
        return {
            "item_id": item_id,
            "pdf_source": pdf_source,
            "status": "error",
            "processing_time": processing_time,
            "error_message": str(e),
        }


async def process_pdf(pdf_url: str, item_id: str, priority: int = 0):
    """下载 PDF 并执行审核，生成评估报告并写入数据库。

    priority: 该 PDF 在 API 阶段的优先级（数值越小越优先，按提交顺序）。
    """
    url_str = str(pdf_url)
    pdf_bytes = await download_pdf(url_str)
    if not pdf_bytes:
        result = {
            "item_id": item_id,
            "pdf_url": url_str,
            "status": "error",
            "processing_time": 0,
            "error_message": "PDF下载失败",
        }
        _update_item_error(item_id, result["error_message"], 0)
        return result

    audit_result = await audit_pdf_bytes(pdf_bytes, item_id, url_str, priority=priority)
    processing_time = audit_result.get("processing_time", 0)

    if audit_result["status"] == "success":
        rule_count = audit_result.get("rule_count", 0)
        if rule_count != EXPECTED_RULE_COUNT:
            error_message = f"规则条数异常: 期望 {EXPECTED_RULE_COUNT}, 实际 {rule_count}"
            _update_item_error(item_id, error_message, processing_time)
            return {
                "item_id": item_id,
                "pdf_url": url_str,
                "status": "error",
                "processing_time": processing_time,
                "error_message": error_message,
                "rule_count": rule_count,
                "parsed_rows": rule_count,
            }

        with sqlite3.connect("audit.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE audit_items
                SET status = 'success', result = ?, error_message = NULL, processing_time = ?
                WHERE item_id = ?
                """,
                (
                    json.dumps(audit_result["result"], ensure_ascii=False),
                    processing_time,
                    item_id,
                ),
            )
            conn.commit()
        return {
            "item_id": item_id,
            "pdf_url": url_str,
            "status": "success",
            "processing_time": processing_time,
            "result": audit_result["result"],
        }

    error_message = audit_result.get("error_message", "未知错误")
    _update_item_error(item_id, error_message, processing_time)
    return {
        "item_id": item_id,
        "pdf_url": url_str,
        "status": "error",
        "processing_time": processing_time,
        "error_message": error_message,
    }


async def download_pdf(url: str, retry_count: int = 3, retry_delay: int = 3):
    """下载PDF文件，带重试机制"""
    try:
        url_str = str(url)
        if not url_str.startswith(("http://", "https://")):
            raise ValueError("无效的URL协议")
        
        for attempt in range(retry_count):
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.get(url_str)
                    response.raise_for_status()
                    
                    # 验证内容类型
                    content_type = response.headers.get("content-type", "").lower()
                    if "pdf" not in content_type:
                        # 对于中文URL的服务端，有时会返回HTML错误页面
                        if "text/html" in content_type:
                            raise ValueError("URL指向的是一个HTML页面，而不是PDF文件")
                        else:
                            raise ValueError(f"URL指向的文件不是PDF格式 (Content-Type: {content_type})")
                    return response.content
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.warning(f"下载PDF失败 (尝试 {attempt+1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    logger.info(f"等待{retry_delay}秒后重试...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"下载PDF彻底失败，已达到最大重试次数 {retry_count}: {e}")
                    return None
            except Exception as e:
                logger.error(f"下载PDF失败: {e}")
                return None
    except Exception as e:
        logger.error(f"下载PDF失败: {e}")
        return None

# 测试接口
@app.get("/audit/health", tags=["健康检查"])
def health_check():
    return {"status": "success", "service": "内容审查API","version":"2.0.0"}

#审核入口
@app.post("/audit")
async def audit(audit_request: List[PDFItem], background_tasks: BackgroundTasks):
    if not audit_request:
        raise HTTPException(status_code=400, detail="请求体不能为空")
    total_items=len(audit_request)

    # 先将所有任务插入数据库，状态设为 waiting（Worker 取走后再变为 processing）
    current_time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    with sqlite3.connect("audit.db") as conn:
        cursor=conn.cursor()
        for item in audit_request:
            cursor.execute("""
                INSERT OR REPLACE INTO audit_items
                (item_id,pdf_url,status,create_time)
                VALUES (?,?,?,?)
            """, (item.id, str(item.url),"waiting",current_time))

    run_id = time.strftime("%Y%m%d_%H%M%S")
    background_tasks.add_task(process_all_items, audit_request, total_items, 5, run_id)
    return {
        "status": "success",
        "run_id": run_id,
        "message": (
            f"审查任务已创建，共 {total_items} 个任务，run_id={run_id}，"
            f"失败记录见 runs/{run_id}/errors.json，可通过 GET /audit/{{item_id}} 查询状态"
        ),
    }

@app.get("/audit/all_items", tags=["查询所有任务"])
def get_all_items():
    conn = sqlite3.connect("audit.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_items")
    items = cursor.fetchall()
    conn.close()
    return items

@app.get("/audit/{item_id}")
def get_item_result(item_id: str):
    """获取单个项目的处理结果"""
    conn = sqlite3.connect("audit.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT item_id, pdf_url, status, result, error_message, processing_time, create_time
        FROM audit_items
        WHERE item_id = ?
    """, (item_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"item_id": item_id, "status": "failure"}

    item_id, pdf_url, status, result, error_message, processing_time, create_time = row
    
    return {
        "item_id": item_id,
        "pdf_url": pdf_url,
        "status": status,
        "result": json.loads(result) if result and status == "success" else None,
        "error_message": error_message,
        "processing_time": processing_time,
        "create_time": create_time
    }

async def process_all_items(
    items: List[PDFItem], total_items: int, max_workers: int = 5, run_id: str = ""
):
    """使用异步队列控制并发处理"""
    completed_count = 0
    count_lock = asyncio.Lock()
    errors: list[dict] = []
    errors_lock = asyncio.Lock()
    queue = asyncio.Queue()

    # 按提交顺序分配优先级（priority=提交索引，数值越小越优先）
    for priority, item in enumerate(items):
        await queue.put((priority, item))

    async def record_failure(item: PDFItem, error: str, parsed_rows: int | None = None) -> None:
        async with errors_lock:
            errors.append(_build_error_entry(item.id, str(item.url), error, parsed_rows))

    async def worker():
        """工作进程函数"""
        nonlocal completed_count
        while True:
            try:
                priority, item = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                _update_item_status(item.id, "processing")
                result = await process_pdf(item.url, item.id, priority=priority)
                if result.get("status") != "success":
                    await record_failure(
                        item,
                        result.get("error_message", "未知错误"),
                        result.get("parsed_rows"),
                    )
                    async with count_lock:
                        completed_count += 1
                    logger.error(
                        f"任务 {completed_count}/{total_items} 处理失败: {item.id} - "
                        f"{result.get('error_message')}"
                    )
                else:
                    async with count_lock:
                        completed_count += 1
                    logger.info(f"任务 {completed_count}/{total_items} 处理完成: {item.id}")
            except Exception as e:
                error_message = str(e)
                _update_item_error(item.id, error_message)
                await record_failure(item, error_message)
                async with count_lock:
                    completed_count += 1
                logger.error(f"任务 {completed_count}/{total_items} 处理失败: {item.id} - {e}")
            finally:
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(max_workers)]
    await queue.join()
    await asyncio.gather(*workers)
    if run_id:
        _save_errors_json(run_id, errors)

def init_db():
    conn = sqlite3.connect("audit.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_items (
            item_id TEXT PRIMARY KEY,
            pdf_url TEXT,
            status TEXT,
            result TEXT,
            error_message TEXT,
            processing_time REAL,
            create_time TEXT
        )
    """)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    if not os.path.exists("audit.db"):
        init_db()
    # 启动FastAPI服务
    uvicorn.run("app:app", host="0.0.0.0", port=8000,reload=True)
