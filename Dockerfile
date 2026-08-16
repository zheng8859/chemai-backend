# ChemAI 后端镜像 — FastAPI + Uvicorn + SQLite + ChromaDB
# 构建：docker build -t chemai-backend .
# 运行：docker compose up -d
#
# 基础镜像选用 3.11（rdkit / chromadb / langgraph 等依赖的 wheel 覆盖最全）；
# 本地开发为 Python 3.14，如需对齐可改为 python:3.14-slim。

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 系统依赖：科学计算/数据库相关包可能需要编译工具链
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖清单，利用 Docker 层缓存加速重复构建
# 使用国内镜像（与宿主机 pip 同源），避免容器内直连 PyPI 超时
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
COPY requirements.txt .
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt

# 复制应用代码与静态数据（运行时 DB 已由 .dockerignore 排除，走 volume）
COPY app ./app
COPY chem_skills ./chem_skills
COPY agent ./agent
COPY prompts ./prompts
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY frontend ./frontend
COPY data ./data

EXPOSE 8000

# 启动前先幂等迁移数据库，再起服务
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
