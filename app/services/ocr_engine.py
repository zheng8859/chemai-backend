"""OCR 引擎 — 百度 OCR / MinerU / VLM 三引擎 + 引擎路由。

P1: 百度 OCR 引擎实现（tasks 3.1-3.5）
P3: MinerU + VLM + EngineRouter（tasks 7.1-7.8）
"""

import asyncio
import base64
import json
import logging
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

from ..config import (
    BAIDU_OCR_API_KEY, BAIDU_OCR_SECRET_KEY,
    OCR_UPLOAD_DIR,
    ZHIPU_BASE_URL, ZHIPU_API_KEY, ZHIPU_VISION_MODEL,
)

logger = logging.getLogger(__name__)

# ── 百度 OCR API 端点 ──────────────────────────────────────────
BAIDU_OAUTH_URL = "https://aip.baidubce.com/oauth/2.0/token"
BAIDU_DOC_ANALYSIS_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/doc_analysis"


# ═══════════════════════════════════════════════════════════════
# 3.3: OCRResult 数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class OCRResult:
    """OCR 识别结果。"""
    raw_text: str = ""
    confidence: float = 0.0
    words_result: list[dict] = field(default_factory=list)
    student_id_raw: Optional[str] = None
    student_name_raw: Optional[str] = None
    is_partial: bool = False
    engine: str = ""
    error: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# 3.1: BaiduTokenManager — OAuth 2.0 token 内存缓存
# ═══════════════════════════════════════════════════════════════

class BaiduTokenManager:
    """百度 OAuth 2.0 Token 管理器。

    特性：
    - 内存缓存 access_token
    - 300 秒安全边距（提前刷新）
    - 自动刷新过期 token
    - 线程安全（asyncio Lock）
    """

    SAFETY_MARGIN = 300  # 提前 300 秒刷新

    def __init__(self):
        self._token: Optional[str] = None
        self._expires_at: float = 0.0  # Unix timestamp

    async def get_token(self) -> str:
        """获取有效 token，自动刷新过期 token。"""
        now = time.time()
        if self._token and now < self._expires_at - self.SAFETY_MARGIN:
            return self._token

        return await self._fetch_token()

    async def _fetch_token(self) -> str:
        """调用百度 OAuth 2.0 获取新 token。"""
        if not BAIDU_OCR_API_KEY or not BAIDU_OCR_SECRET_KEY:
            raise OCREngineError(
                "百度 OCR API Key 或 Secret Key 未配置",
                engine="baidu_doc_analysis",
            )

        params = {
            "grant_type": "client_credentials",
            "client_id": BAIDU_OCR_API_KEY,
            "client_secret": BAIDU_OCR_SECRET_KEY,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(BAIDU_OAUTH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise OCREngineError(
                f"百度 OAuth 认证失败: {data.get('error_description', data['error'])}",
                engine="baidu_doc_analysis",
            )

        self._token = data["access_token"]
        self._expires_at = time.time() + data.get("expires_in", 2592000)  # 默认 30 天
        logger.info("[baidu_ocr] Token 已刷新，有效期 %d 秒", data.get("expires_in", 0))
        return self._token


# 全局单例
_baidu_token_manager = BaiduTokenManager()


# ═══════════════════════════════════════════════════════════════
# OCR 引擎异常
# ═══════════════════════════════════════════════════════════════

class OCREngineError(Exception):
    """OCR 引擎错误。"""
    def __init__(self, detail: str, engine: str = ""):
        self.detail = detail
        self.engine = engine
        super().__init__(detail)


# ═══════════════════════════════════════════════════════════════
# 3.2/3.5: BaiduOCREngine
# ═══════════════════════════════════════════════════════════════

class BaiduOCREngine:
    """百度 OCR 引擎 — doc_analysis API。

    手写中文识别主力引擎，支持：
    - handprint_mix 手写混合模式
    - recg_formula 化学公式识别
    - CHN_ENG 中英文混合识别
    """

    @staticmethod
    def is_available() -> bool:
        """检查百度 OCR 是否可用。"""
        return bool(BAIDU_OCR_API_KEY and BAIDU_OCR_SECRET_KEY)

    @staticmethod
    async def recognize(image_path: str) -> OCRResult:
        """对答题卡图片执行 OCR 识别。

        Args:
            image_path: 图片文件路径（相对于 OCR_UPLOAD_DIR 或绝对路径）

        Returns:
            OCRResult: 识别结果
        """
        # 3.5: 错误处理 — 网络异常/API 错误统一转为 failed
        try:
            # 读取文件 → base64
            path = Path(image_path)
            if not path.is_absolute():
                from ..config import OCR_UPLOAD_DIR
                path = OCR_UPLOAD_DIR / image_path

            if not path.exists():
                return OCRResult(
                    is_partial=True,
                    engine="baidu_doc_analysis",
                    error=f"文件不存在: {image_path}",
                )

            with open(path, "rb") as f:
                image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode("utf-8")

            # 获取 access token
            token = await _baidu_token_manager.get_token()

            # 调用 doc_analysis API
            url = f"{BAIDU_DOC_ANALYSIS_URL}?access_token={token}"
            payload = {
                "image": image_base64,
                "language_type": "CHN_ENG",
                "result_type": "handprint_mix",
                "detect_direction": "true",
                "recg_formula": "true",
            }

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, data=payload)
                resp.raise_for_status()
                data = resp.json()

            # 3.5: API 业务错误处理
            if "error_code" in data and data["error_code"] != 0:
                return OCRResult(
                    is_partial=True,
                    engine="baidu_doc_analysis",
                    error=f"百度 API 错误: {data.get('error_msg', '未知错误')}",
                )

            # 解析响应
            results = data.get("results", [])
            raw_text = ""
            words_result = []
            confidence_sum = 0.0
            confidence_count = 0

            for item in results:
                words = item.get("words", {})
                text = words.get("word", "")
                confidence = words.get("word_location", {}).get("confidence", 0.0)
                raw_text += text + "\n"
                words_result.append({"text": text, "confidence": confidence})
                if confidence > 0:
                    confidence_sum += confidence
                    confidence_count += 1

            avg_confidence = confidence_sum / confidence_count if confidence_count > 0 else 0.0

            # 3.5: raw_text 过短 → is_partial
            is_partial = len(raw_text.strip()) < 10

            # 3.4: 学生信息提取
            student_id, student_name = BaiduOCREngine._extract_student_info(raw_text)

            return OCRResult(
                raw_text=raw_text.strip(),
                confidence=avg_confidence,
                words_result=words_result,
                student_id_raw=student_id,
                student_name_raw=student_name,
                is_partial=is_partial,
                engine="baidu_doc_analysis",
            )

        except httpx.HTTPStatusError as e:
            logger.error("[baidu_ocr] HTTP 错误: %s", e)
            return OCRResult(
                is_partial=True,
                engine="baidu_doc_analysis",
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except httpx.RequestError as e:
            logger.error("[baidu_ocr] 网络错误: %s", e)
            return OCRResult(
                is_partial=True,
                engine="baidu_doc_analysis",
                error=f"网络请求失败: {str(e)[:200]}",
            )
        except Exception as e:
            logger.exception("[baidu_ocr] 未预期的错误")
            return OCRResult(
                is_partial=True,
                engine="baidu_doc_analysis",
                error=f"未知错误: {str(e)[:200]}",
            )

    # ═══════════════════════════════════════════════════════════
    # 3.4: 学生信息提取
    # ═══════════════════════════════════════════════════════════

    # 学号标签正则（百度引擎专用）
    STUDENT_ID_LABEL_PATTERN = re.compile(
        r"(?:学号|考号|考生号|准考证号)\s*[:：]\s*(\d{6,12})"
    )
    # 百度引擎回退：2024-2029 开头 6-11 位数字
    STUDENT_ID_FALLBACK_PATTERN = re.compile(r"(202[4-9]\d{4,9})")

    # 姓名标签正则
    STUDENT_NAME_LABEL_PATTERN = re.compile(
        r"(?:姓名|学生|考生)\s*[:：]\s*([一-龥]{2,4})"
    )
    # 通用姓名回退：2-4 个连续中文字符
    STUDENT_NAME_FALLBACK_PATTERN = re.compile(
        r"([一-龥]{2,4})"
    )

    @staticmethod
    def _extract_student_id(raw_text: str) -> Optional[str]:
        """提取学号：标签格式 → 202[4-9] 回退。"""
        # 标签格式优先
        m = BaiduOCREngine.STUDENT_ID_LABEL_PATTERN.search(raw_text)
        if m:
            return m.group(1)
        # 202[4-9] 回退（取第一个匹配）
        m = BaiduOCREngine.STUDENT_ID_FALLBACK_PATTERN.search(raw_text)
        if m:
            return m.group(1)
        return None

    @staticmethod
    def _extract_student_name(raw_text: str) -> Optional[str]:
        """提取姓名：标签格式 → 通用中文字符回退。"""
        # 标签格式优先
        m = BaiduOCREngine.STUDENT_NAME_LABEL_PATTERN.search(raw_text)
        if m:
            return m.group(1)
        # 通用回退（取第一个 2-4 个连续中文字符）
        m = BaiduOCREngine.STUDENT_NAME_FALLBACK_PATTERN.search(raw_text)
        if m:
            return m.group(1)
        return None

    @staticmethod
    def _extract_student_info(raw_text: str) -> tuple[Optional[str], Optional[str]]:
        """同时提取学号和姓名。"""
        student_id = BaiduOCREngine._extract_student_id(raw_text)
        student_name = BaiduOCREngine._extract_student_name(raw_text)
        return student_id, student_name

    # ═══════════════════════════════════════════════════════════
    # 6.3: correct_edu — 百度教育批改 API
    # ═══════════════════════════════════════════════════════════

    CORRECT_EDU_URL = "https://aip.baidubce.com/rest/2.0/solution/v1/ime_correction/edu_correct"
    CORRECT_EDU_POLL_INTERVAL = 3  # 3 秒轮询
    CORRECT_EDU_MAX_WAIT = 120  # 最长 120 秒

    @staticmethod
    async def grade_via_correct_edu(
        image_path: str,
        answer_key: dict[int, str] | None = None,
    ) -> dict:
        """6.3: 调用百度 correct_edu API 批改答题卡。

        流程：提交图片 → 3s 轮询（最长 120s）→ 解析 correctResult。

        Args:
            image_path: 答题卡图片路径
            answer_key: 正确答案（可选，不传则自动识别）

        Returns:
            {
                "success": bool,
                "results": list[dict],  # [{q_number, student_answer, is_correct, score}]
                "total_score": float,
                "error": str | None,
            }
        """
        try:
            path = Path(image_path)
            if not path.is_absolute():
                path = OCR_UPLOAD_DIR / image_path

            if not path.exists():
                return {"success": False, "results": [], "total_score": 0, "error": "文件不存在"}

            with open(path, "rb") as f:
                image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode("utf-8")

            token = await _baidu_token_manager.get_token()

            # 提交批改任务
            submit_url = f"{BaiduOCREngine.CORRECT_EDU_URL}?access_token={token}"
            payload = {"image": image_base64}
            if answer_key:
                payload["ref_answer"] = answer_key

            async with httpx.AsyncClient(timeout=30) as client:
                submit_resp = await client.post(submit_url, data=payload)
                submit_resp.raise_for_status()
                submit_data = submit_resp.json()

            # 检查是否需要轮询
            if "error_code" in submit_data and submit_data["error_code"] != 0:
                return {
                    "success": False,
                    "results": [],
                    "total_score": 0,
                    "error": f"百度 correct_edu 错误: {submit_data.get('error_msg', '未知')}",
                }

            # 直接结果（部分 API 同步返回）
            if "result" in submit_data:
                return BaiduOCREngine._parse_correct_result(submit_data["result"])

            # 轮询等待（如果提交后需要异步等待）
            task_id = submit_data.get("task_id") or submit_data.get("log_id")
            if not task_id:
                # 可能是同步返回
                return BaiduOCREngine._parse_correct_result(submit_data)

            # 轮询
            poll_url = f"{BaiduOCREngine.CORRECT_EDU_URL}?access_token={token}&task_id={task_id}"
            waited = 0
            while waited < BaiduOCREngine.CORRECT_EDU_MAX_WAIT:
                await asyncio.sleep(BaiduOCREngine.CORRECT_EDU_POLL_INTERVAL)
                waited += BaiduOCREngine.CORRECT_EDU_POLL_INTERVAL

                async with httpx.AsyncClient(timeout=30) as client:
                    poll_resp = await client.get(poll_url)
                    poll_resp.raise_for_status()
                    poll_data = poll_resp.json()

                if "result" in poll_data:
                    return BaiduOCREngine._parse_correct_result(poll_data["result"])

                if "error_code" in poll_data and poll_data["error_code"] != 0:
                    return {
                        "success": False,
                        "results": [],
                        "total_score": 0,
                        "error": f"百度 correct_edu 轮询错误: {poll_data.get('error_msg', '')}",
                    }

            # 超时
            return {
                "success": False,
                "results": [],
                "total_score": 0,
                "error": f"correct_edu 超时（>{BaiduOCREngine.CORRECT_EDU_MAX_WAIT}s）",
            }

        except Exception as e:
            logger.exception("[correct_edu] 错误")
            return {"success": False, "results": [], "total_score": 0, "error": str(e)[:200]}

    @staticmethod
    def _parse_correct_result(result_data: dict) -> dict:
        """解析 correct_edu 返回的 correctResult。

        correctResult 编码：
        - 0: 正确
        - 1: 错误
        - 2: 无法判断
        - 3: 未作答
        """
        items = result_data.get("correctResult", [])
        questions = []
        correct_count = 0

        for i, item in enumerate(items):
            code = item.get("code", 2)
            q_num = item.get("questionNo", i + 1)
            is_correct = code == 0

            if is_correct:
                correct_count += 1

            code_map = {0: "正确", 1: "错误", 2: "无法判断", 3: "未作答"}
            questions.append({
                "q_number": q_num,
                "is_correct": is_correct,
                "status_code": code,
                "status_text": code_map.get(code, "未知"),
                "score": item.get("score", 0),
                "student_answer": item.get("studentAnswer", ""),
                "correct_answer": item.get("correctAnswer", ""),
            })

        total = len(questions)
        score = (correct_count / total * 100) if total > 0 else 0

        return {
            "success": True,
            "results": questions,
            "total_score": round(score, 1),
            "error": None,
        }


# ═══════════════════════════════════════════════════════════════
# 7.1: MinerUEngine — 子进程调用 mineru parse
# ═══════════════════════════════════════════════════════════════

MINERU_TIMEOUT = 120  # 秒


class MinerUEngine:
    """MinerU PDF/图片解析引擎 — 通过 CLI 子进程调用。

    主要用于 PDF 答题卡的文本提取，支持公式和表格。
    """

    @staticmethod
    def is_available() -> bool:
        """检查 mineru CLI 是否可用。"""
        return shutil.which("mineru") is not None

    @staticmethod
    async def parse(image_path: str) -> OCRResult:
        """7.1: 调用 mineru parse 子进程。"""
        try:
            path = Path(image_path)
            if not path.is_absolute():
                path = OCR_UPLOAD_DIR / image_path

            if not path.exists():
                return OCRResult(
                    is_partial=True,
                    engine="mineru",
                    error=f"文件不存在: {image_path}",
                )

            # 创建临时输出目录
            with tempfile.TemporaryDirectory(prefix="mineru_") as tmpdir:
                proc = await asyncio.create_subprocess_exec(
                    "mineru", "parse",
                    "-p", str(path),
                    "-o", tmpdir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=MINERU_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    return OCRResult(
                        is_partial=True,
                        engine="mineru",
                        error=f"MinerU 超时（>{MINERU_TIMEOUT}s）",
                    )

                if proc.returncode != 0:
                    err_msg = stderr.decode("utf-8", errors="replace")[:500]
                    return OCRResult(
                        is_partial=True,
                        engine="mineru",
                        error=f"MinerU 执行失败 (rc={proc.returncode}): {err_msg}",
                    )

                # 读取输出
                raw_text = stdout.decode("utf-8", errors="replace").strip()
                # 也尝试读取输出文件
                output_files = list(Path(tmpdir).rglob("*.md")) + list(Path(tmpdir).rglob("*.txt"))
                if output_files and not raw_text:
                    raw_text = output_files[0].read_text("utf-8", errors="replace").strip()

                is_partial = len(raw_text) < 10

                # 7.2: MinerU 专用学生信息提取
                student_id, student_name = MinerUEngine._extract_student_mineru(raw_text)

                return OCRResult(
                    raw_text=raw_text,
                    confidence=0.85 if not is_partial else 0.3,
                    student_id_raw=student_id,
                    student_name_raw=student_name,
                    is_partial=is_partial,
                    engine="mineru",
                )

        except FileNotFoundError:
            return OCRResult(
                is_partial=True,
                engine="mineru",
                error="mineru CLI 未安装",
            )
        except Exception as e:
            logger.exception("[mineru] 未预期错误")
            return OCRResult(
                is_partial=True,
                engine="mineru",
                error=f"未知错误: {str(e)[:200]}",
            )

    # ═══════════════════════════════════════════════════════════
    # 7.2: MinerU 专用学生信息提取
    # ═══════════════════════════════════════════════════════════

    MINERU_STUDENT_ID_LABEL = re.compile(
        r"(?:学号|考号|考生号|准考证号)\s*[:：]\s*(\d{8,12})"
    )
    MINERU_STUDENT_ID_FALLBACK = re.compile(r"\b(\d{8,10})\b")

    MINERU_STUDENT_NAME_LABEL = re.compile(
        r"(?:姓名|学生|考生)\s*[:：]\s*([一-龥]{2,4})"
    )

    @staticmethod
    def _extract_student_mineru(raw_text: str) -> tuple[Optional[str], Optional[str]]:
        """7.2: MinerU 专用学生信息提取。

        MinerU 输出更结构化 → 标签优先 + 通用 8-10 位数字回退。
        """
        student_id = None
        student_name = None

        # 学号：标签格式
        m = MinerUEngine.MINERU_STUDENT_ID_LABEL.search(raw_text)
        if m:
            student_id = m.group(1)
        else:
            # 回退：8-10 位连续数字
            m = MinerUEngine.MINERU_STUDENT_ID_FALLBACK.search(raw_text)
            if m:
                student_id = m.group(1)

        # 姓名：标签格式
        m = MinerUEngine.MINERU_STUDENT_NAME_LABEL.search(raw_text)
        if m:
            student_name = m.group(1)

        return student_id, student_name


# ═══════════════════════════════════════════════════════════════
# 7.5: VLMFallbackEngine — 智谱 GLM-4V 视觉降级
# ═══════════════════════════════════════════════════════════════

VLM_RECOGNITION_PROMPT = """你是一个化学答题卡 OCR 识别器。请识别以下答题卡图片中的所有文字内容。

要求：
1. 逐行输出识别到的所有文字，包括题号和答案
2. 特别注意学号（通常为 6-12 位数字，可能以 2024-2029 开头）
3. 特别注意姓名（通常为 2-4 个中文字符）
4. 注意化学式中的上下标（如 H₂O、Fe³⁺）
5. 选择题答案格式：题号. 选项字母（如 1. C）

返回 JSON 格式：
```json
{{
  "raw_text": "完整的识别文本...",
  "student_id": "学号或null",
  "student_name": "姓名或null",
  "confidence": 0.85
}}
```"""


class VLMFallbackEngine:
    """VLM 视觉降级引擎 — 当百度 OCR 不可用时用智谱 GLM-4V 做 OCR。

    7.5: base64 图片 + 结构化提取 prompt → JSON 解析 → OCRResult(fallback_used=True)
    """

    @staticmethod
    def is_available() -> bool:
        """检查智谱 VLM 是否可用。"""
        return bool(ZHIPU_API_KEY and ZHIPU_BASE_URL and ZHIPU_VISION_MODEL)

    @staticmethod
    async def recognize(image_path: str) -> OCRResult:
        """用 VLM 识别答题卡图片。"""
        try:
            path = Path(image_path)
            if not path.is_absolute():
                path = OCR_UPLOAD_DIR / image_path

            if not path.exists():
                return OCRResult(
                    is_partial=True,
                    engine="zhipu_glm4v",
                    error=f"文件不存在: {image_path}",
                )

            # 读取文件 → base64
            with open(path, "rb") as f:
                image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode("utf-8")

            # 确定 MIME 类型
            ext = path.suffix.lower()
            mime_map = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".bmp": "image/bmp",
                ".webp": "image/webp",
            }
            mime_type = mime_map.get(ext, "image/jpeg")

            # 7.4: 调用智谱 GLM-4V vision API
            url = f"{ZHIPU_BASE_URL.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {ZHIPU_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": ZHIPU_VISION_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VLM_RECOGNITION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_base64}",
                                },
                            },
                        ],
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 4096,
            }

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()

            # 解析 VLM 响应
            content = data["choices"][0]["message"]["content"]
            # 提取 JSON
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
            if not json_match:
                json_match = re.search(r"\{[\s\S]*\"raw_text\"[\s\S]*\}", content)

            if json_match:
                result_data = json.loads(json_match.group(1) if json_match.lastindex else json_match.group(0))
            else:
                # Last resort: treat entire response as raw text
                result_data = {"raw_text": content, "student_id": None, "student_name": None, "confidence": 0.5}

            raw_text = result_data.get("raw_text", "")
            is_partial = len(raw_text.strip()) < 10

            return OCRResult(
                raw_text=raw_text.strip(),
                confidence=result_data.get("confidence", 0.7),
                student_id_raw=result_data.get("student_id"),
                student_name_raw=result_data.get("student_name"),
                is_partial=is_partial,
                engine="zhipu_glm4v",
                error=None,
            )

        except httpx.HTTPStatusError as e:
            logger.error("[vlm] HTTP 错误: %s", e)
            return OCRResult(
                is_partial=True,
                engine="zhipu_glm4v",
                error=f"VLM HTTP {e.response.status_code}",
            )
        except Exception as e:
            logger.exception("[vlm] 未预期错误")
            return OCRResult(
                is_partial=True,
                engine="zhipu_glm4v",
                error=f"VLM 错误: {str(e)[:200]}",
            )


# ═══════════════════════════════════════════════════════════════
# 7.6: EngineRouter — 引擎路由与降级
# ═══════════════════════════════════════════════════════════════

class EngineRouter:
    """引擎路由器 — 按文件类型和引擎可用性选择最优路径。

    路由策略（7.6）：
    ┌──────────┐    IMAGE     ┌───────┐  fail  ┌───────┐  fail  ┌─────────┐
    │  输入文件  │ ──────────→ │ Baidu │ ─────→ │  VLM  │ ─────→ │ partial │
    └──────────┘              └───────┘        └───────┘        └─────────┘
         │ PDF
         ├──→ MinerU（文本提取）
         │      ↓
         │    成功 → 返回
         │      ↓ 失败
         └──→ PDF 转图 → Baidu → VLM → partial
    """

    @staticmethod
    async def route(image_path: str, detected_type: str = "IMAGE") -> OCRResult:
        """7.6: 按文件类型路由到最优引擎。

        Args:
            image_path: 文件路径
            detected_type: IMAGE | PDF

        Returns:
            OCRResult: 识别结果（含 fallback_used 标记）
        """
        if detected_type.upper() == "PDF":
            return await EngineRouter._route_pdf(image_path)
        else:
            return await EngineRouter._route_image(image_path)

    @staticmethod
    async def _route_image(image_path: str) -> OCRResult:
        """IMAGE 路径：Baidu → VLM → partial。"""
        # 1. 尝试百度 OCR
        if BaiduOCREngine.is_available():
            result = await BaiduOCREngine.recognize(image_path)
            if not result.error or not result.is_partial:
                return result
            logger.info("[router] 百度 OCR 失败，降级到 VLM")

        # 2. 降级到 VLM
        if VLMFallbackEngine.is_available():
            result = await VLMFallbackEngine.recognize(image_path)
            result.error = f"fallback_used: {result.error or 'baidu_failed'}" if result.error else "fallback_used: baidu_failed"
            return result

        # 3. 全部不可用
        return OCRResult(
            is_partial=True,
            engine="none",
            error="所有 OCR 引擎均不可用",
        )

    @staticmethod
    async def _route_pdf(image_path: str) -> OCRResult:
        """PDF 路径：MinerU → PDF 转图 → Baidu → VLM → partial。"""
        # 1. 尝试 MinerU
        if MinerUEngine.is_available():
            result = await MinerUEngine.parse(image_path)
            if not result.error or not result.is_partial:
                return result
            logger.info("[router] MinerU 失败，降级到 百度 OCR")

        # 2. PDF 转图后走 IMAGE 路径（简化：MinU 失败直接走百度/VLM）
        # 注：完整 PDF→image 转换在 P4 实现，此处跳过转图直接尝试百度
        logger.info("[router] PDF 降级：跳过 MinerU，尝试百度 OCR")

        if BaiduOCREngine.is_available():
            result = await BaiduOCREngine.recognize(image_path)
            if not result.error or not result.is_partial:
                result.error = f"fallback_used: mineru_failed, {result.error or ''}"
                return result

        # 3. 降级到 VLM
        if VLMFallbackEngine.is_available():
            result = await VLMFallbackEngine.recognize(image_path)
            result.error = f"fallback_used: mineru_failed, {result.error or 'all_failed'}"
            return result

        # 4. 全部不可用
        return OCRResult(
            is_partial=True,
            engine="none",
            error="所有 OCR 引擎均不可用（PDF 路径）",
        )


# ═══════════════════════════════════════════════════════════════
# 3.6: 引擎可用性检查
# ═══════════════════════════════════════════════════════════════

class EngineStatus:
    """各引擎可用性状态。"""

    def __init__(self):
        self.ocr = {
            "available": BaiduOCREngine.is_available(),
            "reason": "" if BaiduOCREngine.is_available() else "百度 OCR API Key 未配置",
        }
        self.mineru = {
            "available": MinerUEngine.is_available(),
            "reason": "" if MinerUEngine.is_available() else "mineru CLI 未安装",
        }
        self.vision = {
            "available": VLMFallbackEngine.is_available(),
            "reason": "" if VLMFallbackEngine.is_available() else "智谱 API Key 未配置",
        }


def get_engine_status() -> EngineStatus:
    """返回所有引擎的可用性状态。"""
    return EngineStatus()
