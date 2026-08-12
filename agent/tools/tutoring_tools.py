"""通用辅导工具集 — 化学讲解、实验模拟、方程式配平。

所有工具通过 @register_tool 注册。
"""

import logging

from .tool_meta import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="chemistry_tutor",
    persona=["teacher", "tutor", "student"],
    call_limit=10,
    description="通用化学知识讲解工具。教师模式 800 字详解，学生模式 500 字引导式讲解。根据当前 persona 自动切换。",
)
async def chemistry_tutor(
    topic: str,
    persona: str = "student",
    context: str = "",
) -> dict:
    """化学知识讲解。

    Args:
        topic: 讲解主题
        persona: 当前角色（teacher→800字详解，student→500字引导）
        context: 额外上下文

    Returns:
        结构化讲解参数，LLM 将基于此生成实际内容。
    """
    max_length = 800 if persona == "teacher" else 500
    return {
        "mode": "detailed" if persona == "teacher" else "guided",
        "topic": topic,
        "max_length": max_length,
        "guidance": (
            "请以教师身份详细讲解，包含示例和注意事项" if persona == "teacher"
            else "请以苏格拉底式提问引导学生理解，每次只问一个问题"
        ),
    }


@register_tool(
    name="simulate_experiment",
    persona=["teacher", "tutor", "student"],
    call_limit=5,
    description="模拟化学实验并生成实验报告。传入实验名称，返回实验步骤、现象描述、化学方程式和安全注意事项。",
)
async def simulate_experiment(experiment_name: str) -> dict:
    """模拟化学实验。"""
    return {
        "experiment": {
            "name": experiment_name,
            "steps": [],
            "phenomena": "",
            "equations": [],
            "safety_notes": [],
        },
        "_component": {
            "type": "experiment-card",
            "experiment_name": experiment_name,
        },
        "message": f"正在模拟「{experiment_name}」实验...",
    }


@register_tool(
    name="balance_equation",
    persona=["teacher", "tutor"],
    call_limit=20,
    description="化学方程式配平（确定性算法，100% 准确）。传入反应物和生成物，返回配平后的方程式。",
)
async def balance_equation(reactants: str, products: str) -> dict:
    """化学方程式配平。"""
    try:
        from chem_skills.chemistry_parser.engine.equation_parser import parse_and_balance
        result = await parse_and_balance(reactants, products)
        return {
            "balanced": result.get("balanced_equation", ""),
            "coefficients": result.get("coefficients", {}),
            "equation_type": result.get("type", "unknown"),
            "verified": True,
        }
    except ImportError:
        logger.warning("chemistry_parser engine 不可用，跳过配平")
        return {
            "balanced": "",
            "error": "配平引擎暂不可用",
            "verified": False,
        }
    except Exception as e:
        logger.warning("方程式配平失败: %s", e)
        return {
            "balanced": "",
            "error": str(e),
            "verified": False,
        }
