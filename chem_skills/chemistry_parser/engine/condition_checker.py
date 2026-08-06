"""维度 2：反应条件审核 — 14 类条件关键词 + 10 反应类型映射。

算法（26号 §三.3）：
1. 关键词扫描：在方程式中查找 14 类条件关键词
2. 燃烧判断：特殊规则检测燃烧物种
3. 催化建议：检测催化指示物
4. 矛盾检测：浓+稀、过量+适量等不可共存

规则数据存于 data/audit_conditions.json（设计决策 #9、#23）。
JSON 在模块 import 时自动加载（设计决策 #13）。
"""

import re
from typing import Any

from .models import (
    ConditionResult,
    CONDITION_PASSED,
    CONDITION_WARNING,
    CONDITION_FAILED,
    CONDITION_ERROR,
)
from .rule_loader import load_json_rules


# ═══════════════════════════════════════════════════════════════
# JSON 规则加载（模块级单例，设计决策 #13）
# ═══════════════════════════════════════════════════════════════

_FALLBACK_CONDITIONS: dict[str, Any] = {
    "conditions": [
        {"name": "点燃", "keywords": ["点燃"], "severity": "failed"},
        {"name": "加热", "keywords": ["加热", "△"], "severity": "failed"},
        {"name": "高温", "keywords": ["高温"], "severity": "failed"},
        {"name": "催化剂", "keywords": ["催化剂", "MnO2"], "severity": "warning"},
        {"name": "通电", "keywords": ["通电", "电解"], "severity": "failed"},
        {"name": "光照", "keywords": ["光照", "光"], "severity": "failed"},
        {"name": "加压", "keywords": ["加压", "高压"], "severity": "failed"},
        {"name": "浓", "keywords": ["浓"], "severity": "failed"},
        {"name": "稀", "keywords": ["稀"], "severity": "warning"},
    ],
    "combustion_species": ["CH4", "C2H5OH", "S", "P", "Fe", "Mg", "Al"],
    "catalyst_indicators": ["H2O2", "KClO3", "KMnO4"],
    "reaction_rules": [],
    "contradictions": [
        {"pair": ["浓", "稀"], "severity": "failed"},
    ],
}

_RULES = load_json_rules("audit_conditions.json", _FALLBACK_CONDITIONS)


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════

def check_conditions(equation: str) -> ConditionResult:
    """检查方程式的反应条件是否完整。

    综合四个子维度：关键词扫描、反应类型匹配、燃烧判断、矛盾检测。

    Args:
        equation: 归一化后的方程式字符串（含已标注的条件）

    Returns:
        ConditionResult: 含 status、conditions_found、missing_conditions、
                         contradictions
    """
    if not equation or not equation.strip():
        return ConditionResult(status=CONDITION_ERROR, message="方程式为空")

    eq = equation.strip()

    # 1. 关键词扫描
    found, found_names = _scan_conditions(eq)

    # 2. 反应类型匹配 → 缺失条件
    missing = _match_reaction_rules(eq, found_names)

    # 3. 燃烧判断 + 催化建议
    _check_combustion(eq, found_names, missing)
    _check_catalyst(eq, found_names, missing)

    # 4. 矛盾检测
    contradictions = _detect_contradictions(found_names)

    # 综合判定
    if not found_names and not missing:
        return ConditionResult(
            status=CONDITION_PASSED,
            message="无需特殊条件",
            conditions_found=[],
        )

    # 确定最终状态：有严重缺失 → failed，仅建议缺失 → warning
    has_failed = any(
        m.get("severity") == "failed"
        for m in missing
    )
    has_contradiction_failed = any(
        c.get("severity") == "failed"
        for c in contradictions
    )

    status = CONDITION_PASSED
    messages: list[str] = []

    if found_names:
        messages.append(f"已标注: {', '.join(found_names)}")

    if missing:
        msg = "缺失条件: " + ", ".join(
            f"{m['name']}({m['reason']})" for m in missing
        )
        messages.append(msg)
        if has_failed:
            status = CONDITION_FAILED
        else:
            status = CONDITION_WARNING

    if contradictions:
        c_msg = "矛盾条件: " + ", ".join(
            f"{c['pair'][0]}+{c['pair'][1]}" for c in contradictions
        )
        messages.append(c_msg)
        if has_contradiction_failed and status != CONDITION_FAILED:
            status = CONDITION_FAILED

    return ConditionResult(
        status=status,
        message="; ".join(messages),
        conditions_found=found_names,
        missing_conditions=[m["name"] for m in missing],
        contradictions=[f"{c['pair'][0]}+{c['pair'][1]}" for c in contradictions],
    )


# ═══════════════════════════════════════════════════════════════
# Internal
# ═══════════════════════════════════════════════════════════════

def _scan_conditions(eq: str) -> tuple[list[dict], list[str]]:
    """扫描方程式中已标注的条件关键词。"""
    found: list[dict] = []
    found_names: list[str] = []
    for cond in _RULES.get("conditions", []):
        for kw in cond.get("keywords", []):
            if kw in eq:
                found.append(cond)
                found_names.append(cond["name"])
                break
    return found, found_names


def _match_reaction_rules(eq: str, found_names: list[str]) -> list[dict]:
    """根据反应类型规则，检测缺失的条件。"""
    missing: list[dict] = []
    for rule in _RULES.get("reaction_rules", []):
        patterns = rule.get("patterns", [])
        if not patterns:
            continue

        # 检查 _match_all: 所有指定 pattern 都必须出现
        match_all = rule.get("_match_all", [])
        if match_all:
            if not all(_pattern_present(eq, p) for p in match_all):
                continue
        else:
            # 默认: 任一 pattern 匹配即可
            matched = any(_pattern_present(eq, p) for p in patterns)
            if not matched:
                continue

        for required in rule.get("required", []):
            if required not in found_names:
                _add_missing(missing, required,
                             f"{rule['type']}需要{required}",
                             rule.get("severity", "warning"))
    return missing


def _pattern_present(eq: str, pattern: str) -> bool:
    """使用词边界检查模式是否在方程式中独立出现。

    允许数字作为边界（系数如 2H2O），但不允许字母。
    特殊处理 CO/CO2 歧义：CO 匹配后检查该位置是否属于 CO2。
    """
    pat = r'(?<![A-Za-z])' + re.escape(pattern) + r'(?![A-Za-z])'
    if not re.search(pat, eq):
        return False

    # CO 不应匹配 CO2/CO3/HCO3（CO 是燃料，这些是常见含氧酸根）
    if pattern == "CO":
        for m in re.finditer(pat, eq):
            end = m.end()
            # CO2, CO3, HCO3 中的 CO 不是独立的燃烧物种
            if end < len(eq) and eq[end] in "23":
                continue
            return True
        return False

    return True


def _check_combustion(eq: str, found_names: list[str], missing: list[dict]) -> None:
    """燃烧反应特殊检测：含燃烧物种 + O2 但未标'点燃'。"""
    has_combustion = any(
        _pattern_present(eq, sp) for sp in _RULES.get("combustion_species", [])
    )
    has_oxygen = _pattern_present(eq, "O2")

    if has_combustion and has_oxygen and "点燃" not in found_names:
        if "加热" not in found_names and "高温" not in found_names:
            _add_missing(missing, "点燃", "燃烧反应需要点燃", "failed")


def _check_catalyst(eq: str, found_names: list[str], missing: list[dict]) -> None:
    """催化指示物检测：含催化指示物但未标催化剂。"""
    for indicator in _RULES.get("catalyst_indicators", []):
        if _pattern_present(eq, indicator) and "催化剂" not in found_names:
            has_any = any(
                kw in eq
                for cond in _RULES.get("conditions", [])
                if cond["name"] == "催化剂"
                for kw in cond.get("keywords", [])
            )
            if not has_any:
                _add_missing(missing, "催化剂",
                             f"含{indicator}，建议标注催化剂", "warning")
                break


def _add_missing(missing: list[dict], name: str, reason: str, severity: str) -> None:
    """添加缺失条件（去重）。"""
    if name not in [m["name"] for m in missing]:
        missing.append({"name": name, "reason": reason, "severity": severity})


def _detect_contradictions(found_names: list[str]) -> list[dict]:
    """检测矛盾条件组合（设计决策 #28：内嵌在 check_conditions 中）。"""
    contradictions: list[dict] = []
    for rule in _RULES.get("contradictions", []):
        pair = rule.get("pair", [])
        if len(pair) == 2 and pair[0] in found_names and pair[1] in found_names:
            contradictions.append({
                "pair": pair,
                "severity": rule.get("severity", "warning"),
            })
    return contradictions
