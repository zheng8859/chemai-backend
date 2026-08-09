"""模型属性测试 — 覆盖所有 __repr__、列默认值、约束。

验证 column metadata（default、server_default、unique、tablename），
不依赖数据库连接。
"""

from datetime import datetime

from app.core.enums import (
    AccountRole, TeacherRole, TeacherAccountStatus,
    StudentStatus, ParentRelation, BindingStatus,
    ApplicationStatus, ApprovalStatus,
    ExamPaperStatus, ExamRecordStatus,
    Difficulty, QuestionSource, AuditStatus,
    BarrierType, DiagnosisSource,
    MemoryType, NotificationType,
    WarningType, WarningSeverity,
    ReviewTaskStatus,
    PracticeSessionStatus,
    OCRTaskStatus, UploadSessionStatus,
)
from app.models.base import Base, TimestampMixin
from app.models.user import (
    Account, Teacher, Student, Parent,
    TeacherClassSubject, TeacherApplication,
)
from app.models.org import School, Grade, Class
from app.models.teaching import (
    PracticeSession, ExamRecord, Question, StudentAnswer,
)
from app.models.exam_paper import ExamPaper, ExamPaperQuestion
from app.models.diagnosis import (
    BarrierConfig, KnowledgePoint, ReviewTask, ReviewHistory, WarningLog,
)
from app.models.question_bank import QuestionSet, QuestionSetItem, HistoricalExam
from app.models.homework import (
    StudentParentBinding, ParentNotification,
)
from app.models.ocr import UploadSession, StudentSubmission, OCRTask
from app.models.agent_memory import (
    ConversationCheckpoint, LongTermMemory, ApprovalRequest,
)

NOW = datetime(2026, 8, 1, 12, 0, 0)

# ── 辅助函数：获取列 default 值 ──────────────────────────

def _col_default(model_class, col_name):
    """提取 mapped_column 的 Python-side default 值。"""
    col = model_class.__table__.c[col_name]
    if col.default and hasattr(col.default, 'arg'):
        return col.default.arg
    return None

def _server_default(model_class, col_name):
    """提取 server_default 的 SQL 文本（如果有）。"""
    col = model_class.__table__.c[col_name]
    if col.server_default and hasattr(col.server_default, 'arg'):
        return col.server_default.arg
    return None


# ═══════════════════════════════════════════════════════════
# user.py models
# ═══════════════════════════════════════════════════════════

class TestAccountModel:
    def test_repr(self):
        a = Account(id=1, phone="13800000000", password_hash="hash",
                    role=AccountRole.teacher)
        r = repr(a)
        assert "Account" in r and "13800000000" in r

    def test_tablename(self):
        assert Account.__tablename__ == "account"

    def test_phone_unique_indexed(self):
        c = Account.__table__.c.phone
        assert c.unique and c.index


class TestTeacherModel:
    def test_repr(self):
        t = Teacher(id=1, account_id=1, school_id=1, name="张老师",
                    status=TeacherAccountStatus.approved, role=TeacherRole.teacher)
        r = repr(t)
        assert "Teacher" in r and "张老师" in r

    def test_tablename(self):
        assert Teacher.__tablename__ == "teacher"

    def test_status_default(self):
        assert _col_default(Teacher, "status") == TeacherAccountStatus.pending
        assert _server_default(Teacher, "status") == "'pending'"

    def test_role_default(self):
        assert _col_default(Teacher, "role") == TeacherRole.teacher
        assert _server_default(Teacher, "role") == "'teacher'"


class TestStudentModel:
    def test_repr(self):
        s = Student(id=1, account_id=2, class_id=1, school_id=1,
                    name="小明", student_id="S001")
        r = repr(s)
        assert "Student" in r and "小明" in r

    def test_tablename(self):
        assert Student.__tablename__ == "student"

    def test_is_activated_default(self):
        assert _server_default(Student, "is_activated") == "0"

    def test_status_default(self):
        assert _col_default(Student, "status") == StudentStatus.approved

    def test_practice_count_default(self):
        assert _server_default(Student, "practice_count") == "0"

    def test_unique_constraint(self):
        from sqlalchemy import UniqueConstraint
        constraints = [c for c in Student.__table__.constraints
                       if isinstance(c, UniqueConstraint)]
        names = {c.name for c in constraints}
        assert "uq_student_school_student_id" in names


class TestParentModel:
    def test_repr(self):
        p = Parent(id=1, account_id=3, name="王爸爸")
        r = repr(p)
        assert "Parent" in r and "王爸爸" in r

    def test_tablename(self):
        assert Parent.__tablename__ == "parent"


class TestTeacherClassSubjectModel:
    def test_repr(self):
        tcs = TeacherClassSubject(id=1, teacher_id=1, class_id=1)
        r = repr(tcs)
        assert "TeacherClassSubject" in r

    def test_tablename(self):
        assert TeacherClassSubject.__tablename__ == "teacher_class_subject"

    def test_subject_default(self):
        assert _col_default(TeacherClassSubject, "subject") == "化学"

    def test_is_head_teacher_default(self):
        assert _server_default(TeacherClassSubject, "is_head_teacher") == "0"

    def test_unique_constraint(self):
        from sqlalchemy import UniqueConstraint
        constraints = [c for c in TeacherClassSubject.__table__.constraints
                       if isinstance(c, UniqueConstraint)]
        names = {c.name for c in constraints}
        assert "uq_tcs_teacher_class" in names


class TestTeacherApplicationModel:
    def test_repr(self):
        ta = TeacherApplication(id=1, name="李老师", phone="13900000000",
                                password_hash="hash", school_id=1, school_name="北京一中")
        r = repr(ta)
        assert "TeacherApplication" in r and "李老师" in r

    def test_tablename(self):
        assert TeacherApplication.__tablename__ == "teacher_application"

    def test_subject_default(self):
        assert _col_default(TeacherApplication, "subject") == "化学"

    def test_status_default(self):
        assert _col_default(TeacherApplication, "status") == ApplicationStatus.pending


# ═══════════════════════════════════════════════════════════
# org.py models
# ═══════════════════════════════════════════════════════════

class TestOrgModels:
    def test_school_tablename(self):
        assert School.__tablename__ == "school"

    def test_grade_tablename(self):
        assert Grade.__tablename__ == "grade"

    def test_class_tablename(self):
        assert Class.__tablename__ == "class"


# ═══════════════════════════════════════════════════════════
# teaching.py + exam_paper.py models
# ═══════════════════════════════════════════════════════════

class TestPracticeSessionModel:
    def test_tablename(self):
        assert PracticeSession.__tablename__ == "practice_session"

    def test_status_default(self):
        assert _col_default(PracticeSession, "status") == PracticeSessionStatus.in_progress

    def test_count_defaults(self):
        assert _server_default(PracticeSession, "questions_served") == "0"
        assert _server_default(PracticeSession, "questions_correct") == "0"


class TestExamPaperModel:
    def test_tablename(self):
        assert ExamPaper.__tablename__ == "exam_paper"

    def test_status_default(self):
        assert _col_default(ExamPaper, "status") == ExamPaperStatus.draft


class TestExamRecordModel:
    def test_tablename(self):
        assert ExamRecord.__tablename__ == "exam_record"

    def test_status_default(self):
        assert _col_default(ExamRecord, "status") == ExamRecordStatus.pending


class TestExamPaperQuestionModel:
    def test_tablename(self):
        assert ExamPaperQuestion.__tablename__ == "exam_paper_question"


class TestQuestionModel:
    def test_repr(self):
        q = Question(id=1, content="题目", answer="A",
                     difficulty=Difficulty.medium, source=QuestionSource.manual,
                     audit_status=AuditStatus.passed)
        r = repr(q)
        assert "Question" in r

    def test_tablename(self):
        assert Question.__tablename__ == "question"

    def test_type_default(self):
        assert _col_default(Question, "question_type") == "choice"

    def test_difficulty_default(self):
        assert _col_default(Question, "difficulty") == Difficulty.medium

    def test_source_default(self):
        assert _col_default(Question, "source") == QuestionSource.manual

    def test_audit_status_default(self):
        assert _col_default(Question, "audit_status") == AuditStatus.passed


class TestStudentAnswerModel:
    def test_repr(self):
        sa = StudentAnswer(id=1, student_id=1, question_id=1, exam_record_id=1,
                           answer_content="A", is_correct=True)
        r = repr(sa)
        assert "StudentAnswer" in r

    def test_tablename(self):
        assert StudentAnswer.__tablename__ == "student_answer"


# ═══════════════════════════════════════════════════════════
# diagnosis.py models
# ═══════════════════════════════════════════════════════════

class TestKnowledgePointModel:
    def test_repr(self):
        kp = KnowledgePoint(id=1, name="氧化还原反应")
        r = repr(kp)
        assert "KnowledgePoint" in r

    def test_tablename(self):
        assert KnowledgePoint.__tablename__ == "knowledge_point"


class TestBarrierConfigModel:
    def test_tablename(self):
        assert BarrierConfig.__tablename__ == "barrier_config"

    def test_threshold_defaults(self):
        assert _col_default(BarrierConfig, "concept_threshold") == 3
        assert _col_default(BarrierConfig, "reading_threshold") == 2
        assert _col_default(BarrierConfig, "expression_threshold") == 3
        assert _col_default(BarrierConfig, "mastery_threshold") == 3

    def test_auto_sync_default(self):
        assert _col_default(BarrierConfig, "auto_sync_enabled") is False


class TestReviewTaskModel:
    def test_tablename(self):
        assert ReviewTask.__tablename__ == "review_task"

    def test_status_default(self):
        assert _col_default(ReviewTask, "status") == ReviewTaskStatus.pending


class TestReviewHistoryModel:
    def test_repr(self):
        rh = ReviewHistory(id=1, review_task_id=1, level=2,
                           review_date=NOW, result=True)
        r = repr(rh)
        assert "ReviewHistory" in r

    def test_tablename(self):
        assert ReviewHistory.__tablename__ == "review_history"


class TestWarningLogModel:
    def test_repr(self):
        wl = WarningLog(id=1, student_id=1, warning_type=WarningType.score_drop,
                        severity=WarningSeverity.warning, message="成绩下滑")
        r = repr(wl)
        assert "WarningLog" in r

    def test_tablename(self):
        assert WarningLog.__tablename__ == "warning_log"

    def test_notified_defaults(self):
        assert _server_default(WarningLog, "notified_teacher") == "0"
        assert _server_default(WarningLog, "notified_parent") == "0"
        assert _server_default(WarningLog, "notified_student") == "0"


# ═══════════════════════════════════════════════════════════
# question_bank.py models
# ═══════════════════════════════════════════════════════════

class TestQuestionSetModel:
    def test_repr(self):
        qs = QuestionSet(id=1, teacher_id=1, name="氧化还原题库")
        r = repr(qs)
        assert "QuestionSet" in r

    def test_tablename(self):
        assert QuestionSet.__tablename__ == "question_set"

    def test_is_system_default(self):
        assert _server_default(QuestionSet, "is_system") == "0"


class TestQuestionSetItemModel:
    def test_repr(self):
        qsi = QuestionSetItem(id=1, question_set_id=1, question_id=100, sort_order=0)
        r = repr(qsi)
        assert "QuestionSetItem" in r

    def test_tablename(self):
        assert QuestionSetItem.__tablename__ == "question_set_item"


class TestHistoricalExamModel:
    def test_repr(self):
        he = HistoricalExam(id=1, source="全国卷", year=2023,
                            difficulty=Difficulty.medium, content="题目", answer="A")
        r = repr(he)
        assert "HistoricalExam" in r

    def test_tablename(self):
        assert HistoricalExam.__tablename__ == "historical_exam"


# ═══════════════════════════════════════════════════════════
# homework.py models
# ═══════════════════════════════════════════════════════════

class TestStudentParentBindingModel:
    def test_tablename(self):
        assert StudentParentBinding.__tablename__ == "student_parent_binding"

    def test_status_default(self):
        assert _col_default(StudentParentBinding, "status") == BindingStatus.active


class TestParentNotificationModel:
    def test_repr(self):
        pn = ParentNotification(id=1, parent_id=1,
                                notification_type=NotificationType.learning_report,
                                title="学习报告", body="内容", sent_at=NOW)
        r = repr(pn)
        assert "ParentNotification" in r

    def test_tablename(self):
        assert ParentNotification.__tablename__ == "parent_notification"

    def test_read_at_default(self):
        """read_at 默认为 None（无 server_default）。"""
        from app.models.homework import ParentNotification
        col = ParentNotification.__table__.c["read_at"]
        assert col.nullable is True


# ═══════════════════════════════════════════════════════════
# ocr.py models
# ═══════════════════════════════════════════════════════════

class TestUploadSessionModel:
    def test_repr(self):
        us = UploadSession(id=1, teacher_id=1, status=UploadSessionStatus.uploaded)
        r = repr(us)
        assert "UploadSession" in r

    def test_tablename(self):
        assert UploadSession.__tablename__ == "upload_session"


class TestStudentSubmissionModel:
    def test_repr(self):
        ss = StudentSubmission(id=1, exam_record_id=1, student_id=1, class_id=1,
                               original_image="/img/001.jpg", submitted_at=NOW)
        r = repr(ss)
        assert "StudentSubmission" in r

    def test_tablename(self):
        assert StudentSubmission.__tablename__ == "student_submission"


class TestOCRTaskModel:
    def test_repr(self):
        ot = OCRTask(id=1, upload_session_id=1, status=OCRTaskStatus.pending)
        r = repr(ot)
        assert "OCRTask" in r

    def test_tablename(self):
        assert OCRTask.__tablename__ == "ocr_task"


# ═══════════════════════════════════════════════════════════
# agent_memory.py models
# ═══════════════════════════════════════════════════════════

class TestConversationCheckpointModel:
    def test_repr(self):
        cc = ConversationCheckpoint(id=1, thread_id="thread-001",
                                    checkpoint_data={"messages": []})
        r = repr(cc)
        assert "ConversationCheckpoint" in r and "thread-001" in r

    def test_tablename(self):
        assert ConversationCheckpoint.__tablename__ == "conversation_checkpoint"


class TestLongTermMemoryModel:
    def test_repr(self):
        ltm = LongTermMemory(id=1, memory_type=MemoryType.student_diagnosis_history,
                             content={"barrier": "concept"})
        r = repr(ltm)
        assert "LongTermMemory" in r

    def test_tablename(self):
        assert LongTermMemory.__tablename__ == "long_term_memory"


class TestApprovalRequestModel:
    def test_repr(self):
        ar = ApprovalRequest(id=1, thread_id="thread-001",
                             tool_name="assign_practice",
                             tool_params={"student_id": 1}, requested_by=1)
        r = repr(ar)
        assert "ApprovalRequest" in r and "assign_practice" in r

    def test_tablename(self):
        assert ApprovalRequest.__tablename__ == "approval_request"

    def test_status_default(self):
        assert _col_default(ApprovalRequest, "status") == ApprovalStatus.pending
        assert _server_default(ApprovalRequest, "status") == "'pending'"


# ═══════════════════════════════════════════════════════════
# base.py
# ═══════════════════════════════════════════════════════════

class TestBaseAndMixin:
    def test_base_is_declarative(self):
        from sqlalchemy.orm import DeclarativeBase
        assert issubclass(Base, DeclarativeBase)

    def test_timestamp_mixin_has_columns(self):
        assert hasattr(TimestampMixin, "created_at")
        assert hasattr(TimestampMixin, "updated_at")
