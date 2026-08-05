"""Teaching API router — 考试/题目/作答/出题/批改。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, require_permission, UserContext, get_pagination_params
from ...services.teaching_service import TeachingService, TeachingError
from ...schemas.teaching import (
    ExamCreate, QuestionCreate, PracticeSubmitRequest, GradingRunRequest,
    ExamQuestionAssociateResponse, ExamPublishResponse, ExamFinalizeResponse,
    ExamQuestionsResponse, QuestionImportResponse, QuestionGenerateResponse,
    QuestionGenerateRequest,
)
from ...schemas.base import PaginatedResponse

router = APIRouter(prefix="", tags=["teaching"])


# ═══════════════════════════════════════════════════
# Exams
# ═══════════════════════════════════════════════════

@router.post("/exams", status_code=status.HTTP_201_CREATED)
async def create_exam(
    data: ExamCreate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("exam", "create")),
):
    return await TeachingService.create_exam(db, data)


@router.get("/exams")
async def list_exams(
    class_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    items, total = await TeachingService.list_exams_by_class(
        db, class_id=class_id,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(items=items, total=total,
                             limit=pagination["limit"], offset=pagination["offset"])


@router.get("/exams/{exam_id}")
async def get_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    try:
        return await TeachingService.get_exam(db, exam_id)
    except TeachingError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.patch("/exams/{exam_id}")
async def update_exam(
    exam_id: int,
    name: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("exam", "create")),
):
    try:
        return await TeachingService.update_exam(db, exam_id, name)
    except TeachingError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.delete("/exams/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("exam", "create")),
):
    try:
        await TeachingService.delete_exam(db, exam_id)
    except TeachingError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ═══════════════════════════════════════════════════
# 考试-题目关联（25号 §六.2 / §六.4）
# ═══════════════════════════════════════════════════

from ...services.exam_management_service import ExamManagementService, ExamManagementError


@router.post("/exams/{exam_id}/questions", response_model=ExamQuestionAssociateResponse)
async def add_questions_to_exam(
    exam_id: int,
    question_ids: list[int] = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("exam", "create")),
):
    """添加题目到考试（双渠道：已有题目 + 历史真题复制）。"""
    try:
        result = await ExamManagementService.add_questions_to_exam(
            db, exam_id, question_ids,
        )
        return {"success": True, **result}
    except ExamManagementError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)


@router.get("/exams/{exam_id}/questions", response_model=ExamQuestionsResponse)
async def get_exam_questions(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取考试当前题目列表。"""
    questions = await ExamManagementService.get_exam_questions(db, exam_id)
    return {"success": True, "questions": questions}


@router.delete("/exams/{exam_id}/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_question_from_exam(
    exam_id: int,
    question_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("exam", "create")),
):
    """从考试中移除题目。"""
    try:
        await ExamManagementService.remove_question_from_exam(db, exam_id, question_id)
    except ExamManagementError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.post("/exams/{exam_id}/publish", response_model=ExamPublishResponse)
async def publish_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("exam", "create")),
):
    """发布考试（验证≥1题 → 更新状态 → 统计学生数）。"""
    try:
        return await ExamManagementService.publish_exam(db, exam_id)
    except ExamManagementError as e:
        code = status.HTTP_400_BAD_REQUEST if e.error_code == "VALIDATION_ERROR" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=code, detail=e.detail)


@router.post("/exams/{exam_id}/finalize", response_model=ExamFinalizeResponse)
async def finalize_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("exam", "create")),
):
    """完成考试（统计分数）。"""
    try:
        return await ExamManagementService.finalize_exam(db, exam_id)
    except ExamManagementError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ═══════════════════════════════════════════════════
# Mode 2: 手动录入题目（25号 §三 Mode2）
# ═══════════════════════════════════════════════════

class ImportQuestionItem(BaseModel):
    content: str
    question_type: str = "choice"
    options: list | None = None
    answer: str
    analysis: str | None = None
    knowledge_point_tags: list | None = None
    difficulty: str = "medium"


class ImportQuestionsRequest(BaseModel):
    source_name: str = ""
    questions: list[ImportQuestionItem]


@router.post("/questions/import", response_model=QuestionImportResponse,
             status_code=status.HTTP_201_CREATED)
async def import_questions(
    request: ImportQuestionsRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("question", "create")),
):
    """批量导入题目（手动录入/OCR确认后）。

    Request body:
      {
        "source_name": "2024年长沙市一模",
        "questions": [
          {
            "content": "题目正文...",
            "question_type": "choice",
            "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
            "answer": "D",
            "analysis": "解析...",
            "knowledge_point_tags": ["氧化还原"],
            "difficulty": "medium"
          }
        ]
      }
    """
    questions_data = [q.model_dump() for q in request.questions]
    created = await ExamManagementService.import_questions(
        db, questions_data, source_name=request.source_name,
    )
    return {"success": True, "imported_count": len(created), "questions": created}


# ═══════════════════════════════════════════════════
# Exam Answers
# ═══════════════════════════════════════════════════

@router.get("/exams/{exam_id}/answers")
async def list_answers_by_exam(
    exam_id: int,
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    items, total = await TeachingService.list_answers_by_exam(
        db, exam_id,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(items=items, total=total,
                             limit=pagination["limit"], offset=pagination["offset"])


# ═══════════════════════════════════════════════════
# Questions
# ═══════════════════════════════════════════════════

@router.post("/questions", status_code=status.HTTP_201_CREATED)
async def create_question(
    data: QuestionCreate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("question", "create")),
):
    return await TeachingService.create_question(db, data)


@router.get("/questions")
async def list_questions(
    difficulty: str | None = Query(None),
    question_type: str | None = Query(None),
    knowledge_point: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    items, total = await TeachingService.list_questions(
        db, difficulty=difficulty, question_type=question_type,
        knowledge_point=knowledge_point,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(items=items, total=total,
                             limit=pagination["limit"], offset=pagination["offset"])


@router.get("/questions/{question_id}")
async def get_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    try:
        return await TeachingService.get_question(db, question_id)
    except TeachingError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.patch("/questions/{question_id}")
async def update_question(
    question_id: int,
    content: str | None = Query(None),
    answer: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("question", "create")),
):
    try:
        return await TeachingService.update_question(db, question_id, content=content, answer=answer)
    except TeachingError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("question", "create")),
):
    try:
        await TeachingService.delete_question(db, question_id)
    except TeachingError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ═══════════════════════════════════════════════════
# AI Generate（25号 §三：完整出题管线）
# ═══════════════════════════════════════════════════

from ...services.question_generation_service import generate_questions as _generate


@router.post("/questions/generate", response_model=QuestionGenerateResponse)
async def generate_questions(
    request: QuestionGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("question", "create")),
):
    """AI 出题：RAG检索 → LLM生成 → JSON解析 → 四维审核 → 持久化。

    请求体 (JSON):
      - knowledge_points: 知识点列表（必填）
      - difficulty: 难度 (easy/medium/hard)，默认 medium
      - quantity: 生成数量 (1-20)，默认 3
      - question_types: 题型列表 (choice/fill_blank/calculation/experiment_inquiry/equation_balancing)
      - variant_qid: 可选变体蓝本题 ID
    """
    return await _generate(
        db,
        knowledge_points=request.knowledge_points,
        difficulty=request.difficulty,
        quantity=request.quantity,
        question_types=request.question_types or ["choice"],
        variant_qid=request.variant_qid,
    )


# ═══════════════════════════════════════════════════
# Practice Submit
# ═══════════════════════════════════════════════════

@router.post("/practice/submit")
async def submit_practice(
    request: PracticeSubmitRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    try:
        return await TeachingService.submit_answer(
            db, request.student_id, request.question_id, request.answer_content,
        )
    except TeachingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)


# ═══════════════════════════════════════════════════
# Grading Run (stub)
# ═══════════════════════════════════════════════════

@router.post("/grading/run")
async def trigger_grading(
    request: GradingRunRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("grading", "create")),
):
    return await TeachingService.trigger_grading_stub(request.exam_id, request.class_id)


# ═══════════════════════════════════════════════════
# Student Answers
# ═══════════════════════════════════════════════════

@router.get("/students/{student_id}/answers")
async def list_answers_by_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    items, total = await TeachingService.list_answers_by_student(
        db, student_id,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(items=items, total=total,
                             limit=pagination["limit"], offset=pagination["offset"])
