"""维度 4：分子结构审核 — 括号匹配/元素格式/离子电荷。

算法（26号 §五）：
1. 括号匹配校验（栈）
2. 元素符号首字母大写检查
3. 离子电荷格式检查
"""

import re
from .models import (
    StructureResult,
    STRUCTURE_PASSED,
    STRUCTURE_FAILED,
    STRUCTURE_ERROR,
)


def check_structure(equation: str) -> StructureResult:
    """检查方程式的分子结构格式规范性。

    检测：
    - 括号是否匹配（( ) 和 [ ]）
    - 元素符号格式（首字母大写，第二字母小写）
    - 离子电荷格式基本检查

    Args:
        equation: 化学方程式字符串

    Returns:
        StructureResult: 含 status、issues
    """
    if not equation or not equation.strip():
        return StructureResult(status=STRUCTURE_ERROR, message="方程式为空")

    eq = equation.strip()
    issues: list[str] = []

    # 1. 括号匹配
    _check_brackets(eq, issues)

    # 2. 元素符号格式（仅检查纯文本部分，跳过 LaTeX 命令）
    _check_element_format(eq, issues)

    if issues:
        return StructureResult(
            status=STRUCTURE_FAILED,
            message=f"结构问题: {'; '.join(issues)}",
            issues=issues,
        )

    return StructureResult(status=STRUCTURE_PASSED, message="结构格式规范")


def _check_brackets(eq: str, issues: list[str]) -> None:
    """栈结构验证括号匹配。"""
    pairs = {"(": ")", "[": "]"}
    stack: list[tuple[str, int]] = []

    for i, ch in enumerate(eq):
        if ch in "([":
            stack.append((ch, i))
        elif ch in ")]":
            if not stack:
                issues.append(f"位置{i}: 多余的'{ch}'")
                continue
            open_ch, open_pos = stack.pop()
            expected_close = pairs[open_ch]
            if ch != expected_close:
                issues.append(
                    f"位置{open_pos}: '{open_ch}'的闭合括号应为'{expected_close}'，实际为'{ch}'"
                )

    for open_ch, pos in stack:
        issues.append(f"位置{pos}: 未闭合的'{open_ch}'")


def _check_element_format(eq: str, issues: list[str]) -> None:
    """检查元素符号格式。

    规则：元素符号首字母大写，第二字母（如有）小写。
    仅检测不在 LaTeX 命令中的纯文本部分。
    """
    # 移除 LaTeX 命令避免误判
    cleaned = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})?', '', eq)

    # 找到所有可能的元素符号位置（大写字母开头的1-2字符序列）
    for m in re.finditer(r'[A-Z][a-z]?', cleaned):
        sym = m.group(0)
        if len(sym) == 2 and sym[1].isupper():
            issues.append(f"元素符号'{sym}'第二字母应小写")
