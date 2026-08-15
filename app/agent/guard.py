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
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command, interrupt

from agent.tools.tool_meta import get_tool_meta

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
    user_id: Optional[int] = None  # 线程归属用户（用于 /chat/resume 越权校验）
    tool_call_counts: dict[str, int] = field(default_factory=dict)  # {tool_name: count}
    dedup_keys: set[str] = field(default_factory=set)
    approval_queue: dict[str, dict] = field(default_factory=dict)  # {approval_id: {tool_name, args}}
    stripped_components: list[dict] = field(default_factory=list)
    stripped_routes: list[dict] = field(default_factory=list)
    # 身份绑定（防 IDOR）：权威身份由入口从 JWT 解析，Guard 层据此覆盖/校验工具实参
    teacher_id: Optional[int] = None  # Teacher.id（teacher/tutor persona）
    student_id: Optional[int] = None  # Student.id（student persona）
    bound_student_ids: set[int] = field(default_factory=set)  # 家长绑定子女（parent persona）

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
            logger.error("Guard: 工具 '%s' 未在 TOOL_META 注册，拒绝执行（fail-closed）", tool_name)
            return GuardResult(
                allowed=False,
                reason=f"工具 '{tool_name}' 未在 TOOL_META 注册，已拒绝执行",
                layer="L0",
            )

        # ── L0: 角色越权校验（纵深防御，防止跨角色工具泄漏）──
        # 正常路径工具集已被 get_tools_for_persona 过滤，此处兜底拦截任何
        # 绕过过滤直接触达 wrapper 的越权调用（如非模型路径 invoke）。
        persona_allow = meta.get("persona", [])
        if persona_allow and self.persona not in persona_allow:
            return GuardResult(
                allowed=False,
                reason=f"工具 '{tool_name}' 不允许角色 '{self.persona}' 使用",
                layer="L0",
            )

        # ── L1: 前置条件检查 ──
        # 1a. 必填参数（每个都非空）
        prerequisites = meta.get("prerequisites", [])
        for param in prerequisites:
            if not _is_present(args.get(param)):
                return GuardResult(
                    allowed=False,
                    reason=f"缺少必填参数: {param}",
                    layer="L1",
                )

        # 1b. OR 条件组（每组至少一个非空）
        any_of = meta.get("prerequisite_any_of", [])
        for group in any_of:
            if not any(_is_present(args.get(p)) for p in group):
                return GuardResult(
                    allowed=False,
                    reason=f"缺少必填参数（至少一个）: {' 或 '.join(group)}",
                    layer="L1",
                )

        # 1c. 参数最小长度
        min_length = meta.get("prerequisite_min_length", {})
        for param, min_len in min_length.items():
            value = args.get(param)
            if value is None or not isinstance(value, str) or len(value) < min_len:
                return GuardResult(
                    allowed=False,
                    reason=f"参数 '{param}' 长度不足（至少 {min_len} 字符）",
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

    def bind_identity(self, tool_name: str, args: dict) -> Optional[GuardResult]:
        """身份参数绑定（防 IDOR，L0 之后、L1 之前执行）。

        将身份参数绑定到 JWT 认证身份，防止 LLM 注入任意 student_id/teacher_id
        造成水平越权。原地修改 args，使绑定后的值流入工具函数。

        Returns:
            GuardResult(allowed=False) 当绑定校验失败；否则原地修改 args 后返回 None
        """
        # teacher_id：任何工具只能以当前教师身份读/写
        if "teacher_id" in args and self.teacher_id is not None:
            args["teacher_id"] = self.teacher_id

        # student_id：按 persona 绑定
        if "student_id" in args and _is_present(args["student_id"]):
            if self.persona == "student":
                if self.student_id is not None:
                    args["student_id"] = self.student_id
            elif self.persona == "parent":
                sid = args["student_id"]
                if self.bound_student_ids:
                    if sid not in self.bound_student_ids:
                        return GuardResult(
                            allowed=False,
                            reason=f"无权访问学生 id={sid}（未与当前家长绑定）",
                            layer="L0",
                        )
                else:
                    return GuardResult(
                        allowed=False,
                        reason="当前家长未绑定任何学生，无法访问学生数据",
                        layer="L0",
                    )
        return None


async def guard_tool_call_wrapper(
    request: ToolCallRequest,
    execute: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
) -> ToolMessage | Command:
    """Guard 拦截器（`awrap_tool_call`）：每次工具执行前跑四层护栏。

    挂载点：`ToolNode(tools, awrap_tool_call=guard_tool_call_wrapper)`。
    拦截器从 `request.state["guard_state"]` 读取 GuardState（D2：放进图状态，
    跨 interrupt/resume 持久），按 L1→L4 依次检查：
    - L1/L2/L3 拒绝 → 短路返回带 `{error, layer}` 的 ToolMessage，不调 `execute`
    - L4 未审批 → `interrupt(approval_payload)` 暂停图，等待 /chat/resume 恢复
    - 放行/审批通过 → `execute` 执行，`record_execution`，剥离 `_component`/`_route`

    Args:
        request: ToolCallRequest（含 tool_call / tool / state / runtime）
        execute: 异步执行回调 `(request) -> ToolMessage | Command`

    Returns:
        ToolMessage | Command
    """
    tool_call = request.tool_call
    tool_name = tool_call["name"]
    tool_args = tool_call["args"]
    tool_call_id = tool_call["id"]

    guard_state = request.state.get("guard_state") if isinstance(request.state, dict) else None
    if guard_state is None:
        # fail-closed：护栏状态缺失时拒绝执行，而非跳过护栏直接放行。
        # 任何反序列化抖动都不应静默关闭四层防护与字段剥离。
        logger.error("Guard: state 中缺少 guard_state，拒绝执行 %s（fail-closed）", tool_name)
        return ToolMessage(
            content=json.dumps(
                {"error": "护栏状态不可用，已拒绝执行该工具", "layer": "L0"},
                ensure_ascii=False,
            ),
            tool_call_id=tool_call_id,
        )

    # 身份绑定（防 IDOR）：在 L1 前置校验前把身份参数绑定到 JWT 认证身份
    identity_err = guard_state.bind_identity(tool_name, tool_args)
    if identity_err is not None:
        return ToolMessage(
            content=json.dumps(
                {"error": identity_err.reason, "layer": identity_err.layer},
                ensure_ascii=False,
            ),
            tool_call_id=tool_call_id,
        )

    result = guard_state.check(tool_name, tool_args)

    if not result.allowed:
        if result.needs_approval:
            # L4: 审批门控 → interrupt 暂停
            approval_payload = {
                "approval_id": result.approval_id,
                "tool_name": tool_name,
                "args": tool_args,
            }
            decision = interrupt(approval_payload)
            if not decision or not decision.get("approved"):
                guard_state.reject(result.approval_id)
                msg = ToolMessage(
                    content=json.dumps(
                        {"error": "审批被拒绝，操作已取消", "layer": "L4", "cancelled": True},
                        ensure_ascii=False,
                    ),
                    tool_call_id=tool_call_id,
                )
                return _guard_update(guard_state, msg)
            guard_state.approve(result.approval_id)
            # 审批通过，落入下方执行
        else:
            # L1/L2/L3: 短路返回拒绝消息（无状态变更）
            return ToolMessage(
                content=json.dumps(
                    {"error": result.reason, "layer": result.layer},
                    ensure_ascii=False,
                ),
                tool_call_id=tool_call_id,
            )

    # 放行（或审批通过）：执行工具
    tool_output = await execute(request)

    # 记录执行（L2 计数 + L3 去重键）
    guard_state.record_execution(tool_name, tool_args)

    # 剥离 _component/_route（纯净结果返回 LLM，特殊字段进 guard_state）
    # 归一化工具结果：str 尝试 JSON 解析，dict 直接用，其余（list/多模态）跳过
    content = tool_output.content
    if isinstance(content, str):
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            data = None
    elif isinstance(content, dict):
        data = content
    else:
        data = None

    if isinstance(data, dict) and ("_component" in data or "_route" in data):
        clean = guard_state.strip_special_fields(data)
        tool_output = ToolMessage(
            content=json.dumps(clean, ensure_ascii=False, default=str),
            tool_call_id=tool_output.tool_call_id,
        )

    # 回写 guard_state 到图状态（D2：in-place 变更不跨 checkpoint，必须显式更新）
    return _guard_update(guard_state, tool_output)


def _guard_update(guard_state: GuardState, tool_message: ToolMessage) -> Command:
    """把 guard_state 连同工具消息一并写回图状态。

    LangGraph 的 checkpoint 仅记录节点返回值（而非嵌套对象 in-place 变更），
    因此 GuardState 的变更必须通过 Command.update 显式回写才能跨 interrupt/resume 持久。
    """
    return Command(update={"messages": [tool_message], "guard_state": guard_state})


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def _is_present(value: Any) -> bool:
    """判断参数值是否「非空」（L1 前置检查专用）。

    契约：
    - None、空字符串 → 「未提供」
    - 数值 0 → 「未提供」（仅对 ID 哨兵参数成立：plan_id/bank_id/session_id/
      student_id/class_id 等默认 0 表示未指定，0 作为 ID 无意义）
    - 其余非空值 → 「已提供」

    注意：此约定仅适用于 ID 哨兵参数。未来若出现「合法取值 0」的非 ID 数值
    参数，不得复用本函数判空，须另行处理。
    """
    if value is None:
        return False
    if isinstance(value, str) and value == "":
        return False
    if isinstance(value, (int, float)) and value == 0:
        return False
    return True


def _args_json(args: dict) -> str:
    """参数规范化 JSON 序列化（去重键与审批 ID 共用，保证两者序列化一致）。"""
    return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)


def _make_dedup_key(tool_name: str, args: dict) -> str:
    """生成去重键（工具名 + 参数 JSON 的 SHA256 前 16 位）。"""
    digest = hashlib.sha256(f"{tool_name}:{_args_json(args)}".encode()).hexdigest()[:16]
    return f"{tool_name}:{digest}"


def _make_approval_id(tool_name: str, args: dict) -> str:
    """生成审批 ID。"""
    digest = hashlib.sha256(f"{tool_name}:{_args_json(args)}".encode()).hexdigest()[:12]
    return f"approval-{tool_name}-{digest}"
