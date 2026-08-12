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
from typing import AsyncGenerator, Optional

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
) -> AsyncGenerator[str, None]:
    """LangGraph Agent 执行 → SSE 事件流。

    使用 agent.astream_events() 捕获 LangGraph 内部事件，
    转换为 10 种标准 SSE 事件格式。

    Args:
        agent: LangGraph compiled graph
        messages: 消息列表
        config: LangGraph config（含 thread_id）
        guard_state: GuardState 实例
        thread_id: 对话线程 ID

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
            async for event in agent.astream_events(
                {"messages": messages}, config, version="v2"
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

                    # 剥离 _component/_route
                    if guard_state and isinstance(output, dict):
                        clean_output = guard_state.strip_special_fields(output)
                    else:
                        clean_output = output

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

            # ── 发射剥离的特殊字段 ──
            if guard_state:
                for comp in guard_state.stripped_components:
                    await _safe_put(queue, {
                        "type": "component",
                        "component": comp,
                        "timestamp": time.time(),
                    })

                for route in guard_state.stripped_routes:
                    await _safe_put(queue, {
                        "type": "navigate",
                        "route": route,
                        "timestamp": time.time(),
                    })

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
