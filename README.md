# 智聘云（Boss_bot）— AI 智能招聘助手

> 简历解析 → AI 画像 → 自动分流 → 问卷/面试 → 录用决策的**全流程 AI 招聘系统**。
> 前端为 React SPA，后端为 FastAPI + LangGraph 状态机编排；LLM 走 OpenAI 兼容接口（DeepSeek / 通义千问等）；另附独立 **RAG 服务** 做企业制度问答。

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-LangGraph-green)
![React](https://img.shields.io/badge/React-18+TS-blue)
![LLM](https://img.shields.io/badge/LLM-OpenAI%20Compatible-orange)
![MySQL](https://img.shields.io/badge/DB-MySQL%2FSQLite-9cf)

</div>

---

## 目录

- [核心功能](#核心功能)
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [目录结构](#目录结构)
- [快速开始](#快速开始)
- [环境变量](#环境变量)
- [API 一览](#api-一览)
- [测试](#测试)
- [部署建议](#部署建议)
- [已知限制](#已知限制)

---

## 核心功能

| 模块 | 说明 |
|------|------|
| 候选人管理 | 候选人 CRUD、批量流程入口、人才池、自然语言查询（Function Calling） |
| 简历解析 | PDF / Word / TXT / 图片；扫描件 PDF 自动渲染后走 **PaddleOCR** 识别 |
| AI 智能分析 | 基本信息 / 技能 / 经验 **3 路并行分析**（LangGraph `Send`），维度分落库、按权重加权出总分 |
| 自动分流 | 按匹配分阈值（默认 80 / 60 / 40）路由：快速面试 / 问卷通道 / 人才池 / 结束 |
| 面试管理 | **月视图日历**展示排期，支持按候选人过滤；AI 生成可选时段、候选人确认、提交反馈、**一键取消面试** |
| 面试评审 | 面试完成后 3 路并行评审（技术 / 沟通 / 文化）→ Supervisor 综合决策 → 结果联动候选人状态 |
| 问卷管理 | **全量总览**发送/完成情况，支持姓名/手机搜索与状态筛选；向候选人发送问卷链接 |
| 评分优化 | 用真实面试结果（回标 + 面试官反馈）计算通过率与各维度区分度，**给出简历评分权重调整建议**，可应用并记录迭代历史 |
| 制度问答 RAG | 文档上传 → 向量化 → Milvus 检索 → CrossEncoder 重排 → LLM 流式回答（SSE），带引用来源 |
| 通知 | 邮件通知模板（问卷 / 面试 / 提醒 / 拒信 / Offer），可选钉钉日历集成 |
| 高并发防护 | 简历分析任务可入 **RabbitMQ 队列**（有界并发 + 死信 + 指数退避重试），不可用时自动降级为内联同步 |
| 可观测性 | 后端自动记录每次 LLM 调用（输入输出 / Token / 延迟），可查询聚合统计（`/api/llm`） |

> 已上线页面：**仪表盘 · 候选人 · 招聘管道 · 面试管理（月历） · 问卷管理（总览） · 制度问答 · 试卷分析 · 评分优化**。

---

## 系统架构

### 运行时服务

| 服务 | 端口 | 入口 | 说明 |
|------|------|------|------|
| Backend（主后端） | `18000` | `backend/src/app/main.py` | FastAPI API + LangGraph 工作流 + 任务队列 + 定时任务 |
| RAG Service | `18003` | `rag_service/src/app/main.py` | 企业制度文档索引与智能问答（SSE 流式） |
| Frontend（开发态） | `18016` | `frontend/`（Vite） | React SPA，`/api`、`/rag-api` 由 Vite 代理转发 |
| MySQL / 消息队列 / 向量库 | 见 docker-compose | 容器 | mysql / rabbitmq / milvus + minio / redis 均为可独立启停的基础设施 |

### 服务拓扑

```mermaid
flowchart LR
    U[浏览器] --> F[Frontend :18016]
    F -->|"/api 代理"| B[Backend :18000]
    F -->|"/rag-api 代理"| R[RAG Service :18003]
    B --> W[LangGraph 招聘工作流]
    B --> Q[(RabbitMQ)]
    Q --> WK[backend-worker]
    WK --> W
    B <--> DB[(MySQL)]
    W --> N[通知 / 日历]
    W --> M[MCP 工具: 查库/发邮件]
    R --> MV[(Milvus)]
    R --> DB
```

### 一次简历的完整数据流

```
HR 创建候选人 / 上传简历
  → POST /api/resumes/upload              解析文件为纯文本（PDF/DOCX/TXT/OCR）
  → POST /api/workflow/start/{cid}        进入 LangGraph
      parse_resume → classify（岗位关键词 + LLM 兜底）
      → 3 路并行分析（basic/skills/experience）→ synthesize（按权重加权出 match_score）
      → 按阈值自动分流
          ≥80  → 面试排期     60~79 → 问卷（链接）→ 通过后进入面试
          40~59 → 人才池      <40   → 流程结束
  → schedule_interview → confirm → complete
  → 3 路并行评审（技术/沟通/文化）→ supervisor_decision（录用/拒绝，联动候选人状态）
  → 结果写回 candidates / resumes / interviews / talent_pool 等表
```

---

## 技术栈

- **后端**：Python 3.11 / FastAPI / Uvicorn / SQLAlchemy 2.0（async）/ Pydantic v2
- **工作流**：LangGraph（StateGraph + 条件边 + `Send` 并行分支）
- **LLM**：OpenAI 兼容 SDK（DeepSeek、通义千问等，`OPENAI_BASE_URL` / `OPENAI_MODEL` 可配）
- **AI 工具协议**：MCP Server（stdio）+ 内联 Client（查库 / 发邮件）
- **队列**：aio-pika / RabbitMQ（durable + DLX + TTL 退避重试，自动降级内联）
- **RAG**：Milvus 2.4 / pymilvus / 向量化（Embedding 可配）+ CrossEncoder 重排 / Redis 语义缓存
- **数据**：MySQL（`aiomysql`，默认）/ SQLite（`aiosqlite`，可切换开发）
- **前端**：React 18 / TypeScript / Vite / Tailwind CSS / recharts / lucide-react
- **认证**：JWT（python-jose）+ bcrypt；RBAC 角色 admin / hr / interviewer
- **其他**：PyMuPDF、python-docx、PaddleOCR（扫描件 OCR）、Dify（试卷分析，可选）

---

## 目录结构

```text
Boss_bot/
├── .env.example                 # 环境变量模板（复制为 .env 并填入真实值）
├── docker-compose.yml           # 一键部署基础设施与应用容器
├── Dockerfile.backend           # Backend 镜像（uvicorn app.main:app --app-dir src，容器内 8000）
├── Dockerfile.rag               # RAG 镜像（uvicorn app.main:app --app-dir src，容器内 18003）
├── start_all.py                 # 本地一键启动（Backend + Frontend，可选 RAG）
├── seed_admin.py                # 创建首个管理员脚本
│
├── backend/                     # 主后端（Maven 式：src + pyproject.toml + tests）
│   ├── pyproject.toml / requirements.txt
│   ├── tests/                   # pytest：routers / workflow / scoring / resume_analyzer / llm_client
│   └── src/app/
│       ├── main.py              # FastAPI 入口：lifespan、CORS、路由注册、全局异常
│       ├── config.py            # Pydantic Settings（自动向上查找根目录 .env）
│       ├── database.py          # 异步引擎 / get_db / init_db（create_all 建表）
│       ├── dependencies/        # 认证：bcrypt 哈希、JWT、get_current_user、require_role
│       ├── models/              # 14 张表 ORM（candidate/resume/questionnaire/interview/policy/...）
│       ├── schemas/             # Pydantic 请求/响应模型
│       ├── routers/             # auth / candidates / resumes / questionnaires / interviews /
│       │                        # workflow / dashboard / policy / exam-analysis / llm / scoring
│       ├── agents/              # LLM 层：llm_client（chat / 流式）/ prompts / tracing
│       ├── workflow/            # LangGraph：state / graph / scoring + nodes/（解析·分类·分析·问卷·面试·评审等节点）
│       ├── mcp/                 # MCP Server（stdio）+ Client + tools（database / email）
│       ├── queue/               # RabbitMQ broker / worker（有界并发 + 重试，可降级）
│       ├── services/            # resume_analyzer / scheduler / questionnaire / notification /
│       │                        # calendar_svc / exam_analysis_svc / scheduler_tasks / milvus_indexer ...
│       └── utils/               # SSE 事件工具
│
├── rag_service/                 # 独立 RAG 服务（Maven 式模块）
│   ├── pyproject.toml / requirements.txt
│   ├── start.py                 # uvicorn app.main:app --app-dir src --port 18003
│   ├── tests/                   # policy_rag 管线测试
│   └── src/app/
│       ├── main.py / config.py / database.py
│       ├── agents/              # llm_client / prompts
│       ├── routers/             # chat（SSE）/ documents
│       ├── services/            # policy_rag / text_splitter / semantic_cache
│       └── models/              # policy 文档与对话历史表
│
└── frontend/                    # React SPA（Vite dev :18016）
    └── src/
        ├── App.tsx              # 路由表（/login、/scoring 等）
        ├── contexts/AuthContext.tsx   # 登录态 / JWT
        ├── lib/api.ts           # 全部接口封装 + SSE 解析
        ├── components/          # Layout（侧边栏）、ProtectedRoute、Toast、ui
        └── pages/               # Dashboard/Candidates/CandidateDetail/Interviews(月历)/
                                 # Questionnaires(总览)/ScoringInsights/PolicyAgent/Pipeline/ExamAnalysis
```

> **目录规范（Maven 式）**：每个服务模块拥有独立 `pyproject.toml`（≈ pom.xml）声明依赖与构建配置；源码统一放 `src/`（≈ src/main），测试镜像源码结构放 `tests/`（≈ src/test）；根目录只保留跨服务共享的编排 / 部署文件。

---

## 快速开始

### 1. 本地开发

```bash
# ① 准备环境变量
cp .env.example .env
#    填入 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL / DATABASE_URL 等

# ② 安装依赖（二选一）
pip install -r backend/requirements.txt -r rag_service/requirements.txt
# 或： pip install -e ./backend -e ./rag_service   （走 pyproject.toml）

# ③ 一键启动（Backend + Frontend，默认不含 RAG）
python start_all.py
```

前端 / 后端 / RAG 也可分别启动：

```bash
# Backend（:18000，Swagger 在 /docs）
cd backend && python -m uvicorn app.main:app --app-dir src --host 127.0.0.1 --port 18000

# Frontend（:18016，/api、/rag-api 自动代理）
cd frontend && npm install && npm run dev

# RAG Service（:18003）
cd rag_service && python start.py
```

| 访问入口 | 地址 |
|----------|------|
| Web 控制台 | http://localhost:18016 |
| Backend Swagger | http://127.0.0.1:18000/docs |
| RAG Swagger | http://127.0.0.1:18003/docs |

### 2. 初始化管理员

系统**无任何管理员时**，二选一：

```bash
# 方式一：调用初始化接口
POST /api/auth/setup   {"username":"admin","password":"至少6位","email":"admin@example.com"}

# 方式二：运行脚本（存在管理员自动跳过）
python seed_admin.py --username admin --password yourpass --email admin@example.com
```

> 后续新增 HR / 面试官账号须由已登录的 admin 调用 `POST /api/auth/register` 创建。

### 3. Docker 部署（基础设施 + 应用）

```bash
docker compose up -d
```

包含：`backend`、`rag-service`、`mysql`、`minio`、`milvus-standalone`、`rabbitmq`、`backend-worker`。

> - Backend 镜像内 uvicorn 监听 `8000`，宿主机映射为 `18000`（`18000:8000`）。
> - 前端镜像未包含在 compose 中（Dockerfile 待补），生产建议 `npm run build` 后用 Nginx 托管静态产物并反代 `:18000`。
> - MySQL / Milvus / RabbitMQ 均有健康检查，Backend 与 Worker 等待依赖就绪后才启动。

---

## 环境变量

以根目录 `.env` 为唯一配置源（Backend / RAG 服务共用），模板见 `.env.example`。

| 变量 | 必填 | 说明 |
|------|------|------|
| `OPENAI_API_KEY` | ✅ | OpenAI 兼容接口密钥 |
| `OPENAI_BASE_URL` | ✅ | 接口地址（示例默认 `https://api.deepseek.com`） |
| `OPENAI_MODEL` | ✅ | 模型名（示例默认 `deepseek-v4-flash`） |
| `DATABASE_URL` | ✅ | `mysql+aiomysql://user:pass@host:3306/recruit_ai?...`，也支持 SQLite |
| `JWT_SECRET` | ✅ | 生产务必 ≥32 字节随机值（`python -c "import secrets;print(secrets.token_urlsafe(32))"`） |
| `MILVUS_HOST` / `MILVUS_PORT` | RAG | Milvus 向量库地址 |
| `EMBEDDING_MODEL` | RAG | 向量化模型 |
| `SMTP_*` / `NOTIFICATION_EMAIL_FROM` | 否 | 邮件通知 |
| `SCORE_THRESHOLD_FAST_TRACK` 等 | 否 | 分流阈值，默认 80 / 60 / 40 |
| `SCORE_WEIGHTS_*` | 否 | 评分权重与按岗位类别覆盖（代码内置默认值） |
| `RABBITMQ_URL` / `TASK_*` | 否 | 异步任务队列，不可达时自动降级内联 |
| `REDIS_URL` / `SEMANTIC_CACHE_*` | 否 | RAG 语义缓存 |
| `DIFY_API_URL` / `DIFY_API_KEY` | 否 | 试卷分析；未配置返回内置模拟分析 |
| `DINGTALK_APP_KEY` / `DINGTALK_APP_SECRET` | 否 | 钉钉日历集成 |
| `EXAM_WEBHOOK_TOKEN` | 否 | 考试平台回调签名（`X-Webhook-Token`） |

---

## API 一览

完整可交互文档见 Backend `/docs`、RAG `/docs`。按模块速览：

| 前缀 | 说明 | 主要端点 |
|------|------|----------|
| `/api/auth` | 认证 | `POST /setup`（首个管理员）、`POST /register`（admin 建账号）、`POST /login`、`GET /me`、`POST /change-password` |
| `/api/candidates` | 候选人 | `POST /`、`GET /`（分页/搜索/状态）、`GET/PUT/DELETE /{id}` |
| `/api/resumes` | 简历 | `POST /upload`、`POST /{rid}/analyze`、`POST /{rid}/analyze/stream`（SSE）、`GET /candidate/{cid}` |
| `/api/questionnaires` | 问卷 | `POST /send-link`、`GET /`（全量总览+筛选）、`GET /{qid}`、`GET /candidate/{cid}` |
| `/api/interviews` | 面试 | `POST /generate-slots`、`POST /confirm-slot`、`POST /feedback`、`GET /calendar?start&end`、`POST /{id}/cancel`、`GET /candidate/{cid}`、`GET /{id}` |
| `/api/workflow` | 招聘流程 | `POST /start/{cid}`、`POST /auto-process/{cid}`、`GET /pipeline`、`GET /talent-pool`、`POST /talent-pool/reactivate`、`GET /status/{cid}`、`POST /function-call/stream`、`POST /start/{cid}/stream`、`GET /task/{tid}` |
| `/api/dashboard` | 统计 | `GET /stats`、`GET /score-buckets`、`POST /scoring-weights`（admin） |
| `/api/scoring` | 评分优化 | `GET /insights`（通过率+维度区分度+建议权重）、`POST /iterations`（应用并落迭代历史）、`GET /iterations` |
| `/api/policy` | 制度文档管理 | `POST /documents/upload`、`GET /documents`、`DELETE /documents/{id}`、`POST /chat`、`POST /chat/stream` |
| `/api/llm` | LLM 可观测性（后端） | `GET /logs`、`GET /logs/{id}`、`GET /stats` |
| `/api/exam-analysis` | 试卷分析 | `POST /webhook`（回调）、`GET /`（分页）、`POST /import` |
| RAG `/api/documents` | RAG 文档 | `POST /upload`、`POST /index/{id}`、`GET /`、`DELETE /{id}`、`POST /reindex` |
| RAG `/api/chat` | 制度问答 | `POST /`、`POST /stream`（SSE）、`GET /history/{session_id}` |

---

## 测试

```bash
cd backend && pytest -q      # routers / workflow 阈值分流 / scoring / resume_analyzer / llm_client
cd rag_service && pytest -q # policy_rag 管线
```

测试要点：
- `test_workflow.py`：State 字段、阈值分流（80/60/40）、图可编译。
- `test_routers.py`：健康检查、登录/注册权限、未认证访问被拒。
- `test_scoring.py`：评分权重合法性与计算逻辑。
- `test_llm_client.py`：LLM 客户端与 Trace 装饰器（注入 mock）。

---

## 部署建议

- **开发环境**：单机即可（8C16G 以下即可流畅运行）；`python start_all.py` 一键起。
- **生产 ECS（推荐 Ubuntu 22.04）**：
  1. `apt install docker.io docker-compose-plugin`（或 `curl -fsSL https://get.docker.com | sh`）；
  2. `git clone` 项目并写好根目录 `.env`（**LLM Key、JWT_SECRET、数据库密码由自己填，勿外泄**）；
  3. `docker compose up -d` 拉起 MySQL / Milvus / RabbitMQ 等基础设施；
  4. Backend 与 Worker 就绪后 `python seed_admin.py` 初始化首个管理员；
  5. 前端 `cd frontend && npm run build`，产物放 Nginx 静态目录，并反向代理 `/api` → `:18000`、`/rag-api` → `:18003`。

> 建议配置：生产可按 2C4G 起步（Backend + RAG + 轻量 Milvus），承载数十~数百候选人/日的规模；更高并发时给 MySQL 单独机器并横向扩展 `backend-worker`。

---

## 已知限制

1. **建表非迁移式**：当前用 `Base.metadata.create_all`，字段变更需手动 ALTER（无 Alembic 自动迁移）。
2. **问卷为简化模式**：发送固定链接（轻速云等），不内置题目与作答评分；问卷通道默认「完成即通过」。
3. **评分权重应用为进程内存热更新**：与仪表盘一致，重启后回退 `.env`/代码默认值；每次应用都会写入 `scoring_iterations` 迭代历史。
4. **可选基础设施**（RabbitMQ / Milvus / Redis）不可达时分别降级为内联执行 / 跳过向量检索 / 跳过缓存，能力会受相应影响。
5. **Docker 前端未内置**：compose 中 frontend 处于注释状态，生产需自行补前端镜像或用 Nginx 托管产物。
6. **角色模型**：RBAC 面向 admin / hr / interviewer；候选人侧交互（确认面试、填问卷）通过公开链接/口令完成，暂无候选人账号体系。

---

*说明：本文档基于仓库当前代码实际结构与行为编写；`.env.example` 为环境变量唯一模板。*
