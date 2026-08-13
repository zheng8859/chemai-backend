"""出题与题库 Agent 工具组单元测试 — 7 个工具 + SSE 契约。

覆盖 tasks 2.3 / 3.4 / 4.2 / 5.3 / 6.4 / 7.3：
- 工具元数据（persona / call_limit / 审批 / 前置条件）
- search_exam_bank 三级搜索（关键词 → 向量补充 → 联网兜底）
- web_search 降级与摘要截断
- generate_questions 参数透传 + 审核统计
- save_to_bank 三实体入库 + 自动命名 + _route 契约 + 事务回滚
- list_banks / delete_bank（系统预设拒绝 / 正常删除）
- _component props 契约 + _flatten_route
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

# ── 触发所有 @register_tool 装饰器 ──
import agent.tools  # noqa: F401
import agent.tools.exam_tools as exam_tools


class _FakeMainSession:
    """把 exam_tools.MainSession 替换为返回固定测试 session 的伪工厂。"""

    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def fake_session(db_session, monkeypatch):
    """让工具走测试 db_session，而非生产 main_engine。"""
    monkeypatch.setattr(exam_tools, "MainSession", _FakeMainSession(db_session))
    return db_session


# ═══════════════════════════════════════════════════════════════
# 工具元数据
# ═══════════════════════════════════════════════════════════════

class TestExamToolMetadata:
    def test_call_limits(self):
        from agent.tools.tool_meta import get_all_tools
        expected = {
            "search_exam_bank": 3,
            "web_search": 2,
            "show_exam_workbench": 3,
            "save_to_bank": 1,
            "generate_questions": 5,
            "list_banks": 1,
            "delete_bank": 1,
        }
        all_tools = get_all_tools()
        for name, limit in expected.items():
            meta = all_tools.get(name)
            assert meta is not None, f"工具 {name} 未注册"
            assert meta["call_limit"] == limit, f"{name} call_limit 应为 {limit}"

    def test_personas(self):
        from agent.tools.tool_meta import get_all_tools
        all_tools = get_all_tools()
        assert "parent" in all_tools["web_search"]["persona"]
        assert "student" in all_tools["web_search"]["persona"]
        teacher_tools = [
            "search_exam_bank", "show_exam_workbench", "save_to_bank",
            "generate_questions", "list_banks", "delete_bank",
        ]
        for name in teacher_tools:
            assert "teacher" in all_tools[name]["persona"], f"{name} 应含 teacher"
            assert "tutor" in all_tools[name]["persona"], f"{name} 应含 tutor"
            assert "student" not in all_tools[name]["persona"], f"{name} 不应含 student"

    def test_delete_bank_requires_approval(self):
        from agent.tools.tool_meta import get_all_tools
        meta = get_all_tools()["delete_bank"]
        assert meta["requires_approval"] is True
        assert "bank_id" in meta["prerequisites"]


# ═══════════════════════════════════════════════════════════════
# search_exam_bank — 三级搜索
# ═══════════════════════════════════════════════════════════════

class TestSearchExamBank:
    @pytest.mark.anyio
    async def test_keyword_match(self, fake_session, make_question, monkeypatch):
        await make_question(
            content="下列关于氧化还原反应的说法正确的是",
            knowledge_point_tags=["氧化还原反应"], answer="B",
        )
        await make_question(
            content="pH 计算题", knowledge_point_tags=["酸碱中和"], answer="A",
        )
        # 关闭向量补充与联网，隔离第一层关键词匹配
        async def fake_rank(candidates, kps, limit):
            return []
        async def fake_web(query):
            return {"query": query, "summary": "联网摘要"}
        monkeypatch.setattr(exam_tools, "search_questions_vector", fake_rank)
        monkeypatch.setattr(exam_tools, "web_search", fake_web)

        result = await exam_tools.search_exam_bank(keyword="氧化还原")
        bank = [it for it in result["items"] if it.get("source") == "bank"]
        assert len(bank) == 1
        assert "氧化还原" in bank[0]["content"]

    @pytest.mark.anyio
    async def test_vector_supplement(self, fake_session, make_question, monkeypatch):
        await make_question(
            content="氧化还原第一题", knowledge_point_tags=["氧化还原"], answer="A",
        )
        await make_question(
            content="电化学原电池", knowledge_point_tags=["电化学"], answer="B",
        )
        # 向量层把候选池全量补回，模拟语义补充命中第二题
        async def fake_rank(candidates, kps, limit):
            return list(candidates)
        async def fake_web(query):
            return {"query": query, "summary": "联网摘要"}
        monkeypatch.setattr(exam_tools, "search_questions_vector", fake_rank)
        monkeypatch.setattr(exam_tools, "web_search", fake_web)

        result = await exam_tools.search_exam_bank(keyword="氧化还原")
        bank = [it for it in result["items"] if it.get("source") == "bank"]
        assert len(bank) == 2, f"向量层应补回第二题，实际 {[b['content'] for b in bank]}"

    @pytest.mark.anyio
    async def test_web_fallback(self, fake_session, monkeypatch):
        async def fake_rank(candidates, kps, limit):
            return []
        async def fake_web(query):
            return {"query": query, "summary": "联网兜底内容"}
        monkeypatch.setattr(exam_tools, "search_questions_vector", fake_rank)
        monkeypatch.setattr(exam_tools, "web_search", fake_web)

        result = await exam_tools.search_exam_bank(keyword="冷门知识点")
        assert result["total"] == 1
        assert result["items"][0]["source"] == "web"
        assert result["items"][0]["label"] == "AI辅助搜索"
        assert result["items"][0]["summary"] == "联网兜底内容"


# ═══════════════════════════════════════════════════════════════
# web_search — 降级与摘要
# ═══════════════════════════════════════════════════════════════

class TestWebSearch:
    @pytest.mark.anyio
    async def test_degraded_when_no_key(self, monkeypatch):
        monkeypatch.setattr(exam_tools, "MIMO_API_KEY", "")
        result = await exam_tools.web_search("氧化还原")
        assert "未配置" in result["summary"]
        assert result["results"] == []

    @pytest.mark.anyio
    async def test_summary_truncated(self, monkeypatch):
        monkeypatch.setattr(exam_tools, "MIMO_API_KEY", "test-key")
        monkeypatch.setattr(exam_tools, "MIMO_BASE_URL", "https://api.test.com/v1")

        fake_provider = MagicMock()
        fake_provider.chat = AsyncMock(return_value={"content": "原始搜索结果"})
        monkeypatch.setattr(exam_tools, "OpenAICompatProvider", lambda **kw: fake_provider)

        async def fake_llm_chat(messages, **kwargs):
            return "摘要" * 300  # 600 字，超出 400 上限
        monkeypatch.setattr(exam_tools, "llm_chat", fake_llm_chat)

        result = await exam_tools.web_search("氧化还原")
        assert result["query"] == "氧化还原"
        assert len(result["summary"]) == exam_tools.WEB_SUMMARY_MAX_CHARS
        assert result["results"] == ["原始搜索结果"]

    @pytest.mark.anyio
    async def test_provider_failure_degrades(self, monkeypatch):
        monkeypatch.setattr(exam_tools, "MIMO_API_KEY", "test-key")
        monkeypatch.setattr(exam_tools, "MIMO_BASE_URL", "https://api.test.com/v1")

        fake_provider = MagicMock()
        fake_provider.chat = AsyncMock(side_effect=Exception("boom"))
        monkeypatch.setattr(exam_tools, "OpenAICompatProvider", lambda **kw: fake_provider)

        result = await exam_tools.web_search("氧化还原")
        assert "暂不可用" in result["summary"]
        assert result["results"] == []


# ═══════════════════════════════════════════════════════════════
# generate_questions — 参数透传 + 审核统计
# ═══════════════════════════════════════════════════════════════

class TestGenerateQuestions:
    @pytest.mark.anyio
    async def test_passthrough_and_audit(self, fake_session, monkeypatch):
        captured = {}
        q = SimpleNamespace(
            id=1, content="题目1", audit_status="passed",
            model_dump=lambda: {"id": 1, "content": "题目1", "audit_status": "passed"},
        )

        async def fake_gen(db, knowledge_points, difficulty="medium", quantity=3,
                           question_types=None, variant_qid="", **kwargs):
            captured["knowledge_points"] = knowledge_points
            captured["difficulty"] = difficulty
            captured["quantity"] = quantity
            captured["question_types"] = question_types
            captured["variant_qid"] = variant_qid
            return {
                "questions": [q],
                "generated_count": 1,
                "audit_summary": {"blocked": 0},
                "rag_mark": None,
            }

        monkeypatch.setattr(
            exam_tools.question_generation_service, "generate_questions", fake_gen,
        )

        result = await exam_tools.generate_questions(
            "氧化还原反应,离子反应", quantity=2, difficulty="hard",
            question_types=["choice", "fill_blank"], variant_qid="42",
        )

        assert captured["knowledge_points"] == ["氧化还原反应", "离子反应"]
        assert captured["difficulty"] == "hard"
        assert captured["quantity"] == 2
        assert captured["question_types"] == ["choice", "fill_blank"]
        assert captured["variant_qid"] == "42"

        assert result["questions"] == [{"id": 1, "content": "题目1", "audit_status": "passed"}]
        assert result["generated_count"] == 1
        assert result["audit_summary"] == {"total": 1, "passed": 1, "blocked": 0}

    @pytest.mark.anyio
    async def test_quantity_capped_at_5(self, fake_session, monkeypatch):
        captured = {}

        async def fake_gen(db, knowledge_points, difficulty="medium", quantity=3,
                           question_types=None, variant_qid="", **kwargs):
            captured["quantity"] = quantity
            return {"questions": [], "generated_count": 0,
                    "audit_summary": {"blocked": 0}, "rag_mark": None}

        monkeypatch.setattr(
            exam_tools.question_generation_service, "generate_questions", fake_gen,
        )
        await exam_tools.generate_questions("氧化还原", quantity=99)
        assert captured["quantity"] == 5


# ═══════════════════════════════════════════════════════════════
# save_to_bank — 三实体入库
# ═══════════════════════════════════════════════════════════════

class TestSaveToBank:
    @staticmethod
    async def _mock_index(monkeypatch):
        async def fake_index(db, mode="append"):
            return {"status": "ok", "count": 0}
        monkeypatch.setattr(exam_tools, "index_questions", fake_index)

    @pytest.mark.anyio
    async def test_skip_empty(self):
        result = await exam_tools.save_to_bank(questions=[])
        assert result["status"] == "skipped"

    @pytest.mark.anyio
    async def test_save_three_entities_and_route(self, fake_session, monkeypatch):
        from app.models.question_bank import QuestionSet, QuestionSetItem
        from app.models.teaching import Question

        await self._mock_index(monkeypatch)

        result = await exam_tools.save_to_bank(
            questions=[
                {"content": "题目A", "answer": "B", "question_type": "choice",
                 "knowledge_points": ["氧化还原"]},
                {"content": "题目B", "answer": "C", "question_type": "fill_blank"},
            ],
            teacher_id=1,
            bank_name="我的题库",
        )
        assert result["status"] == "saved"
        assert result["saved_count"] == 2
        assert result["bank_name"] == "我的题库"
        assert result["_route"] == {"page": "exam-v2", "params": {"bank_id": result["bank_id"]}}

        # 三实体落库：文件夹 + 题目 + 关联
        qs = (await fake_session.execute(
            select(QuestionSet).where(QuestionSet.id == result["bank_id"])
        )).scalar_one()
        assert qs.name == "我的题库"

        items = (await fake_session.execute(
            select(QuestionSetItem).where(
                QuestionSetItem.question_set_id == result["bank_id"]
            )
        )).scalars().all()
        assert len(items) == 2

        q_count = (await fake_session.execute(
            select(Question).where(Question.content.in_(["题目A", "题目B"]))
        )).scalars().all()
        assert len(q_count) == 2

    @pytest.mark.anyio
    async def test_auto_name(self, fake_session, monkeypatch):
        await self._mock_index(monkeypatch)
        result = await exam_tools.save_to_bank(
            questions=[{"content": "题目", "answer": "A",
                        "knowledge_points": ["氧化还原反应"]}],
            teacher_id=1,
        )
        assert result["status"] == "saved"
        assert result["bank_name"].startswith("AI出题")
        assert "氧化还原" in result["bank_name"]

    @pytest.mark.anyio
    async def test_index_sync_failure_does_not_flip_save(self, fake_session, monkeypatch):
        """向量同步失败不影响主流程：save 仍返回 saved。"""
        async def fake_index_fail(db, mode="append"):
            raise RuntimeError("ChromaDB 不可用")
        monkeypatch.setattr(exam_tools, "index_questions", fake_index_fail)

        result = await exam_tools.save_to_bank(
            questions=[{"content": "题目", "answer": "A"}],
            teacher_id=1,
            bank_name="同步失败仍保存",
        )
        assert result["status"] == "saved"
        assert result["saved_count"] == 1

    @pytest.mark.anyio
    async def test_rollback_on_failure(self, db_session):
        """单事务回滚：任一题目失败则整体不落库。"""
        from app.models.question_bank import QuestionSet
        from app.services.question_bank_service import QuestionBankService

        with pytest.raises(Exception):
            await QuestionBankService.save_questions_batch(
                db_session, name="会回滚",
                questions=[
                    {"content": "题目1", "answer": "A"},
                    {"content": "题目2", "answer": None},  # answer NOT NULL → 失败
                ],
                teacher_id=1,
            )
        await db_session.rollback()
        result = await db_session.execute(
            select(QuestionSet).where(QuestionSet.name == "会回滚")
        )
        assert result.scalar_one_or_none() is None


# ═══════════════════════════════════════════════════════════════
# list_banks / delete_bank
# ═══════════════════════════════════════════════════════════════

class TestListDeleteBank:
    @pytest.mark.anyio
    async def test_list_banks(self, fake_session):
        from app.models.question_bank import QuestionSet
        fake_session.add(QuestionSet(name="专题A", teacher_id=1))
        fake_session.add(QuestionSet(name="专题B", teacher_id=1))
        await fake_session.commit()

        result = await exam_tools.list_banks()
        assert result["total"] == 2
        names = {b["name"] for b in result["banks"]}
        assert names == {"专题A", "专题B"}
        for b in result["banks"]:
            assert b["item_count"] == 0

    @pytest.mark.anyio
    async def test_delete_bank_normal(self, fake_session):
        from app.models.question_bank import QuestionSet
        qs = QuestionSet(name="待删除", teacher_id=1)
        fake_session.add(qs)
        await fake_session.commit()
        await fake_session.refresh(qs)

        result = await exam_tools.delete_bank(qs.id)
        assert result["status"] == "deleted"
        assert result["bank_id"] == qs.id

    @pytest.mark.anyio
    async def test_delete_bank_system_rejected(self, fake_session):
        from app.models.question_bank import QuestionSet
        qs = QuestionSet(name="系统题库", teacher_id=1, is_system=True)
        fake_session.add(qs)
        await fake_session.commit()
        await fake_session.refresh(qs)

        result = await exam_tools.delete_bank(qs.id)
        assert result["status"] == "error"
        assert "不可删除" in result["reason"]
        assert result["error_code"] == "FORBIDDEN"

    @pytest.mark.anyio
    async def test_delete_bank_not_found(self, fake_session):
        result = await exam_tools.delete_bank(99999)
        assert result["status"] == "error"
        assert result["error_code"] == "RESOURCE_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════
# SSE 契约
# ═══════════════════════════════════════════════════════════════

class TestSSEContract:
    @pytest.mark.anyio
    async def test_show_workbench_uses_props(self):
        result = await exam_tools.show_exam_workbench()
        comp = result["_component"]
        assert comp["type"] == "exam-workbench"
        assert "props" in comp
        assert comp["props"] == {}
        # 不再使用 params/action 契约
        assert "params" not in comp
        assert "action" not in comp
        assert result["message"]

    def test_flatten_route_dict(self):
        from app.agent.sse.adapter_v2 import _flatten_route
        page, params = _flatten_route({"page": "exam-v2", "params": {"bank_id": 1}})
        assert page == "exam-v2"
        assert params == {"bank_id": 1}

    def test_flatten_route_non_dict(self):
        from app.agent.sse.adapter_v2 import _flatten_route
        page, params = _flatten_route("exam-v2")
        assert page == ""
        assert params == {}
