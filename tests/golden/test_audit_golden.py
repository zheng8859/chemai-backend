"""四维审核引擎 Golden 测试 — 86 道确定性测试。

使用 pytest.mark.parametrize，每个 case 独立统计（设计决策 #26）。
--lf 可精准重跑失败 case。
"""

import json
from pathlib import Path
import pytest

from chem_skills.chemistry_parser.engine.audit_engine import audit_equation

# 加载 golden 数据
_GOLDEN_PATH = Path(__file__).parent / "audit_golden_86.json"
with open(_GOLDEN_PATH, encoding="utf-8") as f:
    _DATA = json.load(f)

_TESTS = _DATA["tests"]


def _make_test_id(test: dict) -> str:
    """生成可读的测试 ID。"""
    eq = test["equation"][:40].replace("\n", " ")
    return f"{test['id']}: {eq}"


@pytest.mark.parametrize(
    "test_case",
    _TESTS,
    ids=[_make_test_id(t) for t in _TESTS],
)
def test_golden(test_case: dict):
    """逐条验证 Golden 测试。

    对每条测试：
    1. 调用 audit_equation()
    2. 比对 overall_status
    3. 逐维度比对 balance/condition/product/structure 状态
    """
    equation = test_case["equation"]
    expected = test_case["expected"]

    report = audit_equation(equation)

    # 综合判定
    assert report.overall_status == expected["overall"], (
        f"[{test_case['id']}] overall: expected={expected['overall']}, "
        f"got={report.overall_status}\n  equation: {equation[:80]}"
    )

    # 逐维度比对
    for dim in ["balance", "condition", "product", "structure"]:
        expected_status = expected.get(dim)
        if expected_status is None:
            # 无效输入 → 该维度未执行，应为 None
            actual = getattr(report, dim, None)
            assert actual is None, (
                f"[{test_case['id']}] {dim}: expected None, got {actual}"
            )
        else:
            result = getattr(report, dim)
            assert result is not None, (
                f"[{test_case['id']}] {dim}: expected {expected_status}, got None"
            )
            actual_status = result.status
            assert actual_status == expected_status, (
                f"[{test_case['id']}] {dim}: expected={expected_status}, "
                f"got={actual_status}\n  message: {result.message}\n"
                f"  equation: {equation[:80]}"
            )
