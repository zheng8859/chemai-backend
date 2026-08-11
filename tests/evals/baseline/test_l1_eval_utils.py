"""L1 单元测试 — eval_utils 工具函数 (28 道)

覆盖 eval_utils.py 全部 6 个函数 + 辅助函数。
"""

import pytest
from app.utils.eval_utils import (
    check_scientific_accuracy,
    compare_diagnosis,
    compute_metrics,
    difficulty_match_score,
    keyword_match_ratio,
    load_golden_samples,
    semantic_similarity,
)


# ═══════════════════════════════════════════════════════════
# check_scientific_accuracy (8 道)
# ═══════════════════════════════════════════════════════════

class TestScientificAccuracy:
    """科学性检查 — 8 道测试"""

    def test_empty_questions_returns_zero(self):
        """空列表返回 0.0"""
        assert check_scientific_accuracy([]) == 0.0

    def test_perfect_question_scores_1(self):
        """完整题目（含题干/正确选项/解释）得分 1.0"""
        questions = [{
            "stem": "标准状况下，44.8L CO₂的物质的量是多少？",
            "options": ["0.5mol", "1mol", "2mol", "4mol"],
            "correct_answer": "C",
            "explanation": "n=V/Vm=44.8L/(22.4L/mol)=2mol",
        }]
        assert check_scientific_accuracy(questions) == 1.0

    def test_missing_stem_deducts(self):
        """题干为空扣 0.5"""
        questions = [{
            "stem": "",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "A",
            "explanation": "测试",
        }]
        assert check_scientific_accuracy(questions) == 0.5

    def test_missing_answer_deducts(self):
        """正确答案为空扣 0.5"""
        questions = [{
            "stem": "题目内容",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "",
            "explanation": "测试",
        }]
        assert check_scientific_accuracy(questions) == 0.5

    def test_missing_explanation_deducts(self):
        """无解释扣 0.1"""
        questions = [{
            "stem": "题目内容",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "A",
            "explanation": "",
        }]
        assert check_scientific_accuracy(questions) == 0.9

    def test_distractor_equals_correct_answer_deducts(self):
        """干扰项等于正确答案扣 0.3"""
        questions = [{
            "stem": "题目内容",
            "options": ["A", "A", "C", "D"],  # B = A, same content
            "correct_answer": "A",
            "explanation": "正常解释",
        }]
        # 第一个选项 A = correct, 第二个选项也是 A（干扰项与正确答案相同）
        # correct_idx = 0, option[1] != option[0] → 不触发
        # Actually, correct_answer is "A" which is in "ABCD", so correct_idx = 0
        # option[0] = "A", option[1] = "A" → i=1, option[1]==option[0] → -=0.3
        # score = 1.0 - 0.3 = 0.7
        assert check_scientific_accuracy(questions) == 0.7

    def test_missing_stem_and_answer_scores_zero(self):
        """题干和答案都为空得分 0.0（不会负数）"""
        questions = [{
            "stem": "",
            "options": [],
            "correct_answer": "",
            "explanation": "",
        }]
        assert check_scientific_accuracy(questions) == 0.0

    def test_multiple_questions_averaged(self):
        """多道题取平均分"""
        questions = [
            {"stem": "Q1", "options": ["A", "B"], "correct_answer": "A", "explanation": "正确"},
            {"stem": "", "options": ["A", "B"], "correct_answer": "", "explanation": ""},
        ]
        # Q1: 1.0, Q2: 0.0, avg = 0.5
        assert check_scientific_accuracy(questions) == 0.5


# ═══════════════════════════════════════════════════════════
# keyword_match_ratio (5 道)
# ═══════════════════════════════════════════════════════════

class TestKeywordMatchRatio:
    """关键词覆盖率 — 5 道测试"""

    def test_all_keywords_matched(self):
        """全部关键词命中"""
        assert keyword_match_ratio(
            "摩尔是连接微观粒子与宏观质量的桥梁",
            ["摩尔", "微观粒子", "宏观质量", "桥梁"],
        ) == 1.0

    def test_partial_keywords_matched(self):
        """部分关键词命中"""
        assert keyword_match_ratio(
            "摩尔用于化学计量比计算",
            ["摩尔", "微观粒子", "宏观质量"],
        ) == pytest.approx(1 / 3, 0.01)

    def test_no_keywords_matched(self):
        """无关键词命中"""
        assert keyword_match_ratio("Hello World", ["摩尔", "化学"]) == 0.0

    def test_empty_keywords_returns_zero(self):
        """空关键词列表返回 0.0"""
        assert keyword_match_ratio("任意文本", []) == 0.0

    def test_case_insensitive(self):
        """大小写不敏感"""
        assert keyword_match_ratio(
            "Mole is the SI unit",
            ["mole", "SI", "unit"],
        ) == 1.0


# ═══════════════════════════════════════════════════════════
# semantic_similarity (5 道)
# ═══════════════════════════════════════════════════════════

class TestSemanticSimilarity:
    """语义相似度 — 5 道测试"""

    def test_identical_strings_return_1(self):
        """完全相同返回 1.0"""
        assert semantic_similarity("化学平衡", "化学平衡") == 1.0

    def test_completely_different_return_low(self):
        """完全不同返回低值"""
        score = semantic_similarity("化学平衡", "体育比赛")
        assert score < 0.3

    def test_similar_sentences_high_score(self):
        """相似句子得分 >= 0.6"""
        score = semantic_similarity(
            "勒夏特列原理描述了平衡移动的方向",
            "勒夏特列原理说明了平衡移动方向",
        )
        assert score >= 0.6

    def test_empty_string_returns_zero(self):
        """空字符串返回 0.0"""
        assert semantic_similarity("", "非空") == 0.0
        assert semantic_similarity("非空", "") == 0.0

    def test_case_insensitive(self):
        """大小写不敏感"""
        score = semantic_similarity("Hello World", "hello world")
        assert score == 1.0


# ═══════════════════════════════════════════════════════════
# compare_diagnosis (3 道)
# ═══════════════════════════════════════════════════════════

class TestCompareDiagnosis:
    """诊断结果比较 — 3 道测试"""

    def test_matching_diagnosis(self):
        """匹配诊断返回 True"""
        assert compare_diagnosis(
            "学生混淆了加成反应和取代反应",
            "该生将加成反应和取代反应搞混了",
        ) is True

    def test_non_matching_diagnosis(self):
        """不匹配诊断返回 False"""
        assert compare_diagnosis(
            "学生混淆了加成反应和取代反应",
            "学生的学习态度非常认真积极努力上进",
        ) is False

    def test_threshold_boundary(self):
        """恰好在阈值边界附近的测试"""
        # 约 50% 相似的短文本
        result = compare_diagnosis("概念A错误", "概念B错误")
        # SequenceMatcher("概念a错误", "概念b错误") ≈ 0.67 > 0.6
        assert result is True


# ═══════════════════════════════════════════════════════════
# difficulty_match_score (4 道)
# ═══════════════════════════════════════════════════════════

class TestDifficultyMatchScore:
    """难度匹配得分 — 4 道测试"""

    def test_exact_match(self):
        assert difficulty_match_score(3, 3) == 1.0

    def test_one_level_diff(self):
        assert difficulty_match_score(3, 4) == 0.7
        assert difficulty_match_score(4, 3) == 0.7

    def test_two_level_diff(self):
        assert difficulty_match_score(2, 4) == 0.3
        assert difficulty_match_score(5, 3) == 0.3

    def test_three_plus_level_diff(self):
        assert difficulty_match_score(1, 5) == 0.0
        assert difficulty_match_score(5, 1) == 0.0


# ═══════════════════════════════════════════════════════════
# compute_metrics (3 道)
# ═══════════════════════════════════════════════════════════

class TestComputeMetrics:
    """聚合指标计算 — 3 道测试"""

    def test_all_passed(self):
        results = [
            {"passed": True, "score": 0.95},
            {"passed": True, "score": 0.88},
            {"passed": True, "score": 0.92},
        ]
        metrics = compute_metrics(results)
        assert metrics["total"] == 3
        assert metrics["passed"] == 3
        assert metrics["failed"] == 0
        assert metrics["pass_rate"] == 100.0
        assert metrics["avg_score"] == pytest.approx(0.9167, 0.01)

    def test_mixed_results(self):
        results = [
            {"passed": True, "score": 0.9},
            {"passed": False, "score": 0.5},
            {"passed": True, "score": 0.8},
            {"passed": False, "score": 0.4},
        ]
        metrics = compute_metrics(results)
        assert metrics["total"] == 4
        assert metrics["passed"] == 2
        assert metrics["failed"] == 2
        assert metrics["pass_rate"] == 50.0

    def test_empty_results(self):
        metrics = compute_metrics([])
        assert metrics["total"] == 0
        assert metrics["pass_rate"] == 100.0
        assert metrics["avg_score"] == 0.0


# ═══════════════════════════════════════════════════════════
# load_golden_samples (2 道)
# ═══════════════════════════════════════════════════════════

class TestLoadGoldenSamples:
    """Golden 样本加载 — 2 道测试"""

    def test_load_all_returns_100_samples(self):
        samples = load_golden_samples()
        assert len(samples) == 100

    def test_load_specific_module(self):
        samples = load_golden_samples(module="chemical_equilibrium")
        assert len(samples) == 20
        assert all(s["category"] == "化学平衡" for s in samples)
