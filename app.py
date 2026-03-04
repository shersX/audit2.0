from pypdf import PdfReader
import logging,asyncio,uvicorn,io,re,os,httpx
from openai import AsyncOpenAI
from pathlib import Path
from fastapi import FastAPI,HTTPException,BackgroundTasks
from pydantic import BaseModel,HttpUrl
import json
import time
import sqlite3
from prompt import prompt_rule
from typing import List
import fitz

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger=logging.getLogger("PDF-Audit-API")

# 并发控制
pdf_semaphore=asyncio.Semaphore(5)
api_semaphore=asyncio.Semaphore(5)
app=FastAPI(title="PDF-Audit-API",summary="PDF审核API",version="2.0.0")



class PDFItem(BaseModel):
    url: HttpUrl
    id: str

async def process_pdf(file_path: str,item_id:str):
    """处理PDF文件，生成评估报告"""
    start_time=time.time()
    url_str=str(file_path)
    logger.info(f"开始处理PDF: {item_id}")
    try:
        # 1. 提取PDF文本
        truncated_text, has_global_image,has_section23_image, has_tech_route_image = extract_pdf(await download_pdf(url_str))
        if not truncated_text:
            raise HTTPException(status_code=400, detail="PDF内容为空")
        # 2. 清理文本
        cleaned_text, last_page_num = clean_text_pageofnum(truncated_text)
        # 3. 分割PDF内容为模块
        modules = splitpdf(cleaned_text)
        # 4. 生成所有prompt
        prompts = prompt_rule(modules, last_page_num, has_global_image,has_section23_image, has_tech_route_image)
        # #保存prompts到temp/{item_id}.txt
        # os.makedirs("temp",exist_ok=True)
        # with open(f"temp/{item_id}.txt","w",encoding="utf-8") as f:
        #     f.write("\n\n".join(prompts))
        # exit(0)
        # 5. 并发调用API处理所有prompt
        tasks = [hunyuanAPI(prompt) for prompt in prompts]
        results = await asyncio.gather(*tasks)
        # 6. 处理API返回结果
        all_reviews = []
        for result in results:
            parsed = parse_review_str(result)
            if parsed:
                all_reviews.extend(parsed)
        # 7. 生成最终报告
        final_report = process_review_results(all_reviews)
        processing_time=round(time.time()-start_time,2)
        # 8. 保存报告到数据库
        with sqlite3.connect('audit.db') as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE audit_items 
                SET status = 'success', result = ?, error_message = NULL, processing_time = ?
                WHERE item_id = ?
        """, (json.dumps(final_report, ensure_ascii=False), processing_time, item_id))
            conn.commit()

        return {
            "item_id": item_id,
            "pdf_url": url_str,
            "status": "success",
            "processing_time": processing_time,
            "result": final_report
        }
    except Exception as e:
        processing_time=round(time.time()-start_time,2)
        with sqlite3.connect('audit.db') as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE audit_items 
                SET status = 'error', result = NULL, error_message = ?, processing_time = ?
                WHERE item_id = ?
            """, (str(e), processing_time, item_id))
            conn.commit()
        return {
            "item_id": item_id,
            "pdf_url": url_str,
            "status": "error",
            "processing_time": processing_time,
            "error_message": str(e)
        }

def extract_pdf(file_bytes:bytes):
    SENTENCES="对其他来源资金的经费来源、资金具体开支用途做简要说明。"

    # 模块二：完整标题 + 降级匹配的核心标题（新增）
    MODULE2_FULL = "二、立项依据"
    MODULE2_CORE = "立项依据"
    # 模块三：完整标题 + 降级匹配的核心标题（新增）
    MODULE3_FULL = "三、项目的研究内容、研究目标，以及拟解决的关键科学问题"
    MODULE3_CORE = "项目的研究内容、研究目标，以及拟解决的关键科学问题"

    # 模块四：完整标题 + 降级匹配的核心标题，模块五：完整标题 + 降级匹配的核心标题
    MODULE4_FULL = "四、拟采取的研究方案及可行性分析"
    MODULE4_CORE = "拟采取的研究方案及可行性分析"
    MODULE5_FULL = "五、本项目的特色与创新之处"
    MODULE5_CORE = "本项目的特色与创新之处"

    stream=io.BytesIO(file_bytes)
    reader=PdfReader(stream)
    total_pages=len(reader.pages)

    full_raw_text = ""
    truncated_text = ""
    cutoff_page_idx = None
    module2_page_idx = None
    module3_page_idx = None
    module4_page_idx = None
    module5_page_idx = None

    # 编译正则：严格匹配完整标题，未匹配则匹配核心标题（两级匹配）
    pattern_module2 = re.compile(f"{re.escape(MODULE2_FULL)}|{re.escape(MODULE2_CORE)}", flags=re.UNICODE)
    pattern_module3 = re.compile(f"{re.escape(MODULE3_FULL)}|{re.escape(MODULE3_CORE)}", flags=re.UNICODE)
    pattern_module4 = re.compile(f"{re.escape(MODULE4_FULL)}|{re.escape(MODULE4_CORE)}", flags=re.UNICODE)
    pattern_module5 = re.compile(f"{re.escape(MODULE5_FULL)}|{re.escape(MODULE5_CORE)}", flags=re.UNICODE)
    # 终止语句严格匹配正则
    pattern_terminal = re.compile(re.escape(SENTENCES))

    for page_idx in range(total_pages):
        page_text=reader.pages[page_idx].extract_text() or ""
        full_raw_text+=page_text + "\n"

        # ========== 新增：模块二 两级匹配 ==========
        if module2_page_idx is None and pattern_module2.search(page_text):
            module2_page_idx = page_idx
        # ========== 新增：模块三 两级匹配 ==========
        if module3_page_idx is None and pattern_module3.search(page_text):
            module3_page_idx = page_idx

        # ========== 优化点：模块四两级匹配（仅首次匹配赋值） ==========
        if module4_page_idx is None and pattern_module4.search(page_text):
            module4_page_idx = page_idx
        # ========== 优化点：模块五两级匹配（仅首次匹配赋值） ==========
        if module5_page_idx is None and pattern_module5.search(page_text):
            module5_page_idx = page_idx

        terminal_match=pattern_terminal.search(full_raw_text)
        if terminal_match:
            truncated_text=full_raw_text[:terminal_match.end()]
            cutoff_page_idx = page_idx
            break
    if cutoff_page_idx is None:
        truncated_text = full_raw_text
        cutoff_page_idx = total_pages - 1
    
    stream.seek(0)
    doc=fitz.open(stream=stream, filetype="pdf")
    has_global_image = False
    has_section23_image=False
    has_tech_route_image = False

    for page_idx in range(cutoff_page_idx + 1):
        page = doc[page_idx]
        current_page_has_img = len(page.get_images(full=True)) > 0

        if current_page_has_img:
            has_global_image = True

        # ========== 新增：判断页面是否在【模块二 ~ 模块三】区间内 ==========
        in_section23 = False
        if module2_page_idx is not None and module3_page_idx is not None:
            if module2_page_idx <= page_idx <= module3_page_idx:
                in_section23 = True
        if in_section23 and current_page_has_img and not has_section23_image:
            has_section23_image = True

        # 判断是否在目标章节区间内
        in_target_section = False
        if module4_page_idx is not None and module5_page_idx is not None:
            if module4_page_idx <= page_idx <= module5_page_idx:
                in_target_section = True
        if in_target_section and current_page_has_img:
            has_tech_route_image = True
    
    doc.close()
    return truncated_text, has_global_image,has_section23_image, has_tech_route_image
    
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


# 全局AsyncOpenAI client
hunyuan_client = AsyncOpenAI(
    api_key=os.environ.get("HUNYUAN_API_KEY"),
    base_url="https://api.hunyuan.cloud.tencent.com/v1",
)
async def hunyuanAPI(prompt, retry_count=3):
    """异步调用混元API，带重试机制"""
    for attempt in range(retry_count):
        try:
            async with api_semaphore:
                completion = await hunyuan_client.chat.completions.create(
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
    处理评审结果：合并数据、转换格式、统计不符合规则序号
    Args:
        review_list: 解析后的评审结果列表（每个元素是符合格式的字典）
    Returns:
        组装好的最终结果（字典格式，可直接转为JSON）
    """
    # 1. 初始化结果容器
    final_result = {
        "审查结果": [],
        "统计": ""  # 存储不符合规则序号，格式如"1、10、"
    }
    # 2. 统计不符合规则序号
    non_compliant_rules = []
    # 3. 遍历处理每个评审结果
    for review in review_list:
        # 3.1 字段映射（转换为目标格式）
        processed_item = {
            "规则内容（需带规则序号）": review.get("规则内容", ""),
            "评估结果": review.get("是否符合", ""),
            "理由": review.get("理由", "")
        }
        final_result["审查结果"].append(processed_item)
        # 3.2 统计不符合规则序号
        if review.get("是否符合", "") == "不符合":
            # 提取规则序号（假设规则内容以"X."开头）
            rule_content = review.get("规则内容", "")
            if "." in rule_content:
                rule_number = rule_content.split(".")[0]
                non_compliant_rules.append(rule_number)
    
    # 4. 格式化统计结果为"1、10、"形式
    final_result["统计"] = "、".join(non_compliant_rules) + "、" if non_compliant_rules else ""
    return final_result

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
