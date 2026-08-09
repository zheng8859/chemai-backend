"""OCR service — 上传会话/OCR 任务/学生提交记录管理。"""

import asyncio
import uuid
import logging
from datetime import datetime, timezone, date
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from fastapi import UploadFile

from ..core.enums import UploadSessionStatus, OCRTaskStatus
from ..models.ocr import UploadSession, StudentSubmission, OCRTask
from ..models.teaching import ExamRecord
from ..schemas.ocr import (
    UploadSessionRead, OCRTaskRead, StudentSubmissionRead,
)
from ..config import (
    OCR_UPLOAD_DIR, OCR_MAX_FILE_SIZE_MB, OCR_MAX_BATCH_SIZE,
    OCR_ALLOWED_EXTENSIONS, OCR_ALLOWED_MIME_TYPES,
)

logger = logging.getLogger(__name__)

# ── 4.4: 百度 API 并发控制 ──
_baidu_semaphore = asyncio.Semaphore(5)


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
    # Batch Upload
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _validate_file(file: UploadFile) -> tuple[str, str]:
        """校验单个文件：MIME 类型、扩展名、大小。返回 (error_code, detail) 或 ("", "")."""
        # 检查 MIME 类型
        if file.content_type and file.content_type not in OCR_ALLOWED_MIME_TYPES:
            return "UNSUPPORTED_TYPE", f"不支持的文件类型: {file.content_type}"

        # 检查扩展名
        if file.filename:
            ext = Path(file.filename).suffix.lower()
            if ext not in OCR_ALLOWED_EXTENSIONS:
                return "UNSUPPORTED_TYPE", f"不支持的文件扩展名: {ext}"

        return "", ""

    @staticmethod
    async def _check_file_size(file: UploadFile) -> tuple[str, str, bytes]:
        """读取文件内容并检查大小。返回 (error_code, detail, content)。成功时 error_code=""。"""
        content = await file.read()
        if len(content) > OCR_MAX_FILE_SIZE_MB * 1024 * 1024:
            return "FILE_TOO_LARGE", f"文件大小超过 {OCR_MAX_FILE_SIZE_MB}MB 限制", b""
        return "", "", content

    @staticmethod
    def _save_file(content: bytes, teacher_id: int, original_filename: str) -> tuple[str, str, str]:
        """保存文件到磁盘，返回 (relative_path, detected_type, mime_type)。"""
        ext = Path(original_filename).suffix.lower()
        unique_name = f"{uuid.uuid4().hex}{ext}"
        today = date.today().isoformat()
        rel_dir = Path(str(teacher_id)) / today
        abs_dir = OCR_UPLOAD_DIR / rel_dir
        abs_dir.mkdir(parents=True, exist_ok=True)

        file_path = abs_dir / unique_name
        file_path.write_bytes(content)

        relative_path = str(rel_dir / unique_name).replace("\\", "/")

        # 判断文件类型
        if ext == ".pdf":
            detected_type = "PDF"
        else:
            detected_type = "IMAGE"

        # MIME 类型
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".bmp": "image/bmp",
            ".webp": "image/webp", ".pdf": "application/pdf",
        }
        mime_type = mime_map.get(ext, "application/octet-stream")

        return relative_path, detected_type, mime_type

    @staticmethod
    async def batch_upload(
        db: AsyncSession,
        files: list[UploadFile],
        teacher_id: int,
        class_id: int,
        exam_name: str = "",
        exam_paper_id: int | None = None,
    ) -> dict:
        """批量上传答题卡：校验 → 写磁盘 → 创建 UploadSession + OCRTask → 自动创建 ExamRecord。"""
        # 2.4: 批量大小校验
        if len(files) == 0:
            raise OCRError("至少需要上传一个文件", error_code="EMPTY_BATCH")
        if len(files) > OCR_MAX_BATCH_SIZE:
            raise OCRError(
                f"单次最多上传 {OCR_MAX_BATCH_SIZE} 个文件",
                error_code="BATCH_TOO_LARGE",
            )

        # 预校验 MIME/扩展名 + 读取内容 + 大小检查
        file_data: list[tuple[UploadFile, str, str, bytes]] = []  # (file, rel_path, detected_type, mime_type, content)
        for f in files:
            err_code, detail = OCRService._validate_file(f)
            if err_code:
                raise OCRError(detail, error_code=err_code)

            err_code, detail, content = await OCRService._check_file_size(f)
            if err_code:
                raise OCRError(detail, error_code=err_code)

            rel_path, detected_type, mime_type = OCRService._save_file(
                content, teacher_id, f.filename or "unknown",
            )
            file_data.append((f, rel_path, detected_type, mime_type))

        # 2.3: 创建 UploadSession
        first_file = file_data[0]
        session = UploadSession(
            teacher_id=teacher_id,
            status=UploadSessionStatus.uploaded,
            original_filename=first_file[0].filename or "",
            mime_type=first_file[3],
            file_path=first_file[1],
            detected_type=first_file[2],
            total_pages=len(file_data),
        )
        db.add(session)
        await db.flush()

        # 为每个文件创建 OCRTask
        tasks = []
        for f, rel_path, detected_type, _ in file_data:
            task = OCRTask(
                upload_session_id=session.id,
                teacher_id=teacher_id,
                image_path=rel_path,
                title=f.filename or "未命名",
                status=OCRTaskStatus.pending,
            )
            db.add(task)
            await db.flush()
            tasks.append({
                "task_id": task.id,
                "student_name": f.filename or "未知",
                "status": "pending",
            })

        # 自动创建 ExamRecord
        exam_record = ExamRecord(
            name=exam_name or f"OCR上传-{date.today().isoformat()}",
            class_id=class_id,
            exam_type="practice",
            exam_date=datetime.now(timezone.utc),
            status="grading",
        )
        if exam_paper_id:
            exam_record.exam_paper_id = exam_paper_id
        db.add(exam_record)
        await db.flush()

        # 在 session 的 JSON 字段中记录 exam_record_id，供后续状态流转使用
        session.ocr_result_json = {"exam_record_id": exam_record.id}

        await db.commit()

        return {
            "success": True,
            "batch_id": str(uuid.uuid4()),
            "session_id": session.id,
            "total": len(tasks),
            "tasks": tasks,
        }

    # ═══════════════════════════════════════════════════════════
    # 4.2-4.4: 调度器 OCR 任务处理
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    async def claim_next_pending_tasks(
        db: AsyncSession, limit: int = 5,
    ) -> list[OCRTask]:
        """4.2: 拾取最多 limit 个 pending 任务，更新为 processing。"""
        result = await db.execute(
            select(OCRTask)
            .where(OCRTask.status == OCRTaskStatus.pending)
            .order_by(OCRTask.created_at.asc())
            .limit(limit)
        )
        tasks = result.scalars().all()

        if not tasks:
            return []

        # 批量更新状态
        task_ids = [t.id for t in tasks]
        await db.execute(
            update(OCRTask)
            .where(OCRTask.id.in_(task_ids))
            .values(status=OCRTaskStatus.processing, progress=10)
        )
        await db.commit()

        # 重新刷新 task 对象
        refreshed = []
        for task in tasks:
            await db.refresh(task)
            refreshed.append(task)

        logger.info("[ocr_service] 拾取 %d 个 pending 任务", len(refreshed))
        return refreshed

    @staticmethod
    async def process_ocr_task(task: OCRTask) -> None:
        """7.8: 调用 EngineRouter.route() 使用最优引擎识别答题卡。"""
        from ..infrastructure.database import MainSession
        from .ocr_engine import EngineRouter

        # 4.4: Semaphore 控制并发
        async with _baidu_semaphore:
            logger.info("[ocr_service] 开始处理 task_id=%d, image=%s", task.id, task.image_path)

            # 推断文件类型
            ext = Path(task.image_path).suffix.lower()
            detected_type = "PDF" if ext == ".pdf" else "IMAGE"

            # 7.8: 通过 EngineRouter 路由到最优引擎
            result = await EngineRouter.route(task.image_path, detected_type)

            # 写入结果
            async with MainSession() as db:
                stmt = (
                    update(OCRTask)
                    .where(OCRTask.id == task.id)
                )

                if result.error and not result.raw_text:
                    # 完全失败
                    await db.execute(
                        stmt.values(
                            status=OCRTaskStatus.failed,
                            error_message=result.error,
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                else:
                    # 成功或部分成功（含 fallback 路径）
                    is_fallback = "fallback_used" in (result.error or "")
                    await db.execute(
                        stmt.values(
                            status=OCRTaskStatus.done,
                            progress=100,
                            ocr_raw_result={
                                "raw_text": result.raw_text,
                                "confidence": result.confidence,
                                "words_result": result.words_result,
                                "engine": result.engine,
                                "fallback_used": is_fallback,
                            },
                            student_id_raw=result.student_id_raw,
                            student_name_raw=result.student_name_raw,
                            error_message=result.error if result.is_partial else None,
                            completed_at=datetime.now(timezone.utc),
                        )
                    )

                await db.commit()
                logger.info(
                    "[ocr_service] task_id=%d 完成, status=%s, is_partial=%s",
                    task.id,
                    "done" if not (result.error and not result.raw_text) else "failed",
                    result.is_partial,
                )

    @staticmethod
    async def process_pending_tasks(db: AsyncSession) -> dict:
        """4.1: 调度器入口 — 拾取并发射 OCR 任务。"""
        tasks = await OCRService.claim_next_pending_tasks(db, limit=5)

        if not tasks:
            return {"processed": 0}

        # 4.4: asyncio.create_task 发射，不阻塞下次 tick
        for task in tasks:
            asyncio.create_task(OCRService.process_ocr_task(task))

        return {"processed": len(tasks)}

    # ── 兼容旧接口（保留 stub 以备过渡） ──
    @staticmethod
    async def batch_upload_stub(
        db: AsyncSession, teacher_id: int, class_id: int, exam_name: str,
    ) -> dict:
        """批量上传 stub — 创建会话和占位 OCR 任务。"""
        session = UploadSession(teacher_id=teacher_id, status=UploadSessionStatus.uploaded)
        db.add(session)
        await db.flush()

        tasks = []
        for i in range(3):
            task = OCRTask(
                upload_session_id=session.id,
                teacher_id=teacher_id,
                image_path="",
                title=f"答题卡_{i+1}",
            )
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
