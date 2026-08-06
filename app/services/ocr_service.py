"""OCR service — 上传会话/OCR 任务/学生提交记录管理。"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..core.enums import UploadSessionStatus, OCRTaskStatus
from ..models.ocr import UploadSession, StudentSubmission, OCRTask
from ..schemas.ocr import (
    UploadSessionRead, OCRTaskRead, StudentSubmissionRead,
)


class OCRError(Exception):
    def __init__(self, detail: str, error_code: str = "RESOURCE_NOT_FOUND"):
        self.detail = detail
        self.error_code = error_code
        super().__init__(detail)


class OCRService:

    # ═══════════════════════════════════════════════════════════
    # Upload Sessions
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def create_upload_session(
        db: AsyncSession, teacher_id: int,
    ) -> UploadSessionRead:
        session = UploadSession(teacher_id=teacher_id)
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return UploadSessionRead.model_validate(session)

    @staticmethod
    async def get_session(db: AsyncSession, session_id: int) -> UploadSessionRead:
        result = await db.execute(
            select(UploadSession).where(UploadSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise OCRError(f"上传会话不存在: id={session_id}")
        return UploadSessionRead.model_validate(session)

    @staticmethod
    async def list_sessions_by_teacher(
        db: AsyncSession, teacher_id: int,
        limit: int = 20, offset: int = 0,
    ) -> tuple[list[UploadSessionRead], int]:
        total = (await db.execute(
            select(func.count(UploadSession.id)).where(
                UploadSession.teacher_id == teacher_id,
            )
        )).scalar() or 0
        result = await db.execute(
            select(UploadSession)
            .where(UploadSession.teacher_id == teacher_id)
            .order_by(UploadSession.created_at.desc())
            .offset(offset).limit(limit)
        )
        return [UploadSessionRead.model_validate(s) for s in result.scalars().all()], total

    # ═══════════════════════════════════════════════════════════
    # OCR Tasks
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def list_tasks_by_session(
        db: AsyncSession, session_id: int,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[OCRTaskRead], int]:
        total = (await db.execute(
            select(func.count(OCRTask.id)).where(
                OCRTask.upload_session_id == session_id,
            )
        )).scalar() or 0
        result = await db.execute(
            select(OCRTask)
            .where(OCRTask.upload_session_id == session_id)
            .order_by(OCRTask.created_at.desc())
            .offset(offset).limit(limit)
        )
        return [OCRTaskRead.model_validate(t) for t in result.scalars().all()], total

    @staticmethod
    async def get_task(db: AsyncSession, task_id: int) -> OCRTaskRead:
        result = await db.execute(select(OCRTask).where(OCRTask.id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            raise OCRError(f"OCR 任务不存在: id={task_id}")
        return OCRTaskRead.model_validate(task)

    # ═══════════════════════════════════════════════════════════
    # Student Submissions
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def list_submissions_by_exam(
        db: AsyncSession, exam_id: int,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[StudentSubmissionRead], int]:
        total = (await db.execute(
            select(func.count(StudentSubmission.id)).where(
                StudentSubmission.exam_record_id == exam_id,
            )
        )).scalar() or 0
        result = await db.execute(
            select(StudentSubmission)
            .where(StudentSubmission.exam_record_id == exam_id)
            .order_by(StudentSubmission.submitted_at.desc())
            .offset(offset).limit(limit)
        )
        return [StudentSubmissionRead.model_validate(s) for s in result.scalars().all()], total

    @staticmethod
    async def get_submission(
        db: AsyncSession, submission_id: int,
    ) -> StudentSubmissionRead:
        result = await db.execute(
            select(StudentSubmission).where(StudentSubmission.id == submission_id)
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            raise OCRError(f"提交记录不存在: id={submission_id}")
        return StudentSubmissionRead.model_validate(sub)

    # ═══════════════════════════════════════════════════════════
    # Batch Upload (stub)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def batch_upload_stub(
        db: AsyncSession, teacher_id: int, class_id: int, exam_name: str,
    ) -> dict:
        """批量上传 stub — 创建会话和占位 OCR 任务。"""
        import uuid

        session = UploadSession(teacher_id=teacher_id, status=UploadSessionStatus.uploaded)
        db.add(session)
        await db.flush()

        # Create placeholder tasks
        tasks = []
        for i in range(3):  # placeholder: 3 tasks
            task = OCRTask(upload_session_id=session.id)
            db.add(task)
            await db.flush()
            tasks.append({"task_id": task.id, "student_name": f"学生{i+1}", "status": "pending"})

        await db.commit()
        return {
            "success": True,
            "batch_id": str(uuid.uuid4()),
            "total": len(tasks),
            "tasks": tasks,
        }
