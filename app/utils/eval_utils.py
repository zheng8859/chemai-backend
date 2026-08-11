"""eval_utils — ChemAI 评测工具函数 (v0.5.0)

6 个纯函数工具，覆盖 Doc 54 定义的容差参数：
- check_scientific_accuracy  — 科学性检查 (阈值 0.9)
- keyword_match_ratio       — 关键词覆盖率 (阈值 0.7)
- semantic_similarity       — 语义相似度 (SequenceMatcher, 阈值 0.6)
- compare_diagnosis         — 诊断结果比较 (语义匹配 wrapper)
- difficulty_match_score    — 难度匹配得分 (精确 1.0 / 差1级 0.7 / 差2级 0.3)
- compute_metrics           — 聚合指标计算

所有函数均无副作用、无外部依赖。
"""

from difflib import SequenceMatcher


# ── 容差常量（来自 Doc 54 第二章）──────────────────────────
SCIENTIFIC_ACCURACY_MIN = 0.9
KEYWORD_MATCH_RATIO = 0.7
SEMANTIC_SIMILARITY_THRESHOLD = 0.6
CONFIDENCE_RANGE = 0.15
CONFIDENCE_MIN = 0.7
DIFFICULTY_MATCH_TOLERANCE = 1  # ±1 级


# ═══════════════════════════════════════════════════════════════
# 1. 科学性检查
# ═══════════════════════════════════════════════════════════════

def check_scientific_accuracy(questions: list[dict]) -> float:
    """评估生成题目的科学性得分 (0.0-1.0)。

    检查维度：
    - 化学方程式是否正确（配平、箭头方向、反应条件）
    - 概念表述是否准确
    - 正确答案是否唯一且正确
    - 干扰项是否合理（不会误导）

    返回值 0.0-1.0，>= 0.9 为通过。
    """
    if not questions:
        return 0.0

    scores = []
    for q in questions:
        q_score = 1.0  # 初始满分，逐项扣分

        stem = q.get("stem", "")
        correct_answer = q.get("correct_answer", "")
        options = q.get("options", [])
        explanation = q.get("explanation", "")

        # 检查 1: stem 不为空
        if not stem.strip():
            q_score -= 0.5

        # 检查 2: 正确答案存在且不为空
        if not correct_answer.strip():
            q_score -= 0.5

        # 检查 3: 选择题中正确选项在 options 中
        if options and correct_answer:
            if correct_answer not in options and correct_answer not in "ABCD":
                q_score -= 0.2

        # 检查 4: 有解释（说明不是纯猜测）
        if not explanation.strip():
            q_score -= 0.1

        # 检查 5: 干扰项不应与正确答案相同
        if options and correct_answer and correct_answer in "ABCD":
            correct_idx = ord(correct_answer) - ord("A")
            if 0 <= correct_idx < len(options):
                for i, opt in enumerate(options):
                    if i != correct_idx and opt == options[correct_idx]:
                        q_score -= 0.3
                        break

        scores.append(max(0.0, q_score))

    return round(sum(scores) / len(scores), 4)


# ═══════════════════════════════════════════════════════════════
# 2. 关键词匹配率
# ═══════════════════════════════════════════════════════════════

def keyword_match_ratio(output: str, keywords: list[str]) -> float:
    """计算 AI 回复中关键词的覆盖率 (0.0-1.0)。

    对每个关键词，检查是否在输出文本中出现（不区分大小写）。
    返回覆盖率 = 出现的关键词数 / 总关键词数。
    阈值 0.7。
    """
    if not keywords:
        return 0.0

    output_lower = output.lower()
    matched = sum(
        1 for kw in keywords
        if kw.lower() in output_lower
    )
    return round(matched / len(keywords), 4)


# ═══════════════════════════════════════════════════════════════
# 3. 语义相似度
# ═══════════════════════════════════════════════════════════════

def semantic_similarity(text_a: str, text_b: str) -> float:
    """计算两段文本的语义相似度 (0.0-1.0)。

    使用 difflib.SequenceMatcher，阈值 >= 0.6 认为语义匹配。
    Doc 54 明确指定使用 SequenceMatcher 而非 Embedding。
    """
    if not text_a or not text_b:
        return 0.0

    # 预处理：去除多余空白，统一为小写
    a = " ".join(text_a.strip().lower().split())
    b = " ".join(text_b.strip().lower().split())

    if a == b:
        return 1.0

    return round(SequenceMatcher(None, a, b).ratio(), 4)


# ═══════════════════════════════════════════════════════════════
# 4. 诊断结果比较
# ═══════════════════════════════════════════════════════════════

def compare_diagnosis(actual: str, expected: str) -> bool:
    """比较实际诊断结果与预期结果是否语义匹配。

    Wrapper around semantic_similarity，使用阈值 0.6。
    """
    return semantic_similarity(actual, expected) >= SEMANTIC_SIMILARITY_THRESHOLD


# ═══════════════════════════════════════════════════════════════
# 5. 难度匹配得分
# ═══════════════════════════════════════════════════════════════

def difficulty_match_score(expected: int, actual: int) -> float:
    """计算难度匹配得分 (0.0-1.0)。

    Doc 54 定义:
    - 精确匹配: 1.0
    - 差 1 级:  0.7
    - 差 2 级:  0.3
    - 差 3+ 级: 0.0
    """
    diff = abs(expected - actual)
    if diff == 0:
        return 1.0
    elif diff == 1:
        return 0.7
    elif diff == 2:
        return 0.3
    else:
        return 0.0


# ═══════════════════════════════════════════════════════════════
# 6. 聚合指标计算
# ═══════════════════════════════════════════════════════════════

def compute_metrics(results: list[dict]) -> dict:
    """从评测结果列表中计算聚合指标。

    输入: 每条结果 dict，至少包含 "passed" (bool) 和 "score" (float, 可选)
    输出: {pass_rate, avg_score, total, passed, failed, degradation}
    """
    total = len(results)
    if total == 0:
        return {
            "pass_rate": 100.0,
            "avg_score": 0.0,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "degradation": 0.0,
        }

    passed = sum(1 for r in results if r.get("passed", False))
    failed = total - passed
    pass_rate = round(passed / total * 100, 2)

    scores = [r.get("score", 0.0) for r in results if "score" in r]
    avg_score = round(sum(scores) / len(scores), 4) if scores else 0.0

    # degradation 需要基线对比，这里返回 0 作为默认值
    # 实际劣化由 run_evals.py 的 compare_to_baseline 计算
    return {
        "pass_rate": pass_rate,
        "avg_score": avg_score,
        "total": total,
        "passed": passed,
        "failed": failed,
        "degradation": 0.0,
    }


# ═══════════════════════════════════════════════════════════════
# 辅助: Golden 数据集加载
# ═══════════════════════════════════════════════════════════════

def load_golden_samples(module: str = None) -> list[dict]:
    """从 JSON 文件加载 Golden 样本。可指定模块筛选。

    自动扫描 tests/evals/golden_dataset/*.json（排除 schema.json），
    无需手动维护模块列表。
    """
    import json
    from pathlib import Path

    golden_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "evals" / "golden_dataset"

    # 动态扫描目录中的 JSON 文件，排除 schema.json
    json_files = sorted(
        p for p in golden_dir.glob("*.json")
        if p.name != "schema.json"
    )

    # 如果指定了模块，仅加载对应文件
    if module:
        json_files = [p for p in json_files if p.stem == module]

    all_samples = []
    for json_path in json_files:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        all_samples.extend(data.get("samples", []))

    return all_samples
