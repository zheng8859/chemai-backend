"""化学方程式确定性配平器。

通过构建「元素 × 化合物」原子矩阵并求其零空间（高斯消元），
求解最小正整数化学计量系数。100% 确定、不依赖 LLM。

算法（26 号 §二 红线：配平准确率 = 100%）：
1. 解析反应物/产物 → 化合物列表
2. 逐化合物统计元素原子数（剥离前导系数）
3. 构建矩阵 A[元素][化合物]（反应物 +、产物 -），满足 A·c = 0
4. 高斯消元求零空间基；唯一基向量 → 化为最小正整数系数
5. 还原配平后的方程式字符串
"""

import re
from fractions import Fraction
from math import gcd

from .equation_parser import parse_equation
from .formula_counter import count_elements

# 前导系数剥离（如 2H2O → H2O）
_COEFF_RE = re.compile(r"^\d+")


def balance(reactants: str, products: str) -> dict:
    """配平化学方程式，返回系数与配平后的方程式。

    Args:
        reactants: 反应物侧（如 'H2 + O2'）
        products: 生成物侧（如 'H2O'）

    Returns:
        {
            "balanced_equation": str,
            "coefficients": {化合物: 系数},
            "type": "reversible" | "irreversible",
        }

    Raises:
        ValueError: 解析失败、两侧元素不一致或存在多解时
    """
    parts = parse_equation(f"{reactants} → {products}")

    reactants = [_strip_coeff(c) for c in parts.reactants if _strip_coeff(c)]
    products = [_strip_coeff(c) for c in parts.products if _strip_coeff(c)]
    compounds = reactants + products

    if not compounds:
        raise ValueError("方程式两侧为空，无法配平")

    # 逐化合物统计元素（不含前导系数）
    counts = [count_elements(c) for c in compounds]
    if any(not d for d in counts):
        raise ValueError("存在无法解析的化学式")

    elements = sorted({e for d in counts for e in d})
    elem_index = {e: i for i, e in enumerate(elements)}

    # 构建原子矩阵 A[elem][compound]：反应物 +、产物 -，满足 A·c = 0
    n = len(compounds)
    matrix = [[Fraction(0) for _ in range(n)] for _ in elements]
    for k, d in enumerate(counts):
        sign = 1 if k < len(reactants) else -1
        for elem, cnt in d.items():
            matrix[elem_index[elem]][k] += sign * cnt

    basis = _null_space(matrix)

    if len(basis) == 0:
        raise ValueError("两侧元素不一致，无法配平")
    if len(basis) > 1:
        raise ValueError("存在多个独立配平方案，无法唯一确定")

    coeffs = _to_smallest_integers(basis[0])

    lhs = _format_side(reactants, coeffs[:len(reactants)])
    rhs = _format_side(products, coeffs[len(reactants):])
    balanced_equation = f"{lhs} {parts.separator} {rhs}"
    coefficients = {c: coeffs[k] for k, c in enumerate(compounds)}

    return {
        "balanced_equation": balanced_equation,
        "coefficients": coefficients,
        "type": "reversible" if parts.separator == "⇌" else "irreversible",
    }


def _strip_coeff(compound: str) -> str:
    """剥离化合物前导系数（如 2H2O → H2O）。"""
    return _COEFF_RE.sub("", compound.strip())


def _null_space(matrix: list[list[Fraction]]) -> list[list[Fraction]]:
    """高斯消元（RREF）求矩阵零空间的一组基向量。"""
    m = len(matrix)
    n = len(matrix[0]) if m else 0
    mat = [row[:] for row in matrix]

    pivot_cols: list[int] = []
    row = 0
    for col in range(n):
        pivot = None
        for r in range(row, m):
            if mat[r][col] != 0:
                pivot = r
                break
        if pivot is None:
            continue
        mat[row], mat[pivot] = mat[pivot], mat[row]
        pv = mat[row][col]
        mat[row] = [x / pv for x in mat[row]]
        for r in range(m):
            if r != row and mat[r][col] != 0:
                factor = mat[r][col]
                mat[r] = [mat[r][j] - factor * mat[row][j] for j in range(n)]
        pivot_cols.append(col)
        row += 1
        if row == m:
            break

    free_cols = [c for c in range(n) if c not in pivot_cols]
    basis: list[list[Fraction]] = []
    for fc in free_cols:
        vec = [Fraction(0)] * n
        vec[fc] = Fraction(1)
        for i, pc in enumerate(pivot_cols):
            vec[pc] = -mat[i][fc]
        basis.append(vec)
    return basis


def _to_smallest_integers(vec: list[Fraction]) -> list[int]:
    """将零空间基向量化为最小正整数系数。"""
    denom_lcm = 1
    for x in vec:
        denom_lcm = denom_lcm * x.denominator // gcd(denom_lcm, x.denominator)
    ints = [int(x * denom_lcm) for x in vec]

    # 物理解各系数均 > 0；首个非零系数若为负则整体翻转
    if next((v for v in ints if v != 0), 0) < 0:
        ints = [-v for v in ints]

    g = 0
    for v in ints:
        g = gcd(g, abs(v))
    if g > 1:
        ints = [v // g for v in ints]
    return ints


def _format_side(compounds: list[str], coeffs: list[int]) -> str:
    """按系数格式化方程式某一侧（系数 1 省略）。"""
    terms = [c if k == 1 else f"{k}{c}" for c, k in zip(compounds, coeffs)]
    return " + ".join(terms)
