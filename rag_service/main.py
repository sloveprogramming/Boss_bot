"""RAG Service — 企业规章制度智能问答独立服务

启动:
    uvicorn main:app --host 0.0.0.0 --port 18003

功能:
    - 文档上传 + 自动向量索引 (Milvus + BGE-M3)
    - RAG 问答（混合检索 + CrossEncoder 重排序 + LLM 生成）
    - SSE 流式输出
    - 语义缓存（Redis）
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.routers import documents, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    """生命周期：初始化数据库"""
    await init_db()
    print("  [RAG Service] 数据库初始化完成")
    print("  [RAG Service] 服务已启动")
    yield
    print("  [RAG Service] 服务关闭")


app = FastAPI(
    title="RAG Service — 企业制度智能问答",
    description="基于 Milvus + BGE-M3 的企业规章制度 RAG 服务，后续对接钉钉机器人",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "RAG Service", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=18003, reload=True)
