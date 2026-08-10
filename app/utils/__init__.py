"""ChemAI - 通用工具函数。"""

from datetime import datetime, timedelta, timezone

# ── 化学术语 → 通俗表述映射表 ─────────────────────────────────
# 与 33-家长端与通知系统设计 对齐，确保家长看到的内容无专业术语。

CHEM_TERM_MAP: dict[str, str] = {
    "氧化还原反应": "与电子转移相关的反应",
    "离子反应": "溶液中离子的反应",
    "物质的量": "化学计量单位",
    "摩尔": "化学计量单位",
    "化学平衡": "反应的动态平衡",
    "元素周期律": "元素性质的规律",
    "电解质": "能导电的化合物",
    "共价键": "原子间的连接方式",
    "离子键": "原子间的连接方式",
    "配平": "方程式配平",
    "沉淀": "不溶于水的固体",
    "中和反应": "酸碱反应",
    "摩尔质量": "单位物质的量的质量",
    "阿伏加德罗常数": "微观粒子计数单位",
    "电离": "物质在水中分解",
    "水解": "物质与水的反应",
    "酯化反应": "酸与醇生成酯的反应",
    "加成反应": "有机物加成的反应",
    "取代反应": "有机物原子替换的反应",
    "消去反应": "有机物消除小分子的反应",
}


def convert_chemical_terms(raw: str) -> str:
    """将化学专业术语替换为通俗表述（供家长端展示）。

    Args:
        raw: 可能包含化学术语的原始文本

    Returns:
        替换后的通俗表述文本
    """
    result = raw
    for term, plain in CHEM_TERM_MAP.items():
        if term in result:
            result = result.replace(term, plain)
    return result


def convert_chemical_terms_list(terms: list[str]) -> list[str]:
    """对术语列表逐条转换为通俗表述。

    Args:
        terms: 化学术语列表

    Returns:
        通俗表述列表
    """
    if not terms:
        return []
    return [convert_chemical_terms(t) for t in terms]


def get_current_week_start(now: datetime | None = None) -> datetime:
    """返回本周一 00:00:00 (UTC)。

    Args:
        now: 当前时间，默认 datetime.now(timezone.utc)

    Returns:
        本周一零点（带 UTC 时区）
    """
    if now is None:
        now = datetime.now(timezone.utc)
    return (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def get_current_week_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    """返回本周起止时间 [周一 00:00, 下周一 00:00) (UTC)。"""
    start = get_current_week_start(now)
    end = (start + timedelta(days=7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start, end
