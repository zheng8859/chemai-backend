"""Home-school schemas — Binding, ParentNotification, Report."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.core.enums import ParentRelation, BindingStatus, NotificationType
from app.schemas.homework import (
    BindingCreate, BindingRead,
    ParentNotificationRead, ParentNotificationListParams,
    ReportSendRequest, ReportSendResponse,
)

NOW = datetime(2026, 8, 1, 12, 0, 0)


class TestBindingCreate:
    def test_valid(self):
        r = BindingCreate(
            student_id=10, parent_id=20,
            bind_code="A1B2C3", relation=ParentRelation.mother,
        )
        assert r.bind_code == "A1B2C3"
        assert r.relation == ParentRelation.mother

    def test_default_relation(self):
        r = BindingCreate(student_id=10, parent_id=20, bind_code="A1B2C3")
        assert r.relation == ParentRelation.other

    def test_bind_code_too_short(self):
        with pytest.raises(ValidationError):
            BindingCreate(student_id=10, parent_id=20, bind_code="ABC")

    def test_bind_code_too_long(self):
        with pytest.raises(ValidationError):
            BindingCreate(student_id=10, parent_id=20, bind_code="A1B2C3D")


class TestBindingRead:
    def test_valid(self):
        r = BindingRead(
            id=1, student_id=10, parent_id=20,
            status=BindingStatus.active,
            relation=ParentRelation.father,
            created_at=NOW,
        )
        assert r.status == BindingStatus.active


class TestParentNotificationRead:
    def test_valid(self):
        r = ParentNotificationRead(
            id=1, parent_id=20,
            notification_type=NotificationType.learning_report,
            title="本周学习报告", body="您的孩子本周完成了...",
            read_at=None, sent_at=NOW,
        )
        assert r.notification_type == NotificationType.learning_report
        assert r.read_at is None

    def test_read_at_set(self):
        r = ParentNotificationRead(
            id=2, parent_id=20,
            notification_type=NotificationType.weekly_report,
            title="周报", body="...",
            read_at=NOW, sent_at=NOW,
        )
        assert r.read_at == NOW


class TestParentNotificationListParams:
    def test_valid(self):
        r = ParentNotificationListParams(parent_id=20)
        assert r.limit == 20


class TestReportSendRequest:
    def test_valid(self):
        r = ReportSendRequest(exam_record_id=1)
        assert r.exam_record_id == 1


class TestReportSendResponse:
    def test_valid(self):
        r = ReportSendResponse(
            sent_count=45, failed_count=0,
            parent_notifications_sent=45,
        )
        assert r.success is True
        assert r.sent_count == 45
