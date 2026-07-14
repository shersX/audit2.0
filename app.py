<<<<<<< HEAD
import logging,asyncio,uvicorn,os,httpx
=======
from pypdf import PdfReader
import logging,asyncio,uvicorn,io,re,os,httpx
from openai import AsyncOpenAI
>>>>>>> master
from fastapi import FastAPI,HTTPException,BackgroundTasks
from pydantic import BaseModel,HttpUrl
import json
import time
import sqlite3
<<<<<<< HEAD
from pathlib import Path
from urllib.parse import unquote, urlparse
from prompt import prompt_rule
from model import get_llm_api
from preprocess import extract_pdf, clean_text_pageofnum, splitpdf
from postprocess import parse_review_str, process_review_results
from typing import List

EXPECTED_RULE_COUNT = 49
RUNS_DIR = Path("runs")
=======
from typing import List,Optional,Dict
import fitz
from prompt import prompt_rule

>>>>>>> master

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger=logging.getLogger("PDF-Audit-API")

app=FastAPI(title="PDF-Audit-API",summary="PDF审核API",version="2.0.0")

class PDFItem(BaseModel):
    url: HttpUrl
    id: str

<<<<<<< HEAD

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
        llm_api = get_llm_api()
        tasks = [llm_api(prompt, priority=priority) for prompt in prompts]
        results = await asyncio.gather(*tasks)
=======
TARGET_SENTENCE="对其他来源资金的经费来源、资金具体开支用途做简要说明。"
MODULE_CONFIG={
    2:{"full":"二、立项依据","core":"立项依据"},
    3:{"full":"三、项目的研究内容、研究目标，以及拟解决的关键科学问题","core":"项目的研究内容、研究目标，以及拟解决的关键科学问题"},
    4:{"full":"四、拟采取的研究方案及可行性分析","core":"拟采取的研究方案及可行性分析"},
    5:{"full":"五、本项目的特色与创新之处","core":"本项目的特色与创新之处"},
    6:{"full":"六、年度研究计划及预期研究结果","core":"年度研究计划及预期研究结果"},
    7:{"full":"七、研究基础与⼯作条件","core":"研究基础与⼯作条件"},
    8:{"full":"⼋、申请⼈简介","core":"申请⼈简介"}
}


def find_module_positions(doc:fitz.Document,max_pages:int):
    """查找PDF中模块2-5的位置"""
    target_modules = [2,3,4,5]
    module_positions = {k: None for k in target_modules}
    for page_idx in range(min(max_pages,len(doc))):
        if all(pos is not None for pos in module_positions.values()):
            break
        page=doc[page_idx]
        for module_num in target_modules:
            if module_positions[module_num] is not None:
                continue
            titles=MODULE_CONFIG[module_num]
            full_matches=page.search_for(titles["full"])
            if full_matches:
                module_positions[module_num]=page_idx
                continue
            core_matches=page.search_for(titles["core"])
            if core_matches:
                module_positions[module_num]=page_idx
    return module_positions

def check_images_in_sections(doc:fitz.Document,total_pages:int,module_positions:Dict[int,Optional[int]]):
    """检查模块中的图片存在情况"""
    has_global_image=False
    has_section23_image=False
    has_tech_route_image=False

    for page_idx in range(total_pages):
        page=doc[page_idx]
        current_page_has_img=len(page.get_images(full=True))>0
        if current_page_has_img:
            has_global_image=True
        if module_positions[2] is not None and module_positions[3] is not None:
            if module_positions[2] <= page_idx <= module_positions[3] and current_page_has_img:
                has_section23_image = True
        if module_positions[4] is not None and module_positions[5] is not None:
            if module_positions[4] <= page_idx <= module_positions[5] and current_page_has_img:
                has_tech_route_image=True
    return has_global_image,has_section23_image,has_tech_route_image


def extract_pdf(file_bytes):
    """从PDF中提取文本和图像信息"""
    try:
        stream=io.BytesIO(file_bytes)
        reader=PdfReader(stream)
        doc=fitz.open(stream=file_bytes,filetype="pdf")
        total_pages=len(reader.pages)
        full_raw_text=""
        for page_idx in range(total_pages):
            page_text=reader.pages[page_idx].extract_text() or ""
            full_raw_text+=page_text + "\n"
        module_positions=find_module_positions(doc,total_pages)
        has_global_image,has_section23_image,has_tech_route_image=check_images_in_sections(doc,total_pages,module_positions)
        doc.close()
        return full_raw_text,has_global_image,has_section23_image,has_tech_route_image
    except Exception as e:
        raise ValueError(f"Error extract_PDF: {str(e)}")

def truncate_pdf_at_sentence(pdf_bytes):
    """
    从内存字节流处理PDF，截取到包含目标句子的页面，返回处理后的字节流
    :param pdf_bytes: 原始PDF的字节流（bytes类型）
    :return: 处理后的PDF字节流（bytes），未找到目标则返回None
    """
    target_pagenum=-1# 初始化目标页码（默认-1表示未找到）
    with fitz.open(stream=pdf_bytes,filetype="pdf")as doc:# 1. 从字节流打开PDF（内存操作，无本地文件）
        for page_num,page in enumerate(doc):# 遍历所有页面，查找目标句子
            text_position=page.search_for(TARGET_SENTENCE)# 用search_for查找（贴合PDF排版，抗换行）
            if text_position:
                target_pagenum=page_num
                break# 找到第一个匹配页就停止
        if target_pagenum != -1:# 2. 如果找到目标页，截取并生成字节流
            new_doc=fitz.open()
            new_doc.insert_pdf(doc,from_page=0,to_page=target_pagenum)# 复制目标页及之前的所有页面到新文档
            processed_pdf_bytes=new_doc.write()# 核心：生成处理后的字节流（不落地文件）
            new_doc.close()
            return processed_pdf_bytes
        else:
            logger.warning(f"未在PDF中找到目标句子：{TARGET_SENTENCE}")
            return pdf_bytes


async def process_pdf(file_path: str,item_id:str):
    """处理PDF文件，生成评估报告"""
    start_time=time.time()
    url_str=str(file_path)
    logger.info(f"开始处理PDF: {item_id}")
    try:
        # 1.下载PDF
        raw_pdf_bytes=await download_pdf(url_str)
        # 2. 截取PDF到目标句子
        processed_pdf_bytes=truncate_pdf_at_sentence(raw_pdf_bytes)
        # 3. 提取PDF文本
        truncated_text, has_global_image,has_section23_image, has_tech_route_image = extract_pdf(processed_pdf_bytes)
        #truncated_text保存至{item_id}_fulltext.txt
        with open(f"{item_id}_fulltext.txt","w",encoding="utf-8") as f:
            f.write(truncated_text)
        if not truncated_text:
            raise HTTPException(status_code=400, detail="PDF内容为空")
        # 4. 清理文本
        cleaned_text, last_page_num = clean_text_pageofnum(truncated_text)
        # 5. 分割PDF内容为模块
        modules = splitpdf(cleaned_text)
        # 6. 生成所有prompt
        prompts = prompt_rule(modules, last_page_num, has_global_image,has_section23_image, has_tech_route_image)
        # 6.1 分开保存所有prompt，即每个prompt一个txt文件
        for idx,prompt in enumerate(prompts):
            with open(f"{item_id}_prompt_{idx}.txt","w",encoding="utf-8") as f:
                f.write(prompt)

        # 7. 并发调用API处理所有prompt
        tasks = [hunyuanAPI(prompt) for prompt in prompts]
        results = await asyncio.gather(*tasks)

        # 8. 处理API返回结果
>>>>>>> master
        all_reviews = []
        for result in results:
            parsed = parse_review_str(result)
            if parsed:
                all_reviews.extend(parsed)
<<<<<<< HEAD
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
=======
        # 9. 生成最终报告
        final_report = process_review_results(all_reviews)
        processing_time=round(time.time()-start_time,2)
        # 10. 保存报告到数据库
        with sqlite3.connect('audit.db') as conn:
>>>>>>> master
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

<<<<<<< HEAD
    error_message = audit_result.get("error_message", "未知错误")
    _update_item_error(item_id, error_message, processing_time)
    return {
        "item_id": item_id,
        "pdf_url": url_str,
        "status": "error",
        "processing_time": processing_time,
        "error_message": error_message,
=======




    
def clean_text_pageofnum(text):
    lines = text.splitlines()
    cleaned = []
    i = 0
    last_page_num=None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        match = re.match(r'^Page\s+(\d+)\s+of\s+(\d+)$', stripped)
        # 命中 Page x of y
        if match:
            last_page_num=int(match.group(1))
            if i + 1 < len(lines) and lines[i + 1].strip().isdigit():
                i += 2
            else:
                i += 1
            continue
        # 修复Unicode编码问题，移除无效代理字符
        cleaned_line = ''.join(c for c in line if c.isprintable() or c in '\n\r\t')
        cleaned.append(cleaned_line)
        i += 1
    return "\n".join(cleaned),last_page_num

def splitpdf(text):
    # 预处理文本，移除无效Unicode字符
    text = ''.join(c for c in text if c.isprintable() or c in '\n\r\t')
    pattern=r"课题名称"
    all_pa=list(re.finditer(pattern,text))
    second_ktmc_start=None
    if len(all_pa)>=2:
        second_ktmc_start=all_pa[1].start()

    # 1. 定义模块标题（按顺序）和对应关键字
    title_info = [
        ("二、立项依据", "立项依据"),
        ("三、项目的研究内容、研究目标，以及拟解决的关键科学问题", "项目的研究内容、研究目标，以及拟解决的关键科学问题"),
        ("四、拟采取的研究方案及可行性分析", "拟采取的研究方案及可行性分析"),
        ("五、本项目的特色与创新之处", "本项目的特色与创新之处"),
        ("六、年度研究计划及预期研究结果", "年度研究计划及预期研究结果"),
        ("七、研究基础与工作条件", "研究基础与工作条件"),
        ("八、申请人简介", "申请人简介"),
        ("项目预算表", "项目预算表")
    ]
    titles = [item[0] for item in title_info]
    keywords = [item[1] for item in title_info]
    
    # 2. 第一步匹配：使用原有精确匹配逻辑
    matches = [re.search(re.escape(t), text) for t in titles]
    
    # 3. 第二步匹配：对未匹配到的标题使用灵活正则表达式
    for i, (match, keyword) in enumerate(zip(matches, keywords)):
        if not match:
            # 灵活正则表达式：支持多种前缀格式
            flexible_pattern = rf'^\s*(?:[一二三四五六七八九十]+|\d+)\s*[、.）]\s*{re.escape(keyword)}'
            flexible_match = re.search(flexible_pattern, text, re.MULTILINE)
            if flexible_match:
                matches[i] = flexible_match
                logger.info(f"使用灵活匹配成功匹配标题：{titles[i]}")
    
    # 4. 验证并修复匹配顺序
    # 收集所有有效匹配结果及其索引
    valid_matches = [(i, match) for i, match in enumerate(matches) if match]
    if valid_matches:
        # 按匹配位置排序
        valid_matches.sort(key=lambda x: x[1].start())
        
        # 创建修复后的matches列表
        fixed_matches = matches.copy()
        last_pos = -1
        
        # 确保匹配顺序正确，且不重叠
        for idx, match in valid_matches:
            current_start = match.start()
            if current_start < last_pos:
                # 重叠匹配，跳过该匹配
                fixed_matches[idx] = None
            else:
                # 有效匹配，更新last_pos
                last_pos = current_start
        
        matches = fixed_matches
    
    # 5. 提取封面和概览
    modules={}
    if second_ktmc_start is not None:
        modules["封面"]=text[:second_ktmc_start].strip()
        if matches[0]:
            modules["一、课题项目概览"]=text[second_ktmc_start:matches[0].start()].strip()
        else:
            modules["一、课题项目概览"]=text[second_ktmc_start:].strip()
    else:
        modules["封面"]=""
        if matches[0]:
            modules["一、课题项目概览"]=text[:matches[0].start()].strip()
        else:
            modules["一、课题项目概览"]=text.strip()
    
    # 6. 提取各章节内容
    # 首先提取所有能匹配到的章节
    for i, (title, match) in enumerate(zip(titles, matches)):
        if not match:
            modules[title] = ""
            logger.warning(f"未匹配到标题：{title}")
            continue
        
        # 查找下一个有效匹配作为结束位置
        next_match = None
        for j in range(i+1, len(matches)):
            if matches[j]:
                next_match = matches[j]
                break
        
        start = match.end()
        end = next_match.start() if next_match else len(text)
        
        # 确保内容顺序正确
        if start < end:
            modules[title] = text[start:end].strip()
        else:
            modules[title] = ""
            logger.warning(f"标题 {title} 的结束位置早于或等于开始位置，无法提取内容")
    
    # 7. 处理未匹配标题的内容合并
    # 关键标题索引：七、研究基础与工作条件(5)，八、申请人简介(6)，项目预算表(7)
    
    # 情况1：项目预算表未匹配到
    if not matches[7]:  # 项目预算表未匹配到
        modules["项目预算表"] = ""
        logger.info("项目预算表未匹配到，将剩余内容并入八、申请人简介")
        
        if matches[6]:  # 申请人简介匹配到了
            # 将申请人简介的内容扩展到文本末尾
            start = matches[6].end()
            modules["八、申请人简介"] = text[start:].strip()
        elif matches[5]:  # 申请人简介未匹配，但研究基础匹配到了
            # 情况2：申请人简介未匹配到
            modules["八、申请人简介"] = ""
            # 将研究基础的内容扩展到文本末尾
            start = matches[5].end()
            modules["七、研究基础与工作条件"] = text[start:].strip()
    # 情况2：申请人简介未匹配到
    elif not matches[6]:  # 申请人简介未匹配到
        modules["八、申请人简介"] = ""
        modules["项目预算表"] = ""
        logger.info("申请人简介未匹配到，将剩余内容并入七、研究基础与工作条件")
        
        if matches[5]:  # 研究基础匹配到了
            # 将研究基础的内容扩展到文本末尾
            start = matches[5].end()
            modules["七、研究基础与工作条件"] = text[start:].strip()
    
    return modules

async def hunyuanAPI(prompt, retry_count=3):
    """异步调用混元API，带重试机制"""
    # 构造异步client
    client = AsyncOpenAI(
        api_key=os.environ.get("HUNYUAN_API_KEY"),  # 混元 APIKey
        base_url="https://api.hunyuan.cloud.tencent.com/v1",  # 混元 endpoint
    )
    for attempt in range(retry_count):
        try:
            async with api_semaphore:
                completion = await client.chat.completions.create(
                    model="hunyuan-2.0-thinking-20251109",
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    extra_body={
                        "enable_enhancement": True,  # <- 自定义参数
                    }
                )
                return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"API调用失败 (尝试 {attempt+1}/{retry_count}): {e}")
            if attempt < retry_count - 1:
                logger.info(f"等待3秒后重试...")
                await asyncio.sleep(3)
            else:
                logger.critical(f"API调用彻底失败，已达到最大重试次数 {retry_count}")
                # 返回空字符串，让parse函数处理
                return ""
    return ""

def parse_review_str(review_str):
    """
    辅助函数：将JSON字符串解析为Python列表，处理常见格式问题
    Args:
        review_str: 字符串格式的评审数据（JSON格式）
    Returns:
        解析后的Python列表（若解析失败，返回空列表，确保程序不会崩溃）
    """
    # 1. 基本输入验证
    if not review_str:
        logger.warning("警告：输入字符串为空，无法解析")
        return []
    
    if not isinstance(review_str, str):
        logger.warning(f"警告：输入不是字符串格式，类型为 {type(review_str)}，无法解析")
        return []
    
    # 2. 预处理和清理
    try:
        processed_str = review_str.strip()
        # 移除可能的BOM头
        if processed_str.startswith('\ufeff'):
            processed_str = processed_str[1:]
            logger.info("移除了BOM头")
        # 移除可能的前后引号（如果API返回时包含额外引号）
        if (processed_str.startswith('"') and processed_str.endswith('"')) or \
           (processed_str.startswith("'") and processed_str.endswith("'")):
            processed_str = processed_str[1:-1]
            logger.info("移除了前后额外引号")
        # 基本检查：是否为空字符串
        if not processed_str:
            logger.warning("警告：预处理后字符串为空，无法解析")
            return []
        # 基本检查：是否为有效的JSON结构开头
        if not (processed_str.startswith('[') or processed_str.startswith('{')):
            logger.warning(f"警告：字符串不是有效的JSON结构开头，内容：{processed_str[:50]}...")
            return []
        
    except Exception as e:
        logger.error(f"字符串预处理失败：{e}")
        return []
    
    # 3. 多次尝试解析，逐步增强修复力度
    parse_attempts = [
        # 尝试1：基础修复
        lambda s: s.replace("，", ",").replace("：", ":").replace("“", '"').replace("”", '"'),
        
        # 尝试2：增强修复 - 替换所有中文引号和处理特殊空格
        lambda s: s.replace("，", ",").replace("：", ":").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").replace("\n", " ").replace("\r", " ").strip(),
        
        # 尝试3：高级修复 - 处理多余逗号、修复字段名
        lambda s: re.sub(r',\s*}(?!\s*\])', '}', re.sub(r',\s*](?!\s*$)', ']', 
                  re.sub(r'(?<![":\w])(\w+)(?=\s*:)', r'"\1"', 
                  s.replace("，", ",").replace("：", ":").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").replace("\n", " ").replace("\r", " ")))),
        
        # 尝试4：终极修复 - 使用更严格的正则表达式修复
        lambda s: re.sub(r'([^,\s])\s+([^,\s])', r'\1 \2', 
                  re.sub(r',\s*}\s*$', '}', 
                  re.sub(r',\s*}\s*]', '}]', 
                  re.sub(r'(\w+)\s*:', r'"\1":', 
                  s.replace("，", ",").replace("：", ":").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").replace("\n", " ").replace("\r", " ")))))
    ]
    
    for i, fix_func in enumerate(parse_attempts):
        try:
            # 应用修复函数
            current_str = fix_func(processed_str)
            # 尝试解析
            parsed_data = json.loads(current_str)
            # 确保返回结果是列表
            if not isinstance(parsed_data, list):
                parsed_data = [parsed_data]
            return parsed_data
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败 (尝试 {i+1}/{len(parse_attempts)}): {e}")
            logger.debug(f"当前尝试的修复后字符串：{current_str[:200]}...")
        except Exception as e:
            logger.error(f"JSON解析过程中发生未知错误 (尝试 {i+1}/{len(parse_attempts)}): {e}")
    
    # 4. 所有尝试都失败，进行最后的挽救措施
    logger.critical(f"所有JSON解析尝试都失败，尝试使用最后的挽救措施")
    # 尝试从字符串中提取可能的JSON片段
    try:
        # 寻找JSON数组的开始和结束位置
        start_idx = processed_str.find('[')
        end_idx = processed_str.rfind(']')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            # 提取可能的JSON数组片段
            json_fragment = processed_str[start_idx:end_idx+1]

            # 再次尝试解析片段
            parsed_data = json.loads(json_fragment)
            if not isinstance(parsed_data, list):
                parsed_data = [parsed_data]
            logger.info(f"从片段中解析成功，包含 {len(parsed_data)} 个评审项")
            return parsed_data
    except Exception as e:
        logger.error(f"片段提取和解析也失败：{e}")
    
    # 5. 彻底失败，返回空列表，确保程序不会崩溃
    logger.critical("JSON解析彻底失败，返回空列表")
    return []

def process_review_results(review_list):
    """
    处理评审结果：合并数据、转换格式、统计总分（直接求和各分项分数）
    Args:
        review_list: 解析后的评审结果列表（每个元素是符合格式的字典）
    Returns:
        组装好的最终结果（字典格式，可直接转为JSON）
    """
    # 1. 初始化结果容器
    final_result = {
        "审查结果": [],
        "统计": {
            "总分": ""  # 仅保留总分，直接求和各分项分数
        }
>>>>>>> master
    }


async def download_pdf(url: str, retry_count: int = 3, retry_delay: int = 3):
    """下载PDF文件，带重试机制"""
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
        except Exception as e:
            logger.warning(f"下载PDF失败 (尝试 {attempt+1}/{retry_count}): {e}")
            if attempt < retry_count - 1:
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"下载PDF彻底失败，已达到最大重试次数 {retry_count}: {e}")
                return None
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
    # 启动 FastAPI 服务
    uvicorn.run("app:app", host="127.0.0.1", port=8000,reload=True)
