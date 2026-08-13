"""ChemAI 配置管理 — 所有环境变量与默认值集中定义。"""

import os
from pathlib import Path

# ── 项目根目录 ────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# ── 四维审核引擎数据目录 ──────────────────────────────────
CHEMAI_DATA_DIR = os.getenv("CHEMAI_DATA_DIR", str(DATA_DIR))

# ── 数据库 ─────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{PROJECT_ROOT}/data/chemai.db")
CHECKPOINT_DB_URL = os.getenv("CHECKPOINT_DB_URL", f"sqlite+aiosqlite:///{PROJECT_ROOT}/data/checkpoint.db")
MEMORY_DB_URL = os.getenv("MEMORY_DB_URL", f"sqlite+aiosqlite:///{PROJECT_ROOT}/data/memory.db")

# ── ChromaDB 向量库 ────────────────────────────────────────
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", str(DATA_DIR / "chroma_db"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "exam_questions")

# ── LLM Provider ───────────────────────────────────────────
# 三级 Fallback：MiMo → 通义千问 → DeepSeek
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")
MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "")
MIMO_MODEL = os.getenv("MIMO_MODEL", "mimo-v2.5")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "")
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")

# Provider 选择策略
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto")  # auto | mimo | qwen | deepseek
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))

# ── OCR 管道 ───────────────────────────────────────────────
BAIDU_OCR_API_KEY = os.getenv("BAIDU_OCR_API_KEY", "")
BAIDU_OCR_SECRET_KEY = os.getenv("BAIDU_OCR_SECRET_KEY", "")
OCR_SHEET_PROVIDER = os.getenv("OCR_SHEET_PROVIDER", "mineru")  # mineru | baidu
OCR_POLL_INTERVAL = int(os.getenv("OCR_POLL_INTERVAL", "5"))  # 轮询间隔（秒）

# ── OCR 文件上传配置 ────────────────────────────────────────
OCR_UPLOAD_DIR = Path(os.getenv("OCR_UPLOAD_DIR", str(DATA_DIR / "ocr_uploads")))
OCR_MAX_FILE_SIZE_MB = int(os.getenv("OCR_MAX_FILE_SIZE_MB", "10"))
OCR_MAX_BATCH_SIZE = int(os.getenv("OCR_MAX_BATCH_SIZE", "50"))
OCR_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".pdf"}
OCR_ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/bmp", "image/webp",
    "application/pdf",
}

# ── VLM 配置 ────────────────────────────────────────────────
ZHIPU_BASE_URL = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
ZHIPU_VISION_MODEL = os.getenv("ZHIPU_VISION_MODEL", "glm-4v")

# ── Agent 引擎 ─────────────────────────────────────────────
AGENT_VERSION = os.getenv("AGENT_VERSION", "v2")  # v2 (单 Agent) | v1 (多 Agent 回退)
AGENT_RECURSION_LIMIT = int(os.getenv("AGENT_RECURSION_LIMIT", "12"))
AGENT_CONTEXT_MAX_MESSAGES = int(os.getenv("AGENT_CONTEXT_MAX_MESSAGES", "30"))

# ── 知识图谱 ───────────────────────────────────────────────
KNOWLEDGE_GRAPH_PATH = os.getenv("KNOWLEDGE_GRAPH_PATH", str(DATA_DIR / "knowledge_graph" / "knowledge_points.json"))
EXAM_BANK_PATH = os.getenv("EXAM_BANK_PATH", str(DATA_DIR / "exam_bank"))

# ── 安全 ───────────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

# ── 调度 ───────────────────────────────────────────────────
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "Asia/Shanghai")
