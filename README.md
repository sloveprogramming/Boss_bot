# Boss_bot — AI 智能招聘助手

基于 LangGraph + FastAPI + React 的全流程 AI 招聘系统，覆盖「简历分析 → 智能分流 → 面试排期 → 录用决策」完整闭环，支持 MCP 工具协议、SSE 流式输出、企业制度 RAG 问答。

---

## 业务场景

某中型企业的 HR 团队每天需要处理 50+ 份简历，涉及 Python 开发、Java 工程师、AI 算法、产品经理、外贸运营等 15+ 个岗位类别。当前痛点：

1. **简历量大，人工筛选慢** — 每份简历需要 HR 逐份阅读、判断匹配度，日均耗时 3 小时
2. **分流决策靠经验** — 哪些直接面试、哪些先做笔试、哪些进人才池，没有统一标准
3. **面试排期混乱** — 协调面试官和候选人的时间需要来回发邮件，效率低
4. **候选人信息分散** — 简历、笔试成绩、面试反馈散落在不同系统里，每次沟通都要翻半天
5. **人才池沉睡** — 暂时不匹配但有潜力的候选人，放进去就再也想不起来了

**Boss_bot 的解决方式**：AI 自动读取简历 → 8 维度打分 → 按分数自动分流（快速面试 / 先做问卷 / 进人才池 / 拒绝）→ 自动排面试并发送邮件通知 → 面试反馈 LLM 摘要 → 录用/拒绝决策。整个流程最多需要 HR 确认两次（确认面试时间、做最终决策），其余全部自动完成。

---

## 业务链路（完整闭环）

```
HR 创建候选人 + 上传简历
       │
       ▼
  简历解析（PDF/Word/TXT → 纯文本）
       │
       ▼
  岗位分类（关键词匹配 + LLM 兜底，支持 16 个类别）
       │
       ▼
  LLM 智能分析（8 维度评分，0-100 分）
       │
       ├── >= 80 分 → 快速通道
       │     ├── 自动生成 3 个面试时间段
       │     ├── 发送面试邀请邮件
       │     ├── 候选人确认时间 → 钉钉自动创建日历
       │     ├── 面试完成 → 面试官提交反馈 → LLM 生成摘要
       │     └── 最终决策 → 录用(发 Offer) / 拒绝(发拒信)
       │
       ├── 60~79 分 → 问卷通道
       │     ├── 发送技术问卷链接（对接轻速云）
       │     ├── 等待完成 + 评分
       │     ├── 通过 → 进入面试流程（同上）
       │     └── 不通过 → 拒绝
       │
       ├── 40~59 分 → 人才池
       │     ├── 存入人才池（保留所有分析结果）
       │     ├── 3 个月后自动归档
       │     └── 【闭环回流】随时可重新激活，走新一轮流程
       │
       └── < 40 分 → 拒绝
```

**三个闭环机制**：

| 闭环 | 说明 |
|------|------|
| **通知闭环** | 面试邀请、问卷链接、录用 Offer、拒信 — 每个关键节点自动触发邮件/短信，HR 和候选人双向信息同步 |
| **人才池回流** | 40-59 分的候选人不是"扔掉"，而是"暂存"。后续有新岗位时可以重新激活，避免优质潜力股流失 |
| **画像沉淀闭环** | LLM 每轮分析结果（8 维分数、优势、风险、面试反馈）全部写回数据库，候选人从录入到录用的完整成长轨迹可追溯 |

---

## 技术架构

```
用户浏览器 (:18016)
       │
       ▼
  React SPA (Vite 代理 → :18000)
       │
       ├──────────────────────────────────┐
       ▼                                  ▼
  FastAPI Backend (:18000)        RAG Service (:18003)
  ┌─────────────────────┐         ┌──────────────────────┐
  │ Routers (10 个模块)   │         │ 文档上传 + Milvus 索引 │
  │ LangGraph 工作流引擎  │         │ BGE-M3 混合检索       │
  │ ├── 12 个流程节点      │         │ CrossEncoder 重排序    │
  │ └── Function Calling  │         │ Redis 语义缓存        │
  │ MCP Server (5 Tools)  │         │ SSE 流式问答          │
  │ SSE 流式输出 (4 端点)  │         └──────────────────────┘
  │ SQLAlchemy → MySQL    │                    │
  │ Alembic 迁移           │         Milvus 向量数据库
  └─────────────────────┘         BGE-M3 混合检索 (稠密+稀疏)
              │                            │
              └──────────┬─────────────────┘
                         ▼
                 MySQL + Milvus + Redis + MinIO
```

---

## 技术栈

**前端**: React 18, TypeScript, Vite, Tailwind CSS, recharts, SSE EventSource

**后端**: FastAPI, Uvicorn, SQLAlchemy 2.0, Pydantic v2, JWT, Alembic

**AI/LLM**: DeepSeek V4 Flash (OpenAI 兼容), LangGraph 1.2, LangChain 1.3, MCP SDK 1.28, BGE-M3, CrossEncoder

**数据**: MySQL, Milvus 2.4, Redis, MinIO

**部署**: Docker, Docker Compose

---

## 项目结构

```
Boss_bot/
├── .env.example                   # 环境变量模板（脱敏）
├── docker-compose.yml             # Docker 一键部署 (5 个服务)
├── start_all.py                   # 本地开发一键启动
│
├── backend/                       # 主后端 (:18000) — 招聘流程引擎 + API 服务
│   ├── app/
│   │   ├── main.py                # FastAPI 入口 + CORS + 全局异常处理
│   │   ├── config.py              # Pydantic 配置（从 .env 加载）
│   │   ├── database.py            # SQLAlchemy 异步引擎
│   │   ├── agents/                # LLM 层
│   │   │   ├── llm_client.py      # 统一 LLM 客户端 (chat / stream_chat / stream_chat_json)
│   │   │   ├── prompts.py         # 4 套提示词（简历分析 / 面试排期 / 制度问答 / 反馈摘要）
│   │   │   └── tracing.py         # @trace_llm_call 装饰器
│   │   ├── mcp/                   # MCP 工具协议
│   │   │   ├── server.py          # MCP Server (stdio transport, 5 个 Tools)
│   │   │   ├── client.py          # 内部直连客户端
│   │   │   └── tools/
│   │   │       ├── database.py    # 数据库查询工具（4 个：候选人/详情/面试/仪表盘）
│   │   │       └── email.py       # 邮件发送工具（7 种模板 + 自定义内容）
│   │   ├── models/                # ORM 模型 (10 张表)
│   │   │   ├── candidate.py       # 候选人（姓名/岗位/分数/标签/状态）
│   │   │   ├── resume.py          # 简历（原文 + LLM 分析结果）
│   │   │   ├── interview.py       # 面试（轮次/时间/面试官/反馈）
│   │   │   ├── questionnaire.py   # 问卷 + 问卷回复
│   │   │   ├── notification.py    # 通知记录
│   │   │   ├── policy.py          # 制度文档
│   │   │   ├── talent_pool.py     # 人才池
│   │   │   ├── user.py            # 用户（admin/hr/interviewer/candidate）
│   │   │   ├── llm_log.py         # LLM 调用日志
│   │   │   └── exam_analysis.py   # 考试分析
│   │   ├── routers/               # API 路由 (10 个模块)
│   │   │   ├── candidates.py      # 候选人 CRUD
│   │   │   ├── resumes.py         # 简历上传 + LLM 分析 + SSE 流式分析
│   │   │   ├── interviews.py      # 面试排期 + 确认 + 反馈
│   │   │   ├── questionnaires.py  # 问卷发送
│   │   │   ├── workflow.py        # 工作流触发 + Function Calling + SSE + 人才池
│   │   │   ├── policy_agent.py    # 制度文档上传入库（RAG 问答已移交 rag_service）
│   │   │   ├── dashboard.py       # 仪表盘统计
│   │   │   ├── auth.py            # 注册/登录/JWT
│   │   │   ├── llm_observability.py  # LLM 调用追踪
│   │   │   └── exam_analysis.py   # 考试分析回调
│   │   ├── workflow/              # LangGraph 工作流引擎（核心编排）
│   │   │   ├── state.py           # RecruitmentState 贯穿对象
│   │   │   ├── graph.py           # StateGraph 定义 (12 节点 + 10 条条件边)
│   │   │   ├── agent_client.py    # 独立 Agent HTTP 客户端（可降级）
│   │   │   └── nodes/             # 工作流节点实现
│   │   │       ├── analyze.py     # LLM 简历分析 (Agent → 内联降级)
│   │   │       ├── classify.py    # 岗位分类 (关键词 + LLM 兜底, 16 类)
│   │   │       ├── function_calling.py  # Function Calling 节点
│   │   │       ├── schedule.py    # 面试排期 + 确认 + 完成
│   │   │       ├── questionnaire.py  # 问卷生成 + 等待 + 评分
│   │   │       ├── decision.py    # 录用/拒绝决策
│   │   │       └── talent_pool.py # 人才池入库
│   │   ├── services/              # 业务服务
│   │   │   ├── resume_analyzer.py # 简历文件解析 + 结构化提取
│   │   │   ├── notification.py    # 多渠道通知（邮件/SMS/企微/钉钉）
│   │   │   ├── scheduler_svc.py   # 面试排期算法
│   │   │   └── scheduler_tasks.py # 定时任务（面试提醒 + 人才池归档）
│   │   ├── schemas/               # Pydantic 请求/响应模型
│   │   └── utils/
│   │       └── sse.py             # SSE 事件构建器 (progress/token/tool_call/done/error)
│   ├── migrations/                # Alembic 数据库迁移
│   │   └── env.py                 # 异步 MySQL 环境配置
│   ├── alembic.ini
│   └── requirements.txt
│
├── frontend/                      # 前端 (:18016) — React SPA
│   └── src/
│       ├── App.tsx                # 路由表 (7 条)
│       ├── Layout.tsx             # 侧边栏导航
│       ├── pages/
│       │   ├── Dashboard.tsx      # 首页仪表盘（统计卡片 + 图表）
│       │   ├── Candidates.tsx     # 候选人列表（搜索/筛选/分页）
│       │   ├── CandidateDetail.tsx # 候选人详情（简历分析 + 操作）
│       │   ├── Interviews.tsx     # 面试排期管理
│       │   ├── Pipeline.tsx       # 看板视图（管道拖拽）
│       │   ├── PolicyAgent.tsx    # 制度问答（SSE 流式聊天）
│       │   ├── Questionnaires.tsx # 问卷发送记录
│       │   └── ExamAnalysis.tsx   # 考试分析报告
│       └── lib/
│           └── api.ts             # API 客户端（含 SSE 流式方法）
│
└── rag_service/                   # RAG 独立服务 (:18003) — 企业制度智能问答
    ├── main.py                    # FastAPI 入口
    ├── config.py                  # 独立配置
    ├── Dockerfile
    ├── start.py                   # 本地启动脚本
    └── app/
        ├── database.py            # 数据库连接（共享 MySQL）
        ├── agents/
        │   ├── llm_client.py      # LLM 客户端
        │   └── prompts.py         # 制度问答提示词
        ├── models/
        │   └── policy.py          # PolicyDocument / PolicyChatHistory
        ├── services/
        │   ├── policy_rag.py      # RAG 核心：混合检索 + 重排序 + LLM 生成
        │   ├── policy_text_splitter.py  # Parent-Child 双层分块
        │   └── semantic_cache.py       # Redis 语义缓存
        └── routers/
            ├── documents.py       # 文档上传/列表/删除/重索引
            └── chat.py            # RAG 问答 + SSE 流式
```

---

## 快速开始

### 1. 环境准备

```bash
git clone https://github.com/sloveprogramming/Boss_bot.git
cd Boss_bot
cp .env.example .env
# 编辑 .env 填入真实的 OPENAI_API_KEY、数据库地址、SMTP 密码等
```

### 2. 安装依赖

```bash
cd backend && pip install -r requirements.txt
cd ../rag_service && pip install -r requirements.txt
cd ../frontend && npm install
```

### 3. 初始化数据库

```bash
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS recruit_ai CHARACTER SET utf8mb4"
cd backend && alembic upgrade head
```

### 4. 启动服务

```bash
# 一键启动（Windows）
python start_all.py

# 或分别启动
cd backend    && uvicorn app.main:app --host 0.0.0.0 --port 18000 --reload
cd rag_service && python start.py    # 端口 18003（需要 Milvus 运行）
cd frontend   && npx vite --port 18016
```

### 5. 访问

| 服务 | 地址 |
|------|------|
| 前端页面 | http://localhost:18016 |
| Backend API 文档 | http://localhost:18000/docs |
| RAG Service API 文档 | http://localhost:18003/docs |
| 健康检查 | http://localhost:18000/api/health |

---

## Docker 部署

```bash
docker compose up -d
# 启动 5 个服务：backend (:18000) + rag-service (:18003) + frontend (:18016) + milvus (:19530) + minio
```

---

## API 概览

### 招聘流程

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/workflow/start/{id} | 启动 LangGraph 招聘流程 |
| POST | /api/workflow/start/{id}/stream | SSE 流式输出流程进度 |
| POST | /api/workflow/auto-process/{id} | 自动执行下一步 |
| GET | /api/workflow/status/{id} | 查询候选人当前进度 |
| GET | /api/workflow/pipeline | 管道整体概览 |

### Function Calling (MCP Tools)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/workflow/mcp/tools | 列出所有 MCP Tools (5 个) |
| POST | /api/workflow/function-call | LLM 自主选择工具并执行 |
| POST | /api/workflow/function-call/stream | SSE 流式 Function Calling |

### 候选人 & 简历

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/candidates | 候选人列表（支持筛选/分页） |
| POST | /api/candidates | 新建候选人 |
| DELETE | /api/candidates/{id} | 删除候选人（级联删除） |
| POST | /api/resumes/upload | 上传简历 + 文本解析 |
| POST | /api/resumes/{id}/analyze | LLM 分析简历 |
| POST | /api/resumes/{id}/analyze/stream | SSE 流式分析 |

### 面试排期

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/interviews/schedule/{candidate_id} | 生成面试时间段 |
| POST | /api/interviews/{id}/confirm | 确认面试时间 |
| POST | /api/interviews/{id}/feedback | 提交面试反馈 |

### 企业制度文档 & RAG

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/policy/documents/upload | 上传制度文档入库 |
| GET | /api/policy/documents | 文档列表 |

### RAG Service 独立端点 (:18003)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/documents/upload | 上传文档 + 自动 Milvus 索引 |
| POST | /api/documents/reindex | 清空并重索引全部文档 |
| POST | /api/chat | RAG 问答 |
| POST | /api/chat/stream | SSE 流式问答 |

---

## 数据库表

| 表名 | 说明 | 核心字段 |
|------|------|----------|
| candidates | 候选人 | name, position, status, match_score, job_category, tags, talent_pool_id |
| resumes | 简历 | raw_text, analysis_result(JSON), match_analysis(JSON), summary |
| interviews | 面试 | round, status, interviewers(JSON), confirmed_start, feedback(JSON), ai_summary |
| questionnaires | 问卷 | questions(JSON), status, sent_at, deadline |
| questionnaire_responses | 问卷回复 | answers(JSON), score, passed |
| notifications | 通知 | type, template, recipient, status, sent_at |
| policy_documents | 制度文档 | title, category, content, indexed, chunk_count |
| policy_chat_history | 对话历史 | session_id, role, content, cited_sources(JSON) |
| talent_pool | 人才池 | match_score, strengths(JSON), skills(JSON), status, reactivated_at |
| users | 系统用户 | username, hashed_password, role(admin/hr/interviewer/candidate) |
| llm_call_logs | LLM 追踪 | function_name, model, prompt_tokens, latency_ms |

---

## 核心设计决策

| 决策 | 原因 |
|------|------|
| LangGraph 替代自研状态机 | 支持条件路由、状态持久化、可视化调试，原生 async |
| MCP 替代自研工具协议 | 社区标准，可被任何 MCP Client 连接，不绑定本项目 |
| SSE 替代 WebSocket | 单向推送场景（LLM 生成进度），SSE 更轻量，HTTP 天然兼容 |
| BGE-M3 替代 text-embedding-3 | 同时输出稠密+稀疏向量，稀疏向量对中文关键词检索效果更好 |
| Parent-Child 分块 | 子块检索(300字)保证命中率，父块返回(1200字)保证上下文完整性 |
| RAG 独立拆分 | 后续对接钉钉机器人需要独立部署，不占用招聘流程资源 |
| Alembic 替代 create_all | 生产环境表结构变更可追踪、可回滚 |

---

## License

MIT
