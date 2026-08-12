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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, UserContext
from app.agent.gateway import classify_provider
from app.agent.planner import generate as planner_generate, single_step_fallback, Plan, validate
from app.agent.engine.factory import create_agent_with_checkpointer
from app.agent.context import build_student_context, inject_student_context, should_inject_context
from app.agent.context_trimmer import trim as trim_context, should_trim
from app.agent.sse.adapter_v2 import langgraph_sse_v2
from app.agent.guard import GuardState
from app.agent.audit import AuditLogger
from app.agent.dependency import AgentContext, set_current_context, clear_current_context
from app.infrastructure.database import get_db

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
    lines = ["## 执行计划", f"共 {len(plan.steps)} 步，按编号顺序执行：", ""]
    for step in plan.steps:
        dep = f"（依赖步骤 {step.depends_on}）" if step.depends_on else ""
        lines.append(f"{step.step_num}. `{step.skill_name}` — {step.intent}{dep}")
        if step.args_hint:
            args = ", ".join(f"{k}={v}" for k, v in step.args_hint.items())
            lines.append(f"   参数提示: {args}")
    lines.append("")
    lines.append("请严格按计划执行，不要跳过或合并步骤。完成全部步骤后总结结果。")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# SSE 对话流
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/stream")
async def chat_stream(
    req: AgentChatRequest,
    user: UserContext = Depends(get_current_user),
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
    persona = context.get("role", "teacher")
    student_id = context.get("student_id")
    teacher_id = user.user_id

    async def event_stream():
        try:
            t_start = time.time()  # Unix 时间戳（非 monotonic，monotonic 原点未定义）
            t_mono = time.monotonic()  # 单调时钟，用于精确计时

            # ── Step 1: Gateway ──
            provider = classify_provider(req.message)
            logger.info("[chat] Gateway: provider=%s, persona=%s", provider, persona)

            # ── 注入 AgentContext（Gateway 之后，使用实际 provider）──
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
    返回最近更新时间。
    """
    raise HTTPException(status_code=501, detail="Conversation listing not yet implemented")


@router.get("/history/{thread_id}")
async def get_history(
    thread_id: str,
    user: UserContext = Depends(get_current_user),
):
    """获取对话历史。

    从 checkpoint 读取消息，按 role 分类返回。
    """
    raise HTTPException(status_code=501, detail="Conversation history not yet implemented")


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
    raise HTTPException(status_code=501, detail="Conversation deletion not yet implemented")


@router.post("/resume")
async def resume_conversation(
    req: ResumeRequest,
    user: UserContext = Depends(get_current_user),
):
    """审批恢复。

    注入审批结果 → Agent 恢复执行 → 继续 SSE stream。
    """
    # 实际实现需要：
    # 1. 从 checkpoint 恢复 Agent 状态
    # 2. 调用 guard_state.approve() 或 guard_state.reject()
    # 3. 重新 invoke Agent

    return StreamingResponse(
        _resume_stream(req.thread_id, req.approval_id, req.approved),
        media_type="text/event-stream",
    )


async def _resume_stream(thread_id: str, approval_id: str, approved: bool):
    """审批恢复 → SSE 流。"""
    yield f"event: phase\ndata: {{\"phase\": \"resume\", \"thread_id\": \"{thread_id}\"}}\n\n"

    if approved:
        yield f"event: text\ndata: {{\"content\": \"审批已通过，继续执行...\"}}\n\n"
    else:
        yield f"event: text\ndata: {{\"content\": \"审批已拒绝，操作取消。\"}}\n\n"

    yield f"event: done\ndata: {{\"thread_id\": \"{thread_id}\"}}\n\n"


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
