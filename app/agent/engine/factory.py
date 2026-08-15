"""Agent 工厂 — 创建 LangGraph ReAct Agent。

核心流程：
1. 加载 Persona 配置（YAML）
2. Persona 工具过滤（YAML available_skills ∩ TOOL_META[persona]）
3. 创建 LangGraph create_react_agent
4. 集成 checkpointer（AsyncSqliteSaver）
5. 配置 recursion_limit=12
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import MessagesState
from langgraph.managed import RemainingSteps
from langgraph.prebuilt import ToolNode, create_react_agent
from typing_extensions import NotRequired

# 触发 agent.tools.__init__ → 所有 @register_tool 装饰器执行
import agent.tools  # noqa: F401

from app.agent.persona.loader import PersonaConfig, load_persona
from app.agent.guard import GuardState, guard_tool_call_wrapper
from app.llm.model_factory import get_agent_model

logger = logging.getLogger(__name__)

# ── 数据库路径 ──
_CHECKPOINT_DB = Path(__file__).resolve().parent.parent.parent.parent / "data" / "checkpoint.db"

# ── 浏览器工具名称（从 agent/tools/browser_tools 注册） ──
_BROWSER_TOOLS = {"browse_navigate", "browse_read", "browse_click", "browse_input", "browse_screenshot"}


class AgentState(MessagesState):
    """图状态：扩展 MessagesState 增加 guard_state 字段（D2）。

    guard_state 放进图状态而非闭包捕获，使 L2 计数 / L3 去重键 / L4 审批队列
    能跨 interrupt/resume checkpoint 持久。

    remaining_steps 是 langgraph 1.x `create_react_agent` 强制要求的托管通道
    （递归限制计数），自定义 state_schema 必须声明，否则抛
    `Missing required key(s) {'remaining_steps'}`。
    """

    guard_state: GuardState
    remaining_steps: NotRequired[RemainingSteps]

# ── 全局单例 + 锁 ──
_checkpointer: Optional[AsyncSqliteSaver] = None
_checkpointer_lock = asyncio.Lock()
_checkpointer_cm: Optional[Any] = None  # 保存 context manager 引用，防止被 GC 提前清理


async def _get_checkpointer() -> AsyncSqliteSaver:
    """获取进程级 Checkpointer 单例（线程安全）。

    LangGraph >= 0.2 中 from_conn_string() 返回 async context manager，
    需手动 __aenter__ 获取实例。context manager 引用保存在全局变量中，
    避免被 GC 提前触发 __aexit__ 关闭数据库连接。
    """
    global _checkpointer, _checkpointer_cm
    if _checkpointer is not None:
        return _checkpointer
    async with _checkpointer_lock:
        if _checkpointer is None:
            _CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
            _checkpointer_cm = AsyncSqliteSaver.from_conn_string(
                str(_CHECKPOINT_DB)
            )
            _checkpointer = await _checkpointer_cm.__aenter__()
            await _checkpointer.setup()
            logger.info("Checkpointer 已初始化: %s", _CHECKPOINT_DB)
    return _checkpointer


async def get_thread_guard_state(thread_id: str) -> GuardState | dict | None:
    """从 checkpoint 读取线程的 guard_state（含 persona / user_id）。

    供 `/chat/resume` 重建 Agent 并做归属校验。guard_state 可能被 msgpack
    反序列化为 dict（严格模式），调用方需兼容两种形态。

    Args:
        thread_id: 对话线程 ID

    Returns:
        GuardState 或 dict，未找到时返回 None
    """
    cp = await _get_checkpointer()
    config = {"configurable": {"thread_id": thread_id}}
    try:
        tup = await cp.aget_tuple(config)
    except Exception:
        logger.exception("读取 checkpoint 失败: %s", thread_id)
        return None
    if tup is None:
        return None
    channel_values = tup.checkpoint.get("channel_values", {}) or {}
    return channel_values.get("guard_state")


async def get_thread_persona(thread_id: str) -> str:
    """从 checkpoint 读取线程的 persona，用于 `/chat/resume` 重建 Agent。

    `/chat/resume` 是独立请求，需重建与原始执行相同的图；persona 决定工具集
    与系统提示词，故从 checkpoint 的 `guard_state.persona`（D2 已入图状态）恢复。

    Args:
        thread_id: 对话线程 ID

    Returns:
        persona 名（teacher/student/tutor/parent），未找到时回退 teacher
    """
    guard_state = await get_thread_guard_state(thread_id)
    if isinstance(guard_state, GuardState):
        return guard_state.persona
    if isinstance(guard_state, dict):
        return guard_state.get("persona", "teacher")
    return "teacher"


def _build_system_prompt(config: PersonaConfig, student_context: str = "") -> str:
    """构建完整系统提示词。

    Args:
        config: Persona 配置
        student_context: 学生上下文（仅 Student/Persona 使用）

    Returns:
        完整 system prompt
    """
    prompt = config.system_prompt

    # 注入学生上下文
    if student_context and "{student_context}" in prompt:
        prompt = prompt.replace("{student_context}", student_context)

    # 追加工具使用说明
    prompt += "\n\n## 可用工具\n"
    prompt += "\n".join(f"- {s}" for s in config.available_skills)

    # 追加 ReAct 行为指令
    prompt += """

## 行为规则
1. 思考后选择合适的工具，每次只调用一个工具
2. 观察工具返回结果后，再决定下一步
3. 如果用户只是打开页面/查看信息，直接通过 _route 或 _component 响应
4. 单次对话中每个工具最多调用其 call_limit 次
5. 如果无法完成用户指令，如实说明原因
6. 用中文回复，化学方程式用 LaTeX 格式"""

    return prompt


async def create_agent(
    persona: str,
    provider: str = "qwen",
    student_context: str = "",
):
    """创建完整的 ReAct Agent（含 Guard 中间件）。

    Args:
        persona: 角色名（teacher/student/tutor/parent）
        provider: LLM Provider
        student_context: 学生上下文

    Returns:
        (agent, tools, config) 三元组
    """
    return await create_agent_with_checkpointer(
        persona=persona,
        provider=provider,
        student_context=student_context,
        use_checkpointer=False,
    )


async def create_agent_with_checkpointer(
    persona: str,
    provider: str = "qwen",
    student_context: str = "",
    use_checkpointer: bool = True,
    user_id: Optional[int] = None,
):
    """创建带 Checkpoint 持久化的 ReAct Agent。

    Args:
        persona: 角色名
        provider: LLM Provider
        student_context: 学生上下文
        use_checkpointer: 是否启用 checkpoint 持久化
        user_id: 线程归属用户 ID（写入 guard_state，供 /chat/resume 越权校验）

    Returns:
        {
            "agent": LangGraph compiled graph,
            "tools": list[Callable],
            "config": PersonaConfig,
            "guard_state": GuardState,
            "checkpointer": AsyncSqliteSaver | None,
        }
    """
    # 1. 加载 Persona
    persona_config = load_persona(persona)
    logger.info("创建 Agent: persona=%s, provider=%s, skills=%d",
                persona, provider, len(persona_config.available_skills))

    # 2. 获取工具集（Persona 过滤 + 浏览器工具）
    from agent.tools.tool_meta import get_tools_for_persona, get_all_tools
    persona_tools = get_tools_for_persona(persona)
    domain_tools = [t["func"] for t in persona_tools]

    # 添加浏览器工具（所有 Persona 共享，从全局注册表查找）
    all_registered = {t["name"]: t["func"] for t in get_all_tools().values()}
    browser_funcs = [
        func for name, func in all_registered.items()
        if name in _BROWSER_TOOLS
    ]

    tools = domain_tools + browser_funcs

    # 3. 构建系统提示词
    system_prompt = _build_system_prompt(persona_config, student_context)

    # 4. 创建 LLM 模型（工具绑定由 create_react_agent 管理，不在模型层预绑定）
    model = get_agent_model(provider)

    # 5. 创建 Guard 状态（请求级，注入图状态）
    guard_state = GuardState(persona=persona, user_id=user_id)

    # 6. 构造 Guard 拦截的 ToolNode（awrap_tool_call 挂载点，D1）
    tool_node = ToolNode(tools, awrap_tool_call=guard_tool_call_wrapper)

    # 7. 创建 checkpointer
    checkpointer = await _get_checkpointer() if use_checkpointer else None

    # 8. 创建 Agent（state_schema 注入 guard_state 字段，D2）
    agent = create_react_agent(
        model=model,
        tools=tool_node,
        prompt=system_prompt,
        checkpointer=checkpointer,
        state_schema=AgentState,
    )

    return {
        "agent": agent,
        "tools": tools,
        "config": persona_config,
        "guard_state": guard_state,
        "checkpointer": checkpointer,
        "model": model,
    }
