# 智聘云前端 v2（前后端分离）

纯 SPA，与后端仅通过 HTTP API 通信，不含任何后端逻辑。

## 技术栈
React 18 · TypeScript · Vite 5 · Tailwind CSS · React Router · axios · recharts · lucide-react · react-markdown

## 启动

```bash
cd frontend
npm install
npm run dev     # http://localhost:18016
```

开发态代理（见 `vite.config.ts`）：
- `/api`     → 主后端 `http://localhost:18000`
- `/rag-api` → RAG 服务 `http://localhost:18003`（制度问答 SSE）

## 生产构建 / 部署

```bash
npm run build   # 输出 dist/
```

`dist/` 可部署到任意静态服务器（Nginx 等），API 地址通过环境变量覆盖：

| 变量 | 默认 | 说明 |
|------|------|------|
| `VITE_API_BASE` | `""` | 主后端 API 前缀（生产 Nginx 需把 `/api` 反代到 :18000） |
| `VITE_RAG_BASE` | `/rag-api` | RAG 服务前缀（反代到 :18003） |

## 目录结构

```
src/
├── lib/api.ts          # 统一 API 层：axios 实例 + JWT 拦截器 + SSE 流式工具
├── types.ts            # 与后端 schema 对齐的类型契约
├── contexts/AuthContext.tsx
├── components/         # Layout(侧边栏壳) / ui(通用组件) / ProtectedRoute
└── pages/
    ├── Login / Register          # 认证
    ├── Dashboard                 # 统计图表
    ├── Candidates                # 候选人列表（搜索/筛选/新建/删除）
    ├── CandidateDetail           # 简历上传、AI 匹配分析、问卷/面试记录
    ├── Pipeline                  # 招聘漏斗 + 人才池管理
    ├── Interviews                # AI 排期 → 确认 → 面试反馈
    ├── Questionnaires            # 问卷发送与跟踪
    ├── PolicyAgent               # 制度文档入库 + RAG 流式问答
    ├── ExamAnalysis              # Dify 试卷分析记录
    └── Observability             # LLM 调用日志 / Token / 延迟监控
```
