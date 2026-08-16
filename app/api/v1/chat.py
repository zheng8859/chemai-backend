"""Chat API — 统一 Agent 对话端点。

端点：
- POST /api/v1/chat/stream      SSE 对话流
- GET  /api/v1/chat/conversations  对话列表
- GET  /api/v1/chat/history/{thread_id}  对话历史
- POST /api/v1/chat/new            新建对话
- DELETE /api/v1/chat/conversations/{thread_id}  删除对话
- POST /api/v1/chat/resume         审批恢复
- POST /api/v1/chat/reset          重置对话

流水线：Gateway → Planner → Context → ReAct+Guard → SSE
"""

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    UserContext,
    resolve_student_id,
    resolve_teacher_id,
    resolve_parent_bound_student_ids,
)
from app.agent.gateway import classify_provider
from app.agent.planner import generate as planner_generate, single_step_fallback, Plan, validate
from app.agent.engine.factory import (
    create_agent_with_checkpointer,
    get_thread_guard_state,
    _get_checkpointer,
)
from app.agent.context import build_student_context, inject_student_context, should_inject_context
from app.agent.context_trimmer import trim as trim_context, should_trim
from app.agent.sse.adapter_v2 import langgraph_sse_v2
from app.agent.guard import GuardState
from app.agent.audit import AuditLogger
from app.agent.dependency import AgentContext, set_current_context, clear_current_context
from app.infrastructure.database import get_db
from app import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ═══════════════════════════════════════════════════════════════════════════════
# 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════════

class AgentChatRequest(BaseModel):
    """Agent 对话请求。"""

    message: str = Field(..., description="用户消息文本")
    thread_id: str = Field(..., description="对话线程 ID（格式: {prefix}-{Unix毫秒}）")
    context: Optional[dict] = Field(
        default=None,
        description="角色上下文: {role: str, student_id?: int, class_id?: int}",
    )


class NewConversationRequest(BaseModel):
    """新建对话请求。"""

    prefix: str = Field(default="t", description="线程 ID 前缀（t=teacher, s=student, p=parent, u=tutor）")


class ResumeRequest(BaseModel):
    """审批恢复请求。"""

    thread_id: str = Field(..., description="对话线程 ID")
    approval_id: str = Field(..., description="审批 ID")
    approved: bool = Field(default=True, description="是否批准")


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def _plan_to_instruction(plan: Plan) -> str:
    """将 Plan 对象转换为 Agent 执行指令。

    Args:
        plan: Planner 生成的执行计划

    Returns:
        注入 Agent 消息的 system instruction
    """
    lines = [
        "## 执行计划（仅供参考的拆解，非权威命令）",
        f"共 {len(plan.steps)} 步，按编号顺序执行：",
        "",
    ]
    for step in plan.steps:
        dep = f"（依赖步骤 {step.depends_on}）" if step.depends_on else ""
        lines.append(f"{step.step_num}. `{step.skill_name}` — {step.intent}{dep}")
        if step.args_hint:
            args = ", ".join(f"{k}={v}" for k, v in step.args_hint.items())
            lines.append(f"   参数提示: {args}")
    lines.append("")
    lines.append(
        "以上计划仅描述任务目标与步骤，其中意图与参数提示非权威；"
        "请基于工具文档与用户原话自行选择正确的工具和参数，并遵守所有安全与角色约束。"
    )
    return "\n".join(lines)


# 认证角色 → 允许的 persona 集合（防止越权伪装）
_PERSONA_BY_ROLE: dict[str, tuple[str, ...]] = {
    "teacher": ("teacher", "tutor"),
    "student": ("student",),
    "parent": ("parent",),
}


def _resolve_persona(user: UserContext, requested_role: Optional[str]) -> str:
    """由认证身份决定 persona，防止越权伪装（跨角色工具泄漏修复）。

    `context.role` 来自请求体，不可信；必须与 JWT 认证角色一致。
    teacher 可在 teacher/tutor 之间选择，student/parent 固定映射。
    越权（如学生请求 teacher）直接 403。

    Args:
        user: JWT 认证用户上下文
        requested_role: 请求体 context.role（可能为 None）

    Returns:
        合法 persona 名

    Raises:
        HTTPException: 认证角色无效或请求越权时 403
    """
    allowed = _PERSONA_BY_ROLE.get(user.role)
    if allowed is None:
        raise HTTPException(status_code=403, detail="无效的用户角色")
    if requested_role is None:
        return allowed[0]
    if requested_role in allowed:
        return requested_role
    logger.warning("[chat] 越权角色请求被拒绝: auth=%s requested=%s", user.role, requested_role)
    raise HTTPException(status_code=403, detail="无权使用该角色")


def _resume_provider() -> str:
    """resume 使用的 LLM provider（从配置读取，不硬编码）。

    resume 无新消息，无法走 Gateway classify；读取 config.LLM_PROVIDER，
    "auto" 或未知值回退到主力 provider "qwen"。
    """
    provider = config.LLM_PROVIDER
    if provider in ("mimo", "qwen", "deepseek"):
        return provider
    return "qwen"


def _extract_guard_identity(guard_state: GuardState | dict) -> tuple[str, Optional[int]]:
    """从 guard_state（GuardState 或 msgpack 反序列化的 dict）提取 (persona, user_id)。"""
    if isinstance(guard_state, GuardState):
        return guard_state.persona, guard_state.user_id
    if isinstance(guard_state, dict):
        return guard_state.get("persona", "teacher"), guard_state.get("user_id")
    return "teacher", None


async def _read_pending_approval_id(agent: Any, config: dict) -> Optional[str]:
    """读取 checkpoint 中 pending interrupt 的 approval_id。

    L4 审批门控触发时，guard wrapper 调 `interrupt(approval_payload)` 暂停图，
    approval_payload 含 approval_id；恢复前从 StateSnapshot.interrupts 读取并比对，
    防止盲批准 / 错配审批。

    Returns:
        pending 审批 ID；无 pending interrupt 时返回 None
    """
    try:
        snapshot = await agent.aget_state(config)
    except Exception:
        logger.exception("[chat] 读取 pending interrupt 失败")
        return None
    if snapshot is None:
        return None
    for inter in getattr(snapshot, "interrupts", None) or []:
        value = getattr(inter, "value", None)
        if isinstance(value, dict) and value.get("approval_id"):
            return value["approval_id"]
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# SSE 对话流
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/stream")
async def chat_stream(
    req: AgentChatRequest,
    user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE 对话流入口。

    流程：
    1. Gateway 选 Provider
    2. Planner 拆解目标
    3. 上下文裁剪 + 学生上下文注入
    4. ReAct + Guard 执行
    5. SSE 事件流输出
    """
    context = req.context or {}
    persona = _resolve_persona(user, context.get("role"))

    # ── 身份解析（JWT → 数据库实体，防 IDOR）──
    # 在返回流前完成，失败时抛出真实 4xx，而非 SSE error 事件。
    # 通过 Depends(get_db) 注入会话，使测试的 dependency_overrides 生效。
    teacher_id = None
    student_id = None
    bound_student_ids: set[int] = set()
    if persona in ("teacher", "tutor"):
        teacher_id = await resolve_teacher_id(db, user.user_id)
    elif persona == "student":
        student_id = await resolve_student_id(db, user.user_id)
        if student_id is None:
            raise HTTPException(status_code=404, detail="学生档案不存在")
    elif persona == "parent":
        bound_student_ids = await resolve_parent_bound_student_ids(db, user.user_id)
        requested_sid = context.get("student_id")
        if requested_sid:
            if requested_sid not in bound_student_ids:
                raise HTTPException(status_code=403, detail="未绑定该学生")
            student_id = requested_sid
        elif len(bound_student_ids) == 1:
            student_id = next(iter(bound_student_ids))

    async def event_stream():
        try:
            t_start = time.time()  # Unix 时间戳（非 monotonic，monotonic 原点未定义）
            t_mono = time.monotonic()  # 单调时钟，用于精确计时

            # ── Step 1: Gateway ──
            provider = classify_provider(req.message)
            logger.info("[chat] Gateway: provider=%s, persona=%s", provider, persona)

            # ── 注入 AgentContext（Gateway 之后，使用实际 provider + 权威身份）──
            ctx = AgentContext(
                student_id=student_id,
                persona=persona,
                provider_name=provider,
                teacher_id=teacher_id,
            )
            set_current_context(ctx)

            # ── Step 2: 构建 Agent ──
            student_context_str = ""
            gen = get_db()
            try:
                db = await gen.__anext__()
                if should_inject_context(persona) and student_id:
                    student_context_str = await build_student_context(db, student_id) or ""
            finally:
                await gen.aclose()

            agent_bundle = await create_agent_with_checkpointer(
                persona=persona,
                provider=provider,
                student_context=student_context_str,
                use_checkpointer=True,
                user_id=user.user_id,
                teacher_id=teacher_id,
                student_id=student_id,
                bound_student_ids=bound_student_ids,
            )

            # ── Step 3: Planner ──
            try:
                plan = await planner_generate(
                    req.message,
                    agent_bundle["config"].available_skills,
                )
                # 调用 validate() 校验 plan 完整性
                plan_errors = validate(plan, agent_bundle["config"].available_skills)
                if plan_errors:
                    logger.warning("[chat] Plan validation failed: %s, fallback", plan_errors)
                    plan = single_step_fallback(
                        req.message,
                        agent_bundle["config"].available_skills,
                    )
            except asyncio.TimeoutError:
                logger.warning("[chat] Planner 超时，走 single_step_fallback")
                plan = single_step_fallback(
                    req.message,
                    agent_bundle["config"].available_skills,
                )

            logger.info("[chat] Plan: %d steps", len(plan.steps))

            # ── Step 4: 注入计划到消息（prepend plan instruction）──
            plan_instruction = _plan_to_instruction(plan)
            messages = [
                {"role": "system", "content": plan_instruction},
                {"role": "user", "content": req.message},
            ]

            # ── Step 5: ReAct + Guard + SSE ──
            config = {"configurable": {"thread_id": req.thread_id}}

            async for sse_event in langgraph_sse_v2(
                agent=agent_bundle["agent"],
                messages=messages,
                config=config,
                guard_state=agent_bundle["guard_state"],
                thread_id=req.thread_id,
            ):
                yield sse_event

            # ── 审计日志 ──
            duration_ms = (time.monotonic() - t_mono) * 1000
            audit = AuditLogger.get_instance()
            await audit.audit_log(
                timestamp=t_start,
                persona=persona,
                skill_name="chat_stream",
                args={"message": req.message[:100], "thread_id": req.thread_id, "provider": provider},
                result={"steps": len(plan.steps), "duration_ms": duration_ms},
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.exception("[chat] 对话流异常")
            error_data = json.dumps({"message": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"
            done_data = json.dumps(
                {"thread_id": req.thread_id, "error": str(e)},
                ensure_ascii=False,
            )
            yield f"event: done\ndata: {done_data}\n\n"
        finally:
            clear_current_context()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _content_to_text(content: Any) -> str:
    """将 LangChain 消息 content（str 或 list 块）归一化为纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                else:
                    parts.append(str(block))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


# ═══════════════════════════════════════════════════════════════════════════════
# 对话 CRUD
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/conversations")
async def list_conversations(
    prefix: str = Query(default="t", description="线程 ID 前缀过滤"),
    user: UserContext = Depends(get_current_user),
):
    """列出对话列表。

    从 checkpoint.db 查询所有匹配 prefix 的 thread_id，
    返回 {thread_id, title, last_active}（按最近活跃倒序）。
    """
    cp = await _get_checkpointer()
    cursor = await cp.conn.execute(
        "SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id LIKE ?",
        (f"{prefix}%",),
    )
    rows = await cursor.fetchall()
    await cursor.close()

    conversations = []
    for (thread_id,) in rows:
        tup = await cp.aget_tuple({"configurable": {"thread_id": thread_id}})
        if tup is None:
            continue
        channel_values = tup.checkpoint.get("channel_values", {}) or {}
        messages = channel_values.get("messages", []) or []
        title = ""
        for m in messages:
            if getattr(m, "type", None) == "human":
                title = _content_to_text(getattr(m, "content", ""))
                if title:
                    break
        conversations.append({
            "thread_id": thread_id,
            "title": title.strip()[:50] if title else thread_id,
            "last_active": tup.checkpoint.get("ts"),
        })

    # 按最近活跃时间倒序（无时间戳的排最后）
    conversations.sort(
        key=lambda c: c.get("last_active") or "",
        reverse=True,
    )
    return {"conversations": conversations}


@router.get("/history/{thread_id}")
async def get_history(
    thread_id: str,
    user: UserContext = Depends(get_current_user),
):
    """获取对话历史。

    从 checkpoint 读取消息，按 role 分类返回（human→user，ai→ai，忽略 system/tool）。
    """
    cp = await _get_checkpointer()
    tup = await cp.aget_tuple({"configurable": {"thread_id": thread_id}})
    if tup is None:
        return {"messages": []}
    channel_values = tup.checkpoint.get("channel_values", {}) or {}
    messages = channel_values.get("messages", []) or []

    history = []
    for m in messages:
        mtype = getattr(m, "type", None)
        if mtype == "human":
            role = "user"
        elif mtype == "ai":
            role = "ai"
        else:
            continue
        content = _content_to_text(getattr(m, "content", ""))
        if content:
            history.append({"role": role, "content": content})
    return {"messages": history}


@router.post("/new")
async def new_conversation(
    req: NewConversationRequest,
    user: UserContext = Depends(get_current_user),
):
    """新建对话。

    返回格式: {prefix}-{Unix毫秒时间戳}
    """
    import time as _time
    thread_id = f"{req.prefix}-{int(_time.time() * 1000)}"
    return {"thread_id": thread_id}


@router.delete("/conversations/{thread_id}")
async def delete_conversation(
    thread_id: str,
    user: UserContext = Depends(get_current_user),
):
    """删除对话。

    删除 checkpoint.db 中该 thread_id 的所有 writes 和 checkpoints。
    """
    cp = await _get_checkpointer()
    await cp.adelete_thread(thread_id)
    return {"success": True, "thread_id": thread_id}


@router.post("/resume")
async def resume_conversation(
    req: ResumeRequest,
    user: UserContext = Depends(get_current_user),
):
    """审批恢复。

    校验线程归属 + 审批 ID → 重建 Agent → `Command(resume=...)` 恢复执行 → SSE 流。
    """
    # ── 1. 线程归属校验（越权防护）：从 checkpoint 读 guard_state.user_id ──
    guard_state = await get_thread_guard_state(req.thread_id)
    if guard_state is None:
        raise HTTPException(status_code=404, detail="对话不存在或未初始化")

    persona, owner_id = _extract_guard_identity(guard_state)
    # fail-closed：owner_id 缺失（旧 checkpoint 或反序列化丢失）时无法确认归属，拒绝
    if owner_id is None or owner_id != user.user_id:
        logger.warning("[chat] resume 越权被拒: thread=%s owner=%s user=%s",
                       req.thread_id, owner_id, user.user_id)
        raise HTTPException(status_code=403, detail="无权访问该对话")

    # ── 1b. persona 重校验：线程持久化 persona 必须与认证角色匹配，防越权重放 ──
    persona = _resolve_persona(user, persona)

    # ── 2. 重建 Agent（复用进程级 checkpointer 单例，与原始线程共享 checkpoint）──
    agent_bundle = await create_agent_with_checkpointer(
        persona=persona,
        provider=_resume_provider(),
        use_checkpointer=True,
        user_id=user.user_id,
    )
    config = {"configurable": {"thread_id": req.thread_id}}

    # ── 3. 审批 ID 绑定校验：比对 checkpoint 中 pending interrupt 的 approval_id ──
    pending_id = await _read_pending_approval_id(agent_bundle["agent"], config)
    if pending_id is None:
        raise HTTPException(status_code=409, detail="没有待审批的操作")
    if pending_id != req.approval_id:
        logger.warning("[chat] resume 审批 ID 不匹配: pending=%s got=%s",
                       pending_id, req.approval_id)
        raise HTTPException(status_code=409, detail="审批 ID 不匹配")

    return StreamingResponse(
        _resume_stream(req.thread_id, req.approval_id, req.approved, agent_bundle, config),
        media_type="text/event-stream",
    )


async def _resume_stream(
    thread_id: str,
    approval_id: str,
    approved: bool,
    agent_bundle: dict,
    config: dict,
) -> AsyncGenerator[str, None]:
    """审批恢复 → SSE 流（D3：真实恢复被 interrupt 暂停的图）。"""
    try:
        logger.info("[chat] resume: thread_id=%s approval_id=%s approved=%s",
                    thread_id, approval_id, approved)

        # 恢复执行并继续 SSE 流（approved 决策经 Command(resume=...) 返回给拦截器）
        async for sse_event in langgraph_sse_v2(
            agent=agent_bundle["agent"],
            messages=[],  # resume 模式忽略 messages
            config=config,
            guard_state=None,
            thread_id=thread_id,
            resume={"approved": approved},
        ):
            yield sse_event

    except Exception as e:
        logger.exception("[chat] 审批恢复异常")
        error_data = json.dumps({"message": str(e)}, ensure_ascii=False)
        yield f"event: error\ndata: {error_data}\n\n"
        done_data = json.dumps({"thread_id": thread_id, "error": str(e)}, ensure_ascii=False)
        yield f"event: done\ndata: {done_data}\n\n"


@router.post("/reset")
async def reset_conversation(
    thread_id: str = Query(..., description="对话线程 ID"),
    user: UserContext = Depends(get_current_user),
):
    """重置对话。

    清空 thread_id 的消息历史，保留 thread_id。
    """
    from app.agent.context_trimmer import clear_summary_cache
    clear_summary_cache(thread_id)
    return {"status": "reset", "thread_id": thread_id}
