"""Gateway — Provider 选择器。

根据消息内容选择 LLM Provider：
- 包含图片/照片/图像/OCR/识别关键词 → "mimo"（支持视觉）
- 其他 → "default"（由调用方选择默认 Provider）

意图分类（chat/navigate）不在此层处理——被 ReAct system prompt 吸收。
工具推荐不在此层处理——Persona 过滤后工具集已足够小（2-8 个）。
"""

import logging
from typing import Literal

logger = logging.getLogger(__name__)

# ── 视觉关键词列表 ──
_VISION_KEYWORDS = [
    "图片", "照片", "图像", "识别", "OCR", "上传",
    "截图", "拍照", "扫描", "图片识别", "看图",
    "image", "photo", "picture", "upload", "scan",
    "这道题",  # 可能附带题目图片
]

# ── 联网搜索关键词 ──
_SEARCH_KEYWORDS = [
    "搜索", "查找", "网上", "最新", "今年",
    "高考", "真题", "查找资料", "查一下",
]

ProviderType = Literal["mimo", "qwen"]


def classify_provider(message: str) -> ProviderType:
    """根据消息内容选择 LLM Provider。

    选择逻辑：
    1. 消息包含视觉关键词 → "mimo"（唯一支持视觉+联网的 Provider）
    2. 消息包含搜索关键词 → "mimo"（MiMo 支持联网搜索）
    3. 其他 → "qwen"（最快，P50 1.5s）

    Args:
        message: 用户消息文本

    Returns:
        Provider 标识字符串
    """
    msg_lower = message.lower()

    # 视觉/搜索场景 → MiMo
    for kw in _VISION_KEYWORDS + _SEARCH_KEYWORDS:
        if kw.lower() in msg_lower:
            logger.debug("Gateway: 选择 mimo（关键词: %s）", kw)
            return "mimo"

    # 默认 → 通义千问（最快）
    logger.debug("Gateway: 选择 qwen（默认）")
    return "qwen"
