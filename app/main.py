"""ChemAI 智辅化学 — FastAPI 应用入口。

三层 Fallback LLM 路由：MiMo → 通义千问 → DeepSeek。
Agent 引擎：LangGraph create_react_agent (v2)，保留 Multi-Agent v1 为回退。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="ChemAI — 智辅化学",
    description="AI 驱动的化学教学辅助平台 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 桌面应用内嵌场景；生产应收紧
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "chemai-api"}
