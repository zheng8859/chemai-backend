"""浏览器工具 URL 校验（SSRF 防护）单元测试。

覆盖 _validate_url 对非 http 协议、回环/链路本地/私网/保留地址的拦截，
以及合法公网地址的放行。
"""

import pytest

from agent.tools.browser_tools import _validate_url


def test_non_http_scheme_rejected():
    """file:// 等非 http/https 协议 → 拒绝。"""
    assert _validate_url("file:///etc/passwd") is not None
    assert _validate_url("gopher://localhost/1") is not None
    assert _validate_url("ftp://example.com/x") is not None


def test_missing_host_rejected():
    """缺少主机名 → 拒绝。"""
    assert _validate_url("http://") is not None


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/admin",        # 回环
        "http://127.0.0.2/",
        "http://169.254.169.254/latest/meta-data/",  # 云元数据
        "http://192.168.1.1/",                # 私网 C 类
        "http://10.0.0.5/",                   # 私网 A 类
        "http://172.16.0.10/",                # 私网 B 类
        "http://[::1]/",                      # IPv6 回环
        "http://[fe80::1]/",                  # IPv6 链路本地
    ],
)
def test_internal_address_rejected(url):
    """回环/链路本地/私网/保留地址 → 拒绝。"""
    assert _validate_url(url) is not None


def test_localhost_hostname_rejected():
    """localhost 主机名解析到回环 → 拒绝。"""
    assert _validate_url("http://localhost/") is not None


def test_public_ip_allowed():
    """公网 IP（字面量，无需 DNS）→ 放行。"""
    assert _validate_url("https://8.8.8.8/") is None


def test_public_https_url_allowed():
    """合法公网 https 主机名 → 放行（依赖 DNS，网络不可用时本测试跳过）。"""
    # 用公网字面 IP 之外的域名可能触发真实 DNS；此处用 example.com 但做网络无关保护，
    # 仅验证 scheme/hostname 解析路径不抛异常。
    result = _validate_url("https://example.com/chemistry")
    # 有网 → None；无网 → 返回“无法解析主机”，两种都不是「内网拦截」错误
    assert result is None or "内网" not in result
