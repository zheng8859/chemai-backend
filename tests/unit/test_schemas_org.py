"""Organization schemas — School, Grade, Class CRUD models."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.schemas.org import (
    SchoolCreate, SchoolRead, SchoolUpdate,
    GradeCreate, GradeRead, GradeUpdate,
    ClassCreate, ClassRead, ClassUpdate,
)

NOW = datetime(2026, 8, 1, 12, 0, 0)


class TestSchoolCreate:
    def test_valid_minimal(self):
        r = SchoolCreate(name="北京一中")
        assert r.name == "北京一中"
        assert r.region is None

    def test_full_fields(self):
        r = SchoolCreate(
            name="北京一中", region="海淀区",
            address="中关村大街1号", phone="010-12345678",
            current_semester="2026-春季",
        )
        assert r.region == "海淀区"
        assert r.current_semester == "2026-春季"

    def test_name_required(self):
        with pytest.raises(ValidationError):
            SchoolCreate()


class TestSchoolRead:
    def test_valid(self):
        r = SchoolRead(
            id=1, name="北京一中", region="海淀区",
            address=None, phone=None, current_semester=None,
            created_at=NOW,
        )
        assert r.id == 1


class TestSchoolUpdate:
    def test_partial(self):
        r = SchoolUpdate(name="新校名")
        assert r.name == "新校名"
        assert r.region is None


class TestGradeCreate:
    def test_valid(self):
        r = GradeCreate(school_id=1, name="高一", academic_year="2026-2027")
        assert r.name == "高一"

    def test_name_required(self):
        with pytest.raises(ValidationError):
            GradeCreate(school_id=1)


class TestGradeRead:
    def test_valid(self):
        r = GradeRead(id=1, school_id=1, name="高一", academic_year=None, created_at=NOW)
        assert r.name == "高一"


class TestGradeUpdate:
    def test_partial(self):
        r = GradeUpdate(name="高二")
        assert r.name == "高二"


class TestClassCreate:
    def test_defaults(self):
        r = ClassCreate(grade_id=1, name="高一(1)班")
        assert r.subject == "化学"
        assert r.stage is None

    def test_custom(self):
        r = ClassCreate(grade_id=1, name="高一(2)班", stage="高一上", subject="化学")
        assert r.stage == "高一上"


class TestClassRead:
    def test_valid(self):
        r = ClassRead(
            id=1, grade_id=1, name="高一(1)班",
            student_count=45, stage="高一上",
            subject="化学", created_at=NOW,
        )
        assert r.student_count == 45


class TestClassUpdate:
    def test_partial(self):
        r = ClassUpdate(name="高一(1)班(调整)")
        assert r.name == "高一(1)班(调整)"
