"""测试化学记忆引擎 — ZPD、策略矩阵、间隔复习、变式题生成。

纯单元测试，无需数据库。覆盖所有函数的主路径和边界条件。
"""

from datetime import timedelta

import pytest

from chem_skills.chemistry_memory.zpd_engine import (
    compute_zpd_difficulty,
    extract_weak_knowledge_points,
    identify_dominant_barrier,
)
from chem_skills.chemistry_memory.strategy_matrix import apply_strategy
from chem_skills.chemistry_memory.spaced_repetition import (
    SPIRAL_REVIEW_DAYS,
    MAX_LEVEL,
    compute_next_review,
    evaluate_level_change,
)
from chem_skills.chemistry_memory.variant_generator import build_variant_prompt


# ===================== ZPD Engine Tests =====================


class TestComputeZpdDifficulty:
    """compute_zpd_difficulty — 30 题滑动窗口正确率 → 难度档位。"""

    def test_cold_start_returns_medium(self):
        """样本不足 5 条时返回 medium。"""
        assert compute_zpd_difficulty([]) == "medium"
        assert compute_zpd_difficulty([True]) == "medium"
        assert compute_zpd_difficulty([True, False, True, False]) == "medium"

    def test_cold_start_custom_min_sample(self):
        """支持自定义最小样本量。"""
        answers = [True, True, False]
        assert compute_zpd_difficulty(answers, min_sample_size=3) == "medium"

    def test_easy_when_accuracy_below_40_percent(self):
        """正确率 < 40% → easy。"""
        # 30 题中 11 正确 = 36.7%
        answers = [True] * 11 + [False] * 19
        assert compute_zpd_difficulty(answers) == "easy"

    def test_easy_when_accuracy_zero(self):
        """全错 → easy。"""
        answers = [False] * 30
        assert compute_zpd_difficulty(answers) == "easy"

    def test_medium_lower_boundary_inclusive(self):
        """正确率 = 40%（含边界）→ medium。"""
        answers = [True] * 12 + [False] * 18  # 12/30 = 40%
        assert compute_zpd_difficulty(answers) == "medium"

    def test_medium_upper_boundary_inclusive(self):
        """正确率 = 70%（含边界）→ medium。"""
        answers = [True] * 21 + [False] * 9  # 21/30 = 70%
        assert compute_zpd_difficulty(answers) == "medium"

    def test_medium_mid_range(self):
        """正确率在 (40%, 70%) 之间 → medium。"""
        answers = [True] * 15 + [False] * 15  # 50%
        assert compute_zpd_difficulty(answers) == "medium"

    def test_hard_when_accuracy_above_70_percent(self):
        """正确率 > 70% → hard。"""
        answers = [True] * 22 + [False] * 8  # 22/30 = 73.3%
        assert compute_zpd_difficulty(answers) == "hard"

    def test_hard_when_accuracy_full(self):
        """全对 → hard。"""
        answers = [True] * 30
        assert compute_zpd_difficulty(answers) == "hard"


class TestExtractWeakKnowledgePoints:
    """extract_weak_knowledge_points — 全量错题统计 → Top N 薄弱知识点。"""

    def test_returns_empty_list_when_no_wrong_answers(self):
        """无错题记录 → 空列表。"""
        result = extract_weak_knowledge_points([])
        assert result == []

    def test_returns_top_knowledge_points(self):
        """按错误频次降序返回 Top N。"""
        wrong_answers = [
            {"knowledge_points": ["氧化还原反应", "离子反应"]},
            {"knowledge_points": ["氧化还原反应"]},
            {"knowledge_points": ["离子反应", "物质的量"]},
            {"knowledge_points": ["氧化还原反应"]},
        ]
        result = extract_weak_knowledge_points(wrong_answers)
        # "氧化还原反应" 出现 3 次，"离子反应" 2 次，"物质的量" 1 次
        assert result == ["氧化还原反应", "离子反应", "物质的量"]

    def test_respects_custom_top_n(self):
        """支持自定义 top_n。"""
        wrong_answers = [
            {"knowledge_points": ["A"]},
            {"knowledge_points": ["B"]},
            {"knowledge_points": ["C"]},
            {"knowledge_points": ["D"]},
        ]
        result = extract_weak_knowledge_points(wrong_answers, top_n=2)
        assert len(result) == 2

    def test_handles_missing_knowledge_points_key(self):
        """缺失 knowledge_points 键的记录被跳过。"""
        wrong_answers = [
            {"knowledge_points": ["氧化还原反应"]},
            {"other_field": "data"},  # 无知识点
        ]
        result = extract_weak_knowledge_points(wrong_answers)
        assert result == ["氧化还原反应"]

    def test_handles_non_list_knowledge_points(self):
        """knowledge_points 为非列表类型时被跳过。"""
        wrong_answers = [
            {"knowledge_points": ["氧化还原反应"]},
            {"knowledge_points": "氧化还原反应"},  # 字符串而非列表
        ]
        result = extract_weak_knowledge_points(wrong_answers)
        assert result == ["氧化还原反应"]

    def test_handles_empty_string_in_knowledge_points(self):
        """知识点列表中包含空字符串时被过滤。"""
        wrong_answers = [
            {"knowledge_points": ["氧化还原反应", "", None, "离子反应"]},
        ]
        result = extract_weak_knowledge_points(wrong_answers)
        # "" 和 None 在迭代中通过 if kp 过滤
        # 注意：None 不是 falsy 的问题——if kp 会正确处理 None 和 ""
        # 实际上 None 和 "" 都是 falsy，所以都会被过滤
        assert "氧化还原反应" in result
        assert "离子反应" in result
        assert "" not in result


class TestIdentifyDominantBarrier:
    """identify_dominant_barrier — 障碍画像 → 主导障碍类型。"""

    def test_returns_max_score_key(self):
        """返回占比最高的障碍类型。"""
        profile = {"concept": 0.7, "reading": 0.15, "expression": 0.15}
        assert identify_dominant_barrier(profile) == "concept"

    def test_returns_reading_when_dominant(self):
        """审题障碍为主导时返回 reading。"""
        profile = {"concept": 0.1, "reading": 0.8, "expression": 0.1}
        assert identify_dominant_barrier(profile) == "reading"

    def test_returns_expression_when_dominant(self):
        """表述障碍为主导时返回 expression。"""
        profile = {"concept": 0.05, "reading": 0.05, "expression": 0.9}
        assert identify_dominant_barrier(profile) == "expression"

    def test_returns_default_when_none(self):
        """无数据时返回默认值 "concept"。"""
        assert identify_dominant_barrier(None) == "concept"

    def test_returns_default_when_empty_dict(self):
        """空字典返回默认值 "concept"。"""
        assert identify_dominant_barrier({}) == "concept"

    def test_returns_custom_default(self):
        """支持自定义默认障碍类型。"""
        assert identify_dominant_barrier(None, default="reading") == "reading"

    def test_returns_default_when_not_dict(self):
        """非字典类型返回默认值。"""
        assert identify_dominant_barrier("invalid") == "concept"


# ===================== Strategy Matrix Tests =====================


class TestApplyStrategy:
    """apply_strategy — 障碍类型 × ZPD 难度 → 出题策略。"""

    # --- concept barrier ---

    def test_concept_strategy_lowers_difficulty(self):
        """概念障碍：hard → medium, medium → easy, easy → easy。"""
        assert apply_strategy("concept", "hard")["difficulty"] == "medium"
        assert apply_strategy("concept", "medium")["difficulty"] == "easy"
        assert apply_strategy("concept", "easy")["difficulty"] == "easy"

    def test_concept_strategy_prefers_foundational_kp(self):
        """概念障碍：知识点倾向为基础型。"""
        result = apply_strategy("concept", "medium")
        assert result["kp_preference"] == "foundational"

    def test_concept_strategy_weights_favor_choice_and_fill(self):
        """概念障碍：题型权重偏向选择+填空。"""
        weights = apply_strategy("concept", "medium")["question_type_weights"]
        assert weights["choice"] == 0.5
        assert weights["fill_blank"] == 0.3
        assert weights["choice"] > weights["calculation"]

    # --- reading barrier ---

    def test_reading_strategy_keeps_difficulty(self):
        """审题障碍：保持原始难度不变。"""
        assert apply_strategy("reading", "hard")["difficulty"] == "hard"
        assert apply_strategy("reading", "medium")["difficulty"] == "medium"
        assert apply_strategy("reading", "easy")["difficulty"] == "easy"

    def test_reading_strategy_prefers_mixed_kp(self):
        """审题障碍：知识点倾向为混合型。"""
        result = apply_strategy("reading", "medium")
        assert result["kp_preference"] == "mixed"

    def test_reading_strategy_weights_favor_inference(self):
        """审题障碍：题型权重偏向推断题。"""
        weights = apply_strategy("reading", "medium")["question_type_weights"]
        assert weights["inference"] > weights["calculation"]
        assert weights["inference"] == 0.25

    # --- expression barrier ---

    def test_expression_strategy_keeps_difficulty(self):
        """表述障碍：保持原始难度不变。"""
        assert apply_strategy("expression", "hard")["difficulty"] == "hard"
        assert apply_strategy("expression", "medium")["difficulty"] == "medium"

    def test_expression_strategy_prefers_equation_kp(self):
        """表述障碍：知识点倾向为方程式型。"""
        result = apply_strategy("expression", "hard")
        assert result["kp_preference"] == "equation"

    def test_expression_strategy_weights_favor_calculation(self):
        """表述障碍：题型权重偏向计算题和实验题。"""
        weights = apply_strategy("expression", "hard")["question_type_weights"]
        assert weights["calculation"] == 0.35
        assert weights["experiment"] == 0.2
        assert weights["calculation"] > weights["choice"]

    # --- unknown barrier ---

    def test_unknown_barrier_falls_back_to_concept(self):
        """未知障碍类型回退到 concept 策略。"""
        result = apply_strategy("unknown", "medium")
        assert result["kp_preference"] == "foundational"
        assert result["difficulty"] == "easy"  # concept 会降档


# ===================== Spaced Repetition Tests =====================


class TestSpiralReviewDays:
    """SPIRAL_REVIEW_DAYS 常量校验。"""

    def test_has_six_levels(self):
        """0-4 级共 5 个有效复习级别。"""
        assert set(SPIRAL_REVIEW_DAYS.keys()) == {0, 1, 2, 3, 4}

    def test_intervals_match_spec(self):
        """间隔天数与设计文档一致。"""
        assert SPIRAL_REVIEW_DAYS[0] == 0
        assert SPIRAL_REVIEW_DAYS[1] == 1
        assert SPIRAL_REVIEW_DAYS[2] == 3
        assert SPIRAL_REVIEW_DAYS[3] == 7
        assert SPIRAL_REVIEW_DAYS[4] == 14


class TestComputeNextReview:
    """compute_next_review — 级别 → 间隔天数。"""

    def test_level_0_returns_immediate(self):
        assert compute_next_review(0) == timedelta(days=0)

    def test_level_1_returns_one_day(self):
        assert compute_next_review(1) == timedelta(days=1)

    def test_level_2_returns_three_days(self):
        assert compute_next_review(2) == timedelta(days=3)

    def test_level_3_returns_seven_days(self):
        assert compute_next_review(3) == timedelta(days=7)

    def test_level_4_returns_fourteen_days(self):
        assert compute_next_review(4) == timedelta(days=14)

    def test_unknown_level_returns_zero(self):
        """未知级别返回 0 天（安全回退）。"""
        assert compute_next_review(99) == timedelta(days=0)
        assert compute_next_review(-1) == timedelta(days=0)


class TestEvaluateLevelChange:
    """evaluate_level_change — 升降级判定。"""

    # --- 连续答对场景 ---

    def test_first_correct_no_upgrade(self):
        """第一次答对：连续正确从 0 → 1，不升级。"""
        result = evaluate_level_change(
            level=1, consecutive_correct=0, consecutive_wrong=0, is_correct=True
        )
        assert result["new_level"] == 1
        assert result["new_consecutive_correct"] == 1
        assert result["new_consecutive_wrong"] == 0
        assert result["level_changed"] is False
        assert result["upgraded"] is False

    def test_second_consecutive_correct_triggers_upgrade(self):
        """连续答对 2 次 → 升级，计数器归零。"""
        result = evaluate_level_change(
            level=1, consecutive_correct=1, consecutive_wrong=0, is_correct=True
        )
        assert result["new_level"] == 2
        assert result["new_consecutive_correct"] == 0
        assert result["upgraded"] is True
        assert result["level_changed"] is True

    def test_third_consecutive_correct_at_max_level(self):
        """在最高级别继续答对：不降级也不升级。"""
        result = evaluate_level_change(
            level=5, consecutive_correct=1, consecutive_wrong=0, is_correct=True
        )
        assert result["new_level"] == 5
        assert result["upgraded"] is False

    # --- 答错场景 ---

    def test_wrong_at_level_0_no_downgrade(self):
        """Level 0 答错：不降级，连续正确归零。"""
        result = evaluate_level_change(
            level=0, consecutive_correct=2, consecutive_wrong=0, is_correct=False
        )
        assert result["new_level"] == 0
        assert result["downgraded"] is False
        assert result["new_consecutive_correct"] == 0

    def test_wrong_at_higher_level_downgrades(self):
        """Level > 0 答错：降级，连续计数器归零。"""
        result = evaluate_level_change(
            level=2, consecutive_correct=0, consecutive_wrong=0, is_correct=False
        )
        assert result["new_level"] == 1
        assert result["downgraded"] is True
        assert result["new_consecutive_correct"] == 0
        assert result["new_consecutive_wrong"] == 0

    # --- 特殊规则：一次回退不降级 ---

    def test_single_correct_then_wrong_no_downgrade(self):
        """上次答对（consecutive_correct=1）本次答错 → 不降级。"""
        result = evaluate_level_change(
            level=3, consecutive_correct=1, consecutive_wrong=0, is_correct=False
        )
        assert result["new_level"] == 3  # 级别不变
        assert result["downgraded"] is False
        assert result["new_consecutive_correct"] == 0  # 计数器归零

    def test_single_correct_then_wrong_at_level_0_still_no_downgrade(self):
        """Level 0 时 single correct then wrong：同样不降级。"""
        result = evaluate_level_change(
            level=0, consecutive_correct=1, consecutive_wrong=0, is_correct=False
        )
        assert result["new_level"] == 0
        assert result["downgraded"] is False

    # --- 连续错误场景 ---

    def test_consecutive_wrong_then_correct(self):
        """连续错误后答对：错误计数器归零，正确+1。"""
        result = evaluate_level_change(
            level=1, consecutive_correct=0, consecutive_wrong=3, is_correct=True
        )
        assert result["new_consecutive_wrong"] == 0
        assert result["new_consecutive_correct"] == 1

    def test_consecutive_wrong_is_tracked(self):
        """答错时连续错误计数器递增。"""
        result = evaluate_level_change(
            level=1, consecutive_correct=0, consecutive_wrong=2, is_correct=False
        )
        # 由于 level > 0 且 consecutive_correct != 1，会降级
        # 降级时 cw 被重置为 0
        assert result["new_consecutive_wrong"] == 0

    # --- 快速多次升级 ---

    def test_full_upgrade_path_to_mastery(self):
        """从 Level 0 到 Level 5 需要连续 10 次答对（每次升级需 2 次答对）。"""
        level = 0
        cc = 0  # consecutive_correct
        cw = 0  # consecutive_wrong
        for _ in range(5 * 2):  # 5 次升级 × 每次 2 次答对
            result = evaluate_level_change(
                level=level, consecutive_correct=cc, consecutive_wrong=cw, is_correct=True
            )
            level = result["new_level"]
            cc = result["new_consecutive_correct"]
            cw = result["new_consecutive_wrong"]
        assert level == 5

    # --- 升降机交织 ---

    def test_upgrade_then_downgrade_then_upgrade(self):
        """升 → 降 → 再升的完整周期。"""
        level = 1
        cc = 1
        cw = 0

        # 第 1 步：答对触发升级
        r = evaluate_level_change(level, cc, cw, is_correct=True)
        assert r["upgraded"] is True
        assert r["new_level"] == 2

        # 第 2 步：答错触发降级（已重置计数器）
        r = evaluate_level_change(r["new_level"], r["new_consecutive_correct"], r["new_consecutive_wrong"], is_correct=False)
        assert r["downgraded"] is True
        assert r["new_level"] == 1

        # 第 3-4 步：再连续答对 2 次升级
        r = evaluate_level_change(r["new_level"], r["new_consecutive_correct"], r["new_consecutive_wrong"], is_correct=True)
        assert r["upgraded"] is False  # 第一次答对不升级
        r = evaluate_level_change(r["new_level"], r["new_consecutive_correct"], r["new_consecutive_wrong"], is_correct=True)
        assert r["upgraded"] is True
        assert r["new_level"] == 2


# ===================== Variant Generator Tests =====================


class TestBuildVariantPrompt:
    """build_variant_prompt — 构造 LLM 变式题 prompt。"""

    def test_choice_question_prompt_contains_key_info(self):
        """选择题 prompt 包含知识点、难度、原题内容和答案。"""
        question = {
            "question_type": "choice",
            "difficulty": "medium",
            "knowledge_points": ["氧化还原反应", "离子反应"],
            "content": "下列反应中，属于氧化还原反应的是？",
            "answer": "B",
        }
        prompt = build_variant_prompt(question)

        assert "氧化还原反应" in prompt
        assert "离子反应" in prompt
        assert "medium" in prompt
        assert "选择题" in prompt
        assert "下列反应中" in prompt
        assert "B" in prompt
        assert "JSON" in prompt
        assert "options" in prompt  # 选择题特有

    def test_choice_prompt_has_options_field(self):
        """选择题 prompt 的输出格式包含 options 数组。"""
        question = {
            "question_type": "choice",
            "difficulty": "easy",
            "knowledge_points": ["物质的量"],
            "content": "1 mol 任何粒子的数量约为？",
            "answer": "B",
        }
        prompt = build_variant_prompt(question)
        assert '"options"' in prompt
        assert '["A. ...", "B. ...", "C. ...", "D. ..."]' in prompt

    def test_generic_question_prompt_no_options_field(self):
        """非选择题 prompt 的输出格式不包含 options。"""
        question = {
            "question_type": "calculation",
            "difficulty": "hard",
            "knowledge_points": ["化学平衡"],
            "content": "计算下列反应的平衡常数 K。",
            "answer": "K = 0.5",
        }
        prompt = build_variant_prompt(question)
        assert '"options"' not in prompt
        assert '"content"' in prompt
        assert '"answer"' in prompt

    def test_custom_count(self):
        """自定义生成数量。"""
        question = {
            "question_type": "fill_blank",
            "difficulty": "medium",
            "knowledge_points": ["电解质"],
            "content": "NaCl 是__电解质。",
            "answer": "强",
        }
        prompt = build_variant_prompt(question, count=5)
        assert "5 道变式题" in prompt

    def test_default_count_is_three(self):
        """默认生成 3 道变式题。"""
        question = {
            "question_type": "experiment",
            "difficulty": "hard",
            "knowledge_points": ["实验室制取氧气"],
            "content": "用高锰酸钾制取氧气。",
            "answer": "加热分解",
        }
        prompt = build_variant_prompt(question)
        assert "3 道变式题" in prompt

    def test_missing_knowledge_points_defaults_to_unspecified(self):
        """缺少知识点的题目用 '未指定' 占位。"""
        question = {
            "question_type": "choice",
            "difficulty": "easy",
            "content": "题目内容",
            "answer": "A",
        }
        prompt = build_variant_prompt(question)
        assert "未指定" in prompt

    def test_requires_json_output(self):
        """prompt 要求 LLM 返回 JSON 数组。"""
        question = {
            "question_type": "inference",
            "difficulty": "medium",
            "knowledge_points": ["有机化学"],
            "content": "推断产物",
            "answer": "乙醇",
        }
        prompt = build_variant_prompt(question)
        assert "JSON" in prompt
        assert "请直接返回 JSON 数组" in prompt

    def test_all_question_types_in_variant_prompt(self):
        """各类型的题目都能正常生成 prompt（不抛异常）。"""
        for q_type in ["choice", "fill_blank", "calculation", "experiment", "inference"]:
            question = {
                "question_type": q_type,
                "difficulty": "medium",
                "knowledge_points": ["化学"],
                "content": "测试题目",
                "answer": "答案",
            }
            prompt = build_variant_prompt(question)
            assert isinstance(prompt, str)
            assert len(prompt) > 0
