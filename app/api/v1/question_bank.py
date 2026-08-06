"""Question bank API router — 题库文件夹/题目集/历年真题。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import get_current_user, require_permission, UserContext, get_pagination_params
from ...services.question_bank_service import QuestionBankService, QuestionBankError
from ...schemas.question_bank import QuestionSetCreate, QuestionSetItemAdd
from ...schemas.base import PaginatedResponse

router = APIRouter(prefix="", tags=["question-bank"])


@router.post("/question-sets", status_code=status.HTTP_201_CREATED)
async def create_question_set(
    data: QuestionSetCreate,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("question", "create")),
):
    """创建题库文件夹。"""
    if data.teacher_id is None:
        data.teacher_id = user.user_id
    return await QuestionBankService.create_question_set(db, data)


@router.get("/question-sets")
async def list_question_sets(
    teacher_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    """获取题库文件夹列表。"""
    items, total = await QuestionBankService.list_question_sets(
        db, teacher_id=teacher_id,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(
        items=items, total=total,
        limit=pagination["limit"], offset=pagination["offset"],
    )


@router.patch("/question-sets/{set_id}")
async def update_question_set(
    set_id: int,
    name: str | None = Query(None),
    description: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("question", "create")),
):
    """更新题库文件夹。"""
    try:
        return await QuestionBankService.update_question_set(db, set_id, name, description)
    except QuestionBankError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.delete("/question-sets/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question_set(
    set_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("question", "create")),
):
    """删除题库文件夹。"""
    try:
        await QuestionBankService.delete_question_set(db, set_id)
    except QuestionBankError as e:
        code = status.HTTP_403_FORBIDDEN if getattr(e, 'error_code', '') == 'FORBIDDEN' else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=code, detail=e.detail)


@router.post("/question-sets/{set_id}/items", status_code=status.HTTP_201_CREATED)
async def add_item(
    data: QuestionSetItemAdd,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("question", "create")),
):
    """添加题目到题库文件夹。"""
    return await QuestionBankService.add_item(db, data)


@router.get("/question-sets/{set_id}/items")
async def list_items(
    set_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取题库文件夹中的题目列表。"""
    items = await QuestionBankService.list_items(db, set_id)
    return {"success": True, "data": items}


@router.patch("/question-sets/items/{item_id}/reorder")
async def reorder_item(
    item_id: int,
    new_order: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("question", "create")),
):
    """调整题目排序。"""
    try:
        return await QuestionBankService.reorder_item(db, item_id, new_order)
    except QuestionBankError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.delete("/question-sets/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_permission("question", "create")),
):
    """从题库文件夹中删除题目。"""
    try:
        await QuestionBankService.remove_item(db, item_id)
    except QuestionBankError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.get("/historical-exams")
async def list_historical_exams(
    source: str | None = Query(None),
    year: int | None = Query(None),
    difficulty: str | None = Query(None),
    knowledge_point: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    """获取历年真题列表（含多维筛选）。"""
    items, total = await QuestionBankService.list_historical_exams(
        db, source=source, year=year, difficulty=difficulty,
        knowledge_point=knowledge_point,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(
        items=items, total=total,
        limit=pagination["limit"], offset=pagination["offset"],
    )
