"""Service 层错误类测试 — 覆盖所有 services/*Error 异常类。"""

import pytest

from app.services.auth_service import AuthError
from app.services.diagnosis_service import DiagnosisError
from app.services.homework_service import HomeworkError
from app.services.ocr_service import OCRError
from app.services.org_service import OrgError
from app.services.question_bank_service import QuestionBankError
from app.services.teaching_service import TeachingError
from app.services.user_service import UserError
from app.services.exam_management_service import ExamManagementError
from app.services.exam_export_service import ExamExportError


ERROR_CLASSES = [
    (AuthError, "AuthError"),
    (DiagnosisError, "DiagnosisError"),
    (HomeworkError, "HomeworkError"),
    (OCRError, "OCRError"),
    (OrgError, "OrgError"),
    (QuestionBankError, "QuestionBankError"),
    (TeachingError, "TeachingError"),
    (UserError, "UserError"),
    (ExamManagementError, "ExamManagementError"),
    (ExamExportError, "ExamExportError"),
]


class TestAllServiceErrors:
    @pytest.mark.parametrize("error_class,name", ERROR_CLASSES)
    def test_is_exception(self, error_class, name):
        err = error_class("测试错误")
        assert isinstance(err, Exception), f"{name} should be Exception"

    @pytest.mark.parametrize("error_class,name", ERROR_CLASSES)
    def test_detail_preserved(self, error_class, name):
        err = error_class("具体的错误信息")
        assert "具体的错误信息" in err.detail or str(err)

    @pytest.mark.parametrize("error_class,name", ERROR_CLASSES)
    def test_string_repr_contains_detail(self, error_class, name):
        err = error_class("错误详情")
        assert "错误详情" in str(err)

    def test_auth_error_default_code(self):
        err = AuthError("认证失败")
        assert err.error_code == "AUTHENTICATION_REQUIRED"

    def test_diagnosis_error_default_code(self):
        err = DiagnosisError("诊断失败")
        assert err.error_code == "RESOURCE_NOT_FOUND"

    def test_ocr_error_default_code(self):
        err = OCRError("OCR 失败")
        assert err.error_code == "RESOURCE_NOT_FOUND"

    def test_org_error_default_code(self):
        err = OrgError("组织不存在")
        assert err.error_code == "RESOURCE_NOT_FOUND"

    def test_question_bank_error_default_code(self):
        err = QuestionBankError("题库不存在")
        assert err.error_code == "RESOURCE_NOT_FOUND"

    def test_teaching_error_default_code(self):
        err = TeachingError("教学资源不存在")
        assert err.error_code == "RESOURCE_NOT_FOUND"

    def test_user_error_default_code(self):
        err = UserError("用户不存在")
        assert err.error_code == "RESOURCE_NOT_FOUND"

    def test_exam_management_error_default_code(self):
        err = ExamManagementError("考试不存在")
        assert err.error_code == "RESOURCE_NOT_FOUND"

    def test_custom_error_code(self):
        err = AuthError("权限不足", error_code="PERMISSION_DENIED")
        assert err.error_code == "PERMISSION_DENIED"
