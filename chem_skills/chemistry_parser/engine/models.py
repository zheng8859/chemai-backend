"""四维安全审核引擎 — 纯 dataclass 数据模型。

设计原则（零外部依赖）：
- 全部使用 Python @dataclass，不依赖 Pydantic
- 状态字符串使用模块级常量，与 26 号文档 §六对齐
- overall_status 传播规则：blocked > failed > uncertain > warning > passed
"""

from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# 状态常量
# ═══════════════════════════════════════════════════════════════

# 配平维度
BALANCE_PASSED = "passed"
BALANCE_BLOCKED = "blocked"
BALANCE_UNCERTAIN = "uncertain"
BALANCE_ERROR = "error"

# 条件维度
CONDITION_PASSED = "passed"
CONDITION_WARNING = "warning"
CONDITION_FAILED = "failed"
CONDITION_UNCERTAIN = "uncertain"
CONDITION_ERROR = "error"

# 产物维度
PRODUCT_PASSED = "passed"
PRODUCT_WARNING = "warning"
PRODUCT_FAILED = "failed"
PRODUCT_UNCERTAIN = "uncertain"
PRODUCT_ERROR = "error"

# 结构维度
STRUCTURE_PASSED = "passed"
STRUCTURE_FAILED = "failed"
STRUCTURE_UNCERTAIN = "uncertain"
STRUCTURE_ERROR = "error"

# 综合判定
OVERALL_PASSED = "passed"
OVERALL_BLOCKED = "blocked"
OVERALL_UNCERTAIN = "uncertain"
OVERALL_ERROR = "error"

# 严重度排序（数值越小越严重）
_SEVERITY_ORDER: dict[str, int] = {
    OVERALL_BLOCKED: 0,
    "failed": 1,
    OVERALL_UNCERTAIN: 2,
    "warning": 3,
    OVERALL_PASSED: 4,
    OVERALL_ERROR: 5,
}


def _severity_key(status: str) -> int:
    return _SEVERITY_ORDER.get(status, 99)


# ═══════════════════════════════════════════════════════════════
# Data models
# ═══════════════════════════════════════════════════════════════

@dataclass
class EquationParts:
    """解析后的方程式结构。

    由 equation_parser.parse_equation() 产出。
    """
    original: str                                    # 原始输入字符串
    normalized: str                                  # 归一化后的方程式
    reactants: list[str]                             # 反应物化学式列表
    products: list[str]                              # 产物化学式列表
    separator: str = "→"                             # 分隔符（→ / = / ⇌）

    def sum_elements(self) -> tuple[dict[str, int], dict[str, int]]:
        """统计两侧各元素的原子总数。

        Returns:
            (left_elements, right_elements) — 反应物侧合计, 产物侧合计
        """
        from .formula_counter import count_elements

        left: dict[str, int] = {}
        for compound in self.reactants:
            for elem, cnt in count_elements(compound).items():
                left[elem] = left.get(elem, 0) + cnt

        right: dict[str, int] = {}
        for compound in self.products:
            for elem, cnt in count_elements(compound).items():
                right[elem] = right.get(elem, 0) + cnt

        return left, right


@dataclass
class BalanceDetail:
    """配平详情 — 两侧元素原子计数合计数。

    只给合计数，不逐化合物拆分（设计决策 #21）。
    """
    left_elements: dict[str, int] = field(default_factory=dict)   # 反应物侧 {元素: 原子数}
    right_elements: dict[str, int] = field(default_factory=dict)  # 产物侧 {元素: 原子数}


@dataclass
class BalanceResult:
    """维度 1：系数配平审核结果。"""
    status: str = BALANCE_PASSED                     # passed | blocked | uncertain | error
    message: str = ""                                # 人类可读描述
    detail: BalanceDetail | None = None              # 两侧元素计数明细

    def is_balanced(self) -> bool:
        return self.status == BALANCE_PASSED


@dataclass
class ConditionResult:
    """维度 2：反应条件审核结果。"""
    status: str = CONDITION_PASSED                   # passed | warning | failed | uncertain | error
    message: str = ""                                # 人类可读描述
    conditions_found: list[str] = field(default_factory=list)    # 已检测到的条件
    missing_conditions: list[str] = field(default_factory=list)  # 缺失的条件
    contradictions: list[str] = field(default_factory=list)      # 矛盾条件对


@dataclass
class ProductResult:
    """维度 3：产物稳定性审核结果。"""
    status: str = PRODUCT_PASSED                     # passed | warning | failed | uncertain | error
    message: str = ""                                # 人类可读描述
    issues: list[str] = field(default_factory=list)  # 问题描述列表


@dataclass
class StructureResult:
    """维度 4：分子结构审核结果。"""
    status: str = STRUCTURE_PASSED                   # passed | failed | uncertain | error
    message: str = ""                                # 人类可读描述
    issues: list[str] = field(default_factory=list)  # 具体问题列表（设计决策 #27）


@dataclass
class AuditReport:
    """四维综合审核报告。

    由 audit_engine.audit_equation() 产出，聚合四个维度的结果。
    """
    question_id: str = ""                            # 题目唯一标识
    equation: str = ""                               # 被审核的原始方程式
    balance: BalanceResult | None = None             # 维度 1
    condition: ConditionResult | None = None         # 维度 2
    product: ProductResult | None = None             # 维度 3
    structure: StructureResult | None = None         # 维度 4
    overall_status: str = OVERALL_PASSED             # 综合判定
    overall_message: str = ""                        # 按严重度排序的摘要

    def compute_overall(self) -> str:
        """根据四维结果计算综合状态。

        26号 §六.3 定义：
        - 仅 balance=blocked → HARD BLOCK（不可输出，触发重生成）
        - 条件/产物/结构的 failed → 不阻断输出，降级为警告标记
        - uncertain/warning → 不阻断
        """
        results: list = [
            r for r in [self.balance, self.condition, self.product, self.structure]
            if r is not None
        ]

        statuses = [r.status for r in results]

        # 红线：仅配平错误触发 blocked
        if BALANCE_BLOCKED in statuses:
            self.overall_status = OVERALL_BLOCKED
        elif BALANCE_ERROR in statuses or OVERALL_ERROR in statuses:
            self.overall_status = OVERALL_ERROR
        elif BALANCE_UNCERTAIN in statuses or OVERALL_UNCERTAIN in statuses:
            self.overall_status = OVERALL_UNCERTAIN
        else:
            self.overall_status = OVERALL_PASSED

        # 构建按严重度排序的 overall_message（设计决策 #29）
        self.overall_message = self._build_overall_message(results)
        return self.overall_status

    def _build_overall_message(self, results: list) -> str:
        """按严重度排序拼接各维度消息。blocked 排最前。"""
        ordered = sorted(results, key=lambda r: _severity_key(r.status))
        parts = []
        labels = {
            "balance": "配平", "condition": "条件",
            "product": "产物", "structure": "结构",
        }
        type_to_label = {
            BalanceResult: "配平", ConditionResult: "条件",
            ProductResult: "产物", StructureResult: "结构",
        }
        for r in ordered:
            label = type_to_label.get(type(r), "未知")
            if r.message and r.status != OVERALL_PASSED:
                parts.append(f"[{label}] {r.message}")
        return "; ".join(parts) if parts else "四维审核全部通过"
