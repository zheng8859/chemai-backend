"""ChemAI 数据模型 — 25 个 SQLAlchemy 实体。

模型按领域拆分：
- base.py       : declarative_base + TimestampMixin
- org.py        : School, Grade, Class（组织链）
- user.py       : Account, Teacher, Student, Parent, TeacherClassSubject, TeacherApplication（身份链）
- teaching.py   : ExamRecord, Question, StudentAnswer（教学链）
- exam_paper.py : ExamPaper, ExamPaperQuestion（试卷模板+考试执行）
- diagnosis.py  : BarrierConfig, KnowledgePoint, ReviewTask, ReviewHistory, WarningLog（诊断与学习）
- homework.py   : StudentParentBinding, ParentNotification, WeeklyReport（家校互通）
- notification.py : Notification（学生消息通知）
- ocr.py        : UploadSession, StudentSubmission, OCRTask（OCR 批改）
- question_bank.py : QuestionSet, QuestionSetItem, HistoricalExam（题库）
- agent_memory.py : ConversationCheckpoint, LongTermMemory（Agent 记忆）
- learning_plan.py : LearningPlan, LearningPlanTask（学习计划）
"""

from .base import Base, TimestampMixin

# 组织链
from .org import School, Grade, Class

# 身份链
from .user import (
    Account,
    Teacher,
    Student,
    Parent,
    TeacherClassSubject,
    TeacherApplication,
)

# 教学链
from .teaching import ExamRecord, Question, StudentAnswer, PracticeSession, PracticeSessionQuestion

# 试卷模板
from .exam_paper import ExamPaper, ExamPaperQuestion

# 诊断与学习
from .diagnosis import (
    BarrierConfig,
    KnowledgePoint,
    ReviewTask,
    ReviewHistory,
    VariantQuestion,
    WarningLog,
)
from .barrier_profile_history import BarrierProfileHistory

# 家校互通
from .homework import StudentParentBinding, ParentNotification, WeeklyReport

# OCR 批改
from .ocr import UploadSession, StudentSubmission, OCRTask

# 题库
from .question_bank import QuestionSet, QuestionSetItem, HistoricalExam

# Agent 记忆
from .agent_memory import ConversationCheckpoint, LongTermMemory, ApprovalRequest

# 学习计划
from .learning_plan import LearningPlan, LearningPlanTask

# 消息通知
from .notification import Notification

__all__ = [
    # base
    "Base",
    "TimestampMixin",
    # org
    "School",
    "Grade",
    "Class",
    # user
    "Account",
    "Teacher",
    "Student",
    "Parent",
    "TeacherClassSubject",
    "TeacherApplication",
    # teaching
    "ExamRecord",
    "Question",
    "StudentAnswer",
    "PracticeSession",
    "PracticeSessionQuestion",
    # exam paper
    "ExamPaper",
    "ExamPaperQuestion",
    # diagnosis
    "BarrierConfig",
    "KnowledgePoint",
    "ReviewTask",
    "ReviewHistory",
    "VariantQuestion",
    "WarningLog",
    "BarrierProfileHistory",
    # homework
    "StudentParentBinding",
    "ParentNotification",
    "WeeklyReport",
    # ocr
    "UploadSession",
    "StudentSubmission",
    "OCRTask",
    # question bank
    "QuestionSet",
    "QuestionSetItem",
    "HistoricalExam",
    # agent memory
    "ConversationCheckpoint",
    "LongTermMemory",
    "ApprovalRequest",
    # learning plan
    "LearningPlan",
    "LearningPlanTask",
    # notification
    "Notification",
]
