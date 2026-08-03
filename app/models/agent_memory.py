"""Agent 记忆模型：ConversationCheckpoint, LongTermMemory。

支撑 Agent 对话系统（34号 §七）：
- ConversationCheckpoint：单次对话状态快照，支撑中断恢复和多轮对话
- LongTermMemory：跨对话持久化信息（学生诊断历史 + 教师偏好）
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Integer, ForeignKey, JSON, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import MemoryType, ApprovalStatus
from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import Student, Teacher


class ConversationCheckpoint(Base, TimestampMixin):
    """对话检查点 — 单次对话的状态快照（34号 §七.1）。

    支撑三个核心场景：
    - 多轮对话中正确引用前几轮内容
    - 教师审批中断后恢复对话（不丢失上下文）
    - 对话异常时回退到上一个正常状态
    """

    __tablename__ = "conversation_checkpoint"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="对话线程 ID，如 conv_abc123"
    )
    student_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("student.id", ondelete="SET NULL"), comment="关联学生（如有）"
    )
    checkpoint_data: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="检查点数据：消息历史 + Agent 状态"
    )

    def __repr__(self) -> str:
        return f"<ConversationCheckpoint id={self.id} thread_id='{self.thread_id}'>"


class LongTermMemory(Base, TimestampMixin):
    """长期记忆 — 跨对话持久化信息（34号 §七.2）。

    不因对话结束而清空。每次新对话开始时自动加载。
    两类记忆：
    - student_diagnosis_history：学生障碍类型变化轨迹、历次正确率
    - teacher_preference：教师常用知识点、出题习惯
    """

    __tablename__ = "long_term_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("student.id", ondelete="CASCADE"), comment="关联学生"
    )
    teacher_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("teacher.id", ondelete="CASCADE"), comment="关联教师"
    )
    memory_type: Mapped[MemoryType] = mapped_column(
        String(50), nullable=False, comment="记忆类型"
    )
    content: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="记忆内容 JSON"
    )

    # ── 关系 ──
    student: Mapped[Optional["Student"]] = relationship(
        "Student", foreign_keys=[student_id], back_populates="long_term_memories"
    )
    teacher: Mapped[Optional["Teacher"]] = relationship(
        "Teacher", foreign_keys=[teacher_id]
    )

    def __repr__(self) -> str:
        return f"<LongTermMemory id={self.id} type={self.memory_type}>"


class ApprovalRequest(Base, TimestampMixin):
    """审批请求 — Agent 破坏性操作的审批门控记录。

    Agent 执行到需要审批的操作时创建此记录并挂起。
    教师显式批准或拒绝后执行对应动作。
    超时后自动过期，操作永不执行。
    """

    __tablename__ = "approval_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="对话线程 ID"
    )
    tool_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="触发审批的 tool 名称"
    )
    tool_params: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="冻结时的参数快照"
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        String(20), default=ApprovalStatus.pending,
        server_default="'pending'", nullable=False,
        comment="审批状态：pending / approved / rejected / expired",
    )
    requested_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("teacher.id", ondelete="CASCADE"), nullable=False, comment="Agent 代表的教师"
    )
    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("teacher.id", ondelete="SET NULL"), comment="审批教师"
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="审批时间"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="超时时间（超时后自动 expired）"
    )

    # ── 关系 ──
    requested_teacher: Mapped["Teacher"] = relationship(
        "Teacher", foreign_keys=[requested_by]
    )
    approved_teacher: Mapped[Optional["Teacher"]] = relationship(
        "Teacher", foreign_keys=[approved_by]
    )

    def __repr__(self) -> str:
        return f"<ApprovalRequest id={self.id} tool='{self.tool_name}' status={self.status}>"
