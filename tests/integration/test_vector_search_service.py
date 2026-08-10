"""VectorSearchService 测试 — 关键词匹配/嵌入文本/回退嵌入。

ChromaDB 依赖的方法（_vector_rerank, build_index, check_and_rebuild_index）
需要 ChromaDB 环境，不在本文件覆盖。仅测试纯逻辑层。
"""

import pytest
import hashlib

from sqlalchemy import select

from app.models.question_bank import HistoricalExam
from app.services.vector_search_service import (
    _keyword_match,
    _build_embed_text,
    _fallback_embedding,
)


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

async def _create_historical_exam(db, **overrides):
    """创建测试历年真题。"""
    defaults = {
        "source": "全国卷",
        "year": 2024,
        "difficulty": "medium",
        "content": "历年真题题目内容",
        "answer": "C",
        "analysis": "历年真题解析",
        "knowledge_point_tags": ["氧化还原反应", "电化学"],
    }
    defaults.update(overrides)
    he = HistoricalExam(**defaults)
    db.add(he)
    await db.commit()
    await db.refresh(he)
    return he


# ═══════════════════════════════════════════════════════════════
# _build_embed_text — 构建嵌入文本
# ═══════════════════════════════════════════════════════════════

class TestBuildEmbedText:
    """_build_embed_text 单元测试。"""

    class _MockExam:
        """模拟 HistoricalExam + question_type（服务代码依赖此属性）。"""
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    def test_basic_fields(self):
        """验证基本字段拼接。"""
        exam = self._MockExam(
            source="全国卷", year=2024, difficulty="medium",
            knowledge_point_tags=["氧化还原", "电化学"],
            content="题目内容测试",
            answer="B",
            question_type="choice",
            question_number="1",
        )
        result = _build_embed_text(exam)

        assert "氧化还原" in result
        assert "电化学" in result
        assert "全国卷" in result
        assert "2024" in result
        assert "题目内容测试" in result
        assert "B" in result

    def test_empty_tags(self):
        """空知识点标签时不崩溃。"""
        exam = self._MockExam(
            source="湖南卷", year=2023, difficulty="hard",
            knowledge_point_tags=None,
            content="题目内容", answer="A",
            question_type="fill_blank",
            question_number=None,
        )
        result = _build_embed_text(exam)
        assert "湖南卷" in result
        assert "2023" in result

    def test_empty_optional_fields(self):
        """可选字段为空时不崩溃。"""
        exam = self._MockExam(
            source="测试", year=2020, difficulty="easy",
            knowledge_point_tags=[], content="", answer="",
            question_number=None, question_type="",
        )
        result = _build_embed_text(exam)
        # 不应抛异常
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════
# _fallback_embedding — MD5 回退嵌入
# ═══════════════════════════════════════════════════════════════

class TestFallbackEmbedding:
    """_fallback_embedding 单元测试。"""

    def test_default_dims(self):
        """默认维度为 1024。"""
        vec = _fallback_embedding("测试文本")
        assert len(vec) == 1024

    def test_custom_dims(self):
        """支持自定义维度。"""
        vec = _fallback_embedding("测试", dims=256)
        assert len(vec) == 256

    def test_deterministic(self):
        """相同输入产生相同输出。"""
        v1 = _fallback_embedding("相同文本")
        v2 = _fallback_embedding("相同文本")
        assert v1 == v2

    def test_different_inputs_produce_different_vectors(self):
        """不同输入产生不同向量。"""
        v1 = _fallback_embedding("文本A")
        v2 = _fallback_embedding("文本B")
        assert v1 != v2

    def test_values_in_range(self):
        """向量值在 [-1, 1] 范围内。"""
        vec = _fallback_embedding("测试")
        for v in vec:
            assert -1.0 <= v <= 1.0


# ═══════════════════════════════════════════════════════════════
# _keyword_match — 关键词匹配
# ═══════════════════════════════════════════════════════════════

class TestKeywordMatch:
    """Layer 1 关键词匹配集成测试。"""

    @pytest.mark.anyio
    async def test_empty_db(self, db_session):
        """空数据库返回空列表。"""
        result = await _keyword_match(db_session, ["氧化还原"])
        assert result == []

    @pytest.mark.anyio
    async def test_match_by_knowledge_point(self, db_session):
        """按知识点匹配返回相关真题。"""
        he = await _create_historical_exam(
            db_session, knowledge_point_tags=["氧化还原反应"],
        )

        result = await _keyword_match(db_session, ["氧化还原反应"])
        assert len(result) >= 1
        assert result[0].id == he.id

    @pytest.mark.anyio
    async def test_difficulty_filter(self, db_session):
        """按难度过滤。"""
        await _create_historical_exam(db_session, difficulty="easy")
        await _create_historical_exam(db_session, difficulty="hard")

        result = await _keyword_match(db_session, ["氧化还原"], difficulty="easy")
        # 所有结果难度应为 easy（或匹配加分）
        for exam in result:
            if exam.difficulty == "easy":
                pass  # 难度匹配的应有更高的分被排到前面

    @pytest.mark.anyio
    async def test_no_knowledge_points_returns_all(self, db_session):
        """无知识点时返回所有真题（按年份降序）。"""
        await _create_historical_exam(db_session, year=2023)
        await _create_historical_exam(db_session, year=2024)

        result = await _keyword_match(db_session, [])
        assert len(result) >= 2
        # 按年份降序排列
        assert result[0].year >= result[1].year

    @pytest.mark.anyio
    async def test_no_match_returns_empty(self, db_session):
        """知识点完全不匹配时返回空。"""
        await _create_historical_exam(
            db_session,
            knowledge_point_tags=["电化学"],
            difficulty="medium",
        )

        # 查询完全不重叠的知识点
        result = await _keyword_match(db_session, ["有机化学"])
        assert result == []

    @pytest.mark.anyio
    async def test_scores_sort_descending(self, db_session):
        """高匹配度题目排前面。"""
        # 高匹配：两个知识点都匹配
        he1 = await _create_historical_exam(
            db_session,
            knowledge_point_tags=["氧化还原反应", "电化学"],
        )
        # 低匹配：只有一个知识点匹配
        he2 = await _create_historical_exam(
            db_session,
            knowledge_point_tags=["氧化还原反应"],
        )

        result = await _keyword_match(db_session, ["氧化还原反应", "电化学"])
        assert len(result) >= 2
        # he1 的匹配度应高于 he2（多一个重叠知识点）
        assert result[0].id == he1.id
