"""ExamExportService 服务层测试 — Word 文档导出（学生版/教师版）。

直接调用 ExamExportService 静态方法，使用 db_session fixture。
"""

import io
import zipfile
import pytest
from datetime import datetime, timezone

from app.services.exam_export_service import ExamExportService, ExamExportError
from app.models.exam_paper import ExamPaper, ExamPaperQuestion
from app.models.teaching import ExamRecord, Question


def _extract_doc_xml(buf: io.BytesIO) -> str:
    """从 docx BytesIO 中提取 word/document.xml 文本。"""
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        return zf.read("word/document.xml").decode("utf-8")


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

async def _create_question(db, **overrides):
    """创建测试题目。"""
    defaults = {
        "content": "测试题目内容",
        "question_type": "choice",
        "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
        "answer": "B",
        "analysis": "测试解析内容",
        "difficulty": "medium",
        "knowledge_point_tags": ["氧化还原反应"],
    }
    defaults.update(overrides)
    q = Question(**defaults)
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return q


async def _setup_exam_with_questions(db, num_questions=2):
    """创建含题目的考试（完整关联链）。"""
    # 创建 ExamRecord
    exam = ExamRecord(
        name="高一期末模拟考",
        class_id=1,
        exam_type="monthly",
        status="pending",
        exam_date=datetime.now(timezone.utc),
    )
    db.add(exam)
    await db.flush()

    # 创建 ExamPaper
    paper = ExamPaper(name="高一期末模拟考", teacher_id=1, status="draft")
    db.add(paper)
    await db.flush()

    exam.exam_paper_id = paper.id
    await db.flush()

    # 创建题目 + 关联
    questions = []
    for i in range(num_questions):
        q = Question(
            content=f"题目{i+1}: 这是第{i+1}道测试题",
            question_type="choice" if i % 2 == 0 else "calculation",
            options=["A", "B", "C", "D"] if i % 2 == 0 else [],
            answer=f"答案{i+1}",
            analysis=f"解析{i+1}",
            difficulty="medium",
            knowledge_point_tags=["氧化还原"],
        )
        db.add(q)
        await db.flush()
        epq = ExamPaperQuestion(
            exam_paper_id=paper.id,
            question_id=q.id,
            sort_order=i,
        )
        db.add(epq)
        questions.append(q)

    await db.commit()
    await db.refresh(exam)
    return exam, questions


# ═══════════════════════════════════════════════════════════════
# export_to_docx
# ═══════════════════════════════════════════════════════════════

class TestExportToDocx:
    """POST 导出 Word → export_to_docx。"""

    @pytest.mark.anyio
    async def test_nonexistent_exam_raises(self, db_session):
        """考试不存在 → ExamExportError。"""
        with pytest.raises(ExamExportError, match="考试不存在"):
            await ExamExportService.export_to_docx(db_session, exam_id=99999)

    @pytest.mark.anyio
    async def test_exam_without_questions_raises(self, db_session):
        """考试无题目 → ExamExportError。"""
        exam = ExamRecord(
            name="空考试", class_id=1, exam_type="monthly",
            status="pending", exam_date=datetime.now(timezone.utc),
        )
        db_session.add(exam)
        await db_session.commit()
        await db_session.refresh(exam)

        with pytest.raises(ExamExportError, match="暂无题目"):
            await ExamExportService.export_to_docx(db_session, exam_id=exam.id)

    @pytest.mark.anyio
    async def test_export_student_version(self, db_session):
        """导出学生版（无答案）。"""
        exam, _ = await _setup_exam_with_questions(db_session, num_questions=2)

        buf = await ExamExportService.export_to_docx(
            db_session, exam_id=exam.id, with_answers=False,
        )

        assert isinstance(buf, io.BytesIO)
        doc_xml = _extract_doc_xml(buf)
        assert len(doc_xml) > 0
        # 学生版不应含答案版标记
        assert "含答案版" not in doc_xml

    @pytest.mark.anyio
    async def test_export_teacher_version(self, db_session):
        """导出教师版（含答案+解析）。"""
        exam, _ = await _setup_exam_with_questions(db_session, num_questions=2)

        buf = await ExamExportService.export_to_docx(
            db_session, exam_id=exam.id, with_answers=True,
        )

        assert isinstance(buf, io.BytesIO)
        doc_xml = _extract_doc_xml(buf)
        assert len(doc_xml) > 0
        # 教师版应含标记
        assert "含答案版" in doc_xml

    @pytest.mark.anyio
    async def test_export_includes_exam_name(self, db_session):
        """导出文档包含考试名称。"""
        exam, _ = await _setup_exam_with_questions(db_session, num_questions=1)

        buf = await ExamExportService.export_to_docx(
            db_session, exam_id=exam.id,
        )
        doc_xml = _extract_doc_xml(buf)
        assert "高一期末模拟考" in doc_xml

    @pytest.mark.anyio
    async def test_export_includes_seal_line(self, db_session):
        """导出文档包含密封线（姓名/班级/得分）。"""
        exam, _ = await _setup_exam_with_questions(db_session, num_questions=1)

        buf = await ExamExportService.export_to_docx(
            db_session, exam_id=exam.id,
        )
        doc_xml = _extract_doc_xml(buf)
        assert "姓名" in doc_xml
        assert "班级" in doc_xml

    @pytest.mark.anyio
    async def test_teacher_version_has_answer_section(self, db_session):
        """教师版文档包含【答案】和【解析】标记。"""
        exam, _ = await _setup_exam_with_questions(db_session, num_questions=1)

        buf = await ExamExportService.export_to_docx(
            db_session, exam_id=exam.id, with_answers=True,
        )
        doc_xml = _extract_doc_xml(buf)
        assert "【答案】" in doc_xml
        assert "【解析】" in doc_xml

    @pytest.mark.anyio
    async def test_student_version_no_answer_section(self, db_session):
        """学生版文档不含【答案】标记。"""
        exam, _ = await _setup_exam_with_questions(db_session, num_questions=1)

        buf = await ExamExportService.export_to_docx(
            db_session, exam_id=exam.id, with_answers=False,
        )
        doc_xml = _extract_doc_xml(buf)
        assert "【答案】" not in doc_xml

    @pytest.mark.anyio
    async def test_calculation_questions_have_answer_area(self, db_session):
        """计算题文档包含"解："答题区。"""
        # 创建含计算题的考试
        exam = ExamRecord(
            name="计算题测试", class_id=1, exam_type="monthly",
            status="pending", exam_date=datetime.now(timezone.utc),
        )
        db_session.add(exam)
        await db_session.flush()
        paper = ExamPaper(name="计算题测试", teacher_id=1, status="draft")
        db_session.add(paper)
        await db_session.flush()
        exam.exam_paper_id = paper.id
        await db_session.flush()

        q = Question(
            content="计算题", question_type="calculation",
            answer="42", difficulty="medium",
        )
        db_session.add(q)
        await db_session.flush()
        db_session.add(ExamPaperQuestion(
            exam_paper_id=paper.id, question_id=q.id, sort_order=0,
        ))
        await db_session.commit()

        buf = await ExamExportService.export_to_docx(
            db_session, exam_id=exam.id, with_answers=False,
        )
        doc_xml = _extract_doc_xml(buf)
        assert "解：" in doc_xml
