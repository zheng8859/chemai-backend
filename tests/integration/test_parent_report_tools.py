"""家长报告 Agent 工具集成测试 — generate_parent_report / send_report_to_parent。

覆盖 tasks 5.1–5.2：
- generate_parent_report 报告生成、学生无数据返回说明、内容过滤（不暴露具体错题）
- send_report_to_parent 发送通知返回状态、审批门控元数据
"""

import pytest
from sqlalchemy import select

# ── 触发所有 @register_tool 装饰器 ──
import agent.tools  # noqa: F401
import agent.tools.parent_tools as parent_tools

from app.models.notification import Notification


@pytest.fixture
def fake_session(db_session, monkeypatch, fake_main_session_cls):
    """让工具走测试 db_session，而非生产 main_engine。"""
    monkeypatch.setattr(parent_tools, "MainSession", fake_main_session_cls(db_session))
    return db_session


# ═══════════════════════════════════════════════════════════════
# generate_parent_report — 报告生成 + 内容过滤
# ═══════════════════════════════════════════════════════════════

class TestGenerateParentReport:

    @pytest.mark.anyio
    async def test_generates_report(self, fake_session, make_student):
        """有数据的学生 → 返回通俗报告。"""
        student = await make_student(weak_knowledge_points=["氧化还原反应", "离子反应"])

        result = await parent_tools.generate_parent_report(student.id)
        assert result["student_id"] == student.id
        assert result["language"] == "plain"

        report = result["report"]
        assert report.student_id == student.id
        assert report.student_name == "测试学生"
        assert isinstance(report.weak_knowledge_points, list)
        assert report.advice  # 教师建议非空
        assert "夯实基础概念" in report.advice

    @pytest.mark.anyio
    async def test_no_data_returns_explanation(self, fake_session, make_student):
        """无诊断数据的学生 → 返回「暂无足够数据」说明。"""
        student = await make_student(barrier_profile=None, weak_knowledge_points=[])

        result = await parent_tools.generate_parent_report(student.id)
        assert result["report"].characteristics == "暂无足够数据进行分析"
        assert result["report"].advice == "暂无建议"

    @pytest.mark.anyio
    async def test_report_filters_specific_wrong_answers(self, fake_session, make_student):
        """报告仅含薄弱知识点摘要，不暴露具体错题/答案/逐题内容。"""
        student = await make_student(weak_knowledge_points=["氧化还原反应"])

        result = await parent_tools.generate_parent_report(student.id)
        report = result["report"]

        # 只暴露知识点名称与掌握程度
        assert all(isinstance(kp, str) for kp in report.weak_knowledge_points)

        # 报告中不存在具体错题 / 原始作答 / 逐题答案相关字段
        dumped = report.model_dump()
        for forbidden in ("student_answer", "answers", "questions", "wrong_questions", "错题", "逐题答案"):
            assert forbidden not in dumped, f"报告不应包含具体错题字段: {forbidden}"


# ═══════════════════════════════════════════════════════════════
# send_report_to_parent — 推送通知 + 审批门控
# ═══════════════════════════════════════════════════════════════

class TestSendReportToParent:

    @pytest.mark.anyio
    async def test_sends_notification(self, fake_session):
        """发送报告 → 返回 sent 状态并写入通知。"""
        result = await parent_tools.send_report_to_parent(123)
        assert result["status"] == "sent"
        assert result["student_id"] == 123

        notif = (
            await fake_session.execute(
                select(Notification).where(Notification.student_id == 123)
            )
        ).scalar_one_or_none()
        assert notif is not None
        assert notif.type == "report_ready"
        assert notif.title == "学习报告已生成"

    def test_requires_approval_metadata(self):
        """send_report_to_parent 元数据：requires_approval + student_id 前置条件。"""
        from agent.tools.tool_meta import get_tool_meta
        meta = get_tool_meta("send_report_to_parent")
        assert meta is not None
        assert meta["requires_approval"] is True
        assert "student_id" in meta["prerequisites"]
        assert "parent" in meta["persona"]
