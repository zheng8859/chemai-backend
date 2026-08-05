"""四维安全审核 API — 出题工作台调用入口。

端点:
  POST /api/v1/audit/equation    — 审核单个化学方程式
  POST /api/v1/audit/extract     — 从文本中提取并审核所有方程式
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from chem_skills.chemistry_parser.engine import (
    audit_equation,
    extract_equations,
    AuditReport,
)

router = APIRouter(prefix="/audit", tags=["audit"])


# ── Request/Response models ──────────────────────────────────

class AuditEquationRequest(BaseModel):
    equation: str = Field(..., min_length=1, description="待审核的化学方程式")
    question_id: str = Field("", description="可选的题目标识符")


class AuditExtractRequest(BaseModel):
    text: str = Field(..., min_length=1, description="含方程式的文本")
    question_id: str = Field("", description="可选的题目标识符")


class AuditEquationResponse(BaseModel):
    """单个方程式审核响应"""
    question_id: str
    equation: str
    overall_status: str
    overall_message: str
    balance: dict | None
    condition: dict | None
    product: dict | None
    structure: dict | None


class AuditExtractResponse(BaseModel):
    """批量方程式审核响应"""
    success: bool = True
    equations_found: int
    reports: list[AuditEquationResponse]


# ── Endpoints ────────────────────────────────────────────────

@router.post("/equation", response_model=AuditEquationResponse)
async def audit_single_equation(request: AuditEquationRequest):
    """审核单个化学方程式。

    返回四维审核报告（配平/条件/产物/结构 + 综合判定）。

    Example:
        POST /api/v1/audit/equation
        {"equation": "Fe + O2 → Fe2O3"}

    Response:
        {
          "equation": "Fe + O2 → Fe2O3",
          "overall_status": "blocked",
          "overall_message": "[配平] 方程式未配平: Fe: 左1 vs 右2; O: 左2 vs 右3",
          "balance": {"status": "blocked", ...},
          "condition": {"status": "failed", ...},
          ...
        }
    """
    try:
        report = audit_equation(request.equation, question_id=request.question_id)
        return _report_to_dict(report)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"审核失败: {str(e)}",
        )


@router.post("/extract", response_model=AuditExtractResponse)
async def audit_extract_equations(request: AuditExtractRequest):
    """从文本中提取所有方程式并逐一审核。

    用于出题引擎在生成的题目内容中自动提取方程式并过审。

    Example:
        POST /api/v1/audit/extract
        {"text": "甲烷燃烧: CH4 + 2O2 → CO2 + 2H2O"}

    Response:
        {
          "equations_found": 1,
          "reports": [...]
        }
    """
    try:
        eqs = extract_equations(request.text)
        reports = []
        for eq in eqs:
            report = audit_equation(eq, question_id=request.question_id)
            reports.append(_report_to_dict(report))

        return {
            "success": True,
            "equations_found": len(eqs),
            "reports": reports,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"提取审核失败: {str(e)}",
        )


# ── Helper ───────────────────────────────────────────────────

def _report_to_dict(report: AuditReport) -> dict:
    """将 AuditReport 转为 JSON 友好的 dict。"""
    return {
        "question_id": report.question_id,
        "equation": report.equation,
        "overall_status": report.overall_status,
        "overall_message": report.overall_message,
        "balance": {
            "status": report.balance.status,
            "message": report.balance.message,
            "detail": {
                "left_elements": report.balance.detail.left_elements if report.balance.detail else {},
                "right_elements": report.balance.detail.right_elements if report.balance.detail else {},
            },
        } if report.balance else None,
        "condition": {
            "status": report.condition.status,
            "message": report.condition.message,
            "conditions_found": report.condition.conditions_found,
            "missing_conditions": report.condition.missing_conditions,
            "contradictions": report.condition.contradictions,
        } if report.condition else None,
        "product": {
            "status": report.product.status,
            "message": report.product.message,
            "issues": report.product.issues,
        } if report.product else None,
        "structure": {
            "status": report.structure.status,
            "message": report.structure.message,
            "issues": report.structure.issues,
        } if report.structure else None,
    }
