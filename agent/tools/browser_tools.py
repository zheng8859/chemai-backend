"""浏览器工具集（5 个）— Playwright 浏览器自动化。

封装 Playwright 为 Agent 工具，支持导航、读取、点击、输入和截图。
单浏览器实例 + 60s 空闲自动回收。
注册给所有 Persona（通用工具）。
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

from .tool_meta import register_tool

logger = logging.getLogger(__name__)

# ── 浏览器实例管理（模块级单例） ──

_browser_instance = None
_browser_last_used = 0.0


async def _get_browser():
    """获取或创建 Playwright 浏览器实例（60s 空闲回收）。"""
    global _browser_instance, _browser_last_used
    import time

    now = time.monotonic()
    if _browser_instance is not None and (now - _browser_last_used) > 60:
        logger.info("浏览器实例空闲超 60s，关闭回收")
        await _browser_instance.close()
        _browser_instance = None

    if _browser_instance is None:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        _browser_instance = await pw.chromium.launch(headless=True)
        logger.info("Playwright 浏览器实例已创建")

    _browser_last_used = now
    return _browser_instance


# ── SSRF 防护：禁止访问的内网/保留地址块 ──

_BLOCKED_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::/128"),
)


def _validate_url(url: str) -> str | None:
    """校验 URL，返回错误信息（None = 通过）。防 SSRF。

    仅放行 http/https；拒绝回环、链路本地（含云元数据 169.254.169.254）、
    私网与保留地址。
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return "无法解析 URL"
    if parsed.scheme not in ("http", "https"):
        return f"仅支持 http/https 协议，收到: {parsed.scheme or '空'}"
    host = parsed.hostname
    if not host:
        return "URL 缺少主机名"
    try:
        addrs = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except Exception:
        return f"无法解析主机: {host}"
    for addr in addrs:
        ip = ipaddress.ip_address(addr[4][0])
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                return f"禁止访问内网地址: {host} ({ip})"
    return None


@register_tool(
    name="browse_navigate",
    persona=["teacher", "tutor", "student", "parent"],
    call_limit=10,
    description="浏览器导航到指定 URL。用于打开网页资源、查看在线文档等。",
)
async def browse_navigate(url: str) -> dict:
    """导航到指定 URL。

    Args:
        url: 目标网页地址

    Returns:
        {"url": str, "title": str, "status": int}
    """
    err = _validate_url(url)
    if err:
        logger.warning("browse_navigate SSRF 拦截: %s", err)
        return {"url": url, "error": err}

    try:
        browser = await _get_browser()
        page = await browser.new_page()
        response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        title = await page.title()
        await page.close()
        return {"url": url, "title": title, "status": response.status if response else 0}
    except Exception as e:
        logger.warning("browse_navigate 失败: %s", e)
        return {"url": url, "error": str(e)}


@register_tool(
    name="browse_read",
    persona=["teacher", "tutor", "student", "parent"],
    call_limit=10,
    description="读取当前浏览器页面的文本内容。用于提取网页中的化学资料、题目等信息。",
)
async def browse_read(selector: str = "body") -> dict:
    """读取页面文本内容。

    Args:
        selector: CSS 选择器（默认 body）

    Returns:
        {"text": str, "length": int}
    """
    try:
        browser = await _get_browser()
        pages = browser.contexts[0].pages if browser.contexts else []
        if not pages:
            return {"text": "", "error": "无打开的页面"}
        text = await pages[-1].text_content(selector)
        text = text[:5000] if text else ""  # 截断过长文本
        return {"text": text, "length": len(text)}
    except Exception as e:
        logger.warning("browse_read 失败: %s", e)
        return {"text": "", "error": str(e)}


@register_tool(
    name="browse_click",
    persona=["teacher", "tutor", "student", "parent"],
    call_limit=10,
    description="点击浏览器页面中的元素。用于交互式网页操作。",
)
async def browse_click(selector: str) -> dict:
    """点击页面元素。

    Args:
        selector: CSS 选择器

    Returns:
        {"selector": str, "success": bool}
    """
    try:
        browser = await _get_browser()
        pages = browser.contexts[0].pages if browser.contexts else []
        if not pages:
            return {"selector": selector, "success": False, "error": "无打开的页面"}
        await pages[-1].click(selector, timeout=5000)
        return {"selector": selector, "success": True}
    except Exception as e:
        logger.warning("browse_click 失败: %s", e)
        return {"selector": selector, "success": False, "error": str(e)}


@register_tool(
    name="browse_input",
    persona=["teacher", "tutor", "student", "parent"],
    call_limit=10,
    description="在浏览器页面的输入框中填入文本。用于表单填写、搜索框输入等。",
)
async def browse_input(selector: str, text: str) -> dict:
    """在输入框中填入文本。

    Args:
        selector: CSS 选择器（input/textarea）
        text: 要填入的文本

    Returns:
        {"selector": str, "success": bool}
    """
    try:
        browser = await _get_browser()
        pages = browser.contexts[0].pages if browser.contexts else []
        if not pages:
            return {"selector": selector, "success": False, "error": "无打开的页面"}
        await pages[-1].fill(selector, text, timeout=5000)
        return {"selector": selector, "success": True}
    except Exception as e:
        logger.warning("browse_input 失败: %s", e)
        return {"selector": selector, "success": False, "error": str(e)}


@register_tool(
    name="browse_screenshot",
    persona=["teacher", "tutor", "student", "parent"],
    call_limit=5,
    description="对当前浏览器页面截图。用于保存网页内容、OCR 识别前的图片获取等。",
)
async def browse_screenshot() -> dict:
    """页面截图。

    Returns:
        {"screenshot": str (base64), "format": str}
    """
    try:
        browser = await _get_browser()
        pages = browser.contexts[0].pages if browser.contexts else []
        if not pages:
            return {"screenshot": "", "error": "无打开的页面"}
        import base64
        screenshot_bytes = await pages[-1].screenshot(full_page=False)
        return {
            "screenshot": base64.b64encode(screenshot_bytes).decode(),
            "format": "png",
        }
    except Exception as e:
        logger.warning("browse_screenshot 失败: %s", e)
        return {"screenshot": "", "error": str(e)}
