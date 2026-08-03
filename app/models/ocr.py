"""OCR 批改模型：UploadSession, StudentSubmission, OCRTask。

支撑答题卡 OCR 批改工具链（34号 §五）：
- 教师上传 → 创建 UploadSession
- 每张答题卡 → 一个 OCRTask（批改任务） + 一个 StudentSubmission（提交记录）
- 十步批改管线：上传→识别→提取→批改→确认→保存→诊断→统计→报告
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import UploadSessionStatus, OCRTaskStatus
from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import Teacher, Student
    from .teaching import ExamRecord
    from .org import Class


class UploadSession(Base, TimestampMixin):
    """上传会话 — 追踪单次批量上传的全生命周期（34号 §五.1）。

    状态机：uploaded → previewing → ready → importing → imported →
            grading → graded → done → discarded/error
    降级路径：OCR 引擎失败 → 降级标记 → VLM 重新识别 → done
    """

    __tablename__ = "upload_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teacher.id", ondelete="CASCADE"), nullable=False, comment="上传教师"
    )
    status: Mapped[UploadSessionStatus] = mapped_column(
        String(20), default=UploadSessionStatus.uploaded,
        server_default="'uploaded'", nullable=False, comment="会话状态"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="处理完成时间"
    )

    # ── 关系 ──
    teacher: Mapped["Teacher"] = relationship(back_populates="upload_sessions")
    ocr_tasks: Mapped[List["OCRTask"]] = relationship(back_populates="upload_session")

    def __repr__(self) -> str:
        return f"<UploadSession id={self.id} status={self.status}>"


class StudentSubmission(Base, TimestampMixin):
    """学生提交 — 一次考试中单个学生的答题卡提交记录（34号 §五.2）。"""

    __tablename__ = "student_submission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_record_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam_record.id", ondelete="CASCADE"), nullable=False, comment="所属考试"
    )
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), nullable=False, comment="学生"
    )
    class_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("class.id", ondelete="CASCADE"), nullable=False, comment="班级（冗余，加速查询）"
    )
    original_image: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="原始答题卡图片路径"
    )
    graded_image: Mapped[Optional[str]] = mapped_column(
        String(500), comment="批改后图片路径（含批注）"
    )
    answer_list: Mapped[Optional[list]] = mapped_column(
        JSON, comment="学生答案列表 JSON"
    )
    total_score: Mapped[Optional[float]] = mapped_column(Float, comment="总分")
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=datetime.utcnow, comment="提交时间"
    )
    graded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="批改完成时间"
    )

    # ── 关系 ──
    exam_record: Mapped["ExamRecord"] = relationship(back_populates="submissions")
    student: Mapped["Student"] = relationship(back_populates="submissions")

    def __repr__(self) -> str:
        return f"<StudentSubmission id={self.id} student_id={self.student_id}>"


class OCRTask(Base, TimestampMixin):
    """批改任务 — 单张答题卡的 OCR 识别与批改任务（34号 §五.3）。

    教师视角的操作单元：上传一批答题卡 → 为每张创建 OCRTask。
    存储 OCR 原始结果 + LLM 批改结果。
    """

    __tablename__ = "ocr_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    upload_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("upload_session.id", ondelete="CASCADE"), nullable=False, comment="所属上传会话"
    )
    status: Mapped[OCRTaskStatus] = mapped_column(
        String(20), default=OCRTaskStatus.pending,
        server_default="'pending'", nullable=False,
        comment="任务状态：pending / processing / done / failed",
    )
    ocr_raw_result: Mapped[Optional[dict]] = mapped_column(
        JSON, comment="OCR 原始识别结果"
    )
    grading_result: Mapped[Optional[dict]] = mapped_column(
        JSON, comment="批改结果：逐题判定 + 汇总统计"
    )

    # ── 关系 ──
    upload_session: Mapped["UploadSession"] = relationship(back_populates="ocr_tasks")

    def __repr__(self) -> str:
        return f"<OCRTask id={self.id} status={self.status}>"
