# Boss_bot — AI 智能招聘助手

基于 LangGraph + FastAPI + React 的全流程 AI 招聘系统，支持简历自动分析、智能分流、面试排期、候选人画像、企业制度 RAG 问答。

## 功能特性

- **简历智能分析** — 上传 PDF/Word/TXT，LLM 自动提取结构化信息并计算 8 维度匹配度
- **LangGraph 招聘流程引擎** — 12 个节点的状态图自动编排：解析 → 分类 → 分析 → 分流决策 → 面试/问卷/人才池/拒绝
- **Function Calling** — 封装 5 个 MCP Tools（查候选人、查面试、看仪表盘、发邮件），LLM 自主选择调用
- **SSE 流式输出** — 4 个流式端点，支持 Function Calling 全流程、工作流进度、简历分析、制度问答的逐字生成
- **候选人画像** — 跨会话记忆候选人偏好、标签、历史表现，支持人才池激活
- **企业制度 RAG** — BGE-M3 混合检索 + CrossEncoder 重排序 + 语义缓存，计划对接钉钉机器人
- **多渠道通知** — 邮件/SMS/企微/钉钉，7 种邮件模板（面试邀请、拒信、录用通知等）
- **仪表盘** — 候选人总数、状态分布、录用率、周趋势图表

## 技术栈

**前端**: React 18, TypeScript, Vite, Tailwind CSS, recharts

**后端**: FastAPI, Uvicorn, SQLAlchemy 2.0, Pydantic v2, JWT, Alembic

**AI/LLM**: DeepSeek V4 Flash (OpenAI 兼容), LangGraph, LangChain, MCP SDK, BGE-M3, CrossEncoder

**数据**: MySQL, Milvus, Redis, MinIO

**部署**: Docker, Docker Compose

## 项目结构

```
Boss_bot/
├── .env.example              # 环境变量模板（脱敏）
├── docker-compose.yml        # Docker 一键部署
├── start_all.py              # 本地开发一键启动
│
├── backend/                  # 主后端 (:18000)
│   ├── app/
│   │   ├── main.py           # FastAPI 入口
│   │   ├── config.py         # Pydantic 配置
│   │   ├── database.py       # SQLAlchemy 异步引擎
│   │   ├── agents/           # LLM 客户端 + 提示词 + 调用追踪
│   │   ├── mcp/              # MCP Server (5 个 Tools)
│   │   ├── models/           # ORM 模型 (10 张表)
│   │   ├── routers/          # API 路由 (10 个模块)
│   │   ├── workflow/         # LangGraph 工作流引擎
│   │   ├── services/         # 业务服务
│   │   ├── schemas/          # Pydantic 数据模型
│   │   └── utils/            # SSE 事件构建器
│   ├── migrations/           # Alembic 数据库迁移
│   └── requirements.txt
│
├── frontend/                 # 前端 (:18016)
│   └── src/
│       ├── pages/            # 7 个页面（仪表盘/候选人/面试/管道/制度问答/考试分析）
│       └── lib/api.ts        # API 客户端
│
└── rag_service/              # RAG 独立服务 (:18003)
    ├── app/
    │   ├── services/policy_rag.py  # 混合检索 + 重排序 + LLM 生成
    │   └── routers/          # 文档管理 + 制度问答 (含 SSE)
    ├── Dockerfile
    └── start.py
```

## 快速开始

### 1. 环境准备

```bash
# 克隆仓库
git clone https://github.com/sloveprogramming/Boss_bot.git
cd Boss_bot

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入真实的 API Key、数据库地址等
```

### 2. 安装依赖

```bash
cd backend && pip install -r requirements.txt
cd ../rag_service && pip install -r requirements.txt
```

### 3. 初始化数据库

```bash
# 确保 MySQL 已运行，并创建数据库
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS recruit_ai CHARACTER SET utf8mb4"

# 运行 Alembic 迁移
cd backend && alembic upgrade head
```

### 4. 启动服务

```bash
# 一键启动全部服务（Windows）
python start_all.py

# 或分别启动
cd backend    && uvicorn app.main:app --host 0.0.0.0 --port 18000 --reload
cd rag_service && python start.py          # 端口 18003
cd frontend   && npx vite --port 18016
```

### 5. 访问

| 服务 | 地址 |
|------|------|
| 前端页面 | http://localhost:18016 |
| API 文档 | http://localhost:18000/docs |
| RAG 服务文档 | http://localhost:18003/docs |
| 健康检查 | http://localhost:18000/api/health |

## Docker 部署

```bash
# 确保 Docker 已安装
docker compose up -d

# 查看日志
docker compose logs -f backend
```

## API 概览

### 招聘流程
| 端点 | 说明 |
|------|------|
| POST /api/workflow/start/{id} | 启动工作流 |
| POST /api/workflow/start/{id}/stream | SSE 流式工作流进度 |
| GET /api/workflow/status/{id} | 查询候选人当前进度 |
| GET /api/workflow/pipeline | 管道整体概览 |

### Function Calling (MCP Tools)
| 端点 | 说明 |
|------|------|
| GET /api/workflow/mcp/tools | 列出所有 MCP Tools |
| POST /api/workflow/function-call | LLM 自主选择工具 |
| POST /api/workflow/function-call/stream | SSE 流式 Function Calling |

### 候选人 & 简历
| 端点 | 说明 |
|------|------|
| GET /api/candidates | 候选人列表（支持筛选/分页） |
| POST /api/resumes/upload | 上传简历 |
| POST /api/resumes/{id}/analyze | LLM 分析简历 |
| POST /api/resumes/{id}/analyze/stream | SSE 流式分析 |

### 企业制度文档
| 端点 | 说明 |
|------|------|
| POST /api/policy/documents/upload | 上传制度文档入库 |
| GET /api/policy/documents | 文档列表 |

### RAG 服务独立端点 (:18003)
| 端点 | 说明 |
|------|------|
| POST /api/documents/upload | 上传文档 + 自动 Milvus 索引 |
| POST /api/chat | RAG 问答 |
| POST /api/chat/stream | SSE 流式问答 |

## 数据库表

| 表名 | 说明 |
|------|------|
| candidates | 候选人核心信息 + 状态 + 匹配分 |
| resumes | 简历原文 + LLM 分析结果 |
| interviews | 面试排期 + 反馈 + 评价 |
| questionnaires | 问卷发送记录 |
| notifications | 通知发送记录 |
| policy_documents | 企业制度文档 |
| policy_chat_history | 制度问答对话历史 |
| talent_pool | 人才池（候补候选人） |
| users | 系统用户（admin/hr/interviewer） |
| llm_call_logs | LLM 调用追踪日志 |

## 架构设计

```
用户浏览器 (:18016)
       │
       ▼
  React SPA (Vite 代理 → :18000)
       │
       ▼
  FastAPI Backend (:18000)
  ├── Routers (10 个模块)
  ├── LangGraph Workflow Engine
  │     ├── 12 个节点
  │     └── Function Calling 节点
  ├── MCP Server (5 个 Tools)
  ├── Services (简历分析/通知/面试排期)
  ├── SQLAlchemy → MySQL
  └── Milvus ← → RAG Service (:18003)
                    ├── BGE-M3 混合检索
                    ├── CrossEncoder 重排序
                    └── Redis 语义缓存
```

## License

MIT
