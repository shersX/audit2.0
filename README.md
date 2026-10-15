# PDF-Audit-API

**国家自然科学基金项目申报书 PDF 自动审核系统**，版本 `2.0.0`。

接收 PDF 公开链接后，自动提取文本与图像前置事实，按 **49 条预设规则** 做二元符合性判定（`符合` / `不符合`），结果异步写入 SQLite，并可通过接口查询。

---

## 功能特性

- **全自动 PDF 管线**：下载 → 截断 → 抽文本 + 图像检测 → 清洗 → 分章 → 生成 Prompt → 调用大模型 → 解析汇总
- **二元符合性评审**：49 条规则统一输出 `符合` / `不符合`，不再打分；理由要求证据位置 + 原文 + 对照标准
- **多模型 Provider**：通过环境变量切换 `hunyuan` / `doubao` / `ali`（默认混元）
- **双层并发控制**：
  - PDF 处理：最多 **5** 个 Worker 并行
  - LLM 调用：全局 **6** 个槽位的优先级信号量；按**提交顺序**优先让靠前的 PDF 先完成 API 调用（不抢占、不空转）
- **任务状态机**：`waiting` → `processing` → `success` / `error`（查询不存在为 `failure`）
- **批次失败落盘**：每次提交生成 `run_id`，失败样本写入 `runs/{run_id}/errors.json`（流式追加）
- **规则条数校验**：解析后须恰好 49 条，否则记为 `error`
- **多级容错**：PDF 下载与 LLM 调用均支持重试；JSON 解析支持直接解析与片段提取

---

## 技术栈

| 组件 | 库/服务 |
|------|---------|
| Web 框架 | FastAPI |
| ASGI 服务器 | Uvicorn |
| AI 调用 | OpenAI 兼容接口（混元 TokenHub / 豆包 Ark / 阿里云） |
| PDF 文本提取 | pypdf（单页失败时降级 PyMuPDF） |
| PDF 图像检测 | PyMuPDF (`fitz`) |
| HTTP 客户端 | httpx |
| 数据库 | SQLite |
| Python | ≥ 3.12 |

---

## 快速开始

### 1. 安装依赖

推荐使用 [uv](https://github.com/astral-sh/uv)：

```bash
uv sync
```

> 依赖已包含 fastapi / openai / pypdf / pymupdf / httpx / uvicorn 等。

### 2. 配置环境变量

**选择模型 Provider**（可选，默认 `hunyuan`）：

```bash
# Windows
set AUDIT_LLM_PROVIDER=hunyuan

# Linux / macOS
export AUDIT_LLM_PROVIDER=hunyuan
```

可选值：`hunyuan` | `doubao` | `ali`。

**按 Provider 配置 API Key**：

| Provider | 环境变量 | 说明 |
|----------|----------|------|
| `hunyuan`（默认） | 见 `model/hunyuan.py` | TokenHub OpenAI 兼容接口 |
| `doubao` | `DOUBAO_API_KEY` | 火山引擎方舟 |
| `ali` | `DASHSCOPE_API_KEY` | 阿里云兼容模式 |

服务启动时会在日志中打印当前默认 Provider。

### 3. 启动服务

```bash
python app.py
# 或
uv run python app.py
```

默认监听 `http://0.0.0.0:8000`；启动时 lifespan 会确保 `audit.db` 建表。交互式文档：`http://127.0.0.1:8000/docs`。

### 4. 本地联调（不启 HTTP / 不下载 / 不写 DB）

```bash
# 只跑前处理 + 生成 prompts（不调 LLM）
python -m cli --pdf path/to/file.pdf --dry-prompt

# 落盘第 1 个模块的 prompt 文本
python -m cli --pdf path/to/file.pdf --dry-prompt --module 1

# 完整审核管线，结果打印到 stdout（需配置 AUDIT_LLM_PROVIDER 与对应 API Key）
python -m cli --pdf path/to/file.pdf --item-id local_001 --out out.json

# 跳过「必须恰好 49 条」校验，便于排查解析问题
python -m cli --pdf path/to/file.pdf --no-rule-count-check
```

---

## API 文档

### 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/audit/health` | 健康检查 |
| `POST` | `/audit` | 批量提交审核任务（异步后台处理） |
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
| `url` | string (HttpUrl) | PDF 公开可访问 URL |
| `id` | string | 任务唯一标识，由调用方指定 |

**响应**：

```json
{
  "status": "success",
  "run_id": "20260611_153000",
  "message": "审查任务已创建，共 2 个任务，run_id=20260611_153000，失败记录见 runs/20260611_153000/errors.json，可通过 GET /audit/{item_id} 查询状态"
}
```

提交后立即返回；数组中的顺序即 API 优先级（越靠前越优先占用 LLM 槽位）。失败明细见 `runs/{run_id}/errors.json`。

---

### GET /audit/{item_id} — 查询任务结果

**排队中 / 处理中**：

```json
{
  "item_id": "task_001",
  "pdf_url": "https://example.com/file.pdf",
  "status": "waiting",
  "result": null,
  "error_message": null,
  "processing_time": null,
  "create_time": "2026-06-11 15:30:00"
}
```

**成功**（二元符合性）：

```json
{
  "item_id": "task_001",
  "pdf_url": "https://example.com/file.pdf",
  "status": "success",
  "result": {
    "审查结果": [
      {
        "规则内容（需带规则序号）": "1.整体篇幅对比国自然同类别项目是否合适",
        "评估结果": "符合",
        "理由": "证据位置：全文；证据原文：共28页；对照标准：20<=页数<=50；判定结论：符合。"
      }
    ],
    "统计": "3、8、21、"
  },
  "error_message": null,
  "processing_time": 185.3,
  "create_time": "2026-06-11 15:30:00"
}
```

- `评估结果`：仅 `符合` 或 `不符合`
- `统计`：所有「不符合」规则序号，以顿号拼接（无不符合时为空字符串）

**`status` 取值**：

| 值 | 说明 |
|----|------|
| `waiting` | 已入库，尚未被 Worker 取走 |
| `processing` | Worker 已开始处理 |
| `success` | 审核完成，可查看 `result` |
| `error` | 处理失败（下载失败、规则条数异常等），见 `error_message` |
| `failure` | 任务 ID 不存在 |

---

## 审核规则说明

系统对申报书做 **49 条规则、二元符合性** 评审，分为 6 个 Prompt 模块：

| 模块 | 规则编号 | 评审内容 |
|------|---------|---------|
| 模块一 | 规则 1–12 | 全文规范性（篇幅、格式、错别字、术语、图文、逻辑等） |
| 模块二 | 规则 13–17 | 项目名称与摘要 |
| 模块三 | 规则 18–26 | 立项依据（背景、文献、字数、配图等） |
| 模块四 | 规则 27–33 | 研究方案（分阶段、样本量、技术路线等） |
| 模块五 | 规则 34–41 | 创新性与成果（转化价值、痛点、计划与产出等） |
| 模块六 | 规则 42–49 | 申请人与经费（团队匹配、分工、文章质量、预算等） |

每条规则在 Prompt 中统一为：**检查步骤 → 符合标准 → 不符合触发**；证据不足时默认判定为「不符合」。

大模型原始字段为 `规则内容` / `理由` / `是否符合`；入库前映射为接口中的 `规则内容（需带规则序号）` / `评估结果` / `理由`。

---

## 处理流程

```
POST /audit（接收 PDF URL 列表）
  │
  ├─ 插入数据库（status: waiting），按提交顺序分配 priority
  ├─ 生成 run_id，后台启动最多 5 个 Worker
  │
  └─ Worker 取任务 → status: processing
       │
       ├─ 1. 下载 PDF（httpx，最多 3 次重试）
       ├─ 2. 提取文本 + 截断 + 三类图像标记（pypdf / PyMuPDF）
       ├─ 3. 清理文本（页码等）
       ├─ 4. 分割章节模块
       ├─ 5. 生成 6 组 Prompt（共 49 条规则）
       ├─ 6. 并发调用 LLM（全局 6 槽 PrioritySemaphore，按提交顺序优先）
       ├─ 7. 解析 JSON → 汇总「不符合」序号
       ├─ 8. 校验规则条数 == 49
       └─ 9. 更新数据库（success / error）；失败写入 runs/{run_id}/errors.json
```

**API 优先级（简要）**：空槽优先分给提交顺序更靠前、且仍有待发请求的 PDF；某路调用卡住只占用 1 个槽，其余槽继续服务其他任务，不会整批停摆。

---

## 项目结构

```
audit2.0/
├── app.py                 # FastAPI 装配入口（lifespan + 挂载路由）
├── cli.py                 # 本地联调：本地 PDF → 管线（可 --dry-prompt）
├── config.py              # 常量（规则数、DB、workers、下载重试等）
├── api/                   # HTTP 路由与请求模型
│   ├── schemas.py
│   └── routes.py
├── pipeline/              # 纯审核管线（不写 DB）
│   └── audit.py
├── services/              # 下载、SQLite、错误落盘、批量 Worker
│   ├── download.py
│   ├── store.py
│   ├── errors.py
│   └── batch.py
├── prompt.py              # 49 条规则 / 6 模块 Prompt
├── preprocess/            # PDF 提取、清洗、分章
├── model/                 # LLM Provider 与并发控制
├── postprocess/           # 解析与结果格式化
├── eval/                  # 金标准评测（见 eval/README.md）
├── runs/                  # 线上批次失败记录 runs/{run_id}/errors.json
├── pyproject.toml
└── README.md
```

评测流水线（批量预测、与金标准对比等）详见 [`eval/README.md`](eval/README.md)。

---

## 数据库结构

```sql
CREATE TABLE audit_items (
    item_id         TEXT PRIMARY KEY,   -- 任务 ID（调用方指定）
    pdf_url         TEXT,               -- PDF URL
    status          TEXT,               -- waiting / processing / success / error
    result          TEXT,               -- JSON 审核结果（成功时）
    error_message   TEXT,               -- 错误信息
    processing_time REAL,               -- 耗时（秒）
    create_time     TEXT                -- 创建时间
);
```

---

## 注意事项

- PDF 须通过公开 URL 访问，且 `Content-Type` 含 `pdf`
- 单任务耗时通常约数分钟（取决于页数与模型响应）
- 同一 `id` 重复提交会覆盖原记录（`INSERT OR REPLACE`）
- 成功落库要求解析后规则条数恰好为 **49**；否则 `status=error`，并写入 `runs/{run_id}/errors.json`
- 切换模型：设置 `AUDIT_LLM_PROVIDER` 并配置对应 API Key 后重启服务
