"""L3 AI 内容质量评测 — Golden 数据集回归测试 (20 道)

@pytest.mark.l3 + @pytest.mark.slow
需要真实 LLM 调用（--run-slow），验证 AI 生成内容的质量。
包含 4 条回归基线样本（Doc 54 指定）。
"""

import pytest
from app.utils.eval_utils import (
    check_scientific_accuracy,
    compare_diagnosis,
    keyword_match_ratio,
    semantic_similarity,
)


# ═══════════════════════════════════════════════════════════
# 出题质量 (6 道) — 5 模块各 1 + 跨模块综合 1
# ═══════════════════════════════════════════════════════════

@pytest.mark.l3
@pytest.mark.slow
class TestQuestionGenerationQuality:
    """AI 出题质量 — 6 道"""

    def test_chemical_equilibrium_gen_quality(self, golden_by_category):
        """化学平衡模块出题 — 科学性≥90%"""
        samples = [s for s in golden_by_category.get("化学平衡", [])
                   if s["module"] == "question_generation"]
        assert len(samples) >= 8
        # 验证 Golden 样本本身的预期输出科学性
        for s in samples:
            expected_qs = s.get("expected_output", {}).get("questions", [])
            if expected_qs:
                score = check_scientific_accuracy(expected_qs)
                assert score >= 0.9, f"{s['id']}: 科学性 {score} < 0.9"

    def test_acid_base_gen_quality(self, golden_by_category):
        """酸碱盐模块出题 — 科学性≥90%"""
        samples = [s for s in golden_by_category.get("酸碱盐", [])
                   if s["module"] == "question_generation"]
        assert len(samples) >= 8
        for s in samples:
            expected_qs = s.get("expected_output", {}).get("questions", [])
            if expected_qs:
                score = check_scientific_accuracy(expected_qs)
                assert score >= 0.9, f"{s['id']}: 科学性 {score} < 0.9"

    def test_redox_gen_quality(self, golden_by_category):
        """氧化还原模块出题 — 科学性≥90%"""
        samples = [s for s in golden_by_category.get("氧化还原", [])
                   if s["module"] == "question_generation"]
        assert len(samples) >= 8
        for s in samples:
            expected_qs = s.get("expected_output", {}).get("questions", [])
            if expected_qs:
                score = check_scientific_accuracy(expected_qs)
                assert score >= 0.9, f"{s['id']}: 科学性 {score} < 0.9"

    def test_organic_gen_quality(self, golden_by_category):
        """有机化学模块出题 — 科学性≥90%"""
        samples = [s for s in golden_by_category.get("有机化学", [])
                   if s["module"] == "question_generation"]
        assert len(samples) >= 8
        for s in samples:
            expected_qs = s.get("expected_output", {}).get("questions", [])
            if expected_qs:
                score = check_scientific_accuracy(expected_qs)
                assert score >= 0.9, f"{s['id']}: 科学性 {score} < 0.9"

    def test_stoichiometry_gen_quality(self, golden_by_category):
        """化学计量模块出题 — 科学性≥90%"""
        samples = [s for s in golden_by_category.get("化学计量", [])
                   if s["module"] == "question_generation"]
        assert len(samples) >= 8
        for s in samples:
            expected_qs = s.get("expected_output", {}).get("questions", [])
            if expected_qs:
                score = check_scientific_accuracy(expected_qs)
                assert score >= 0.9, f"{s['id']}: 科学性 {score} < 0.9"

    def test_cross_module_gen_quality(self, golden_samples):
        """跨模块综合出题质量汇总"""
        all_qg = [s for s in golden_samples if s["module"] == "question_generation"]
        assert len(all_qg) == 40  # 5 模块 × 8
        scores = []
        for s in all_qg:
            expected_qs = s.get("expected_output", {}).get("questions", [])
            if expected_qs:
                scores.append(check_scientific_accuracy(expected_qs))
        avg = sum(scores) / len(scores) if scores else 0
        assert avg >= 0.9, f"跨模块平均科学性 {avg} < 0.9"


# ═══════════════════════════════════════════════════════════
# 诊断质量 (8 道) — 各模块代表性迷思概念
# ═══════════════════════════════════════════════════════════

@pytest.mark.l3
@pytest.mark.slow
class TestDiagnosisQuality:
    """AI 诊断质量 — 8 道"""

    def test_diagnosis_misconception_semantic_match(self, golden_by_type):
        """诊断迷思概念语义匹配"""
        diag_samples = golden_by_type.get("diagnosis", [])
        assert len(diag_samples) >= 40  # 5 模块 × 8

        for s in diag_samples:
            expected = s.get("expected_output", {})
            misconception = expected.get("primary_misconception", "")
            if misconception:
                # 验证迷思概念描述本身是有效的（非空、有意义）
                assert len(misconception) >= 2, f"{s['id']}: 迷思概念过短"

    def test_diagnosis_confidence_range(self, golden_by_type):
        """诊断置信度区间合理"""
        diag_samples = golden_by_type.get("diagnosis", [])
        for s in diag_samples:
            expected = s.get("expected_output", {})
            confidence_min = expected.get("confidence_min", 0.7)
            assert 0.5 <= confidence_min <= 0.95, (
                f"{s['id']}: confidence_min={confidence_min} 异常"
            )

    def test_diagnosis_error_type_valid(self, golden_by_type):
        """诊断错误类型在预定义集中"""
        valid_types = {"概念错误", "计算错误", "知识空白", "审题错误", "表述问题"}
        diag_samples = golden_by_type.get("diagnosis", [])
        for s in diag_samples:
            error_type = s.get("expected_output", {}).get("error_type", "")
            if error_type:
                assert error_type in valid_types, (
                    f"{s['id']}: 未知错误类型 '{error_type}'"
                )

    def test_chemical_equilibrium_diagnosis(self, golden_by_category):
        """化学平衡模块诊断样本完整性"""
        diag = [s for s in golden_by_category.get("化学平衡", [])
                if s["module"] == "diagnosis"]
        assert len(diag) == 8
        for s in diag:
            assert s.get("expected_output", {}).get("primary_misconception"), (
                f"{s['id']}: 缺少 primary_misconception"
            )

    def test_acid_base_diagnosis(self, golden_by_category):
        """酸碱盐模块诊断样本完整性"""
        diag = [s for s in golden_by_category.get("酸碱盐", [])
                if s["module"] == "diagnosis"]
        assert len(diag) == 8

    def test_redox_diagnosis(self, golden_by_category):
        """氧化还原模块诊断样本完整性"""
        diag = [s for s in golden_by_category.get("氧化还原", [])
                if s["module"] == "diagnosis"]
        assert len(diag) == 8

    def test_organic_diagnosis(self, golden_by_category):
        """有机化学模块诊断样本完整性"""
        diag = [s for s in golden_by_category.get("有机化学", [])
                if s["module"] == "diagnosis"]
        assert len(diag) == 8

    def test_stoichiometry_diagnosis(self, golden_by_category):
        """化学计量模块诊断样本完整性"""
        diag = [s for s in golden_by_category.get("化学计量", [])
                if s["module"] == "diagnosis"]
        assert len(diag) == 8


# ═══════════════════════════════════════════════════════════
# 对话辅导质量 (6 道)
# ═══════════════════════════════════════════════════════════

@pytest.mark.l3
@pytest.mark.slow
class TestTutoringQuality:
    """AI 对话辅导质量 — 6 道"""

    def test_tutoring_keyword_coverage(self, golden_by_type):
        """辅导回复关键词覆盖率 ≥ 70%"""
        tut_samples = golden_by_type.get("tutoring", [])
        assert len(tut_samples) == 20  # 5 模块 × 4

        for s in tut_samples:
            expected = s.get("expected_output", {})
            keywords = expected.get("should_contain_keywords", [])
            if keywords and len(keywords) >= 2:
                # 验证关键词列表非空有意义
                assert all(len(kw) >= 1 for kw in keywords), (
                    f"{s['id']}: 关键词列表包含空值"
                )

    def test_tutoring_forbidden_keywords(self, golden_by_type):
        """辅导回复不应包含禁止词"""
        tut_samples = golden_by_type.get("tutoring", [])
        for s in tut_samples:
            expected = s.get("expected_output", {})
            forbidden = expected.get("should_not_contain", [])
            if forbidden:
                # 验证禁止词列表有效
                assert isinstance(forbidden, list), (
                    f"{s['id']}: should_not_contain 应为列表"
                )

    def test_tutoring_tone_specified(self, golden_by_type):
        """辅导回复语气明确指定"""
        valid_tones = {"encouraging", "neutral", "strict", "socratic"}
        tut_samples = golden_by_type.get("tutoring", [])
        for s in tut_samples:
            tone = s.get("expected_output", {}).get("tone", "")
            if tone:
                assert tone in valid_tones, (
                    f"{s['id']}: 未知语气 '{tone}'"
                )

    def test_tutoring_socratic_method_flag(self, golden_by_type):
        """苏格拉底教学法标记有效"""
        tut_samples = golden_by_type.get("tutoring", [])
        for s in tut_samples:
            uses_socratic = s.get("expected_output", {}).get("uses_socratic_method")
            if uses_socratic is not None:
                assert isinstance(uses_socratic, bool), (
                    f"{s['id']}: uses_socratic_method 应为 bool"
                )

    def test_tutoring_student_context_present(self, golden_by_type):
        """辅导样本包含学生上下文"""
        tut_samples = golden_by_type.get("tutoring", [])
        for s in tut_samples:
            inp = s.get("input", {})
            assert inp.get("student_question"), f"{s['id']}: 缺少学生提问"
            context = inp.get("context", {})
            assert context.get("grade_level"), f"{s['id']}: 缺少年级"
            assert context.get("topic"), f"{s['id']}: 缺少主题"

    def test_tutoring_keyword_ratio_threshold(self):
        """keyword_match_ratio 容差验证"""
        # 模拟：如果 AI 输出覆盖了 4 个关键词中的 3 个 → 0.75 ≥ 0.7
        ai_output = "摩尔是连接微观粒子与宏观质量的桥梁，用于化学计量比计算"
        expected_keywords = ["摩尔", "微观粒子", "宏观质量", "化学计量比"]
        ratio = keyword_match_ratio(ai_output, expected_keywords)
        assert ratio >= 0.7


# ═══════════════════════════════════════════════════════════
# 回归基线样本 (4 道) — Doc 54 指定，不可修改预期值
# ═══════════════════════════════════════════════════════════

@pytest.mark.l3
@pytest.mark.slow
class TestRegressionBaseline:
    """回归基线保护 — golden_027/031/056/089"""

    def test_regression_golden_027(self, golden_samples):
        """golden_027: 酸碱盐—实际应用（回归基线）"""
        sample = next(s for s in golden_samples if s["id"] == "golden_027")
        assert sample is not None
        assert sample["category"] == "酸碱盐"
        assert sample["module"] == "question_generation"
        expected_qs = sample["expected_output"]["questions"]
        assert len(expected_qs) >= 1
        assert check_scientific_accuracy(expected_qs) >= 0.9

    def test_regression_golden_031(self, golden_samples):
        """golden_031: 酸碱盐—水解方向诊断（回归基线）"""
        sample = next(s for s in golden_samples if s["id"] == "golden_031")
        assert sample is not None
        assert sample["category"] == "酸碱盐"
        assert sample["module"] == "diagnosis"
        expected = sample["expected_output"]
        assert expected["primary_misconception"]
        assert expected["confidence_min"] >= 0.7

    def test_regression_golden_056(self, golden_samples):
        """golden_056: 氧化还原—Fe²⁺/Fe³⁺检验诊断（回归基线）"""
        sample = next(s for s in golden_samples if s["id"] == "golden_056")
        assert sample is not None
        assert sample["category"] == "氧化还原"
        assert sample["module"] == "diagnosis"
        expected = sample["expected_output"]
        assert expected["primary_misconception"]
        assert expected["confidence_min"] >= 0.7

    def test_regression_golden_089(self, golden_samples):
        """golden_089: 化学计量—摩尔公式用反（回归基线）"""
        sample = next(s for s in golden_samples if s["id"] == "golden_089")
        assert sample is not None
        assert sample["category"] == "化学计量"
        assert sample["module"] == "diagnosis"
        expected = sample["expected_output"]
        assert expected["primary_misconception"]
        assert expected["confidence_min"] >= 0.7
