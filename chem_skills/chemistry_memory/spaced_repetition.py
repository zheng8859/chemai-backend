"""艾宾浩斯间隔复习引擎 — 升降级规则与间隔天数的纯函数实现。

设计文档 29 号 §二~§四：
    - 6 级螺旋复习模型（Level 0-5）
    - 间隔天数从当前时间起算（非上次复习日+间隔）
    - 升降级判定：先判正误 → 更新计数器 → 再判级别变化
"""

from datetime import timedelta


# Level → 下次复习间隔天数
# Level 0: 初次学习 → 当天（0 天，趁热打铁）
# Level 1: 第 1 次复习 → 1 天后
# Level 2: 第 2 次复习 → 3 天后
# Level 3: 第 3 次复习 → 7 天后
# Level 4: 第 4 次复习 → 14 天后
# Level 5: 已掌握 → 不再安排（调用方应设置 next_review_date=NULL）
SPIRAL_REVIEW_DAYS = {
    0: 0,
    1: 1,
    2: 3,
    3: 7,
    4: 14,
}

MAX_LEVEL = 5  # 掌握级别上限


def compute_next_review(level: int) -> timedelta:
    """根据复习级别返回下次复习间隔。

    Args:
        level: 当前复习级别 (0-4)。Level 5 表示已掌握，调用方应特殊处理。

    Returns:
        到下次复习的时间增量。
    """
    days = SPIRAL_REVIEW_DAYS.get(level, 0)
    return timedelta(days=days)


def evaluate_level_change(
    level: int,
    consecutive_correct: int,
    consecutive_wrong: int,
    is_correct: bool,
) -> dict:
    """根据作答正误和连续计数计算升降级结果。

    判定顺序（设计文档 29 号 §4.2）：
        1. 先判正误
        2. 更新计数器
        3. 再判升降级

    特殊规则（§4.1）：
        - 连续答对 2 次才升级（上限 MAX_LEVEL）
        - 答错且 level > 0 时降级
        - Level 0 答错不降级
        - 上次答对（consecutive_correct=1）本次答错 → 不降级
          （"一次回退不降级——可能是粗心而非遗忘"）

    Args:
        level: 当前复习级别。
        consecutive_correct: 当前连续答对次数（本次作答前）。
        consecutive_wrong: 当前连续答错次数（本次作答前）。
        is_correct: 本次作答是否正确。

    Returns:
        {
            "new_level": int,           # 更新后的级别
            "new_consecutive_correct": int,  # 更新后的连续答对次数
            "new_consecutive_wrong": int,    # 更新后的连续答错次数
            "level_changed": bool,           # 级别是否发生变化
            "upgraded": bool,                # 是否升级
            "downgraded": bool,              # 是否降级
        }
    """
    new_cc = consecutive_correct
    new_cw = consecutive_wrong
    upgraded = False
    downgraded = False

    if is_correct:
        # 答对：连续正确+1，连续错误归零
        new_cc += 1
        new_cw = 0

        if new_cc >= 2 and level < MAX_LEVEL:
            level += 1
            new_cc = 0
            upgraded = True
    else:
        # 答错：连续错误+1
        new_cw += 1

        # 特殊规则：上次答对本次答错 → 不降级
        if consecutive_correct == 1:
            # 只重置计数器，不降级
            new_cc = 0
        elif level > 0:
            # 降级
            level -= 1
            new_cw = 0
            new_cc = 0
            downgraded = True
        else:
            # Level 0 答错不降级
            new_cc = 0

    return {
        "new_level": level,
        "new_consecutive_correct": new_cc,
        "new_consecutive_wrong": new_cw,
        "level_changed": upgraded or downgraded,
        "upgraded": upgraded,
        "downgraded": downgraded,
    }
