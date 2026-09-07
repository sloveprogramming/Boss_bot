# 智聘云（Boss_bot）— AI 智能招聘助手

> 简历解析 → AI 画像 → 自动分流 → 问卷/面试 → 录用决策的**全流程 AI 招聘系统**。
> 前端为 React SPA，后端为 FastAPI + LangGraph 状态机编排；LLM 走 OpenAI 兼容接口（DeepSeek / 通义千问等）；另附独立 **RAG 服务** 做企业制度问答、**RabbitMQ worker** 承载高并发分析任务。

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-LangGraph-green)
![React](https://img.shields.io/badge/React-18+TS-blue)
![LLM](https://img.shields.io/badge/LLM-OpenAI%20Compatible-orange)
![MySQL](https://img.shields.io/badge/DB-MySQL%2FSQLite-9cf)
![Langfuse](https://img.shields.io/badge/Observability-Langfuse-red)

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
| 候选人管理 | 候选人 CRUD、批量流程入口、人才池、自然语言查询（Function Calling）、**Excel 导出** |
| **HR 行级数据隔离** | 每位候选人带 `owner_user_id` 归属：HR 只能查看/跟进**自己名下**候选人，admin 全量可见并可**改派负责人**；简历/问卷/面试/人才池/仪表盘全链路按归属过滤 |
| **显示姓名** | 登录名与展示名分离（`users.display_name`）：左下角用户块、候选人「负责人」列、Excel「负责 HR」列统一**姓名优先、缺省回退登录名**；本人左下角自助修改 |
| 简历解析 | PDF / Word / TXT / 图片；扫描件 PDF 自动渲染后走 **PaddleOCR** 识别；支持上传前**预览自动识别回填**与 **quick-add 一步建档** |
| AI 智能分析 | 基本信息 / 技能 / 经验 **3 路并行分析**（LangGraph `Send`），维度分落库、按权重加权出总分；权重支持按岗位类别覆盖 |
| 自动分流 | 按匹配分阈值（默认 80 / 60 / 40）路由：快速面试 / 问卷通道 / 人才池 / 结束；维度分不齐自动转人工复核 |
| **全自动流程** | 候选人详情「全自动流程」一键续跑：后端自动回填该候选人最新简历文本并入队，worker 从当前状态推进（解析→分析→分流→问卷→面试→评审→决策），进度写 `task_progress` 可轮询 |
| 面试管理 | **月视图日历**展示排期，支持按候选人过滤；AI 生成可选时段、候选人确认、提交反馈、**一键取消面试** |
| 面试评审 | 面试完成后 3 路并行评审（技术 / 沟通 / 文化）→ Supervisor 综合决策 → 结果联动候选人状态 |
| 问卷管理 | **全量总览**发送/完成情况，支持姓名/手机搜索与状态筛选；向候选人发送问卷链接 |
| 评分优化 | 用真实面试结果（回标 + 面试官反馈）计算通过率与各维度区分度，**给出简历评分权重调整建议**，可应用并记录迭代历史 |
| 制度问答 RAG | 文档上传 → **RAG 服务**向量化（bge-m3 混合检索 + Milvus）→ LLM 流式回答（SSE），带账号会话历史与引用 |
| **JD 生成器** | 少量结构化输入（岗位/薪资/学历）→ SSE 流式输出结构化 JD；内置《就业促进法》反歧视合规红线；注入岗位专项评分标准保持一致 |
| **JD 全网参考** | 生成 JD 时可选「参考全网」：无 API key 网页搜索同类真实 JD（搜狗/Bing 多 provider 兜底）+ 公司档案适配，产出带来源的草稿；同时暴露为 **MCP 工具** `jd_reference_search` |
| **智能助手（ReAct）** | `POST /api/workflow/function-call/stream` 多轮工具循环：MCP 工具集查库 / 发邮件 / 制度检索 / JD 参考，回答招聘运营问题 |
| 通知 | 邮件通知模板（问卷 / 面试 / 提醒 / 拒信 / Offer），可选钉钉日历集成 |
| 高并发防护 | 简历分析任务入 **RabbitMQ 队列**（有界并发 + 死信 + 指数退避重试），任务进度行**仅由 worker upsert** 写入；不可用时自动降级为内联同步 |
| 可观测性 | 本地 LLM 调用日志聚合统计（`/api/llm`），另支持 **Langfuse** 全链路 trace（可选开关） |
| 试卷分析 | 轻速云 Webhook 回调 + 手动导入 + **主动拉取 Workmenul 自研答题看板**（周期同步，幂等 upsert），支持结果报告下载 |

> 已上线页面：**仪表盘 · 候选人 · 招聘管道 · 面试管理（月历） · 问卷管理（总览） · 制度问答 · 试卷分析 · 评分优化 · JD 生成器**。

---

## 系统架构

### 运行时服务

| 服务 | 端口 | 入口 | 说明 |
|------|------|------|------|
| Backend（主后端） | `18000` | `backend/src/app/main.py` | FastAPI API + LangGraph 工作流 + MCP/Function Calling + 定时任务 |
| Backend Worker | — | `backend/src/app/queue/worker.py` | 独立进程消费 RabbitMQ，有界并发跑 LangGraph，唯一写 `task_progress` |
| RAG Service | `18003` | `rag_service/src/app/main.py` | 企业制度文档向量化（bge-m3）+ 智能问答（SSE） |
| Frontend（开发态） | `18016` | `frontend/`（Vite） | React SPA，`/api`、`/rag-api` 由 Vite 代理转发 |
| MySQL / 消息队列 / 向量库 | 见 docker-compose | 容器 | mysql / rabbitmq / milvus + minio / redis 均为可独立启停的基础设施 |

### 服务拓扑

```mermaid
flowchart LR
    U[浏览器] --> F[Frontend :18016]
    F -->|"/api 代理"| B[Backend :18000]
    F -->|"/rag-api 代理"| R[RAG Service :18003]
    B --> W[LangGraph 招聘工作流]
    B -->|publish 任务| Q[(RabbitMQ)]
    Q --> WK[backend-worker]
    WK --> W
    W --> TP[(task_progress)]
    B <--> DB[(MySQL)]
    W --> N[通知 / 日历]
    W --> M[MCP 工具: 查库/发邮件/制度检索/JD参考]
    B -->|文档向量化/问答| R
    R --> MV[(Milvus)]
```

### 一次简历的完整数据流

```
HR 创建候选人 / 上传简历
  → POST /api/resumes/quick-add 或 preview+upload    解析文件为纯文本（PDF/DOCX/TXT/OCR）
  → POST /api/resumes/analyze 或「全自动流程」auto-process  进入 LangGraph
      parse_resume → classify（岗位关键词 + LLM 兜底）
      → 3 路并行分析（basic/skills/experience）→ synthesize（按权重加权出 match_score）
      → 按阈值自动分流
          ≥80  → 面试排期     60~79 → 问卷（链接）→ 通过后进入面试
          40~59 → 人才池      <40   → 流程结束（维度分不齐 → 人工复核）
  → schedule_interview → confirm → complete
  → 3 路并行评审（技术/沟通/文化）→ supervisor_decision（录用/拒绝，联动候选人状态）
  → 结果写回 candidates / resumes / interviews / talent_pool / task_progress 等表
```

> 「全自动流程」在 HR 不传简历文本时，后端会自动回填该候选人最新 `resumes.raw_text` 再入队；
> 任务进度由 worker 消费时**唯一写入** `task_progress`（API 不再预插行，避免双写撞唯一键）。

---

## 技术栈

- **后端**：Python 3.11 / FastAPI / Uvicorn / SQLAlchemy 2.0（async）/ Pydantic v2
- **工作流**：LangGraph（StateGraph + 条件边 + `Send` 并行分支）
- **LLM**：OpenAI 兼容 SDK（DeepSeek、通义千问等，`OPENAI_BASE_URL` / `OPENAI_MODEL` 可配）
- **AI 工具协议**：MCP Server（stdio）+ 内联 Client；工具集 = 数据库查询 / 邮件 / 制度 RAG / JD 全网参考
- **队列**：aio-pika / RabbitMQ（durable + DLX + TTL 退避重试，自动降级内联）
- **RAG**：Milvus 2.4 / pymilvus / bge-m3 混合检索 + CrossEncoder 重排 / Redis 语义缓存
- **数据**：MySQL（`aiomysql`，默认）/ SQLite（`aiosqlite`，可切换开发）
- **前端**：React 18 / TypeScript / Vite / Tailwind CSS / recharts / lucide-react
- **认证**：JWT（python-jose）+ bcrypt；RBAC 角色 admin / hr / interviewer + 候选人行级归属
- **导出**：openpyxl（候选人 Excel 全量导出）
- **网页搜索**：httpx 无 key 抓取（sogou 为主，Bing RSS/HTML 兜底）
- **其他**：PyMuPDF、python-docx、PaddleOCR（扫描件 OCR）、Langfuse（可选）、Dify / Workmenul（试卷分析，可选）

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
│       ├── dependencies/        # 认证 + 行级隔离：get_current_user / require_role /
│       │                        #   ensure_candidate_visible / candidate_scope_cond
│       ├── models/              # 12 张表 ORM（candidate 含 owner_user_id / resume / questionnaire /
│       │                        #   interview / talent_pool / task_progress / user(display_name) ...）
│       ├── schemas/             # Pydantic 请求/响应模型
│       ├── routers/             # auth / candidates / resumes / questionnaires / interviews /
│       │                        #   workflow / dashboard / policy / exam-analysis / llm / scoring / jd-generator
│       ├── agents/              # LLM 层：llm_client / prompts / company_profile(公司档案·合规红线) /
│       │                        #   session_memory / tracing(Langfuse)
│       ├── workflow/            # LangGraph：state / graph / scoring + nodes/（解析·分类·分析·问卷·面试·评审等节点）
│       ├── mcp/                 # MCP Server（stdio）+ Client + tools/（database / email / policy / jd_reference）
│       ├── queue/               # RabbitMQ broker / worker（有界并发 + 重试，可降级；worker 单写 task_progress）
│       ├── services/            # resume_analyzer / questionnaire / notification / calendar / milvus_indexer /
│       │                        #   exam_analysis_svc / workmenul_sync(主动拉取) / jd_reference_service /
│       │                        #   web_search / scheduler_svc ...
│       └── utils/               # SSE 事件工具
│
├── rag_service/                 # 独立 RAG 服务（Maven 式模块）
│   ├── pyproject.toml / requirements.txt
│   ├── start.py                 # uvicorn app.main:app --app-dir src --port 18003
│   ├── tests/                   # policy_rag 管线测试
│   └── src/app/
│       ├── main.py / config.py / database.py
│       ├── agents/              # llm_client / prompts / embedder
│       ├── routers/             # chat（SSE）/ documents
│       ├── services/            # policy_rag / text_splitter / semantic_cache
│       └── models/              # policy 文档与对话历史表
│
└── frontend/                    # React SPA（Vite dev :18016）
    └── src/
        ├── App.tsx              # 路由表（/login、/candidates/:id、/jd-generator 等）
        ├── contexts/AuthContext.tsx   # 登录态 / JWT / updateProfile
        ├── lib/api.ts           # 全部接口封装 + SSE 解析（主后端直连 / /rag-api 映射分域）
        ├── components/          # Layout（侧边栏 + 左下角改名）、ProtectedRoute、Toast、ui
        └── pages/               # Dashboard / Candidates / CandidateDetail / Pipeline /
                                 # Interviews(月历) / Questionnaires(总览) / PolicyAgent /
                                 # ExamAnalysis / ScoringInsights / JdGenerator / Login / Register
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

# Worker（消费 RabbitMQ，跑异步分析任务；本地单机可不启，自动降级内联）
cd backend/src && python -m app.queue.worker

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

> 后续新增 HR / 面试官账号须由已登录的 admin 调用 `POST /api/auth/register` 创建（可一并填写 `display_name` 展示姓名）。

### 3. Docker 部署（基础设施 + 应用）

```bash
docker compose up -d
```

包含：`backend`、`rag-service`、`mysql`、`minio`、`milvus-standalone`、`rabbitmq`、`backend-worker`。

> - Backend 镜像内 uvicorn 监听 `8000`，宿主机映射为 `18000`（`18000:8000`）。
> - 前端镜像未包含在 compose 中（Dockerfile 待补），生产建议 `npm run build` 后用 Nginx 托管静态产物并反代 `:18000` 与 `:18003`。
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
| `EMBEDDING_MODEL` | RAG | 向量化模型（默认 bge-m3 / text2vec，bge-m3 混合检索需配套 RAG 配置） |
| `SMTP_*` / `NOTIFICATION_EMAIL_FROM` | 否 | 邮件通知 |
| `SCORE_THRESHOLD_FAST_TRACK` 等 | 否 | 分流阈值，默认 80 / 60 / 40 |
| `SCORE_WEIGHTS_DEFAULT` / `SCORE_WEIGHTS_BY_CATEGORY` | 否 | 评分权重与按岗位类别覆盖（代码内置默认值） |
| `RABBITMQ_URL` / `TASK_*` | 否 | 异步任务队列（含 `TASK_ENABLED=false` 全程内联）；不可达时自动降级 |
| `REDIS_URL` / `SEMANTIC_CACHE_*` | 否 | RAG 语义缓存 |
| `EXAM_WEBHOOK_TOKEN` | 否 | 考试平台回调签名（`X-Webhook-Token`）；为空不接受回调 |
| `WORKMENUL_API_BASE` / `EXAM_SYNC_INTERVAL_SECONDS` | 否 | Workmenul 答题看板地址与拉取周期（默认 60s），也可手动 `POST /api/exam-analysis/sync` |
| `DIFY_API_URL` / `DIFY_API_KEY` | 否 | 试卷分析（Dify）；未配置返回内置模拟分析 |
| `JD_REF_ENABLED` / `JD_REF_SEARCH_PROVIDERS` 等 | 否 | JD 全网参考开关与搜索 provider（搜狗/Bing），详见 `.env.example` 注释 |
| `LANGFUSE_ENABLED` / `LANGFUSE_PUBLIC_KEY` 等 | 否 | Langfuse 可观测性（默认关，配置即上报 trace） |
| `DINGTALK_APP_KEY` / `DINGTALK_APP_SECRET` | 否 | 钉钉日历集成 |
| `LLM_PROVIDER` | 否 | 当前仅支持 `openai` 兼容接口 |

---

## API 一览

完整可交互文档见 Backend `/docs`、RAG `/docs`。按模块速览：

| 前缀 | 说明 | 主要端点 |
|------|------|----------|
| `/api/auth` | 认证 / 账号 | `POST /setup`、`POST /register`（admin）、`POST /login`、`GET /me`、`PUT /me`（自助改 display_name）、`GET /users`（按角色列 HR）、`POST /change-password` |
| `/api/candidates` | 候选人 | `POST /`、`GET /`（分页/搜索/状态）、`GET /export`（Excel 全量导出）、`GET/PUT/DELETE /{id}`、`PUT /{id}/owner`（admin 改派负责人） |
| `/api/resumes` | 简历 | `POST /upload`、`POST /preview`（识别回填）、`POST /quick-add`（一步建档）、`POST /{rid}/analyze`、`POST /{rid}/analyze/stream`（SSE）、`GET /candidate/{cid}` |
| `/api/questionnaires` | 问卷 | `POST /send-link`、`GET /`（全量总览+筛选）、`GET /{qid}`、`GET /candidate/{cid}` |
| `/api/interviews` | 面试 | `POST /generate-slots`、`POST /confirm-slot`、`POST /feedback`、`GET /calendar?start&end`、`POST /{id}/cancel`、`GET /candidate/{cid}`、`GET /{id}` |
| `/api/workflow` | 招聘流程 | `POST /start/{cid}`、`POST /auto-process/{cid}`（全自动一键续跑）、`GET /status/{cid}`、`GET /task/{tid}`（队列进度轮询）、`GET /pipeline`、`GET /talent-pool` 系列、`POST /talent-pool/reactivate`、`POST /talent-pool/create`、`GET /mcp/tools`、`POST /function-call`、`POST /function-call/graph/{cid}`、`POST /function-call/stream`（ReAct SSE）、`POST /start/{cid}/stream` |
| `/api/jd` | JD 生成器 | `POST /generate/stream`（SSE，reference=true 走全网参考） |
| `/api/dashboard` | 统计 | `GET /stats`、`GET /score-buckets`、`POST /scoring-weights`（admin） |
| `/api/scoring` | 评分优化 | `GET /insights`、`POST /iterations`、`GET /iterations` |
| `/api/policy` | 制度文档（主后端） | `POST /documents/upload`、`GET /documents`、`DELETE /documents/{id}`、`POST /chat`、`POST /chat/stream`、`GET /sessions`、`GET /history`、`POST /messages`、`DELETE /sessions/{id}` |
| `/api/llm` | LLM 可观测性（后端） | `GET /logs`、`GET /logs/{id}`、`GET /stats` |
| `/api/exam-analysis` | 试卷分析 | `POST /webhook`（轻速云回调）、`GET /`（分页）、`POST /import`、`POST /sync`（手动拉 Workmenul）、`GET /{id}/download-report` |
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
- `test_routers.py`：健康检查、登录/注册权限、未认证访问被拒、行级隔离越权 404。
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

1. **建表非迁移式**：当前用 `Base.metadata.create_all`，字段变更需手动 ALTER（无 Alembic 自动迁移）；历次新增列（`owner_user_id`、`display_name` 等）均为手工幂等 ALTER。
2. **问卷为简化模式**：发送固定链接（轻速云等），不内置题目与作答评分；问卷通道默认「完成即通过」。
3. **评分权重应用为进程内存热更新**：与仪表盘一致，重启后回退 `.env`/代码默认值；每次应用都会写入 `scoring_iterations` 迭代历史。
4. **可选基础设施**（RabbitMQ / Milvus / Redis / RAG 服务）不可达时分别降级为内联执行 / 跳过向量检索 / 跳过缓存 / 跳过向量索引，能力会受相应影响。
5. **Docker 前端未内置**：compose 中 frontend 处于注释状态，生产需自行补前端镜像或用 Nginx 托管产物。
6. **角色模型**：RBAC 面向 admin / hr / interviewer；HR 行级隔离以 `owner_user_id` 判定（admin 全量、HR 只见自己名下）；候选人侧交互（确认面试、填问卷）通过公开链接/口令完成，暂无候选人账号体系。
7. **JD 全网参考为网页抓取**：招聘站对无 cookie 客户端多反爬，默认以搜狗为 provider（Bing RSS 兜底）；无法保证全源可用，失败会静默降级为空素材。
8. **Workmenul 为主动拉取**：bridge 部署在远端时原生 push 到不了本系统，采用本系统周期拉取其公开查询接口 + 幂等 upsert；仅同步终态（completed/failed）答卷。

---

*说明：本文档基于仓库当前代码实际结构与行为编写；`.env.example` 为环境变量唯一模板。*
