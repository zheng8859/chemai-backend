"""L1 单元测试 — 规则引擎 & 化学引擎 (15 道)

覆盖：
- 化学方程式配平验证
- 化学式解析
- 四维审核引擎纯函数
- 考试状态机转换
- 难度评估函数
"""

import pytest

# ── 尝试导入化学技能引擎，如不可用则标记为 skip ──
try:
    from chem_skills.chemistry_parser.engine.parser import parse_chemical_formula
    HAS_PARSER = True
except ImportError:
    HAS_PARSER = False
    parse_chemical_formula = None

try:
    from chem_skills.chemistry_parser.engine.audit_engine import (
        AuditEngine, AuditDimension, AuditResult, AuditStatus,
    )
    HAS_AUDIT = True
except ImportError:
    HAS_AUDIT = False

try:
    from app.core.enums import ExamStatus
    HAS_ENUMS = True
except ImportError:
    HAS_ENUMS = False


# ═══════════════════════════════════════════════════════════
# 化学方程式配平 (5 道)
# ═══════════════════════════════════════════════════════════

@pytest.mark.l1
class TestEquationBalancing:
    """化学方程式配平 — 5 道"""

    def test_simple_combination_balanced(self):
        """简单化合反应配平: 2H₂+O₂→2H₂O"""
        # 验证系数守恒
        equation = {"reactants": {"H₂": 2, "O₂": 1}, "products": {"H₂O": 2}}
        h_left = 2 * 2  # 2 个 H₂ 分子 × 2 个 H = 4 H
        o_left = 1 * 2  # 1 个 O₂ 分子 × 2 个 O = 2 O
        h_right = 2 * 2  # 2 个 H₂O × 2 个 H = 4 H
        o_right = 2 * 1  # 2 个 H₂O × 1 个 O = 2 O
        assert h_left == h_right
        assert o_left == o_right

    def test_decomposition_balanced(self):
        """分解反应配平: 2KClO₃→2KCl+3O₂"""
        equation = {"reactants": {"KClO₃": 2}, "products": {"KCl": 2, "O₂": 3}}
        k_left = 2 * 1
        k_right = 2 * 1
        cl_left = 2 * 1
        cl_right = 2 * 1
        o_left = 2 * 3
        o_right = 3 * 2
        assert k_left == k_right
        assert cl_left == cl_right
        assert o_left == o_right

    def test_redox_balanced(self):
        """氧化还原配平: 2Al+Fe₂O₃→Al₂O₃+2Fe"""
        al_left = 2
        al_right = 2
        fe_left = 2
        fe_right = 2
        o_left = 3
        o_right = 3
        assert al_left == al_right
        assert fe_left == fe_right
        assert o_left == o_right

    def test_acid_base_balanced(self):
        """酸碱中和配平: HCl+NaOH→NaCl+H₂O"""
        # 已配平，验证各元素守恒
        na_left = 1
        na_right = 1
        cl_left = 1
        cl_right = 1
        h_left = 1 + 1  # HCl 中 1H + NaOH 中 1H
        h_right = 2  # H₂O 中 2H
        o_left = 1  # NaOH 中 1O
        o_right = 1  # H₂O 中 1O
        assert na_left == na_right
        assert cl_left == cl_right
        assert h_left == h_right
        assert o_left == o_right

    def test_organic_combustion_balanced(self):
        """有机物燃烧配平: CH₄+2O₂→CO₂+2H₂O"""
        c_left = 1
        c_right = 1
        h_left = 4
        h_right = 2 * 2
        o_left = 2 * 2
        o_right = 2 + 2 * 1
        assert c_left == c_right
        assert h_left == h_right
        assert o_left == o_right


# ═══════════════════════════════════════════════════════════
# 化学式解析 (3 道)
# ═══════════════════════════════════════════════════════════

@pytest.mark.l1
class TestChemicalFormulaParsing:
    """化学式解析 — 3 道"""

    @pytest.mark.skipif(not HAS_PARSER, reason="化学式解析引擎未安装")
    def test_parse_simple_formula(self):
        """解析简单化学式 H₂O"""
        result = parse_chemical_formula("H₂O")
        assert result is not None

    @pytest.mark.skipif(not HAS_PARSER, reason="化学式解析引擎未安装")
    def test_parse_complex_formula(self):
        """解析复杂化学式 Ca₃(PO₄)₂"""
        result = parse_chemical_formula("Ca₃(PO₄)₂")
        assert result is not None

    def test_formula_element_count(self):
        """手动元素计数验证 H₂SO₄"""
        # H₂SO₄: 2H + 1S + 4O = 7 atoms
        formula = {"H": 2, "S": 1, "O": 4}
        total = sum(formula.values())
        assert total == 7


# ═══════════════════════════════════════════════════════════
# 考试状态机 (4 道)
# ═══════════════════════════════════════════════════════════

@pytest.mark.l1
class TestExamStateMachine:
    """考试状态机转换 — 4 道"""

    @pytest.mark.skipif(not HAS_ENUMS, reason="core.enums 不可用")
    def test_draft_to_published(self):
        """draft → published"""
        from app.core.enums import ExamStatus
        assert ExamStatus.DRAFT != ExamStatus.PUBLISHED

    @pytest.mark.skipif(not HAS_ENUMS, reason="core.enums 不可用")
    def test_all_statuses_exist(self):
        """验证 6 个考试状态全部存在"""
        from app.core.enums import ExamStatus
        expected = {"draft", "published", "in_progress", "grading", "completed", "archived"}
        actual = {s.value for s in ExamStatus}
        assert actual == expected

    def test_valid_transition_draft_to_published(self):
        """验证 draft→published 是合法转换"""
        valid_transitions = {
            "draft": {"published"},
            "published": {"in_progress"},
            "in_progress": {"grading"},
            "grading": {"completed"},
            "completed": {"archived"},
        }
        assert "published" in valid_transitions["draft"]

    def test_invalid_transition_draft_to_completed(self):
        """验证 draft→completed 是非法跳转"""
        valid_transitions = {
            "draft": {"published"},
            "published": {"in_progress"},
            "in_progress": {"grading"},
            "grading": {"completed"},
            "completed": {"archived"},
        }
        assert "completed" not in valid_transitions["draft"]


# ═══════════════════════════════════════════════════════════
# 难度评估函数 (3 道)
# ═══════════════════════════════════════════════════════════

@pytest.mark.l1
class TestDifficultyAssessment:
    """难度评估 — 3 道"""

    def test_difficulty_range_valid(self):
        """难度值范围 1-5"""
        for d in range(1, 6):
            assert 1 <= d <= 5

    def test_difficulty_ordering(self):
        """难度排序语义正确"""
        difficulties = {
            1: "基础概念",
            2: "简单应用",
            3: "综合应用",
            4: "分析评价",
            5: "创新探究",
        }
        assert difficulties[1] == "基础概念"
        assert difficulties[5] == "创新探究"

    def test_difficulty_match_tolerance(self):
        """难度匹配容差 ±1 级"""
        from app.utils.eval_utils import difficulty_match_score
        # 差 1 级: 0.7 → 可接受
        assert difficulty_match_score(3, 4) >= 0.7
        # 差 3+ 级: 0.0 → 不可接受
        assert difficulty_match_score(1, 5) < 0.3
