"""Parent API router — 家长端 REST 端点（33号 §六, §八, §九）。

端点清单：
  POST   /bind-code/{student_id}   — 学生发送绑定码
  POST   /bind                      — 家长提交绑定
  GET    /children                  — 已绑定子女列表
  DELETE /bind/{binding_id}         — 解绑
  GET    /child/{student_id}/report     — 子女学习概览
  GET    /child/{student_id}/timeline   — 子女学习时间线
  GET    /child/{student_id}/weekly     — 当周周报（缓存）
  POST   /child/{student_id}/weekly/generate — 手动生成周报
  GET    /notifications                 — 通知列表
  PUT    /notifications/{id}/read       — 标记已读
  POST   /agent/chat                    — Agent SSE 流式对话
  GET    /agent/conversations           — 对话列表
  GET    /agent/history/{thread_id}     — 对话历史
  POST   /agent/new                     — 新建对话
  DELETE /agent/conversations/{thread_id} — 删除对话
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from ...infrastructure.database import get_db
from ...api.deps import (
    get_current_user,
    UserContext,
    get_pagination_params,
    require_student_self,
    require_parent_binding,
    resolve_student_id,
)
from ...services.parent_service import ParentService, ParentError
from ...services.weekly_report_service import WeeklyReportService
from ...schemas.parent import (
    BindCodeRequest,
    BindRequest,
    ChildOverviewResponse,
    ChildTimelineResponse,
    WeeklyReportResponse,
    ParentNotificationResponse,
    ParentAgentRequest,
)
from ...schemas.base import PaginatedResponse
from ...models.user import Parent, Student
from ...models.agent_memory import ConversationCheckpoint
from ...models.homework import StudentParentBinding
from ...llm.router import llm_chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parent", tags=["parent"])


# ── Helper: Account → Parent.id ─────────────────────────────

async def _resolve_parent_id(db: AsyncSession, user: UserContext) -> int:
    """由 JWT Account.id 反查 Parent.id。非家长角色返回 403。"""
    if user.role != "parent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅家长角色可访问",
        )
    from sqlalchemy import select
    result = await db.execute(
        select(Parent).where(Parent.account_id == user.user_id)
    )
    parent = result.scalar_one_or_none()
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="家长档案不存在",
        )
    return parent.id


# ══════════════════════════════════════════════════════════════
# 绑定码管理
# ══════════════════════════════════════════════════════════════

@router.post("/bind-code/{student_id}")
async def set_bind_code(
    student_id: int,
    data: BindCodeRequest,
    db: AsyncSession = Depends(get_db),
    student_db_id: int = Depends(require_student_self()),
):
    """学生设置/更新 6 位绑定码（仅限本人操作）。"""
    try:
        await ParentService.set_student_bind_code(db, student_db_id, data.bind_code)
        return {"success": True, "message": "绑定码已更新"}
    except ParentError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


@router.post("/bind", status_code=status.HTTP_201_CREATED)
async def create_binding(
    data: BindRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """家长提交绑定（验证绑定码）。"""
    parent_db_id = await _resolve_parent_id(db, user)
    try:
        result = await ParentService.create_binding(db, parent_db_id, data)
        return {"success": True, "data": result}
    except ParentError as e:
        code = (
            status.HTTP_400_BAD_REQUEST
            if e.error_code == "INVALID_BIND_CODE"
            else status.HTTP_404_NOT_FOUND
            if e.error_code == "RESOURCE_NOT_FOUND"
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=e.detail)


@router.get("/children")
async def list_children(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """家长查询已绑定子女列表。"""
    parent_db_id = await _resolve_parent_id(db, user)
    children = await ParentService.list_bound_children(db, parent_db_id)
    return {"success": True, "data": children}


@router.delete("/bind/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_binding(
    binding_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """家长解除亲子绑定（校验绑定归属）。"""
    parent_db_id = await _resolve_parent_id(db, user)
    try:
        await ParentService.delete_binding(db, binding_id, parent_db_id)
    except ParentError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ══════════════════════════════════════════════════════════════
# 子女数据查询
# ══════════════════════════════════════════════════════════════

@router.get("/child/{student_id}/report")
async def get_child_report(
    binding: tuple[int, int] = Depends(require_parent_binding()),
    db: AsyncSession = Depends(get_db),
):
    """获取子女学习概览（require_parent_binding）。"""
    _parent_id, student_db_id = binding
    report = await ParentService.get_child_overview(db, student_db_id)
    return {"success": True, "data": report}


@router.get("/child/{student_id}/timeline")
async def get_child_timeline(
    weeks: int = Query(default=4, ge=1, le=12),
    binding: tuple[int, int] = Depends(require_parent_binding()),
    db: AsyncSession = Depends(get_db),
):
    """获取子女学习时间线（近 N 周）。"""
    _parent_id, student_db_id = binding
    timeline = await ParentService.get_child_timeline(db, student_db_id, weeks)
    return {"success": True, "data": timeline}


# ══════════════════════════════════════════════════════════════
# 周报
# ══════════════════════════════════════════════════════════════

@router.get("/child/{student_id}/weekly")
async def get_weekly_report(
    binding: tuple[int, int] = Depends(require_parent_binding()),
    db: AsyncSession = Depends(get_db),
):
    """获取当周周报（缓存优先，无缓存返回 404）。"""
    _parent_id, student_db_id = binding
    report = await WeeklyReportService.get_report(db, student_db_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="本周周报尚未生成，请手动生成或等待系统自动生成",
        )
    return {"success": True, "data": report}


@router.post("/child/{student_id}/weekly/generate", status_code=status.HTTP_201_CREATED)
async def generate_weekly_report(
    binding: tuple[int, int] = Depends(require_parent_binding()),
    db: AsyncSession = Depends(get_db),
):
    """手动生成当周周报（并通知绑定家长）。"""
    _parent_id, student_db_id = binding
    try:
        report = await WeeklyReportService.generate_and_notify(
            db, student_db_id, generated_by="manual"
        )
        return {"success": True, "data": report}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ══════════════════════════════════════════════════════════════
# 通知
# ══════════════════════════════════════════════════════════════

@router.get("/notifications")
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    pagination: dict = Depends(get_pagination_params),
    user: UserContext = Depends(get_current_user),
):
    """获取家长通知列表（90 天保留）。"""
    parent_db_id = await _resolve_parent_id(db, user)
    items, total = await ParentService.list_notifications(
        db, parent_db_id,
        limit=pagination["limit"], offset=pagination["offset"],
    )
    return PaginatedResponse(
        items=items, total=total,
        limit=pagination["limit"], offset=pagination["offset"],
    )


@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """标记通知为已读（校验通知归属）。"""
    parent_db_id = await _resolve_parent_id(db, user)
    try:
        result = await ParentService.mark_notification_read(
            db, notification_id, parent_db_id,
        )
        return {"success": True, "data": result}
    except ParentError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)


# ══════════════════════════════════════════════════════════════
# Agent SSE 对话（30号 §四.A — Parent Persona）
# ══════════════════════════════════════════════════════════════

_PARENT_PERSONA_SYSTEM = """你是一位贴心的教育顾问，专门为家长解答关于孩子化学学习的疑问。

## 你的身份
- 你是 ChemAI 平台的家长端 AI 助手
- 你的回答面向家长，不是面向学生或教师

## 核心原则
1. **通俗易懂**：用家长能理解的日常语言，不使用化学专业术语
2. **正向引导**：先肯定孩子的努力，再指出提升空间
3. **不排名不比较**：只描述孩子自身的学习变化
4. **保护隐私**：不透露其他学生的任何信息
5. **具体可操作**：给家长的建议要具体、可落地

## 你可以帮助家长
- 解读周报中的数据，说明孩子哪些方面进步了
- 解释障碍诊断结果的含义（概念理解 / 审题能力 / 表述能力）
- 推荐在家可以做的辅助学习活动
- 回答关于化学学习方法的一般性问题
- 说明如何使用平台的家长功能

## 你不应该
- 给出具体的化学题目答案
- 替代教师的角色
- 对孩子的学习能力下结论性判断
- 建议家长给孩子报补习班"""


def _make_sse_event(event: str, data: dict) -> str:
    """构造一条 SSE 帧。"""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/agent/chat")
async def agent_chat(
    data: ParentAgentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """家长 Agent SSE 流式对话。

    组装 Parent persona，注入学生上下文，流式返回 SSE 事件：
    - phase: {phase: "thinking"|"reply"}
    - text: {content: "..."}
    - done: {thread_id: "..."}
    - error: {message: "..."}
    """
    parent_db_id = await _resolve_parent_id(db, user)

    # 验证绑定关系
    binding_result = await db.execute(
        select(StudentParentBinding).where(
            StudentParentBinding.student_id == data.student_id,
            StudentParentBinding.parent_id == parent_db_id,
            StudentParentBinding.status == "active",
        )
    )
    if binding_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="未绑定该学生",
        )

    # 获取学生上下文
    student_result = await db.execute(
        select(Student).where(Student.id == data.student_id)
    )
    student = student_result.scalar_one_or_none()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="学生不存在",
        )

    # 获取子女概览（用于上下文注入）
    overview = await ParentService.get_child_overview(db, data.student_id)

    thread_id = data.thread_id or f"p-{uuid.uuid4().hex[:12]}"

    # 构造学生上下文
    student_context = (
        f"当前选中的孩子：{student.name}\n"
        f"本周练习次数：{overview.weekly_practice_count}\n"
        f"加权正确率：{overview.accuracy_rate if overview.accuracy_rate is not None else '暂无数据'}\n"
        f"连续学习天数：{overview.streak_days}\n"
        f"薄弱知识点：{'、'.join(overview.weak_knowledge_points) if overview.weak_knowledge_points else '暂无'}\n"
        f"学习特点：{overview.characteristics}"
    )

    messages = [
        {"role": "system", "content": _PARENT_PERSONA_SYSTEM},
        {"role": "system", "content": f"## 学生上下文\n{student_context}"},
        {"role": "user", "content": data.message},
    ]

    async def event_stream():
        """SSE 事件生成器。"""
        try:
            # Phase: thinking
            yield _make_sse_event("phase", {"phase": "thinking"})

            # 非流式调用 LLM（json_mode=False 获取自然语言回复）
            raw_response = await llm_chat(
                messages,
                temperature=0.7,
                max_tokens=1024,
                json_mode=False,
            )

            # Phase: reply
            yield _make_sse_event("phase", {"phase": "reply"})

            # 模拟逐字流式输出（将响应按短句拆分）
            sentences = raw_response.replace("\n", "\n\n").split("\n\n")
            for sentence in sentences:
                text = sentence.strip()
                if not text:
                    continue
                yield _make_sse_event("text", {"content": text + "\n\n"})
                await asyncio.sleep(0.05)

            # Save checkpoint
            try:
                checkpoint = ConversationCheckpoint(
                    thread_id=thread_id,
                    student_id=data.student_id,
                    checkpoint_data={
                        "role": "parent",
                        "parent_id": parent_db_id,
                        "student_id": data.student_id,
                        "messages": [
                            {"role": "system", "content": _PARENT_PERSONA_SYSTEM[:200]},
                            {"role": "user", "content": data.message},
                            {"role": "assistant", "content": raw_response[:500]},
                        ],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                db.add(checkpoint)
                await db.commit()
            except Exception:
                logger.warning("Agent checkpoint 保存失败", exc_info=True)

            # Done
            yield _make_sse_event("done", {"thread_id": thread_id})

        except Exception as e:
            logger.error(f"Parent agent error: {e}", exc_info=True)
            yield _make_sse_event("error", {"message": "AI 助手暂时无法回复，请稍后重试"})

        finally:
            # 确保客户端收到关闭信号
            yield _make_sse_event("done", {"thread_id": thread_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ══════════════════════════════════════════════════════════════
# Agent 对话管理（34号 §七 — 基于 ConversationCheckpoint）
# ══════════════════════════════════════════════════════════════

@router.get("/agent/conversations")
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取家长对话列表（仅返回当前家长的对话）。"""
    parent_db_id = await _resolve_parent_id(db, user)

    # 查询所有 p- 前缀的 checkpoints，按 parent_id 过滤
    result = await db.execute(
        select(ConversationCheckpoint)
        .where(ConversationCheckpoint.thread_id.like("p-%"))
        .order_by(ConversationCheckpoint.created_at.desc())
    )
    all_checkpoints = result.scalars().all()

    # 按 thread_id 分组，仅保留属于当前家长的对话
    seen: set[str] = set()
    conversations = []
    for cp in all_checkpoints:
        if cp.thread_id in seen:
            continue
        cp_parent_id = (
            cp.checkpoint_data.get("parent_id")
            if isinstance(cp.checkpoint_data, dict) else None
        )
        if cp_parent_id != parent_db_id:
            continue
        seen.add(cp.thread_id)
        conversations.append({
            "thread_id": cp.thread_id,
            "student_id": cp.student_id,
            "last_active": cp.created_at.isoformat() if cp.created_at else None,
        })

    return {"success": True, "data": conversations}


async def _verify_conversation_owner(
    db: AsyncSession, thread_id: str, parent_db_id: int
) -> None:
    """验证指定对话属于当前家长，否则抛出 404。"""
    result = await db.execute(
        select(ConversationCheckpoint)
        .where(ConversationCheckpoint.thread_id == thread_id)
        .limit(1)
    )
    cp = result.scalar_one_or_none()
    if cp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话不存在",
        )
    cp_parent_id = (
        cp.checkpoint_data.get("parent_id")
        if isinstance(cp.checkpoint_data, dict) else None
    )
    if cp_parent_id != parent_db_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话不存在",
        )


@router.get("/agent/history/{thread_id}")
async def get_conversation_history(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """获取指定对话的历史记录（校验对话归属）。"""
    parent_db_id = await _resolve_parent_id(db, user)
    await _verify_conversation_owner(db, thread_id, parent_db_id)

    result = await db.execute(
        select(ConversationCheckpoint)
        .where(ConversationCheckpoint.thread_id == thread_id)
        .order_by(ConversationCheckpoint.id.asc())
    )
    checkpoints = result.scalars().all()
    history = [
        {
            "id": cp.id,
            "thread_id": cp.thread_id,
            "student_id": cp.student_id,
            "checkpoint_data": cp.checkpoint_data,
            "created_at": cp.created_at.isoformat() if cp.created_at else None,
        }
        for cp in checkpoints
    ]
    return {"success": True, "data": history}


@router.post("/agent/new", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """创建新的家长对话（返回 thread_id）。"""
    _parent_db_id = await _resolve_parent_id(db, user)
    thread_id = f"p-{uuid.uuid4().hex[:12]}"
    return {"success": True, "data": {"thread_id": thread_id}}


@router.delete("/agent/conversations/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """删除指定对话（校验对话归属）。"""
    parent_db_id = await _resolve_parent_id(db, user)
    await _verify_conversation_owner(db, thread_id, parent_db_id)

    await db.execute(
        sa_delete(ConversationCheckpoint).where(
            ConversationCheckpoint.thread_id == thread_id
        )
    )
    await db.commit()
