"""Test Account & Auth model changes — fields exist with correct attributes."""

import pytest

from app.models.user import Account, Teacher, Student, Parent, TeacherApplication


class TestAccountModel:
    def test_phone_field_exists(self):
        assert hasattr(Account, "phone"), "Account should have 'phone' column"
        assert not hasattr(Account, "username"), "Account should NOT have 'username'"

    def test_phone_is_string(self):
        col = Account.__table__.c.phone
        assert col.unique, "Account.phone must be unique"
        assert col.index, "Account.phone must be indexed"


class TestTeacherModel:
    def test_no_phone_field(self):
        assert not hasattr(Teacher, "phone"), "Teacher should NOT have 'phone' column"
        assert hasattr(Teacher, "name"), "Teacher should still have 'name'"


class TestStudentModel:
    def test_new_fields_exist(self):
        assert hasattr(Student, "student_id"), "Student should have 'student_id'"
        assert hasattr(Student, "school_id"), "Student should have 'school_id'"
        assert hasattr(Student, "is_activated"), "Student should have 'is_activated'"

    def test_no_phone_field(self):
        assert not hasattr(Student, "phone"), "Student should NOT have 'phone' column"

    def test_is_activated_defaults_false(self):
        col = Student.__table__.c.is_activated
        assert col.server_default.arg == "0"


class TestParentModel:
    def test_no_phone_field(self):
        assert not hasattr(Parent, "phone"), "Parent should NOT have 'phone' column"


class TestTeacherApplicationModel:
    def test_password_hash_exists(self):
        assert hasattr(TeacherApplication, "password_hash"), (
            "TeacherApplication should have 'password_hash'"
        )

    def test_school_id_exists(self):
        assert hasattr(TeacherApplication, "school_id"), (
            "TeacherApplication should have 'school_id' FK"
        )


class TestStudentUniqueConstraint:
    def test_school_student_id_unique(self):
        from sqlalchemy import UniqueConstraint
        constraints = [
            c for c in Student.__table__.constraints
            if isinstance(c, UniqueConstraint)
        ]
        uq_names = {c.name for c in constraints}
        assert "uq_student_school_student_id" in uq_names, (
            "Student must have UniqueConstraint(school_id, student_id)"
        )
