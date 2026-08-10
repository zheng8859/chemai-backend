"""HomeworkService 服务层测试 — 亲子绑定/通知/报告。

直接调用 HomeworkService 静态方法，使用 db_session fixture。
"""

import pytest
from datetime import datetime, timezone

from sqlalchemy import select

from app.services.homework_service import HomeworkService, HomeworkError
from app.models.homework import StudentParentBinding, ParentNotification
from app.models.user import Student
from app.core.enums import BindingStatus


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

async def _create_student(db, **overrides):
    """创建测试学生（含 bind_code）。"""
    defaults = {
        "id": 1,
        "account_id": 1,
        "class_id": 1,
        "school_id": 1,
        "name": "测试学生",
        "student_id": "S20001",
        "bind_code": "ABC123",
        "status": "approved",
    }
    defaults.update(overrides)
    s = Student(**defaults)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


# ═══════════════════════════════════════════════════════════════
# Bindings
# ═══════════════════════════════════════════════════════════════

class TestBindingCreate:
    """POST /bindings → create_binding。"""

    @pytest.mark.anyio
    async def test_nonexistent_student_raises(self, db_session):
        """学生不存在 → HomeworkError。"""
        from app.schemas.homework import BindingCreate
        with pytest.raises(HomeworkError, match="学生不存在"):
            await HomeworkService.create_binding(
                db_session,
                BindingCreate(
                    student_id=99999, parent_id=1,
                    bind_code="ABC123", relation="mother",
                ),
            )

    @pytest.mark.anyio
    async def test_invalid_bind_code_raises(self, db_session):
        """绑定码不匹配 → HomeworkError。"""
        from app.schemas.homework import BindingCreate
        s = await _create_student(db_session, bind_code="CORRECT")

        with pytest.raises(HomeworkError, match="绑定码无效"):
            await HomeworkService.create_binding(
                db_session,
                BindingCreate(
                    student_id=s.id, parent_id=1,
                    bind_code="WRONG1", relation="mother",
                ),
            )

    @pytest.mark.anyio
    async def test_create_binding_success(self, db_session):
        """正确的绑定码 + 学生存在 → 创建成功。"""
        from app.schemas.homework import BindingCreate
        s = await _create_student(db_session, bind_code="ABC123")

        result = await HomeworkService.create_binding(
            db_session,
            BindingCreate(
                student_id=s.id, parent_id=1,
                bind_code="ABC123", relation="mother",
            ),
        )

        assert result.student_id == s.id
        assert result.parent_id == 1
        assert result.relation == "mother"
        assert result.status == BindingStatus.active


class TestBindingList:
    """GET /bindings → list bindings by parent/student。"""

    @pytest.mark.anyio
    async def test_list_bindings_by_parent_empty(self, db_session):
        """无绑定数据时返回空列表。"""
        result = await HomeworkService.list_bindings_by_parent(db_session, parent_id=1)
        assert result == []

    @pytest.mark.anyio
    async def test_list_bindings_by_student_empty(self, db_session):
        """无绑定数据时返回空列表。"""
        result = await HomeworkService.list_bindings_by_student(db_session, student_id=1)
        assert result == []

    @pytest.mark.anyio
    async def test_list_returns_active_only(self, db_session):
        """只返回 active 状态的绑定（by_parent）。"""
        # 创建多个绑定
        db_session.add(StudentParentBinding(
            student_id=1, parent_id=1, status=BindingStatus.active, relation="mother",
        ))
        db_session.add(StudentParentBinding(
            student_id=2, parent_id=1, status=BindingStatus.inactive, relation="father",
        ))
        await db_session.commit()

        result = await HomeworkService.list_bindings_by_parent(db_session, parent_id=1)
        assert len(result) == 1
        assert result[0].status == BindingStatus.active


class TestBindingDelete:
    """DELETE /bindings/{id} → delete_binding。"""

    @pytest.mark.anyio
    async def test_delete_nonexistent_raises(self, db_session):
        """删除不存在绑定 → HomeworkError。"""
        with pytest.raises(HomeworkError, match="绑定关系不存在"):
            await HomeworkService.delete_binding(db_session, 99999)

    @pytest.mark.anyio
    async def test_delete_existing(self, db_session):
        """删除成功。"""
        b = StudentParentBinding(
            student_id=1, parent_id=1, status=BindingStatus.active, relation="mother",
        )
        db_session.add(b)
        await db_session.commit()
        binding_id = b.id

        await HomeworkService.delete_binding(db_session, binding_id)

        # 验证已删除
        result = await db_session.execute(
            select(StudentParentBinding).where(StudentParentBinding.id == binding_id)
        )
        assert result.scalar_one_or_none() is None


# ═══════════════════════════════════════════════════════════════
# Notifications
# ═══════════════════════════════════════════════════════════════

class TestNotificationCreate:
    """POST /notifications → create_notification。"""

    @pytest.mark.anyio
    async def test_create_notification(self, db_session):
        """创建通知成功。"""
        result = await HomeworkService.create_notification(
            db_session,
            parent_id=1,
            notification_type="warning_alert",
            title="测试通知",
            body="这是一条测试通知",
        )

        assert result.parent_id == 1
        assert result.title == "测试通知"
        assert result.body == "这是一条测试通知"
        assert result.read_at is None


class TestNotificationList:
    """GET /notifications → list_notifications_by_parent。"""

    @pytest.mark.anyio
    async def test_list_empty(self, db_session):
        """无通知数据时返回空。"""
        items, total = await HomeworkService.list_notifications_by_parent(
            db_session, parent_id=1,
        )
        assert total == 0
        assert items == []

    @pytest.mark.anyio
    async def test_list_with_data(self, db_session):
        """列出通知并验证分页。"""
        for i in range(3):
            db_session.add(ParentNotification(
                parent_id=1, notification_type="warning_alert", title=f"通知{i}",
                body=f"内容{i}", sent_at=datetime.now(timezone.utc),
            ))
        await db_session.commit()

        items, total = await HomeworkService.list_notifications_by_parent(
            db_session, parent_id=1, limit=2, offset=0,
        )
        assert total == 3
        assert len(items) == 2


class TestNotificationMarkRead:
    """POST /notifications/{id}/read → mark_notification_read。"""

    @pytest.mark.anyio
    async def test_mark_nonexistent_raises(self, db_session):
        """不存在的通知 → HomeworkError。"""
        with pytest.raises(HomeworkError, match="通知不存在"):
            await HomeworkService.mark_notification_read(db_session, 99999)

    @pytest.mark.anyio
    async def test_mark_read(self, db_session):
        """标记为已读成功。"""
        n = ParentNotification(
            parent_id=1, notification_type="warning_alert", title="通知",
            body="内容", sent_at=datetime.now(timezone.utc),
        )
        db_session.add(n)
        await db_session.commit()
        nid = n.id

        result = await HomeworkService.mark_notification_read(db_session, nid)
        assert result.read_at is not None


# ═══════════════════════════════════════════════════════════════
# Reports
# ═══════════════════════════════════════════════════════════════

class TestSendReports:
    """POST /reports → send_exam_reports（stub）。"""

    @pytest.mark.anyio
    async def test_send_reports_stub(self, db_session):
        """Stub 实现返回标准格式。"""
        result = await HomeworkService.send_exam_reports(db_session, exam_id=1)

        assert result["success"] is True
        assert "sent_count" in result
        assert "failed_count" in result
