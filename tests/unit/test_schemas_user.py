"""User schemas — AccountRead, TeacherRead, StudentRead, ParentRead, etc."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.core.enums import (
    AccountRole, TeacherRole, TeacherAccountStatus,
    StudentStatus, ParentRelation, ApplicationStatus,
)
from app.schemas.user import (
    AccountRead, TeacherRead, TeacherUpdate,
    StudentRead, StudentUpdate,
    ParentRead, ParentUpdate,
    TeacherClassSubjectRead, TeacherClassSubjectCreate,
    TeacherApplicationCreate, TeacherApplicationRead,
    TeacherApplicationApprove,
)


NOW = datetime(2026, 8, 1, 12, 0, 0)


class TestAccountRead:
    def test_valid(self):
        r = AccountRead(id=1, username="13800000000", role=AccountRole.teacher, created_at=NOW)
        assert r.role == AccountRole.teacher
        assert r.username == "13800000000"

    def test_role_accepts_enum_value_string(self):
        r = AccountRead(id=1, username="u", role="teacher", created_at=NOW)
        assert r.role == AccountRole.teacher


class TestTeacherRead:
    def test_valid(self):
        r = TeacherRead(
            id=1, account_id=10, school_id=1, name="张老师",
            phone="13800000000", status=TeacherAccountStatus.approved,
            role=TeacherRole.teacher, created_at=NOW,
        )
        assert r.name == "张老师"
        assert r.role == TeacherRole.teacher

    def test_phone_optional(self):
        r = TeacherRead(
            id=1, account_id=10, school_id=1, name="张老师",
            phone=None, status=TeacherAccountStatus.approved,
            role=TeacherRole.teacher, created_at=NOW,
        )
        assert r.phone is None


class TestTeacherUpdate:
    def test_all_none_is_valid(self):
        r = TeacherUpdate()
        assert r.name is None
        assert r.phone is None
        assert r.role is None

    def test_partial_update(self):
        r = TeacherUpdate(name="李老师", role=TeacherRole.subject_lead)
        assert r.name == "李老师"
        assert r.role == TeacherRole.subject_lead


class TestStudentRead:
    def test_valid_minimal(self):
        r = StudentRead(
            id=1, account_id=10, class_id=1, name="小明",
            phone=None, status=StudentStatus.approved,
            barrier_profile=None, barrier_profile_updated_at=None,
            practice_count=0, last_practice_time=None,
            bind_code=None, created_at=NOW,
        )
        assert r.name == "小明"
        assert r.barrier_profile is None

    def test_with_barrier_profile(self):
        r = StudentRead(
            id=1, account_id=10, class_id=1, name="小明",
            phone="13800000001", status=StudentStatus.approved,
            barrier_profile={"concept": 0.5, "reading": 0.3, "expression": 0.2},
            barrier_profile_updated_at=NOW,
            practice_count=12, last_practice_time=NOW,
            bind_code="ABC123", created_at=NOW,
        )
        assert r.barrier_profile == {"concept": 0.5, "reading": 0.3, "expression": 0.2}
        assert r.practice_count == 12


class TestStudentUpdate:
    def test_partial(self):
        r = StudentUpdate(name="小红", class_id=2)
        assert r.name == "小红"
        assert r.class_id == 2


class TestParentRead:
    def test_valid(self):
        r = ParentRead(
            id=1, account_id=10, name="王爸爸",
            phone="13700000000", email="parent@test.com",
            created_at=NOW,
        )
        assert r.name == "王爸爸"
        assert r.email == "parent@test.com"


class TestParentUpdate:
    def test_partial(self):
        r = ParentUpdate(name="新名字", email=None)
        assert r.name == "新名字"


class TestTeacherClassSubjectRead:
    def test_valid(self):
        r = TeacherClassSubjectRead(
            id=1, teacher_id=10, class_id=1,
            subject="化学", is_head_teacher=True,
        )
        assert r.subject == "化学"
        assert r.is_head_teacher is True


class TestTeacherClassSubjectCreate:
    def test_defaults(self):
        r = TeacherClassSubjectCreate(teacher_id=10, class_id=1)
        assert r.subject == "化学"
        assert r.is_head_teacher is False


class TestTeacherApplicationCreate:
    def test_valid(self):
        r = TeacherApplicationCreate(
            name="李老师", phone="13900000000",
            school_name="北京一中",
        )
        assert r.subject == "化学"


class TestTeacherApplicationRead:
    def test_valid(self):
        r = TeacherApplicationRead(
            id=1, name="李老师", phone="13900000000",
            school_name="北京一中", subject="化学",
            status=ApplicationStatus.pending,
            reviewer_id=None, reviewed_at=None, created_at=NOW,
        )
        assert r.status == ApplicationStatus.pending


class TestTeacherApplicationApprove:
    def test_valid(self):
        r = TeacherApplicationApprove(approved=True, reviewer_id=1)
        assert r.approved is True

    def test_reject(self):
        r = TeacherApplicationApprove(approved=False, reviewer_id=2)
        assert r.approved is False
