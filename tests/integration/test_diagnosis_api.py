"""Diagnosis API 集成测试 — LLM 诊断 + 教师覆盖。

需要运行中的数据库（Phase 2 migration 已执行）。
"""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.security import create_access_token


def _auth_header(role="teacher", sub_role="teacher", school_id=1, user_id=1):
    token = create_access_token(
        user_id=user_id, role=role, school_id=school_id, sub_role=sub_role
    )
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════
# Teacher Override 测试
# ═══════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_override_nonexistent_answer():
    """覆盖不存在的作答 → 404。"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/api/v1/diagnosis/override/99999",
            json={"barrier_type": "concept", "misconception_category": "redox"},
            headers=_auth_header(),
        )
        assert resp.status_code == 404


@pytest.mark.anyio
async def test_override_invalid_barrier_type():
    """非法 barrier_type → 422 校验失败。"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/api/v1/diagnosis/override/1",
            json={"barrier_type": "invalid_type"},
            headers=_auth_header(),
        )
        # Pydantic 校验在端点层面不做枚举验证（留给 service），
        # 但如果 schema 加了 Field 约束则 422
        assert resp.status_code in (404, 422)


# ═══════════════════════════════════════════════════════════════
# LLM Diagnosis Run 测试
# ═══════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_run_llm_nonexistent_exam():
    """对不存在的考试触发诊断 → 404。"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/diagnosis/run-llm/99999",
            headers=_auth_header(),
        )
        assert resp.status_code == 404


@pytest.mark.anyio
async def test_run_llm_no_llm_provider():
    """无 LLM Provider 配置时触发诊断 → 503 或成功（取决于环境）。

    如果环境配置了 LLM Key，此测试仍通过。
    仅验证端点可访问性和响应格式。
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/diagnosis/run-llm/1",
            headers=_auth_header(),
        )
        # 可能的结果：
        # - 404：考试不存在
        # - 503：LLM Provider 不可用
        # - 200：已有种子数据 + LLM 可用
        assert resp.status_code in (200, 404, 503)

        if resp.status_code == 200:
            data = resp.json()
            assert "success" in data
            assert "analyzed_count" in data
            assert "failed_count" in data
            assert "remaining_count" in data


# ═══════════════════════════════════════════════════════════════
# Class Diagnosis 聚合测试
# ═══════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_get_class_diagnosis():
    """获取班级诊断 → 验证响应格式（可能为空数据）。"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/diagnosis/class/1/exam/1",
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "class_summary" in data
        assert "students" in data
        # class_summary 应有三个比率字段
        summary = data["class_summary"]
        assert "concept_rate" in summary
        assert "reading_rate" in summary
        assert "expression_rate" in summary
