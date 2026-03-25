"""
Kiro CPA 上传功能

将注册成功的 Kiro (AWS Builder ID) 账号上传到 CPA 管理平台。
接口与 ChatGPT CPA 上传一致：POST /v0/management/auth-files
"""

import json
import logging
from typing import Tuple, Optional
from datetime import datetime, timezone, timedelta

from curl_cffi import requests as cffi_requests
from curl_cffi import CurlMime

logger = logging.getLogger(__name__)


def _get_config_value(key: str) -> str:
    try:
        from core.config_store import config_store
        return config_store.get(key, "")
    except Exception:
        return ""


def generate_token_json(account) -> dict:
    """
    生成 CPA 格式的 Token JSON（Kiro 专用）。
    接受任意 duck-typed 对象或 dict，支持字段：
      email, accessToken, refreshToken, clientId, clientSecret, sessionToken
    """
    if isinstance(account, dict):
        email = account.get("email", "")
        access_token = account.get("accessToken", "") or account.get("access_token", "")
        refresh_token = account.get("refreshToken", "") or account.get("refresh_token", "")
        client_id = account.get("clientId", "") or account.get("client_id", "")
        client_secret = account.get("clientSecret", "") or account.get("client_secret", "")
        session_token = account.get("sessionToken", "") or account.get("session_token", "")
    else:
        email = getattr(account, "email", "")
        extra = getattr(account, "extra", {}) or {}
        access_token = extra.get("accessToken") or getattr(account, "access_token", "") or getattr(account, "accessToken", "")
        refresh_token = extra.get("refreshToken") or getattr(account, "refresh_token", "") or getattr(account, "refreshToken", "")
        client_id = extra.get("clientId") or getattr(account, "client_id", "") or getattr(account, "clientId", "")
        client_secret = extra.get("clientSecret") or getattr(account, "client_secret", "") or getattr(account, "clientSecret", "")
        session_token = extra.get("sessionToken") or getattr(account, "session_token", "") or getattr(account, "sessionToken", "")

    now = datetime.now(tz=timezone(timedelta(hours=8)))

    return {
        "type": "kiro",
        "email": email,
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "clientId": client_id,
        "clientSecret": client_secret,
        "sessionToken": session_token,
        "last_refresh": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }


def upload_to_cpa(
    token_data: dict,
    api_url: str = None,
    api_key: str = None,
    proxy: str = None,
) -> Tuple[bool, str]:
    """上传单个 Kiro 账号到 CPA 管理平台。
    api_url / api_key 为空时自动从 ConfigStore 读取（优先读 kiro 专用配置，回退到全局）。
    """
    if not api_url:
        api_url = _get_config_value("kiro_cpa_api_url") or _get_config_value("cpa_api_url")
    if not api_key:
        api_key = _get_config_value("kiro_cpa_api_key") or _get_config_value("cpa_api_key")

    if not api_url:
        return False, "CPA API URL 未配置"
    if not api_key:
        return False, "CPA API Key 未配置"

    api_url = api_url.rstrip("/")
    email = token_data.get("email", "unknown")
    filename = f"{email}.json"
    file_bytes = json.dumps(token_data, ensure_ascii=False).encode("utf-8")

    headers = {"Authorization": f"Bearer {api_key}"}
    upload_url = f"{api_url}/v0/management/auth-files"

    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        mime = CurlMime()
        mime.addpart(
            name="file",
            data=file_bytes,
            filename=filename,
            content_type="application/json",
        )
        resp = cffi_requests.post(
            upload_url,
            multipart=mime,
            headers=headers,
            proxies=proxies,
            verify=False,
            timeout=15,
            impersonate="chrome110",
        )
        if resp.status_code == 409:
            return True, "已存在（跳过）"
        if resp.status_code in (200, 201):
            return True, "上传成功"
        error_msg = f"上传失败: HTTP {resp.status_code}"
        try:
            detail = resp.json()
            if isinstance(detail, dict):
                error_msg = detail.get("message", error_msg)
        except Exception:
            error_msg = f"{error_msg} - {resp.text[:200]}"
        return False, error_msg
    except Exception as e:
        logger.error(f"Kiro CPA 上传异常: {e}")
        return False, f"上传异常: {str(e)}"


def upload_batch(
    accounts: list,
    api_url: str = None,
    api_key: str = None,
    proxy: str = None,
    log_cb=None,
) -> dict:
    """批量上传 Kiro 账号到 CPA，返回 {success, fail, skipped} 统计。"""
    def log(msg):
        if log_cb:
            log_cb(msg)
        else:
            logger.info(msg)

    results = {"success": 0, "fail": 0, "skipped": 0}
    for acc in accounts:
        token_data = generate_token_json(acc)
        ok, msg = upload_to_cpa(token_data, api_url=api_url, api_key=api_key, proxy=proxy)
        if ok:
            if "已存在" in msg:
                results["skipped"] += 1
                log(f"[CPA] 已存在跳过: {token_data.get('email')}")
            else:
                results["success"] += 1
                log(f"[CPA] ✓ 上传成功: {token_data.get('email')}")
        else:
            results["fail"] += 1
            log(f"[CPA] ✗ 上传失败: {token_data.get('email')} - {msg}")
    return results


def test_cpa_connection(api_url: str, api_token: str, proxy: str = None) -> Tuple[bool, str]:
    """测试 CPA 连接"""
    if not api_url:
        return False, "API URL 不能为空"
    if not api_token:
        return False, "API Token 不能为空"

    api_url = api_url.rstrip("/")
    test_url = f"{api_url}/v0/management/auth-files"
    headers = {"Authorization": f"Bearer {api_token}"}
    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        resp = cffi_requests.options(
            test_url,
            headers=headers,
            proxies=proxies,
            verify=False,
            timeout=10,
            impersonate="chrome110",
        )
        if resp.status_code in (200, 204, 401, 403, 405):
            if resp.status_code == 401:
                return False, "连接成功，但 API Token 无效"
            return True, "CPA 连接测试成功"
        return False, f"服务器返回异常状态码: {resp.status_code}"
    except cffi_requests.exceptions.ConnectionError as e:
        return False, f"无法连接到服务器: {str(e)}"
    except cffi_requests.exceptions.Timeout:
        return False, "连接超时，请检查网络配置"
    except Exception as e:
        return False, f"连接测试失败: {str(e)}"
