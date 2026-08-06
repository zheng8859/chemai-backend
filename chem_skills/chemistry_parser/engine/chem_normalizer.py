"""化学式归一化器 — 将 LaTeX/Unicode 方程式转为纯 ASCII 解析器格式。

设计决策 #16: 归一化器只输出解析器格式 — 箭头统一为 →，下标统一为 ASCII 数字。
解析器正则只需支持 `H2` 格式。

处理管线（按顺序）：
1. 剥离 $...$ 和 \ce{...} 包装
2. 统一箭头符号（\rightarrow / \rightleftharpoons / -> / = → →）
3. 转换 LaTeX 下标 _{N} → N、上标 ^{M} → M
4. 转换 Unicode 下标/上标字符
5. 清理多余空白
"""

import re


# ═══════════════════════════════════════════════════════════════
# Unicode 字符映射
# ═══════════════════════════════════════════════════════════════

_UNICODE_SUBSCRIPT: dict[str, str] = {
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
}

_UNICODE_SUPERSCRIPT: dict[str, str] = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁺": "+", "⁻": "-",
}

def normalize_formulas(text: str) -> str:
    """归一化化学方程式文本，输出纯 ASCII 解析器格式。

    输入示例：
      - '$2H_2 + O_2 \\rightarrow 2H_2O$'
      - '$\\ce{2H2 + O2 -> 2H2O}$'
      - '2H₂ + O₂ → 2H₂O'  (Unicode)
      - 'Ca(OH)₂ + CO₂ → CaCO₃ + H₂O'

    输出示例：
      '2H2 + O2 → 2H2O'
      'Ca(OH)2 + CO2 → CaCO3 + H2O'

    Args:
        text: 原始方程式字符串（可能含 LaTeX、Unicode）

    Returns:
        纯 ASCII 格式的归一化方程式
    """
    if not text or not text.strip():
        return ""

    s = text.strip()

    # ── Step 1: 剥离 LaTeX 包装 ──
    s = _unwrap_latex(s)

    # ── Step 2: 统一箭头 ──
    s = _normalize_arrows(s)

    # ── Step 3: 转换 LaTeX 下标/上标 ──
    s = _normalize_latex_subscripts(s)
    s = _normalize_latex_superscripts(s)

    # ── Step 4: 转换 Unicode 字符 ──
    s = _normalize_unicode_subscripts(s)
    s = _normalize_unicode_superscripts(s)

    # ── Step 5: 清理 ──
    s = _cleanup(s)

    return s


# ═══════════════════════════════════════════════════════════════
# Step implementations
# ═══════════════════════════════════════════════════════════════

def _unwrap_latex(s: str) -> str:
    """剥离 LaTeX 数学模式包装。

    - 去除最外层 $...$ 或 $$...$$
    - 去除 \\ce{...} 命令包装
    - 去除 \text{...} 命令（条件标注用）
    """
    # 去除 $$...$$
    if s.startswith("$$") and s.endswith("$$"):
        s = s[2:-2]

    # 去除最外层 $...$
    if s.startswith("$") and s.endswith("$"):
        s = s[1:-1]

    # 去除 \ce{...} 包装（可能嵌套）
    # 模式: 行首或空格后的 \ce{...}
    s = re.sub(r'\\ce\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', r'\1', s)

    return s


def _normalize_arrows(s: str) -> str:
    """统一所有箭头为 → 或 ⇌。

    - \\rightarrow / \\longrightarrow → →
    - \\rightleftharpoons / \\rightleftharpoons → ⇌
    - \\xrightarrow{...} → →（丢弃条件信息，归一化后由 parser 按 → 处理）
    - -> / = → →（高中化学中 = 通常等价于 →）
    - \\leftarrow → ←
    """
    # LaTeX 长箭头
    s = s.replace("\\longrightarrow", "→")
    s = s.replace("\\rightarrow", "→")
    s = s.replace("\\leftarrow", "←")
    s = s.replace("\\longleftarrow", "←")

    # LaTeX 可逆箭头
    s = s.replace("\\rightleftharpoons", "⇌")
    s = s.replace("\\leftrightharpoons", "⇌")
    s = s.replace("\\rightleftharpoon", "⇌")

    # \xrightarrow{条件} → 剥离为 →
    s = re.sub(r'\\xrightarrow\{[^}]*\}', '→', s)
    s = re.sub(r'\\xleftarrow\{[^}]*\}', '←', s)

    # ASCII 箭头
    s = s.replace("->", "→")

    # = 仅在不在 LaTeX 命令中时转为 →（等号作为箭头在高中学中常见）
    # 保留在 \ce 或 $ 之外的裸 = 转为 →
    # 此处 \ce 已剥离，直接处理
    # 注意：= 也可能出现在离子电荷错误写法中，如 Fe=3+
    # 只在两侧都有化学式时才视为分隔符，简单的启发式：= 前后有空格或字母
    s = re.sub(r'\s*=\s*', ' → ', s)

    return s


def _normalize_latex_subscripts(s: str) -> str:
    """将 LaTeX 下标 _{数字} 转为纯数字。

    H_{2}O → H2O
    (OH)_{2} → (OH)2
    Fe_{2}O_{3} → Fe2O3
    """
    # 匹配 _{...}，提取内部内容
    def _sub_replacer(match):
        inner = match.group(1)
        return inner

    s = re.sub(r'_\{(.*?)\}', _sub_replacer, s)

    # 处理不带花括号的单字符下标: _2 → 2
    s = re.sub(r'_(\d)', r'\1', s)

    return s


def _normalize_latex_superscripts(s: str) -> str:
    """将 LaTeX 上标 ^{...} 转为纯文本。

    Fe^{3+} → Fe3+
    SO_{4}^{2-} → SO42-
    OH^- → OH-  (^ followed by charge without digit)
    """
    def _sup_replacer(match):
        inner = match.group(1)
        return inner

    s = re.sub(r'\^\{(.*?)\}', _sup_replacer, s)

    # 不带花括号的: ^2+ → 2+, ^- → -, ^+ → +
    s = re.sub(r'\^(\d[+\-]?)', r'\1', s)
    s = re.sub(r'\^([+\-])(?![0-9])', r'\1', s)

    return s


def _normalize_unicode_subscripts(s: str) -> str:
    """Unicode 下标 → ASCII 数字。

    ₂ → 2, ₃ → 3, H₂O → H2O
    """
    result = []
    for ch in s:
        result.append(_UNICODE_SUBSCRIPT.get(ch, ch))
    return "".join(result)


def _normalize_unicode_superscripts(s: str) -> str:
    """Unicode 上标 → ASCII 字符。

    ³⁺ → 3+, Fe³⁺ → Fe3+
    """
    result = []
    for ch in s:
        result.append(_UNICODE_SUPERSCRIPT.get(ch, ch))
    return "".join(result)


def _cleanup(s: str) -> str:
    """清理多余空白和残留 LaTeX 命令。

    注意：不可盲目在 + 号周围加空格，会破坏电荷标注（如 Fe3+）。
    只在已有空格的 + 号周围规范化间距。
    """
    # 移除多余的 LaTeX 空格命令
    s = s.replace("\\;", "")
    s = s.replace("\\:", "")
    s = s.replace("\\,", "")
    s = s.replace("\\ ", " ")

    # 移除残留的 LaTeX 文本命令
    s = re.sub(r'\\text\{[^}]*\}', '', s)
    s = re.sub(r'\\mathrm\{([^}]*)\}', r'\1', s)
    s = re.sub(r'\\mathit\{([^}]*)\}', r'\1', s)

    # 修正箭头周围的空格: "A + B → C + D"
    s = re.sub(r'\s*→\s*', ' → ', s)
    s = re.sub(r'\s*⇌\s*', ' ⇌ ', s)

    # 只规范化作为分隔符的 + 号（前后已有空格的），不动电荷标注
    s = re.sub(r'\s+\+\s+', ' + ', s)

    # 压缩多余空白
    s = re.sub(r'\s+', ' ', s)
    s = s.strip()

    return s


# ═══════════════════════════════════════════════════════════════
# 便捷函数：仅归一化化学式（非完整方程式）
# ═══════════════════════════════════════════════════════════════

def normalize_single_formula(formula: str) -> str:
    """归一化单个化学式（不含箭头/加号）。

    Fe_{2}O_{3} → Fe2O3
    Ca(OH)₂ → Ca(OH)2
    """
    s = formula.strip()
    s = _unwrap_latex(s)
    s = _normalize_latex_subscripts(s)
    s = _normalize_latex_superscripts(s)
    s = _normalize_unicode_subscripts(s)
    s = _normalize_unicode_superscripts(s)
    s = s.replace(" ", "")
    return s
