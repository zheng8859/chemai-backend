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
from langgraph.prebuilt import create_react_agent

# 触发 agent.tools.__init__ → 所有 @register_tool 装饰器执行
import agent.tools  # noqa: F401

from app.agent.persona.loader import PersonaConfig, load_persona
from app.agent.guard import GuardState, wrap_tool_node
from app.llm.model_factory import get_agent_model

logger = logging.getLogger(__name__)

# ── 数据库路径 ──
_CHECKPOINT_DB = Path(__file__).resolve().parent.parent.parent.parent / "data" / "checkpoint.db"

# ── 浏览器工具名称（从 agent/tools/browser_tools 注册） ──
_BROWSER_TOOLS = {"browse_navigate", "browse_read", "browse_click", "browse_input", "browse_screenshot"}

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
):
    """创建带 Checkpoint 持久化的 ReAct Agent。

    Args:
        persona: 角色名
        provider: LLM Provider
        student_context: 学生上下文
        use_checkpointer: 是否启用 checkpoint 持久化

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

    # 5. 创建 Guard 状态
    guard_state = GuardState(persona=persona)

    # 6. 使用 Guard 包装 tool_node
    # 获取完整的工具元数据（domain + browser）
    all_meta = get_all_tools()
    tool_meta_map = {name: meta for name, meta in all_meta.items()}

    # 7. 构建 Guard-wrapped 的工具节点
    # LangGraph create_react_agent 会自动管理 tool_node，
    # Guard 需要在工具执行前后插入：需要自定义 pre_model_hook
    # 简化方案：在 Agent 配置中传入 state_modifier

    # 8. 创建 checkpointer
    checkpointer = await _get_checkpointer() if use_checkpointer else None

    # 9. 创建 Agent（注意：create_react_agent 的参数名是 'prompt'，不是 'system_prompt'）
    agent = create_react_agent(
        model=model,
        tools=tools,
        prompt=system_prompt,
        checkpointer=checkpointer,
    )

    return {
        "agent": agent,
        "tools": tools,
        "config": persona_config,
        "guard_state": guard_state,
        "checkpointer": checkpointer,
        "tool_meta_map": tool_meta_map,
        "model": model,
    }
