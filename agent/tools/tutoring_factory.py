"""Socratic 化学 tutoring 工具工厂。

提供 `_make_tutoring_tool` 工厂函数，创建多步骤苏格拉底式问答工具。
每个工具支持三种模式：
- entry: 学生进入 → 引导提供问题
- step_1: 学生提供问题 → Step 1 引导
- step_{n}: 学生回答 Step n → 反馈 + Step n+1 引导
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def make_tutoring_tool(
    tool_name: str,
    step_prompts: list[str],
    feedback_instruction: str,
):
    """创建 Socratic tutoring 工具函数。

    Args:
        tool_name: 工具名称（用于日志和元数据）
        step_prompts: 各步骤的引导提示词列表，如 [
            "请分析元素的原子结构...",
            "根据结构推断元素性质...",
            "验证你的推断是否正确...",
        ]
        feedback_instruction: LLM 反馈指令（用于评估学生的回答）

    Returns:
        async callable(state: dict) -> dict
    """
    async def tutoring_tool(
        user_input: str = "",
        step: int = 0,
        history: Optional[str] = None,
    ) -> dict:
        """Socratic tutoring 对话工具。

        Args:
            user_input: 学生输入（首次为空时进入 entry 模式）
            step: 当前步骤（0 = entry, 1..N = 各步骤）
            history: 历史对话摘要（可选）

        Returns:
            {
                "mode": "entry" | "step",
                "step": int,
                "total_steps": int,
                "prompt": str,           # 引导提示词
                "feedback": str | None,  # 对学生回答的反馈
                "is_complete": bool,
            }
        """
        total_steps = len(step_prompts)

        # Entry 模式：学生尚未提供问题
        if not user_input or not user_input.strip():
            return {
                "mode": "entry",
                "step": 0,
                "total_steps": total_steps,
                "prompt": f"请提供一个与{tool_name}相关的化学问题，我会一步步引导你思考。",
                "feedback": None,
                "is_complete": False,
            }

        # 已完成所有步骤
        if step >= total_steps:
            return {
                "mode": "step",
                "step": step,
                "total_steps": total_steps,
                "prompt": "你已经完成了所有步骤！总结一下你学到的内容吧。",
                "feedback": "很好，你完成了这个问题的完整推理过程。",
                "is_complete": True,
            }

        # Step 模式：返回当前步骤的引导
        next_step = step + 1
        is_last = next_step >= total_steps

        feedback = (
            f"{feedback_instruction}\n\n"
            f"学生对 Step {step} 的回答：{user_input[:500]}"
        )

        return {
            "mode": "step",
            "step": next_step if not is_last else step,
            "total_steps": total_steps,
            "prompt": step_prompts[step],
            "feedback": feedback,
            "is_complete": is_last,
        }

    tutoring_tool.__name__ = tool_name
    return tutoring_tool
