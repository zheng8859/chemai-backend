"""SSE 适配器 v2 — LangGraph 事件 → 10 种标准 SSE 事件。

事件类型：
- phase: Agent 阶段切换（planner/reasoning/acting/observing/done）
- tool_call: 工具调用开始
- tool_result: 工具执行结果
- text: LLM 文本流
- component: 前端组件（来自 _component）
- navigate: 页面导航（来自 _route）
- populate: 数据填充
- action: 动作指令
- exam_images: 考试图片
- error: 错误事件
- done: 流结束

包含：
- 文本去重算法（重叠 > 70% 跳过）
- SSE 背压保护（队列上限 100 条，超限丢弃 text 中间帧）
"""

import asyncio
import json
import logging
import time
from types import SimpleNamespace
from typing import Any, AsyncGenerator, Optional

from langgraph.types import Command

logger = logging.getLogger(__name__)

# ── SSE 背压配置 ──
MAX_QUEUE_SIZE = 100  # 事件队列上限
TEXT_OVERLAP_THRESHOLD = 0.7  # 文本去重重叠阈值


async def langgraph_sse_v2(
    agent,
    messages: list,
    config: dict,
    guard_state=None,
    thread_id: str = "",
    resume: Optional[dict] = None,
) -> AsyncGenerator[str, None]:
    """LangGraph Agent 执行 → SSE 事件流。

    使用 agent.astream_events() 捕获 LangGraph 内部事件，
    转换为 10 种标准 SSE 事件格式。

    Args:
        agent: LangGraph compiled graph
        messages: 消息列表（resume 模式下忽略）
        config: LangGraph config（含 thread_id）
        guard_state: GuardState 实例（首轮执行注入图状态）
        thread_id: 对话线程 ID
        resume: 审批恢复决策（如 {"approved": True}）；非 None 时走
            `Command(resume=...)` 恢复被 interrupt 暂停的图

    Yields:
        SSE 格式的事件字符串（"event: <type>\ndata: <json>\n\n"）
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
    done = asyncio.Event()

    # ── 去重状态 ──
    last_tool_output: str = ""
    llm_text_buffer: str = ""
    dedup_decided: bool = False

    # ── Phase 跟踪 ──
    current_phase = "reasoning"

    async def producer():
        """Agent 执行 → 事件入队。"""
        nonlocal current_phase, llm_text_buffer, dedup_decided, last_tool_output

        try:
            # guard_state 注入图状态（D2：拦截器从 state["guard_state"] 读取）
            if resume is not None:
                # 审批恢复：Command(resume=...) 恢复被 interrupt 暂停的图
                stream_input = Command(resume=resume)
            else:
                input_state = {"messages": messages}
                if guard_state is not None:
                    input_state["guard_state"] = guard_state
                stream_input = input_state

            async for event in agent.astream_events(
                stream_input, config, version="v2"
            ):
                kind = event.get("event", "")
                data = event.get("data", {})

                if kind == "on_chat_model_start":
                    current_phase = "reasoning"
                    await _safe_put(queue, {
                        "type": "phase",
                        "phase": "reasoning",
                        "timestamp": time.time(),
                    })

                elif kind == "on_chat_model_stream":
                    chunk = data.get("chunk", {})
                    content = getattr(chunk, "content", "")
                    if content:
                        llm_text_buffer += content
                        # 去重检查
                        if not dedup_decided and last_tool_output:
                            overlap = _text_overlap(last_tool_output, llm_text_buffer)
                            if overlap > TEXT_OVERLAP_THRESHOLD:
                                continue  # 跳过重复
                            else:
                                dedup_decided = True
                        await _safe_put(queue, {
                            "type": "text",
                            "content": content,
                            "timestamp": time.time(),
                        })

                elif kind == "on_chat_model_end":
                    # LLM 回复完成，重置去重状态
                    llm_text_buffer = ""
                    dedup_decided = False

                elif kind == "on_tool_start":
                    current_phase = "acting"
                    tool_name = event.get("name", "")
                    tool_input = data.get("input", {})
                    await _safe_put(queue, {
                        "type": "phase",
                        "phase": "acting",
                        "timestamp": time.time(),
                    })
                    await _safe_put(queue, {
                        "type": "tool_call",
                        "name": tool_name,
                        "args": _safe_serialize(tool_input),
                        "timestamp": time.time(),
                    })

                elif kind == "on_tool_end":
                    current_phase = "observing"
                    output = data.get("output", {})

                    # 防御性提取真实工具结果：wrapper 正常/批准路径返回
                    # Command(update={"messages":[...], "guard_state":...})，
                    # 此时 output 是 {messages, guard_state} 而非 ToolMessage。
                    raw_result = _try_loads_json(_extract_tool_result(output))

                    # 展示层剥离：wrapper 已将 _component/_route 收集进 guard_state，
                    # 此处仅移除展示层特殊字段（不重复收集，避免 component 事件重复发射）
                    if isinstance(raw_result, dict):
                        clean_output = {
                            k: v for k, v in raw_result.items()
                            if k not in ("_component", "_route")
                        }
                    else:
                        clean_output = raw_result

                    last_tool_output = json.dumps(clean_output, ensure_ascii=False, default=str)

                    await _safe_put(queue, {
                        "type": "phase",
                        "phase": "observing",
                        "timestamp": time.time(),
                    })
                    await _safe_put(queue, {
                        "type": "tool_result",
                        "name": event.get("name", ""),
                        "result": _safe_serialize(clean_output),
                        "timestamp": time.time(),
                    })

                elif kind == "on_custom_event":
                    # 自定义事件
                    await _safe_put(queue, {
                        "type": data.get("event_type", "custom"),
                        **data,
                        "timestamp": time.time(),
                    })

                elif kind == "on_chain_stream":
                    # interrupt 暂停信号（D3）：L4 审批门控触发时发射 awaiting_approval
                    chunk = data.get("chunk", {})
                    if isinstance(chunk, dict) and "__interrupt__" in chunk:
                        for inter in chunk["__interrupt__"]:
                            payload = getattr(inter, "value", None)
                            if not isinstance(payload, dict):
                                payload = {"approval_id": "", "tool_name": "", "args": {}}
                            await _safe_put(queue, {
                                "type": "phase",
                                "phase": "awaiting_approval",
                                "approval_id": payload.get("approval_id", ""),
                                "tool_name": payload.get("tool_name", ""),
                                "args": payload.get("args", {}),
                                "timestamp": time.time(),
                            })

            # ── 发射剥离的特殊字段（从最终图状态读取，见 D5） ──
            final_gs = await _read_final_guard_state(agent, config)
            if final_gs is not None:
                for comp in final_gs.stripped_components:
                    await _safe_put(queue, {
                        "type": "component",
                        "component": comp,
                        "timestamp": time.time(),
                    })

                for route in final_gs.stripped_routes:
                    page, params = _flatten_route(route)
                    await _safe_put(queue, {
                        "type": "navigate",
                        "page": page,
                        "params": params,
                        "timestamp": time.time(),
                    })

                # 发射后清空：stripped_components/routes 是累计字段，不清空会导致
                # resume 流重读完整列表、重复发射已发过的 component/navigate（D5）
                if final_gs.stripped_components or final_gs.stripped_routes:
                    await _clear_stripped_fields(agent, config)

            # ── 完成事件 ──
            await _safe_put(queue, {
                "type": "done",
                "thread_id": thread_id,
                "timestamp": time.time(),
            })

        except Exception as e:
            logger.exception("Agent 执行异常")
            error_msg = json.dumps({"message": str(e)}, ensure_ascii=False)
            await _safe_put(queue, {
                "type": "error",
                "message": error_msg,
                "timestamp": time.time(),
            })
            await _safe_put(queue, {
                "type": "done",
                "thread_id": thread_id,
                "error": str(e),
                "timestamp": time.time(),
            })

        finally:
            done.set()

    # 启动生产者（保存 Task 引用以捕获未处理异常）
    producer_task = asyncio.create_task(producer())
    producer_task.add_done_callback(
        lambda t: logger.exception("SSE producer 异常退出", exc_info=t.exception())
        if t.exception() else None
    )

    # 消费事件 → SSE 输出
    while not done.is_set() or not queue.empty():
        try:
            event_data = await asyncio.wait_for(queue.get(), timeout=0.1)
            yield _format_sse(event_data)
        except asyncio.TimeoutError:
            continue


def _extract_tool_result(output: Any) -> Any:
    """从 on_tool_end 的 output 提取真实工具结果 content。

    Guard wrapper 正常/批准路径返回 `Command(update={"messages": [...], "guard_state": ...})`，
    此时 on_tool_end 的 output 是 `{messages, guard_state}` 结构而非 ToolMessage；
    拒绝/放行路径则可能直接是 ToolMessage。防御性兼容三种形态。

    Args:
        output: on_tool_end 事件的 data.output

    Returns:
        工具结果的 content（dict / str / 其他）
    """
    # Command 结构：{"messages": [...], "guard_state": ...}
    if isinstance(output, dict) and "messages" in output:
        msgs = output.get("messages") or []
        for msg in reversed(msgs):
            content = getattr(msg, "content", None)
            if content is not None:
                return content
        return output
    # ToolMessage / 有 content 属性的对象
    if hasattr(output, "content"):
        return output.content
    return output


def _try_loads_json(value: Any) -> Any:
    """把 msg.content 的 JSON 字符串还原为对象，避免二次编码。

    LangGraph 的 msg_content_output 已把工具返回的 dict/对象序列化为 JSON
    字符串，`_safe_serialize` 若再对其 json.dumps 会产生二次编码：前端
    JSON.parse 一次后得到的仍是字符串而非对象，导致题目卡片等结构化结果
    退化为单张空卡（difficulty/audit_status 等字段丢失）。此处仅还原 JSON
    字符串；纯文本/非 JSON 字符串原样返回。
    """
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


async def _read_final_guard_state(agent, config: dict):
    """读取最终图状态的 GuardState（D5：剥离字段从图状态而非闭包读取）。

    首轮执行传入的 `guard_state` 与图状态是同一对象，但 `/chat/resume` 恢复时
    无 `guard_state` 入参，剥离字段只存在于 checkpoint 的最终状态中，故统一从
    `agent.aget_state(config)` 读取。

    Returns:
        GuardState 或含 stripped_components/stripped_routes 的轻量对象；失败返回 None
    """
    try:
        snapshot = await agent.aget_state(config)
    except Exception:
        logger.exception("读取最终图状态失败")
        return None
    if snapshot is None or not snapshot.values:
        return None
    gs = snapshot.values.get("guard_state")
    if gs is None:
        return None
    if isinstance(gs, dict):
        # msgpack 严格模式可能把 GuardState 反序列化为 dict
        return SimpleNamespace(
            stripped_components=gs.get("stripped_components", []),
            stripped_routes=gs.get("stripped_routes", []),
        )
    return gs


async def _clear_stripped_fields(agent, config: dict) -> None:
    """清空 guard_state 的 stripped_components/stripped_routes（发射后调用）。

    stripped 字段是累计列表，跨 resume 流会重复发射已发过的 component/navigate；
    发射完成后清空并 aupdate_state 写回 checkpoint，使下一次流只读到新增项。
    其余 guard_state 字段（persona/user_id/计数/去重/审批队列）保持不变。
    """
    try:
        snapshot = await agent.aget_state(config)
        if snapshot is None or not snapshot.values:
            return
        gs = snapshot.values.get("guard_state")
        if gs is None:
            return
        if isinstance(gs, dict):
            gs["stripped_components"] = []
            gs["stripped_routes"] = []
        else:
            gs.stripped_components.clear()
            gs.stripped_routes.clear()
        await agent.aupdate_state(config, {"guard_state": gs})
    except Exception:
        logger.exception("清空 stripped 字段失败（不影响流输出，下次流可能重复发射）")


def _flatten_route(route: object) -> tuple[str, dict]:
    """把 `_route` 载荷铺平为 (page, params)。

    前端 navigate handler 读取 data.page / data.params（顶层），
    因此此处不再把 route 包裹为 `{route: {...}}`。
    """
    if isinstance(route, dict):
        return route.get("page", ""), route.get("params", {})
    return "", {}


async def _safe_put(queue: asyncio.Queue, event: dict) -> None:
    """安全入队——队列满时丢弃 text 中间帧。"""
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        # 背压保护：丢弃 text token 中间帧
        if event.get("type") == "text":
            return  # 静默丢弃
        # 结构事件（tool_call/tool_result/error/done）需要等待
        await queue.put(event)


def _text_overlap(prev: str, current: str) -> float:
    """计算文本重叠率（简化版：前缀匹配比例）。"""
    if not prev or not current:
        return 0.0

    # 用最短长度计算前缀匹配
    min_len = min(len(prev), len(current))
    matches = sum(1 for i in range(min_len) if prev[i] == current[i])
    return matches / min_len if min_len > 0 else 0.0


def _safe_serialize(obj) -> str:
    """安全序列化为 JSON 字符串。"""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(obj)


def _format_sse(event: dict) -> str:
    """格式化为 SSE 字符串（不修改入参）。"""
    event_type = event.get("type", "message")
    payload = {k: v for k, v in event.items() if k != "type"}
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {data}\n\n"
