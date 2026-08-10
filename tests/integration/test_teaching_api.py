"""Teaching API 集成测试 — Exam/Question CRUD + 导入 + RBAC。

所有测试使用 conftest fixtures 实现完全隔离。
"""

import pytest


NOW = "2026-08-07T10:00:00"


class TestExamCRUD:
    """考试 CRUD — POST/GET/PATCH/DELETE /exams。"""

    @pytest.mark.anyio
    async def test_create_exam(self, async_client, teacher_headers, class_):
        """教师可创建考试。"""
        resp = await async_client.post(
            "/api/v1/exams",
            json={"class_id": class_["id"], "exam_type": "monthly", "exam_date": NOW},
            headers=teacher_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["class_id"] == class_["id"]
        assert data["exam_type"] == "monthly"

    @pytest.mark.anyio
    async def test_list_exams(self, async_client, teacher_headers, class_):
        """列出所有考试（可按班级过滤）。"""
        # 创建考试
        resp = await async_client.post(
            "/api/v1/exams",
            json={"class_id": class_["id"], "exam_type": "practice", "exam_date": NOW},
            headers=teacher_headers,
        )
        assert resp.status_code == 201

        resp = await async_client.get(
            "/api/v1/exams", headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.anyio
    async def test_get_exam(self, async_client, teacher_headers, class_):
        """获取考试详情。"""
        resp = await async_client.post(
            "/api/v1/exams",
            json={"class_id": class_["id"], "exam_type": "homework", "exam_date": NOW},
            headers=teacher_headers,
        )
        exam_id = resp.json()["id"]

        resp = await async_client.get(
            f"/api/v1/exams/{exam_id}", headers=teacher_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == exam_id

    @pytest.mark.anyio
    async def test_update_exam(self, async_client, teacher_headers, class_):
        """更新考试名称。"""
        resp = await async_client.post(
            "/api/v1/exams",
            json={"class_id": class_["id"], "exam_type": "monthly", "exam_date": NOW},
            headers=teacher_headers,
        )
        exam_id = resp.json()["id"]

        resp = await async_client.patch(
            f"/api/v1/exams/{exam_id}",
            params={"name": "更新后名称"},
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "更新后名称"

    @pytest.mark.anyio
    async def test_delete_exam(self, async_client, teacher_headers, class_):
        """删除考试 → 204。"""
        resp = await async_client.post(
            "/api/v1/exams",
            json={"class_id": class_["id"], "exam_type": "practice", "exam_date": NOW},
            headers=teacher_headers,
        )
        exam_id = resp.json()["id"]

        resp = await async_client.delete(
            f"/api/v1/exams/{exam_id}", headers=teacher_headers,
        )
        assert resp.status_code == 204

    @pytest.mark.anyio
    async def test_get_nonexistent_exam_404(self, async_client, teacher_headers):
        """获取不存在考试 → 404。"""
        resp = await async_client.get(
            "/api/v1/exams/99999", headers=teacher_headers,
        )
        assert resp.status_code == 404


class TestQuestionCRUD:
    """题目 CRUD — POST/GET/PATCH/DELETE /questions。"""

    @pytest.mark.anyio
    async def test_create_question(self, async_client, teacher_headers):
        """教师可创建题目。"""
        resp = await async_client.post(
            "/api/v1/questions",
            json={
                "content": "下列物质中属于电解质的是？",
                "question_type": "choice",
                "options": ["A. 蔗糖", "B. 氯化钠", "C. 酒精", "D. 二氧化碳"],
                "answer": "B",
                "difficulty": "easy",
                "knowledge_point_tags": ["电解质"],
            },
            headers=teacher_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["content"] == "下列物质中属于电解质的是？"
        assert data["answer"] == "B"

    @pytest.mark.anyio
    async def test_list_questions(self, async_client, teacher_headers):
        """列出题目（可按难度/类型/知识点过滤）。"""
        resp = await async_client.post(
            "/api/v1/questions",
            json={
                "content": "测试题目",
                "question_type": "choice",
                "options": ["A", "B", "C", "D"],
                "answer": "A",
                "difficulty": "medium",
            },
            headers=teacher_headers,
        )
        assert resp.status_code == 201

        resp = await async_client.get(
            "/api/v1/questions", headers=teacher_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.anyio
    async def test_get_question(self, async_client, teacher_headers):
        """获取题目详情。"""
        resp = await async_client.post(
            "/api/v1/questions",
            json={
                "content": "专属题目",
                "question_type": "fill_blank",
                "answer": "O2",
                "difficulty": "hard",
            },
            headers=teacher_headers,
        )
        qid = resp.json()["id"]

        resp = await async_client.get(
            f"/api/v1/questions/{qid}", headers=teacher_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "专属题目"

    @pytest.mark.anyio
    async def test_delete_question(self, async_client, teacher_headers):
        """删除题目 → 204。"""
        resp = await async_client.post(
            "/api/v1/questions",
            json={
                "content": "待删除",
                "question_type": "choice",
                "options": ["A", "B"],
                "answer": "A",
                "difficulty": "easy",
            },
            headers=teacher_headers,
        )
        qid = resp.json()["id"]

        resp = await async_client.delete(
            f"/api/v1/questions/{qid}", headers=teacher_headers,
        )
        assert resp.status_code == 204

    @pytest.mark.anyio
    async def test_get_nonexistent_question_404(self, async_client, teacher_headers):
        """获取不存在题目 → 404。"""
        resp = await async_client.get(
            "/api/v1/questions/99999", headers=teacher_headers,
        )
        assert resp.status_code == 404


class TestQuestionImport:
    """POST /questions/import — 批量导入题目。"""

    @pytest.mark.anyio
    async def test_import_questions(self, async_client, teacher_headers):
        """批量导入题目。"""
        resp = await async_client.post(
            "/api/v1/questions/import",
            json={
                "source_name": "2024年长沙市一模",
                "questions": [
                    {
                        "content": "氧化还原反应的本质是？",
                        "question_type": "choice",
                        "options": ["A. 化合价变化", "B. 电子转移", "C. 氧的得失", "D. 氢的得失"],
                        "answer": "B",
                        "difficulty": "medium",
                        "knowledge_point_tags": ["氧化还原"],
                    },
                    {
                        "content": "计算0.1mol/L HCl的pH值",
                        "question_type": "calculation",
                        "answer": "1",
                        "difficulty": "easy",
                        "knowledge_point_tags": ["pH计算"],
                    },
                ],
            },
            headers=teacher_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["imported_count"] == 2
        assert len(data["questions"]) == 2


class TestTeachingRBAC:
    """教学 API 权限测试。"""

    @pytest.mark.anyio
    async def test_student_cannot_create_exam(self, async_client, student_headers, class_):
        """学生无权创建考试 → 403。"""
        resp = await async_client.post(
            "/api/v1/exams",
            json={"class_id": class_["id"], "exam_type": "monthly", "exam_date": NOW},
            headers=student_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_student_cannot_create_question(self, async_client, student_headers):
        """学生无权创建题目 → 403。"""
        resp = await async_client.post(
            "/api/v1/questions",
            json={
                "content": "越权题目",
                "question_type": "choice",
                "options": ["A", "B"],
                "answer": "A",
            },
            headers=student_headers,
        )
        assert resp.status_code == 403


class TestExamQuestions:
    """考试-题目关联 — POST/GET/DELETE /exams/{id}/questions。"""

    @pytest.mark.anyio
    async def test_add_questions_to_exam(self, async_client, teacher_headers, class_):
        """添加题目到考试。"""
        # 创建考试
        resp = await async_client.post(
            "/api/v1/exams",
            json={"class_id": class_["id"], "exam_type": "monthly", "exam_date": NOW},
            headers=teacher_headers,
        )
        exam_id = resp.json()["id"]

        # 创建题目
        resp = await async_client.post(
            "/api/v1/questions",
            json={
                "content": "关联题目",
                "question_type": "choice",
                "options": ["A", "B", "C", "D"],
                "answer": "C",
                "difficulty": "medium",
            },
            headers=teacher_headers,
        )
        qid = resp.json()["id"]

        # 关联到考试
        resp = await async_client.post(
            f"/api/v1/exams/{exam_id}/questions",
            params={"question_ids": [qid]},
            headers=teacher_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True

    @pytest.mark.anyio
    async def test_get_exam_questions_empty(self, async_client, teacher_headers, class_):
        """空考试题目列表。"""
        resp = await async_client.post(
            "/api/v1/exams",
            json={"class_id": class_["id"], "exam_type": "monthly", "exam_date": NOW},
            headers=teacher_headers,
        )
        exam_id = resp.json()["id"]

        resp = await async_client.get(
            f"/api/v1/exams/{exam_id}/questions",
            headers=teacher_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["questions"] == []
