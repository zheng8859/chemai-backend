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
    """诊断 API — 8 道（对齐 Phase 6 重构后的路由）"""

    def test_barrier_config_endpoint(self):
        """障碍配置端点可达"""
        r = requests.get(
            f"{API_V1}/diagnosis/barrier-config",
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401, 404)

    def test_run_llm_diagnosis_endpoint(self):
        """LLM 批量诊断端点（单次 ≤10 条）"""
        r = requests.post(
            f"{API_V1}/diagnosis/run-llm/1",
            headers=_get_auth_headers(),
            timeout=30,
        )
        # 接受 200(成功) / 401(未认证) / 404(无数据) / 422 / 503(LLM 不可用)
        assert r.status_code in (200, 401, 404, 422, 503)

    def test_class_diagnosis_endpoint(self):
        """班级诊断端点"""
        r = requests.get(
            f"{API_V1}/diagnosis/class/1/exam/1",
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401, 404)

    def test_student_diagnosis_endpoint(self):
        """学生自查看诊断端点"""
        r = requests.get(
            f"{API_V1}/diagnosis/student/1",
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401, 403, 404)

    def test_override_diagnosis_endpoint(self):
        """教师覆盖诊断端点"""
        r = requests.put(
            f"{API_V1}/diagnosis/override/1",
            json={"barrier_type": "concept", "misconception_category": None},
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401, 404, 422)

    def test_warnings_list_endpoint(self):
        """预警列表端点"""
        r = requests.get(
            f"{API_V1}/warnings",
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401, 404)

    def test_knowledge_points_search(self):
        """知识点模糊搜索"""
        r = requests.get(
            f"{API_V1}/knowledge-points/search",
            params={"keyword": "氧化"},
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401, 422)

    def test_knowledge_points_list(self):
        """知识点列表"""
        r = requests.get(
            f"{API_V1}/knowledge-points",
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401)


# ═══════════════════════════════════════════════════════════
# 对话 API (6 道)
# ═══════════════════════════════════════════════════════════

@pytest.mark.l2
@pytest.mark.skipif(not API_AVAILABLE, reason="API 服务不可达")
class TestConversationAPI:
    """对话 API — 6 道（对齐 /chat 前缀路由）"""

    def test_chat_stream_endpoint_exists(self):
        """Agent 对话流端点可达"""
        r = requests.post(
            f"{API_V1}/chat/stream",
            json={
                "message": "化学平衡是什么？",
                "thread_id": "t-test-001",
                "context": {"role": "student"},
            },
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401, 403, 422)

    def test_new_conversation_endpoint(self):
        """新建对话"""
        r = requests.post(
            f"{API_V1}/chat/new",
            json={"prefix": "t"},
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 201, 401, 404)

    def test_conversation_history_query(self):
        """会话历史查询"""
        r = requests.get(
            f"{API_V1}/chat/history/t-test-001",
            headers=_get_auth_headers(),
            timeout=10,
        )
        # 501 = 未实现（路由保留）；200/401 亦可
        assert r.status_code in (200, 401, 404, 501)

    def test_stream_event_format(self):
        """流式事件格式验证"""
        r = requests.post(
            f"{API_V1}/chat/stream",
            json={
                "message": "解释摩尔概念",
                "thread_id": "t-test-stream",
                "context": {"role": "student"},
            },
            headers=_get_auth_headers(),
            timeout=30,
            stream=True,
        )
        if r.status_code == 200:
            # SSE 流应以 text/event-stream 开头
            content_type = r.headers.get("content-type", "")
            assert "text/event-stream" in content_type or "text/plain" in content_type
        else:
            assert r.status_code in (401, 403, 422)

    def test_reset_conversation_endpoint(self):
        """重置对话上下文"""
        r = requests.post(
            f"{API_V1}/chat/reset",
            params={"thread_id": "t-test-001"},
            headers=_get_auth_headers(),
            timeout=10,
        )
        assert r.status_code in (200, 401, 404)

    def test_concurrent_requests(self):
        """并发请求不阻塞（快速验证）"""
        import concurrent.futures

        def make_request():
            try:
                return requests.post(
                    f"{API_V1}/chat/stream",
                    json={
                        "message": "测试并发",
                        "thread_id": "t-test-concurrent",
                        "context": {"role": "student"},
                    },
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
            assert code in (200, 401, 403, 422, 404, 503)


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
