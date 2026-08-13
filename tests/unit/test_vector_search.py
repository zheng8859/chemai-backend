"""向量检索服务纯函数测试 — embedding fallback、embed text 构建。

不依赖 ChromaDB 或 dashscope API。
"""

from types import SimpleNamespace

import pytest
from unittest.mock import Mock, patch, MagicMock

from app.services.vector_search_service import (
    _build_embed_text,
    _fallback_embedding,
    _get_embedding,
)


class TestFallbackEmbedding:
    def test_returns_1024_dims_by_default(self):
        vec = _fallback_embedding("测试文本")
        assert len(vec) == 1024

    def test_custom_dims(self):
        vec = _fallback_embedding("test", dims=128)
        assert len(vec) == 128

    def test_all_values_in_range(self):
        """向量值应在 [-1, 1] 范围内。"""
        vec = _fallback_embedding("测试")
        for v in vec:
            assert -1.0 <= v <= 1.0

    def test_deterministic(self):
        """相同输入产生相同向量。"""
        v1 = _fallback_embedding("same text")
        v2 = _fallback_embedding("same text")
        assert v1 == v2

    def test_different_inputs_different_vectors(self):
        v1 = _fallback_embedding("text A")
        v2 = _fallback_embedding("text B")
        assert v1 != v2

    def test_empty_string(self):
        vec = _fallback_embedding("")
        assert len(vec) == 1024

    def test_unicode_text(self):
        vec = _fallback_embedding("化学方程式 H2O → H+ + OH-")
        assert len(vec) == 1024


class TestBuildEmbedText:
    def test_full_fields(self):
        exam = Mock()
        exam.knowledge_point_tags = ["氧化还原反应", "摩尔计算"]
        exam.question_type = "choice"
        exam.difficulty = "medium"
        exam.source = "全国卷"
        exam.year = 2023
        exam.question_number = "7"
        exam.content = "题目正文内容"
        exam.answer = "A"

        text = _build_embed_text(exam)
        assert "氧化还原反应" in text
        assert "摩尔计算" in text
        assert "全国卷" in text
        assert "2023" in text
        assert "题目正文内容" in text

    def test_missing_optional_fields(self):
        exam = Mock()
        exam.knowledge_point_tags = None
        exam.question_type = None
        exam.difficulty = None
        exam.source = "湖南卷"
        exam.year = 2024
        exam.question_number = None
        exam.content = None
        exam.answer = None

        text = _build_embed_text(exam)
        assert "未知" in text  # question_type fallback
        assert "medium" in text  # difficulty fallback
        assert "湖南卷" in text

    def test_content_truncated_to_500(self):
        exam = Mock()
        exam.knowledge_point_tags = ["测试"]
        exam.question_type = "choice"
        exam.difficulty = "easy"
        exam.source = "全国卷"
        exam.year = 2022
        exam.question_number = "1"
        exam.content = "X" * 800
        exam.answer = "A"

        text = _build_embed_text(exam)
        # content should be truncated to 500 chars
        # content truncation: "X" * 501 should not appear if limited to 500
        assert "X" * 501 not in text
        # Verify the text still contains the truncated content
        assert ("X" * 500) in text

    def test_empty_knowledge_points(self):
        exam = Mock()
        exam.knowledge_point_tags = []
        exam.question_type = "fill_blank"
        exam.difficulty = "hard"
        exam.source = "北京卷"
        exam.year = 2021
        exam.question_number = "3"
        exam.content = "填空题内容"
        exam.answer = "答案"

        text = _build_embed_text(exam)
        assert "考点:" in text  # still has the label, just empty content


class TestSimilarityThreshold:
    """向量补充相似度阈值 — 低于 0.6 的候选不补充进结果（spec: ≥ 0.6）。"""

    @pytest.mark.anyio
    async def test_filters_below_threshold(self, monkeypatch):
        from app.services import vector_search_service as vss

        q1 = SimpleNamespace(
            id=1, knowledge_point_tags=["氧化还原"], question_type="choice",
            difficulty="medium", content="题目1",
        )
        q2 = SimpleNamespace(
            id=2, knowledge_point_tags=["电化学"], question_type="choice",
            difficulty="medium", content="题目2",
        )

        class FakeColl:
            def query(self, query_embeddings, n_results):
                return {
                    "ids": [["question_1", "question_2"]],
                    # sim = 1 - distance：0.9（保留）/ 0.2（过滤）
                    "distances": [[0.1, 0.8]],
                }

        monkeypatch.setattr(vss, "_get_question_collection", lambda: FakeColl())
        monkeypatch.setattr(vss, "_get_embedding", lambda text: [0.1] * 3)

        result = await vss.search_questions_vector([q1, q2], ["氧化还原"], limit=5)
        assert [q.id for q in result] == [1]
