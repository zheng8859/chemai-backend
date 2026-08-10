"""模型 __repr__ 覆盖 — 补全 12 个未覆盖的 repr 方法。"""

import pytest
from datetime import datetime

from app.core.enums import (
    BarrierType, Difficulty, QuestionSource, AuditStatus,
    ExamType, ExamRecordStatus, PracticeSessionStatus,
    ReviewTaskStatus,
)
from app.models.org import School, Grade, Class
from app.models.teaching import PracticeSession, ExamRecord
from app.models.diagnosis import BarrierConfig, ReviewTask
from app.models.exam_paper import ExamPaper, ExamPaperQuestion
from app.models.homework import StudentParentBinding

NOW = datetime(2026, 8, 1, 12, 0, 0)


class TestOrgRepr:
    def test_school_repr(self):
        s = School(id=1, name="北京一中")
        r = repr(s)
        assert "School" in r and "北京一中" in r

    def test_grade_repr(self):
        g = Grade(id=1, name="高一", school_id=1)
        r = repr(g)
        assert "Grade" in r and "高一" in r

    def test_class_repr(self):
        c = Class(id=1, name="高一(3)班", grade_id=1)
        r = repr(c)
        assert "Class" in r and "高一(3)班" in r


class TestTeachingRepr:
    def test_practice_session_repr(self):
        ps = PracticeSession(id=1, student_id=1,
                             status=PracticeSessionStatus.in_progress)
        r = repr(ps)
        assert "PracticeSession" in r

    def test_exam_record_repr(self):
        er = ExamRecord(id=1, exam_type=ExamType.monthly, class_id=1,
                        status=ExamRecordStatus.pending, exam_date=NOW)
        r = repr(er)
        assert "ExamRecord" in r


class TestDiagnosisRepr:
    def test_barrier_config_repr(self):
        bc = BarrierConfig(id=1, teacher_id=1)
        r = repr(bc)
        assert "BarrierConfig" in r

    def test_review_task_repr(self):
        rt = ReviewTask(id=1, student_id=1, question_id=1, level=1,
                        status=ReviewTaskStatus.pending,
                        next_review_date=NOW)
        r = repr(rt)
        assert "ReviewTask" in r


class TestExamPaperRepr:
    def test_exam_paper_repr(self):
        ep = ExamPaper(id=1, name="期中考试",
                       status="draft", teacher_id=1)
        r = repr(ep)
        assert "ExamPaper" in r and "期中考试" in r

    def test_exam_paper_question_repr(self):
        epq = ExamPaperQuestion(id=1, exam_paper_id=1, question_id=100, sort_order=0)
        r = repr(epq)
        assert "ExamPaperQuestion" in r


class TestHomeworkRepr:
    def test_binding_repr(self):
        from app.core.enums import BindingStatus, ParentRelation
        b = StudentParentBinding(id=1, student_id=1, parent_id=2,
                                 status=BindingStatus.active,
                                 relation=ParentRelation.father)
        r = repr(b)
        assert "StudentParentBinding" in r
