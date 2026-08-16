"""eval_utils 单测 — 6 个纯函数评测工具 + Golden 样本加载。"""

from app.utils.eval_utils import (
    check_scientific_accuracy,
    compare_diagnosis,
    compute_metrics,
    difficulty_match_score,
    keyword_match_ratio,
    load_golden_samples,
    semantic_similarity,
)


class TestCheckScientificAccuracy:
    def test_empty_questions(self):
        assert check_scientific_accuracy([]) == 0.0

    def test_perfect_question(self):
        q = {
            "stem": "Fe + O2 → Fe2O3 的反应类型是？",
            "correct_answer": "A",
            "options": ["A. 化合反应", "B. 分解反应", "C. 置换反应", "D. 复分解反应"],
            "explanation": "两种物质生成一种，属于化合反应",
        }
        assert check_scientific_accuracy([q]) == 1.0

    def test_missing_stem_and_answer(self):
        q = {"stem": "", "correct_answer": "", "options": [], "explanation": ""}
        assert check_scientific_accuracy([q]) == 0.0

    def test_answer_as_letter_valid(self):
        q = {
            "stem": "题干",
            "correct_answer": "B",
            "options": ["A", "B", "C", "D"],
            "explanation": "解释",
        }
        assert check_scientific_accuracy([q]) == 1.0


class TestKeywordMatchRatio:
    def test_full_match(self):
        assert keyword_match_ratio("氧化还原反应", ["氧化还原", "反应"]) == 1.0

    def test_empty_keywords(self):
        assert keyword_match_ratio("anything", []) == 0.0

    def test_case_insensitive(self):
        assert keyword_match_ratio("Oxidation", ["oxidation"]) == 1.0

    def test_partial_match(self):
        assert keyword_match_ratio("氧化还原", ["氧化", "水解"]) == 0.5


class TestSemanticSimilarity:
    def test_empty_input(self):
        assert semantic_similarity("", "x") == 0.0
        assert semantic_similarity("x", "") == 0.0

    def test_identical(self):
        assert semantic_similarity("hello world", "hello world") == 1.0

    def test_partial(self):
        s = semantic_similarity("氧化还原反应", "氧化还原")
        assert 0.0 < s < 1.0


class TestCompareDiagnosis:
    def test_semantic_match(self):
        assert compare_diagnosis("氧化还原反应", "氧化还原反应") is True

    def test_semantic_mismatch(self):
        assert compare_diagnosis("氧化还原", "完全无关的内容完全不同") is False


class TestDifficultyMatchScore:
    def test_exact(self):
        assert difficulty_match_score(1, 1) == 1.0

    def test_one_level(self):
        assert difficulty_match_score(1, 2) == 0.7

    def test_two_levels(self):
        assert difficulty_match_score(1, 3) == 0.3

    def test_three_plus(self):
        assert difficulty_match_score(1, 5) == 0.0


class TestComputeMetrics:
    def test_empty(self):
        m = compute_metrics([])
        assert m["total"] == 0
        assert m["pass_rate"] == 100.0
        assert m["avg_score"] == 0.0

    def test_mixed_results(self):
        m = compute_metrics([
            {"passed": True, "score": 0.9},
            {"passed": False, "score": 0.5},
        ])
        assert m["total"] == 2
        assert m["passed"] == 1
        assert m["failed"] == 1
        assert m["pass_rate"] == 50.0
        assert m["avg_score"] == 0.7


class TestLoadGoldenSamples:
    def test_loads_list(self):
        samples = load_golden_samples()
        assert isinstance(samples, list)

    def test_loads_by_module(self):
        samples = load_golden_samples("redox")
        assert isinstance(samples, list)
