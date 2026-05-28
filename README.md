# PDF-Audit-API

**国家自然科学基金项目申报书 PDF 自动审核系统**，版本 `2.0.0`。

通过接收 PDF 文件链接，自动提取文本与图像信息，调用大模型按照 49 条预设评审规则对申报书进行逐项打分，并将结果异步存储到数据库供查询。

---

## 功能特性

- **全自动 PDF 处理**：下载 → 截取 → 提取文本 + 检测图像，全流程无需人工干预
- **49 条评审规则**：覆盖全文规范性、项目名称、立项依据、研究方案、创新性与成果、申请人与经费共 6 个模块
- **并发控制**：PDF 处理与 AI API 调用各设最大 5 并发，支持批量任务
- **异步任务队列**：提交后立即返回，后台处理完成后写入数据库
- **多级容错**：PDF 下载与 AI 调用均支持 3 次重试；JSON 解析支持 4 级渐进修复
- **持久化存储**：SQLite 数据库记录每个任务的状态、结果、耗时等信息

---

## 技术栈

| 组件 | 库/服务 |
|------|---------|
| Web 框架 | FastAPI |
| ASGI 服务器 | Uvicorn |
| AI 模型 | 腾讯混元 `hunyuan-2.0-thinking-20251109`（OpenAI 兼容接口）|
| PDF 文本提取 | pypdf |
| PDF 图像检测 | PyMuPDF (fitz) |
| HTTP 客户端 | httpx |
| 数据库 | SQLite |
| Python 版本 | ≥ 3.12 |

---

## 快速开始

### 1. 安装依赖

推荐使用 [uv](https://github.com/astral-sh/uv)：

```bash
uv sync
```

或使用 pip：

```bash
pip install fastapi>=0.128.0 openai>=2.15.0 pypdf>=6.6.0 uvicorn>=0.40.0 pymupdf httpx
```

### 2. 配置 API Key

设置腾讯混元的 API Key 环境变量：

```bash
# Windows
set HUNYUAN_API_KEY=your_api_key_here

# Linux / macOS
export HUNYUAN_API_KEY=your_api_key_here
```

### 3. 启动服务

```bash
python app.py
```

服务默认运行在 `http://127.0.0.1:8000`，启动时会自动初始化 SQLite 数据库 `audit.db`。

---

## API 文档

启动后访问 `http://127.0.0.1:8000/docs` 查看交互式 API 文档。

### 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/audit/health` | 健康检查 |
| `POST` | `/audit` | 批量提交审核任务（异步后台处理）|
| `GET` | `/audit/all_items` | 查询所有任务记录 |
| `GET` | `/audit/{item_id}` | 查询单个任务结果 |

---

### POST /audit — 提交审核任务

**请求体**（JSON 数组）：

```json
[
  {
    "url": "https://example.com/path/to/file.pdf",
    "id": "task_001"
  },
  {
    "url": "https://example.com/path/to/file2.pdf",
    "id": "task_002"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `url` | string (HttpUrl) | PDF 文件的公开可访问 URL |
| `id` | string | 任务唯一标识符，由调用方指定 |

**响应**：

```json
{
  "status": "success",
  "message": "审查任务已创建，共 2 个任务，可以通过GET /audit/{item_id}查询状态"
}
```

> 任务提交后立即返回，实际处理在后台异步进行。

---

### GET /audit/{item_id} — 查询任务结果

**响应示例（处理中）**：

```json
{
  "item_id": "task_001",
  "pdf_url": "https://example.com/file.pdf",
  "status": "processing",
  "result": null,
  "error_message": null,
  "processing_time": null,
  "create_time": "2026-03-17 10:00:00"
}
```

**响应示例（成功）**：

```json
{
  "item_id": "task_001",
  "pdf_url": "https://example.com/file.pdf",
  "status": "success",
  "result": {
    "审查结果": [
      {
        "规则内容（需带规则序号）": "1.整体篇幅对比国自然同类别项目是否合适",
        "评估结果": "0.5/0.5",
        "理由": "全文共28页，处于标准区间（20-40页）内，符合要求。"
      }
      // ... 共49条规则
    ],
    "统计": {
      "总分": "82.5"
    }
  },
  "error_message": null,
  "processing_time": 185.3,
  "create_time": "2026-03-17 10:00:00"
}
```

**`status` 取值说明**：

| 值 | 说明 |
|----|------|
| `processing` | 任务正在处理中 |
| `success` | 审核完成，可查看 `result` |
| `error` | 处理失败，查看 `error_message` |
| `failure` | 任务 ID 不存在 |

---

## 审核规则说明

系统基于 **49 条评审规则** 对申报书进行逐项打分，满分 **97.5 分**，分为 6 个模块：

| 模块 | 规则编号 | 评审内容 | 满分 |
|------|---------|---------|------|
| 模块一 | 规则 1-12 | 全文规范性（篇幅、格式、错别字、术语、逻辑等） | 21.5 分 |
| 模块二 | 规则 13-17 | 项目名称与摘要 | 12 分 |
| 模块三 | 规则 18-26 | 立项依据（背景、文献、字数等） | 13 分 |
| 模块四 | 规则 27-33 | 研究方案（内容分阶段、样本量、技术路线等） | 14 分 |
| 模块五 | 规则 34-41 | 创新性与成果（转化价值、痛点、研究计划等） | 21 分 |
| 模块六 | 规则 42-49 | 申请人与经费（团队匹配度、分工、文章质量、预算等） | 16 分 |

---

## 处理流程

```
POST /audit（接收 PDF URL 列表）
  │
  ├─ 插入数据库（status: processing）
  │
  └─ 后台任务队列（最大 5 并发）
       │
       ├─ 1. 下载 PDF（带重试）
       ├─ 2. 截取 PDF（至指定终止句，去除无关内容）
       ├─ 3. 提取文本 + 图像检测（pypdf + PyMuPDF）
       ├─ 4. 清理文本（去除页码、无效字符）
       ├─ 5. 分割为 8 个章节模块
       ├─ 6. 生成 6 组 Prompt（对应 49 条规则）
       ├─ 7. 并发调用混元 API（最大 5 并发，带重试）
       ├─ 8. 解析 JSON 返回（4 级容错）
       ├─ 9. 汇总总分
       └─ 10. 更新数据库（status: success / error）
```

---

## 项目结构

```
audit2.0/
├── app.py          # 主服务：FastAPI 路由、PDF 处理、AI 调用、数据库操作
├── prompt.py       # 评审规则引擎：49 条规则 / 6 个模块的 Prompt 生成
├── pyproject.toml  # 项目配置与依赖声明
├── audit.db        # SQLite 数据库（首次运行自动创建）
└── temp/           # 开发过程草稿（并发测试、早期版本等，不影响主服务）
```

---

## 数据库结构

```sql
CREATE TABLE audit_items (
    item_id         TEXT PRIMARY KEY,   -- 任务 ID（由调用方指定）
    pdf_url         TEXT,               -- PDF 文件 URL
    status          TEXT,               -- processing / success / error
    result          TEXT,               -- JSON 格式的审核结果
    error_message   TEXT,               -- 错误信息（失败时填写）
    processing_time REAL,               -- 处理耗时（秒）
    create_time     TEXT                -- 任务创建时间
);
```

---

## 注意事项

- PDF 文件需通过公开 URL 访问，确保服务器可以正常下载
- 单个任务处理耗时约 2-5 分钟（取决于 PDF 页数和 AI 响应速度）
- 同一 `id` 重复提交将覆盖原有记录（`INSERT OR REPLACE`）
- `pyproject.toml` 中未声明 `pymupdf` 和 `httpx`，安装时请手动补充
