"""7.9: engine router unit tests — routing logic + fallback trigger."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.ocr_engine import (
    EngineRouter,
    MinerUEngine,
    VLMFallbackEngine,
    BaiduOCREngine,
    OCRResult,
)


# ================================================================
# Engine route selection tests
# ================================================================

class TestEngineRouterImage:
    """IMAGE path: Baidu → VLM → partial."""

    @pytest.mark.asyncio
    async def test_image_route_baidu_success(self):
        """百度可用且成功 → 直接返回。"""
        mock_result = OCRResult(
            raw_text="1. C  2. B", confidence=0.95,
            engine="baidu_doc_analysis",
        )
        with patch.object(BaiduOCREngine, "is_available", return_value=True):
            with patch.object(BaiduOCREngine, "recognize", new_callable=AsyncMock) as mock_rec:
                mock_rec.return_value = mock_result
                result = await EngineRouter._route_image("/path/to/img.jpg")
        assert result.engine == "baidu_doc_analysis"
        assert result.raw_text == "1. C  2. B"

    @pytest.mark.asyncio
    async def test_image_route_baidu_partial_fallback_to_vlm(self):
        """百度返回 partial → 降级到 VLM。"""
        baidu_result = OCRResult(
            is_partial=True, engine="baidu_doc_analysis",
            error="low quality",
        )
        vlm_result = OCRResult(
            raw_text="1. C", confidence=0.7, engine="zhipu_glm4v",
        )
        with patch.object(BaiduOCREngine, "is_available", return_value=True):
            with patch.object(BaiduOCREngine, "recognize", new_callable=AsyncMock) as mock_baidu:
                mock_baidu.return_value = baidu_result
                with patch.object(VLMFallbackEngine, "is_available", return_value=True):
                    with patch.object(VLMFallbackEngine, "recognize", new_callable=AsyncMock) as mock_vlm:
                        mock_vlm.return_value = vlm_result
                        result = await EngineRouter._route_image("/path/to/img.jpg")
        assert result.engine == "zhipu_glm4v"

    @pytest.mark.asyncio
    async def test_image_route_baidu_unavailable_vlm_fallback(self):
        """百度不可用 → 直接用 VLM。"""
        vlm_result = OCRResult(
            raw_text="1. C", confidence=0.7, engine="zhipu_glm4v",
        )
        with patch.object(BaiduOCREngine, "is_available", return_value=False):
            with patch.object(VLMFallbackEngine, "is_available", return_value=True):
                with patch.object(VLMFallbackEngine, "recognize", new_callable=AsyncMock) as mock_vlm:
                    mock_vlm.return_value = vlm_result
                    result = await EngineRouter._route_image("/path/to/img.jpg")
        assert result.engine == "zhipu_glm4v"

    @pytest.mark.asyncio
    async def test_image_route_all_unavailable(self):
        """全部不可用 → 返回 none。"""
        with patch.object(BaiduOCREngine, "is_available", return_value=False):
            with patch.object(VLMFallbackEngine, "is_available", return_value=False):
                result = await EngineRouter._route_image("/path/to/img.jpg")
        assert result.engine == "none"
        assert result.is_partial is True
        assert "不可用" in (result.error or "")


class TestEngineRouterPDF:
    """PDF path: MinerU → Baidu → VLM → partial."""

    @pytest.mark.asyncio
    async def test_pdf_route_mineru_success(self):
        """MinerU 可用且成功。"""
        mineru_result = OCRResult(
            raw_text="1. C  2. B  16. H2O",
            confidence=0.85, engine="mineru",
        )
        with patch.object(MinerUEngine, "is_available", return_value=True):
            with patch.object(MinerUEngine, "parse", new_callable=AsyncMock) as mock_parse:
                mock_parse.return_value = mineru_result
                result = await EngineRouter._route_pdf("/path/to/doc.pdf")
        assert result.engine == "mineru"
        assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_pdf_route_mineru_fails_baidu_fallback(self):
        """MinerU 失败 → Baidu 降级。"""
        mineru_result = OCRResult(
            is_partial=True, engine="mineru", error="parse error",
        )
        baidu_result = OCRResult(
            raw_text="1. C", confidence=0.9, engine="baidu_doc_analysis",
        )
        with patch.object(MinerUEngine, "is_available", return_value=True):
            with patch.object(MinerUEngine, "parse", new_callable=AsyncMock) as mock_mineru:
                mock_mineru.return_value = mineru_result
                with patch.object(BaiduOCREngine, "is_available", return_value=True):
                    with patch.object(BaiduOCREngine, "recognize", new_callable=AsyncMock) as mock_baidu:
                        mock_baidu.return_value = baidu_result
                        result = await EngineRouter._route_pdf("/path/to/doc.pdf")
        assert result.engine == "baidu_doc_analysis"

    @pytest.mark.asyncio
    async def test_pdf_route_all_unavailable(self):
        """MinerU→Baidu→VLM 全部不可用。"""
        with patch.object(MinerUEngine, "is_available", return_value=False):
            with patch.object(BaiduOCREngine, "is_available", return_value=False):
                with patch.object(VLMFallbackEngine, "is_available", return_value=False):
                    result = await EngineRouter._route_pdf("/path/to/doc.pdf")
        assert result.engine == "none"
        assert result.is_partial is True


# ================================================================
# EngineRouter.route() top-level dispatch
# ================================================================

class TestEngineRouterDispatch:

    @pytest.mark.asyncio
    async def test_image_detected_type_routes_to_image_path(self):
        """detected_type=IMAGE → _route_image。"""
        with patch.object(EngineRouter, "_route_image", new_callable=AsyncMock) as mock_img:
            mock_img.return_value = OCRResult(engine="test")
            await EngineRouter.route("/path/img.jpg", "IMAGE")
            mock_img.assert_called_once()

    @pytest.mark.asyncio
    async def test_pdf_detected_type_routes_to_pdf_path(self):
        """detected_type=PDF → _route_pdf。"""
        with patch.object(EngineRouter, "_route_pdf", new_callable=AsyncMock) as mock_pdf:
            mock_pdf.return_value = OCRResult(engine="test")
            await EngineRouter.route("/path/doc.pdf", "PDF")
            mock_pdf.assert_called_once()


# ================================================================
# MinerU engine tests
# ================================================================

class TestMinerUEngine:

    def test_mineru_is_available(self):
        """is_available checks for CLI presence."""
        # Just check it returns bool, don't depend on env
        result = MinerUEngine.is_available()
        assert isinstance(result, bool)


# ================================================================
# VLM engine tests
# ================================================================

class TestVLMFallbackEngine:

    def test_vlm_is_available(self):
        """is_available checks for API key config."""
        result = VLMFallbackEngine.is_available()
        assert isinstance(result, bool)
