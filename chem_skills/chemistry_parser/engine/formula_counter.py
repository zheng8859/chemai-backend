"""化学式元素原子计数器 — 统计单个化学式中各元素的原子总数。

核心算法：
1. 剥离前导系数（如 2H2O → 系数=2）
2. 逐字符解析元素符号 [A-Z][a-z]? 及其后跟的下标数字
3. 递归处理括号组 (GROUP)n 和 [GROUP]n，乘法展开
4. 智能区分下标数字与电荷标注（如 O42-: 下标=4, 电荷=2-）

设计决策：
- #18: 括号用迭代+深度计数（高中化学无递归嵌套）
- 元素正则 [A-Z][a-z]?，下标手动读取以区分电荷
"""

import re
from typing import Dict


# 元素符号匹配（不含下标数字，下标由 _read_subscript 手动读取）
_ELEMENT_SYM = re.compile(r'[A-Z][a-z]?')

# 常见以离子形态单独出现的金属元素（其后单独数字通常为电荷）
_CHARGE_METALS: set[str] = {
    "Fe", "Cu", "Al", "Zn", "Ag", "Na", "K", "Ca", "Mg",
    "Mn", "Pb", "Sn", "Ba", "Li", "Cr", "Co", "Ni", "Hg",
}


def count_elements(formula: str) -> Dict[str, int]:
    """统计单个化学式中各元素的原子总数。

    可直接处理含电荷的化学式（内部自动剥离）。

    Args:
        formula: 化学式，如 'H2O', 'Ca(OH)2', '2H2SO4', 'Fe3+', 'SO42-'

    Returns:
        {元素符号: 原子数}
    """
    if not formula or not formula.strip():
        return {}

    s = formula.strip()

    # Step 1: 剥离前导系数
    coeff, rest = _strip_coefficient(s)

    # Step 2: 解析化学式主体
    counts, _ = _count_inner(rest, 0)

    # Step 3: 乘以前导系数
    if coeff != 1:
        for elem in counts:
            counts[elem] *= coeff

    return counts


# ═══════════════════════════════════════════════════════════════
# Internal
# ═══════════════════════════════════════════════════════════════

def _strip_coefficient(s: str) -> tuple[int, str]:
    m = re.match(r'^(\d+)', s)
    if m:
        return int(m.group(1)), s[m.end():]
    return 1, s


def _count_inner(s: str, start: int) -> tuple[Dict[str, int], int]:
    """从 start 位置递归解析化学式。

    Returns:
        ({元素: 计数}, 下一个未处理位置)
    """
    counts: Dict[str, int] = {}
    i = start
    n = len(s)

    while i < n:
        ch = s[i]

        # 闭合括号 → 返回上层
        if ch in ")]":
            return counts, i

        # 电荷符号 → 停止当前层解析
        if ch in "+-":
            # 跳过电荷剩余部分
            i += 1
            while i < n and s[i].isdigit():
                i += 1
            continue

        # 左括号 → 递归
        if ch in "([":
            close = ")" if ch == "(" else "]"
            inner, next_i = _count_inner(s, i + 1)
            if next_i < n and s[next_i] == close:
                i = next_i + 1
                mult, i = _read_multiplier(s, i)
                for elem, cnt in inner.items():
                    counts[elem] = counts.get(elem, 0) + cnt * mult
            else:
                i = next_i
            continue

        # 元素符号
        elem_m = _ELEMENT_SYM.match(s, i)
        if elem_m:
            symbol = elem_m.group(0)
            i = elem_m.end()
            # 手动读取下标数字（智能区分电荷）
            subscript, i = _read_subscript(s, i, symbol)
            counts[symbol] = counts.get(symbol, 0) + subscript
            continue

        # 无法识别 → 跳过
        i += 1

    return counts, i


def _read_subscript(s: str, i: int, element_symbol: str) -> tuple[int, int]:
    """从位置 i 读取下标数字，智能区分电荷。

    'O42-'  → O: subscript=4, 跳过 '2-'
    'Fe3+'  → Fe: subscript=1, 跳过 '3+'  (Fe 是电荷金属)
    'H4+'   → H: subscript=4, 跳过 '+'    (H 非电荷金属)

    Returns:
        (subscript_value, next_position)
    """
    n = len(s)
    if i >= n:
        return 1, i

    # 读取连续数字
    j = i
    while j < n and s[j].isdigit():
        j += 1

    if j == i:
        return 1, i  # 无数字

    digits = s[i:j]
    has_charge_sign = j < n and s[j] in "+-"

    if not has_charge_sign:
        # 纯数字 → 全部是下标
        return int(digits), j

    # 数字后跟电荷符号：需要区分
    if element_symbol in _CHARGE_METALS:
        # 电荷金属：所有数字属于电荷，下标=1
        return 1, i  # 不消耗数字，留给上层电荷处理
    else:
        # 非金属：第一个数字是下标（若多位则最后一位是电荷量）
        if len(digits) >= 2:
            # O42-: '42' → 下标='4', 电荷='2-'
            return int(digits[:-1]), j - 1
        else:
            # NH4+: '4+' → 下标=4, 电荷='+'
            # 下标消耗数字，跳过电荷符号
            return int(digits), j + 1


def _read_multiplier(s: str, i: int) -> tuple[int, int]:
    """读取括号后的数字乘数。

    注意区分：]2+（电荷）vs )3（乘数）。
    括号后的数字若紧跟 +/- 则为电荷，乘数=1。
    """
    n = len(s)
    j = i
    while j < n and s[j].isdigit():
        j += 1
    if j == i:
        return 1, i
    # 数字后跟电荷符号 → 不是乘数
    if j < n and s[j] in "+-":
        return 1, i
    return int(s[i:j]), j
