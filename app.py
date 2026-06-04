import logging,asyncio,uvicorn,os,httpx
from fastapi import FastAPI,HTTPException,BackgroundTasks
from pydantic import BaseModel,HttpUrl
import json
import time
import sqlite3
from prompt import prompt_rule
from model.hunyuan import hunyuanAPI
from preprocess import extract_pdf, clean_text_pageofnum, splitpdf
from postprocess import parse_review_str, process_review_results
from typing import List

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger=logging.getLogger("PDF-Audit-API")

app=FastAPI(title="PDF-Audit-API",summary="PDF审核API",version="2.0.0")

class PDFItem(BaseModel):
    url: HttpUrl
    id: str

async def audit_pdf_bytes(pdf_bytes: bytes, item_id: str, pdf_source: str = "") -> dict:
    """从 PDF 字节流执行完整审核管线，不写数据库。"""
    start_time = time.time()
    logger.info(f"开始处理PDF: {item_id}")
    try:
        truncated_text, has_global_image, has_section23_image, has_tech_route_image = extract_pdf(pdf_bytes)
        if not truncated_text:
            raise ValueError("PDF内容为空")
        cleaned_text, last_page_num = clean_text_pageofnum(truncated_text)
        modules = splitpdf(cleaned_text)
        prompts = prompt_rule(
            modules, last_page_num, has_global_image, has_section23_image, has_tech_route_image
        )
        tasks = [hunyuanAPI(prompt) for prompt in prompts]
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


async def process_pdf(file_path: str, item_id: str):
    """处理PDF文件，生成评估报告并写入数据库。"""
    url_str = str(file_path)
    pdf_bytes = await download_pdf(url_str)
    if not pdf_bytes:
        result = {
            "item_id": item_id,
            "pdf_url": url_str,
            "status": "error",
            "processing_time": 0,
            "error_message": "PDF下载失败",
        }
        with sqlite3.connect("audit.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE audit_items
                SET status = 'error', result = NULL, error_message = ?, processing_time = ?
                WHERE item_id = ?
                """,
                (result["error_message"], 0, item_id),
            )
            conn.commit()
        return result

    audit_result = await audit_pdf_bytes(pdf_bytes, item_id, url_str)
    processing_time = audit_result.get("processing_time", 0)

    if audit_result["status"] == "success":
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

    with sqlite3.connect("audit.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE audit_items
            SET status = 'error', result = NULL, error_message = ?, processing_time = ?
            WHERE item_id = ?
            """,
            (audit_result.get("error_message", "未知错误"), processing_time, item_id),
        )
        conn.commit()
    return {
        "item_id": item_id,
        "pdf_url": url_str,
        "status": "error",
        "processing_time": processing_time,
        "error_message": audit_result.get("error_message", "未知错误"),
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

    #1、先将所有任务插入数据库，状态设为“processing”
    current_time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    with sqlite3.connect("audit.db") as conn:
        cursor=conn.cursor()
        for item in audit_request:
            cursor.execute("""
                INSERT OR REPLACE INTO audit_items
                (item_id,pdf_url,status,create_time)
                VALUES (?,?,?,?)
            """, (item.id, str(item.url),"processing",current_time))

    # 使用异步队列处理任务，设置并发数为5
    background_tasks.add_task(process_all_items, audit_request, total_items, 5)
    return {"status":"success", "message": f"审查任务已创建，共 {total_items} 个任务，可以通过GET /audit/{{item_id}}查询状态"}

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

async def process_all_items(items: List[PDFItem], total_items: int, max_workers: int = 5):
    """使用异步队列控制并发处理"""
    completed_count = 0
    count_lock = asyncio.Lock()
    queue = asyncio.Queue()
    
    # 将所有任务放入队列
    for item in items:
        await queue.put(item)
    
    async def worker():
        """工作进程函数"""
        nonlocal completed_count
        while not queue.empty():
            item = await queue.get()
            try:
                await process_pdf(item.url, item.id)
                async with count_lock:
                    completed_count += 1
                logger.info(f"任务 {completed_count}/{total_items} 处理完成: {item.id}")
            except Exception as e:
                async with count_lock:
                    completed_count += 1
                logger.error(f"任务 {completed_count}/{total_items} 处理失败: {item.id} - {e}")
            finally:
                queue.task_done()
    
    # 创建指定数量的工作进程
    workers = [asyncio.create_task(worker()) for _ in range(max_workers)]
    await queue.join()  # 等待所有任务完成
    for worker in workers:
        worker.cancel()  # 取消工作进程

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
