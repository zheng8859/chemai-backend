"""Diagnosis API 集成测试 — LLM 诊断 + 教师覆盖。

使用 conftest fixtures 实现隔离。
"""

import pytest


class TestTeacherOverride:
    """教师覆盖诊断结果。"""

    @pytest.mark.anyio
    async def test_override_nonexistent_answer(self, async_client, teacher_headers):
        """覆盖不存在的作答 → 404。"""
        resp = await async_client.put(
            "/api/v1/diagnosis/override/99999",
            json={"barrier_type": "concept", "misconception_category": "redox"},
            headers=teacher_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_override_invalid_barrier_type(self, async_client, teacher_headers):
        """非法 barrier_type → 422 校验失败。"""
        resp = await async_client.put(
            "/api/v1/diagnosis/override/1",
            json={"barrier_type": "invalid_type"},
            headers=teacher_headers,
        )
        assert resp.status_code in (404, 422)


class TestLLMDiagnosis:
    """LLM 诊断运行。"""

    @pytest.mark.anyio
    async def test_run_llm_nonexistent_exam(self, async_client, teacher_headers):
        """对不存在的考试触发诊断 → 404。"""
        resp = await async_client.post(
            "/api/v1/diagnosis/run-llm/99999",
            headers=teacher_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_run_llm_no_llm_provider(self, async_client, teacher_headers):
        """无 LLM Provider 配置时触发诊断 → 503 或成功（取决于环境）。

        如果环境配置了 LLM Key，此测试仍通过。
        仅验证端点可访问性和响应格式。
        """
        resp = await async_client.post(
            "/api/v1/diagnosis/run-llm/1",
            headers=teacher_headers,
        )
        assert resp.status_code in (200, 404, 503)

        if resp.status_code == 200:
            data = resp.json()
            assert "success" in data
            assert "analyzed_count" in data
            assert "failed_count" in data
            assert "remaining_count" in data


class TestClassDiagnosis:
    """班级诊断聚合。"""

    @pytest.mark.anyio
    async def test_get_class_diagnosis(self, async_client, teacher_headers):
        """获取班级诊断 → 验证响应格式（可能为空数据）。"""
        resp = await async_client.get(
            "/api/v1/diagnosis/class/1/exam/1",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "class_summary" in data
        assert "students" in data
        summary = data["class_summary"]
        assert "concept_rate" in summary
        assert "reading_rate" in summary
        assert "expression_rate" in summary
