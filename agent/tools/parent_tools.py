"""家长报告工具集（2 个）— 生成和发送家长报告。

注册给 Parent persona。
"""

import logging

from app.infrastructure.database import MainSession
from app.services.parent_service import ParentService
from app.services.notification_service import NotificationService

from .tool_meta import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="generate_parent_report",
    persona=["parent"],
    call_limit=5,
    prerequisites=["student_id"],
    description="生成详细的家长报告：练习统计、薄弱知识点、学习进度、教师建议。用通俗语言表述。",
)
async def generate_parent_report(student_id: int) -> dict:
    """生成家长报告。"""
    async with MainSession() as db:
        svc = ParentService(db)
        overview = await svc.get_child_overview(db, student_id)
        return {
            "student_id": student_id,
            "report": overview,
            "language": "plain",
        }


@register_tool(
    name="send_report_to_parent",
    persona=["parent"],
    call_limit=5,
    requires_approval=True,
    prerequisites=["student_id"],
    description="将生成的报告推送到家长端（需确认）。",
)
async def send_report_to_parent(student_id: int) -> dict:
    """推送报告至家长端。"""
    async with MainSession() as db:
        svc = NotificationService(db)
        await svc.create_notification(
            db, student_id,
            type_="report_ready",
            title="学习报告已生成",
            body="您的子女学习报告已生成，请查看。",
            related_id=0,
        )
        return {"status": "sent", "student_id": student_id}
