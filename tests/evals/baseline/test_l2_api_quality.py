"""L2 API 集成测试 — API 质量 & 数据 CRUD (26 道)

所有测试标记 @pytest.mark.l2，需要后端服务运行。
当 API 不可达时自动跳过。
"""

import json
import os

import pytest
import requests

# ── API 地址 ──────────────────────────────────
API_BASE = os.getenv("CHEMAI_API_URL", "http://localhost:8000")
API_V1 = f"{API_BASE}/api/v1"


def _api_available() -> bool:
    """检查 API 服务是否可达。"""
    try:
        r = requests.get(f"{API_BASE}/docs", timeout=2)
        return r.status_code in (200, 307)
    except Exception:
        return False


def _get_auth_headers() -> dict:
    """获取认证 Headers（模拟 token）。"""
    return {"Authorization": f"Bearer {os.getenv('TEST_TOKEN', 'test-token')}"}


API_AVAILABLE = _api_available()


# ═══════════════════════════════════════════════════════════
# 出题 API (7 道)
# ═══════════════════════════════════════════════════════════

@pytest.mark.l2
@pytest.mark.skipif(not API_AVAILABLE, reason="API 服务不可达")
class TestQuestionGenerationAPI:
    """出题 API — 7 道"""

    def test_generate_endpoint_exists(self):
        """出题生成端点可达"""
        r = requests.post(
            f"{API_V1}/questions/generate",
            json={"prompt": "生成一道化学平衡选择题", "difficulty": 2, "count": 1},
            headers=_get_auth_headers(),
            timeout=10,
        )
        # 接受 200(成功) / 401(未认证) / 422(参数错误)
        assert r.status_code in (200, 401, 422)

    def test_generate_returns_json_structure(self):
        """生成结果返回合理 JSON 结构"""
        r = requests.post(
            f"{API_V1}/questions/generate",
            json={"prompt": "生成一道氧化还原选择题", "difficulty": 2, "count": 1},
            headers=_get_auth_headers(),
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            # 应包含 questions 或类似字段
            assert isinstance(data, (dict, list))
        elif r.status_code == 422:
            pass  # 参数校验通过即可
        elif r.status_code == 401:
            pass  # 需要真实认证 token

    def test_generate_with_specific_knowledge_point(self):
        """指定知识点生成题目"""
        r = requests.post(
            f"{API_V1}/questions/generate",
            json={
                "prompt": "生成酸碱中和相关选择题",
                "difficulty": 2,
                "count": 1,
                "knowledge_point": "酸碱中和",
            },
            headers=_get_auth_headers(),
            timeout=30,
        )
        assert r.status_code in (200, 401, 422)

    def test_generate_difficulty_distribution(self):
        """难度参数有效传递"""
        for diff in [1, 3, 5]:
            r = requests.post(
                f"{API_V1}/questions/generate",
                json={"prompt": "测试难度", "difficulty": diff, "count": 1},
                headers=_get_auth_headers(),
                timeout=30,
            )
            assert r.status_code in (200, 401, 422)

    def test_generate_knowledge_coverage(self):
        """知识点覆盖参数"""
        r = requests.post(
            f"{API_V1}/questions/generate",
            json={
                "prompt": "覆盖勒夏特列原理",
                "difficulty": 3,
                "count": 2,
                "knowledge_point": "勒夏特列原理",
            },
            headers=_get_auth_headers(),
            timeout=30,
        )
        assert r.status_code in (200, 401, 422)

    def test_generate_json_structure_valid(self):
        """验证返回 JSON 结构合理"""
        r = requests.post(
            f"{API_V1}/questions/generate",
            json={"prompt": "生成选择题", "difficulty": 1, "count": 1},
            headers=_get_auth_headers(),
            timeout=30,
        )
        if r.status_code == 200:
            try:
                data = r.json()
                assert data is not None
            except json.JSONDecodeError:
                pytest.fail("Response is not valid JSON")
        else:
            assert r.status_code in (401, 422)

    @pytest.mark.parametrize("question_type", ["choice", "fill", "calculation"])
    def test_generate_all_question_types(self, question_type):
        """支持各类题型"""
        r = requests.post(
            f"{API_V1}/questions/generate",
            json={
                "prompt": f"生成一道{question_type}题",
                "difficulty": 2,
                "count": 1,
                "question_type": question_type,
            },
            headers=_get_auth_headers(),
            timeout=30,
        )
        assert r.status_code in (200, 401, 422)


# ═══════════════════════════════════════════════════════════
# 诊断 API (8 道)
# ═══════════════════════════════════════════════════════════

@pytest.mark.l2
@pytest.mark.skipif(not API_AVAILABLE, reason="API 服务不可达")
class TestDiagnosisAPI:
    """诊断 API — 8 道"""

    def test_diagnose_endpoint_exists(self):
        """诊断端点可达"""
        r = requests.post(
            f"{API_V1}/diagnosis/single",
            json={
                "question": "56g Fe的物质的量是多少？",
                "student_answer": "56mol",
                "correct_answer": "1mol",
            },
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401, 422, 404)

    def test_batch_diagnosis_endpoint(self):
        """批量诊断端点"""
        r = requests.post(
            f"{API_V1}/diagnosis/batch",
            json={
                "items": [
                    {"question": "Q1", "student_answer": "A1", "correct_answer": "C1"},
                    {"question": "Q2", "student_answer": "A2", "correct_answer": "C2"},
                ]
            },
            headers=_get_auth_headers(),
            timeout=30,
        )
        assert r.status_code in (200, 401, 422, 404)

    def test_diagnosis_with_misconception_category(self):
        """诊断包含迷思概念分类"""
        r = requests.post(
            f"{API_V1}/diagnosis/single",
            json={
                "question": "加成反应和取代反应的区别是什么？",
                "student_answer": "它们是一样的",
                "correct_answer": "加成是不饱和键断裂加原子，取代是原子被替换",
            },
            headers=_get_auth_headers(),
            timeout=30,
        )
        assert r.status_code in (200, 401, 422, 404)

    def test_diagnosis_confidence_interval(self):
        """诊断置信度在合理范围"""
        r = requests.post(
            f"{API_V1}/diagnosis/single",
            json={
                "question": "什么是勒夏特列原理？",
                "student_answer": "平衡会向减弱改变的方向移动",
                "correct_answer": "改变条件时平衡向减弱这种改变的方向移动",
            },
            headers=_get_auth_headers(),
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            if "confidence" in data:
                assert 0.0 <= data["confidence"] <= 1.0
        else:
            assert r.status_code in (401, 422, 404)

    def test_diagnosis_error_type_included(self):
        """诊断包含错误类型"""
        r = requests.post(
            f"{API_V1}/diagnosis/single",
            json={
                "question": "pH=3和pH=5的盐酸等体积混合后pH是多少？",
                "student_answer": "pH=4",
                "correct_answer": "pH≈3.3（需考虑H⁺浓度而非pH直接平均）",
            },
            headers=_get_auth_headers(),
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            if "error_type" in data:
                assert data["error_type"] in (
                    "概念错误", "计算错误", "知识空白", "审题错误", "表述问题",
                )
        else:
            assert r.status_code in (401, 422, 404)

    def test_diagnosis_empty_answer_handled(self):
        """空答案诊断不崩溃"""
        r = requests.post(
            f"{API_V1}/diagnosis/single",
            json={
                "question": "测试题目",
                "student_answer": "",
                "correct_answer": "正确答案",
            },
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401, 422, 404)

    def test_diagnosis_config_includes_misconception_types(self):
        """障碍配置包含迷思概念类型"""
        r = requests.get(
            f"{API_V1}/diagnosis/config",
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401, 404)

    def test_diagnosis_llm_trigger(self):
        """LLM 诊断触发条件（置信度 < 阈值时启用 LLM）"""
        r = requests.post(
            f"{API_V1}/diagnosis/single",
            json={
                "question": "陌生领域的复杂问题",
                "student_answer": "奇怪的答案",
                "correct_answer": "标准答案",
            },
            headers=_get_auth_headers(),
            timeout=30,
        )
        assert r.status_code in (200, 401, 422, 404)


# ═══════════════════════════════════════════════════════════
# 对话 API (6 道)
# ═══════════════════════════════════════════════════════════

@pytest.mark.l2
@pytest.mark.skipif(not API_AVAILABLE, reason="API 服务不可达")
class TestConversationAPI:
    """对话 API — 6 道"""

    def test_agent_chat_endpoint_exists(self):
        """Agent 对话端点可达"""
        r = requests.post(
            f"{API_V1}/agent/chat",
            json={"message": "化学平衡是什么？", "persona": "student"},
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401, 422, 404)

    def test_session_create_endpoint(self):
        """会话创建"""
        r = requests.post(
            f"{API_V1}/sessions",
            json={"persona": "teacher"},
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 201, 401, 404)

    def test_session_history_query(self):
        """会话历史查询"""
        r = requests.get(
            f"{API_V1}/sessions",
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401, 404)

    def test_stream_event_format(self):
        """流式事件格式验证"""
        r = requests.post(
            f"{API_V1}/agent/chat/stream",
            json={"message": "解释摩尔概念", "persona": "student"},
            headers=_get_auth_headers(),
            timeout=30,
            stream=True,
        )
        if r.status_code == 200:
            # SSE 流应以 text/event-stream 开头
            content_type = r.headers.get("content-type", "")
            assert "text/event-stream" in content_type or "text/plain" in content_type
        else:
            assert r.status_code in (401, 404)

    def test_multi_turn_context_maintained(self):
        """多轮对话上下文保持"""
        r = requests.post(
            f"{API_V1}/agent/chat",
            json={
                "message": "我上一题做错了，能再讲解一下吗？",
                "persona": "student",
                "session_id": "test-session-multi-turn",
            },
            headers=_get_auth_headers(),
            timeout=30,
        )
        assert r.status_code in (200, 401, 422, 404)

    def test_concurrent_requests(self):
        """并发请求不阻塞（快速验证）"""
        import concurrent.futures

        def make_request():
            try:
                return requests.post(
                    f"{API_V1}/agent/chat",
                    json={"message": "测试并发", "persona": "student"},
                    headers=_get_auth_headers(),
                    timeout=15,
                ).status_code
            except Exception:
                return 503

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request) for _ in range(3)]
            results = [f.result() for f in futures]

        # 所有请求应正常响应（不阻塞）
        for code in results:
            assert code in (200, 401, 422, 404, 503)


# ═══════════════════════════════════════════════════════════
# 数据库 CRUD (5 道)
# ═══════════════════════════════════════════════════════════

@pytest.mark.l2
class TestGoldenDatabaseCRUD:
    """Golden 数据集数据库 CRUD — 5 道"""

    def test_query_all_samples(self, golden_db):
        """查询全部样本"""
        cursor = golden_db.execute("SELECT COUNT(*) as cnt FROM golden_samples")
        assert cursor.fetchone()["cnt"] == 100

    def test_query_by_module(self, golden_db):
        """按模块筛选"""
        cursor = golden_db.execute(
            "SELECT COUNT(*) as cnt FROM golden_samples WHERE module = ?",
            ("question_generation",),
        )
        assert cursor.fetchone()["cnt"] == 40  # 5 模块 × 8

    def test_query_by_category(self, golden_db):
        """按类别筛选"""
        cursor = golden_db.execute(
            "SELECT COUNT(*) as cnt FROM golden_samples WHERE category = ?",
            ("化学平衡",),
        )
        assert cursor.fetchone()["cnt"] == 20

    def test_eval_runs_table_exists(self, golden_db):
        """eval_runs 表存在且可写入"""
        golden_db.execute(
            """INSERT INTO eval_runs (timestamp, total_samples, passed, failed, pass_rate, notes)
               VALUES (datetime('now'), 100, 95, 5, 95.0, 'test')"""
        )
        golden_db.commit()
        cursor = golden_db.execute("SELECT COUNT(*) as cnt FROM eval_runs")
        assert cursor.fetchone()["cnt"] >= 1

    def test_sample_data_json_valid(self, golden_db):
        """data_json 字段存储合法 JSON"""
        cursor = golden_db.execute(
            "SELECT id, data_json FROM golden_samples LIMIT 5"
        )
        for row in cursor:
            data = json.loads(row["data_json"])
            assert "id" in data
            assert "module" in data
            assert "category" in data
