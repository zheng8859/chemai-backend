"""方程式解析器 — 拆分反应物/产物/分隔符。

设计决策：
- #17: parse_equation() 返回 EquationParts(reactants, products, separator, normalized, original)
- #18: 括号匹配用正则（高中化学无递归嵌套括号），实际实现用深度计数更稳健
- #5:  提供独立的 extract_equations() 从文本中提取方程式列表

分隔符识别优先级: → > ⇌ > =
"""

import re
from .models import EquationParts
from .chem_normalizer import normalize_formulas


# ═══════════════════════════════════════════════════════════════
# 分隔符正则
# ═══════════════════════════════════════════════════════════════

# 匹配方程式的分隔符（按优先级）
_SEPARATOR_PATTERN = re.compile(r'(→|⇌|=)')

# 方程式片段模式：匹配一个完整方程（以箭头为锚点，向两侧扩展到合理的边界）
# 拆分策略：以 → 或 ⇌ 为中心，向两侧扩展直到遇到非化学字符边界
_ARROW = re.compile(r'(→|⇌)')


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════

def parse_equation(equation: str) -> EquationParts:
    """解析化学方程式字符串，拆分为反应物、产物、分隔符。

    Args:
        equation: 化学方程式字符串（可以是原始格式，内部会先归一化）

    Returns:
        EquationParts: 含 original, normalized, reactants, products, separator

    Raises:
        ValueError: 无法解析的方程式（找不到分隔符、或两侧为空）

    Examples:
        >>> parts = parse_equation('2H2 + O2 → 2H2O')
        >>> parts.reactants
        ['2H2', 'O2']
        >>> parts.products
        ['2H2O']
        >>> parts.separator
        '→'
    """
    original = equation.strip()
    if not original:
        raise ValueError("方程式不能为空")

    # 归一化
    normalized = normalize_formulas(original)

    # 找分隔符（优先级: → > ⇌ > =）
    separator, sep_pos = _find_separator(normalized)
    if separator is None:
        raise ValueError(f"找不到有效的分隔符（需要 →、⇌ 或 =）: {original[:80]}")

    left_side = normalized[:sep_pos].strip()
    right_side = normalized[sep_pos + len(separator):].strip()

    if not left_side:
        raise ValueError(f"反应物侧为空: {original[:80]}")
    if not right_side:
        raise ValueError(f"产物侧为空: {original[:80]}")

    # 拆分化合物（保护括号内的 + 号）
    reactants = _split_compounds(left_side)
    products = _split_compounds(right_side)

    if not reactants:
        raise ValueError(f"无法解析反应物: {left_side}")
    if not products:
        raise ValueError(f"无法解析产物: {right_side}")

    return EquationParts(
        original=original,
        normalized=normalized,
        reactants=reactants,
        products=products,
        separator=separator,
    )


def extract_equations(text: str) -> list[str]:
    """从长文本中提取所有化学方程式字符串。

    用于上层（出题引擎）在题目内容中查找需审核的方程式。

    策略：
    1. 先提取 $...$ 中的 LaTeX 方程式
    2. 再对裸文本，以箭头为锚点，向两侧按字符边界提取单个方程式

    Args:
        text: 可能包含多个方程式的文本

    Returns:
        提取出的方程式字符串列表（去重，均能通过 parse_equation 验证）
    """
    results: list[str] = []
    seen: set[str] = set()

    # 1. LaTeX $...$ 片段
    latex_eqs = re.findall(r'\$([^$]+)\$', text)
    for eq in latex_eqs:
        eq = eq.strip()
        if eq and eq not in seen:
            try:
                parse_equation(eq)
                results.append(eq)
                seen.add(eq)
            except ValueError:
                continue

    # 2. 裸方程：以箭头为锚点提取
    cleaned = normalize_formulas(text)
    _extract_bare_equations(cleaned, results, seen)

    return results


def _extract_bare_equations(text: str, results: list[str], seen: set[str]) -> None:
    """以 → / ⇌ 为锚点，向两侧提取方程片段。

    扩展在遇到非化学字符时停止（箭头、英文小写词等）。
    """
    for match in _ARROW.finditer(text):
        arrow = match.group(0)
        pos = match.start()

        # 向左扩展
        left_start = pos - 1
        while left_start >= 0:
            ch = text[left_start]
            if not _is_equation_char(ch):
                break
            # 检查是否为英文小写词边界（如 "and", "the"）
            if ch.islower() and (left_start == 0 or not text[left_start - 1].isupper()):
                # 可能进入英文词，向前查是否为独立小写字母序列
                pass  # 允许单个小写字母（如化学符号第二字母 Cu 中的 u）
            left_start -= 1
        left_start += 1
        left = text[left_start:pos].strip()

        # 向右扩展
        right_end = pos + len(arrow)
        while right_end < len(text):
            ch = text[right_end]
            if not _is_equation_char(ch):
                break
            # 遇到 3+ 连续小写字母 = 英文词边界
            if ch.islower() and _is_english_word_start(text, right_end):
                break
            right_end += 1
        right = text[pos + len(arrow):right_end].strip()

        # 清理右侧尾部英文词（如 "and", "is"）
        right = _trim_trailing_english(right)

        if left and right:
            eq = f"{left} {arrow} {right}"
            eq = re.sub(r'\s+', ' ', eq).strip()
            if eq not in seen:
                try:
                    parse_equation(eq)
                    results.append(eq)
                    seen.add(eq)
                except ValueError:
                    continue


def _is_english_word_start(text: str, pos: int) -> bool:
    """检测 pos 处是否为英文小写词（3+ 连续小写字母）的起始或中间位置。"""
    # 向前找到小写字母序列的起点
    start = pos
    while start > 0 and text[start - 1].islower():
        start -= 1
    # 向后找小写字母序列的终点
    end = pos
    while end < len(text) and text[end].islower():
        end += 1
    length = end - start
    # 3+ 连续小写字母视为英文词
    return length >= 3


def _trim_trailing_english(s: str) -> str:
    """去掉化学式片段末尾的英文单词。"""
    parts = s.split()
    # 从后向前删除纯小写英文词
    while parts and re.match(r'^[a-z]{3,}$', parts[-1]):
        parts.pop()
    return " ".join(parts)


def _is_equation_char(ch: str) -> bool:
    """判断字符是否属于化学方程式的一部分（不含箭头，避免跨方程吞噬）。"""
    if ch.isspace():
        return True
    if ch.isalnum():
        return True
    # 化学式相关符号（不含箭头 → ⇌ =，用于在 extract 中做边界）
    if ch in "+()[]{}_^↑↓.":
        return True
    return False


# ═══════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════

def _find_separator(normalized: str) -> tuple[str | None, int]:
    """在归一化方程式中定位分隔符。

    返回 (separator_char, position_index)。
    优先级: → > ⇌ > =

    注意: 需要忽略可能出现在条件标注中的箭头（如 \\xrightarrow 已归一化为 →）。
    """
    # 找 →
    pos = normalized.find("→")
    if pos >= 0:
        return "→", pos

    # 找 ⇌
    pos = normalized.find("⇌")
    if pos >= 0:
        return "⇌", pos

    # 找 =
    pos = normalized.find("=")
    if pos >= 0:
        return "=", pos

    return None, -1


def _split_compounds(side: str) -> list[str]:
    """在方程式的某一侧按 + 号拆分化合物。

    保护括号内的 + 号不被拆分。此外，紧跟在数字后的 + 号视为电荷标注（如 Fe3+），不是分隔符。
    例如：
    - '2H2 + O2' → ['2H2', 'O2']
    - '[Cu(NH3)4]2+ + 2OH-' → ['[Cu(NH3)4]2+', '2OH-']

    设计决策 #18：用深度计数而非正则，因括号可能存在（高中化学无递归但简单计数更可靠）。
    """
    compounds: list[str] = []
    current: list[str] = []
    depth: int = 0  # 括号嵌套深度
    i: int = 0

    # 先做一次规范化：确保分隔符 + 前后有空格，电荷 + 没有
    # 这依赖于 normalizer 已经正确区分了分隔符和电荷
    while i < len(side):
        ch = side[i]

        if ch in "([":
            depth += 1
            current.append(ch)
        elif ch in ")]":
            depth = max(depth - 1, 0)
            current.append(ch)
        elif ch == "+" and depth == 0:
            # 分隔符 vs 电荷判断：
            # 规则很简单——看 + 前面紧挨的字符：
            # - 空格 → 分隔符（normalizer 保证分隔符 + 前后有空格）
            # - 数字/字母/] → 电荷标注（如 Fe3+, [Cu(NH3)4]2+）
            prev = side[i - 1] if i > 0 else " "
            if prev == " ":
                compounds.append("".join(current).strip())
                current = []
            else:
                current.append(ch)
        else:
            current.append(ch)

        i += 1

    # 最后一个化合物
    remaining = "".join(current).strip()
    if remaining:
        compounds.append(remaining)

    # 过滤空字符串
    return [c for c in compounds if c]


def _prev_non_space(chars: list[str]) -> str | None:
    """获取当前化合物中最后一个非空格字符。"""
    for ch in reversed(chars):
        if ch != " ":
            return ch
    return None
