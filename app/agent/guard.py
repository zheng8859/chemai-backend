"""Guard — 四层护栏。

四层检查（按顺序）：
L1 前置条件：校验必填参数（从 TOOL_META.prerequisites 读取）
L2 调用次数限制：每工具每轮有 call_limit（从 TOOL_META.call_limit 读取）
L3 去重检查：相同工具+相同参数 → 跳过
L4 审批门控：需要审批的工具（TOOL_META.requires_approval=True）→ 中断等待

Guard 作为 tool_node 外层包装，对工具函数透明。
执行工具后剥离 _component/_route 到 GuardState，纯净结果返回 LLM。
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from agent.tools.tool_meta import get_tool_meta, get_all_tools

logger = logging.getLogger(__name__)


@dataclass
class GuardResult:
    """Guard 检查结果。"""

    allowed: bool
    reason: str = ""
    layer: str = ""  # 违规层级（L1/L2/L3/L4）
    needs_approval: bool = False
    approval_id: str = ""


@dataclass
class GuardState:
    """请求级 Guard 状态。

    每个 Agent 请求创建一个实例，不跨请求共享。
    """

    persona: str
    tool_call_counts: dict[str, int] = field(default_factory=dict)  # {tool_name: count}
    dedup_keys: set[str] = field(default_factory=set)
    approval_queue: dict[str, dict] = field(default_factory=dict)  # {approval_id: {tool_name, args}}
    stripped_components: list[dict] = field(default_factory=list)
    stripped_routes: list[dict] = field(default_factory=list)

    def check(self, tool_name: str, args: dict) -> GuardResult:
        """执行四层护栏检查。

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            GuardResult
        """
        meta = get_tool_meta(tool_name)
        if meta is None:
            logger.warning("Guard: 工具 '%s' 不在 TOOL_META 中，放行", tool_name)
            return GuardResult(allowed=True)

        # ── L1: 前置条件检查 ──
        prerequisites = meta.get("prerequisites", [])
        if prerequisites:
            for param in prerequisites:
                value = args.get(param)
                if value is None or (isinstance(value, str) and value == ""):
                    return GuardResult(
                        allowed=False,
                        reason=f"缺少必填参数: {param}",
                        layer="L1",
                    )

        # ── L2: 调用次数限制 ──
        call_limit = meta.get("call_limit", 0)
        if call_limit > 0:
            count = self.tool_call_counts.get(tool_name, 0)
            if count >= call_limit:
                return GuardResult(
                    allowed=False,
                    reason=f"工具 '{tool_name}' 已达调用上限 ({call_limit} 次)",
                    layer="L2",
                )

        # ── L3: 去重检查 ──
        dedup_key = _make_dedup_key(tool_name, args)
        if dedup_key in self.dedup_keys:
            return GuardResult(
                allowed=False,
                reason=f"工具 '{tool_name}' 使用相同参数已执行过，跳过重复调用",
                layer="L3",
            )

        # ── L4: 审批门控 ──
        if meta.get("requires_approval", False):
            approval_id = _make_approval_id(tool_name, args)
            if approval_id not in self.approval_queue:
                # 第一次：创建审批请求，中断执行
                self.approval_queue[approval_id] = {
                    "tool_name": tool_name,
                    "args": args,
                    "status": "pending",
                }
                return GuardResult(
                    allowed=False,
                    reason=f"工具 '{tool_name}' 需要教师审批",
                    layer="L4",
                    needs_approval=True,
                    approval_id=approval_id,
                )
            elif self.approval_queue[approval_id]["status"] == "approved":
                # 审批通过：放行
                self.approval_queue[approval_id]["status"] = "executed"
            else:
                return GuardResult(
                    allowed=False,
                    reason=f"工具 '{tool_name}' 等待审批中",
                    layer="L4",
                    needs_approval=True,
                    approval_id=approval_id,
                )

        return GuardResult(allowed=True)

    def record_execution(self, tool_name: str, args: dict) -> None:
        """记录工具执行（L2 计数 + L3 去重键）。"""
        self.tool_call_counts[tool_name] = self.tool_call_counts.get(tool_name, 0) + 1
        dedup_key = _make_dedup_key(tool_name, args)
        self.dedup_keys.add(dedup_key)

    def approve(self, approval_id: str) -> None:
        """审批通过。"""
        if approval_id in self.approval_queue:
            self.approval_queue[approval_id]["status"] = "approved"
            logger.info("审批通过: %s", approval_id)

    def reject(self, approval_id: str) -> None:
        """审批拒绝。"""
        if approval_id in self.approval_queue:
            self.approval_queue[approval_id]["status"] = "rejected"
            logger.info("审批拒绝: %s", approval_id)

    def strip_special_fields(self, result: dict) -> dict:
        """剥离 _component 和 _route 字段。

        Args:
            result: 工具返回的完整字典

        Returns:
            不含特殊字段的纯净结果（返回给 LLM）
        """
        clean = dict(result)

        if "_component" in clean:
            self.stripped_components.append(clean.pop("_component"))

        if "_route" in clean:
            self.stripped_routes.append(clean.pop("_route"))

        return clean


def wrap_tool_node(tool_node_func, guard_state: GuardState, tool_meta_map: dict[str, dict]):
    """用 Guard 包装 tool_node。

    包装逻辑：
    1. 检查工具调用是否通过 Guard
    2. 执行工具
    3. 剥离特殊字段
    4. 记录执行

    Args:
        tool_node_func: 原始 tool_node 函数
        guard_state: Guard 状态
        tool_meta_map: {func_name: meta_dict}

    Returns:
        包装后的 tool_node 函数（用于 LangGraph StateGraph）
    """
    async def guarded_tool_node(state: dict) -> dict:
        """Guard 包装的 tool_node。"""
        messages = state.get("messages", [])
        if not messages:
            return state

        last_message = messages[-1]
        tool_calls = getattr(last_message, "tool_calls", [])

        if not tool_calls:
            return state

        results = []
        for tc in tool_calls:
            tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            tool_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})

            # Guard 检查
            guard_result = guard_state.check(tool_name, tool_args)

            if not guard_result.allowed:
                if guard_result.needs_approval:
                    # 审批事件：返回审批请求
                    results.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps({
                            "needs_approval": True,
                            "approval_id": guard_result.approval_id,
                            "tool_name": tool_name,
                            "message": guard_result.reason,
                        }),
                    })
                else:
                    # 拒绝：返回错误
                    results.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps({"error": guard_result.reason, "layer": guard_result.layer}),
                    })
                continue

            # 执行工具
            try:
                # 查找工具函数（优先使用传入的 tool_meta_map，O(1) vs O(n)）
                tool_func = None
                tool_entry = tool_meta_map.get(tool_name)
                if tool_entry:
                    tool_func = tool_entry.get("func")

                if tool_func is None:
                    results.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps({"error": f"工具 {tool_name} 未注册"}),
                    })
                    continue

                # 调用工具（支持同步/异步函数）
                import inspect
                raw_result = (
                    await tool_func(**tool_args)
                    if inspect.iscoroutinefunction(tool_func)
                    else tool_func(**tool_args)
                )

                # 记录执行
                guard_state.record_execution(tool_name, tool_args)

                # 剥离特殊字段
                clean_result = guard_state.strip_special_fields(raw_result)

                results.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(clean_result, ensure_ascii=False, default=str),
                })

            except Exception as e:
                logger.exception("工具 %s 执行失败", tool_name)
                results.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps({"error": str(e)}),
                })

        # 将结果写入 state
        state["messages"] = messages + results
        return state

    return guarded_tool_node


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def _make_dedup_key(tool_name: str, args: dict) -> str:
    """生成去重键（工具名 + 参数 JSON 的 SHA256 前 16 位）。"""
    args_str = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(f"{tool_name}:{args_str}".encode()).hexdigest()[:16]
    return f"{tool_name}:{digest}"


def _make_approval_id(tool_name: str, args: dict) -> str:
    """生成审批 ID。"""
    args_str = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(f"{tool_name}:{args_str}".encode()).hexdigest()[:12]
    return f"approval-{tool_name}-{digest}"
