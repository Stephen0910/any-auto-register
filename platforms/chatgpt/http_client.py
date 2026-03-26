"""OpenAI 专用 HTTP 客户端"""
from typing import Optional, Dict, Any, Tuple, List
from core.http_client import HTTPClient, HTTPClientError, RequestConfig
from .constants import ERROR_MESSAGES
import logging
logger = logging.getLogger(__name__)

class OpenAIHTTPClient(HTTPClient):
    """
    OpenAI 专用 HTTP 客户端
    包含 OpenAI API 特定的请求方法
    """

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        config: Optional[RequestConfig] = None
    ):
        """
        初始化 OpenAI HTTP 客户端

        Args:
            proxy_url: 代理 URL
            config: 请求配置
        """
        super().__init__(proxy_url, config)

        # OpenAI 特定的默认配置
        if config is None:
            self.config.timeout = 30
            self.config.max_retries = 3

        # 默认请求头
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }

    def check_ip_location(self) -> Tuple[bool, Optional[str]]:
        """
        检查 IP 地理位置

        Returns:
            Tuple[是否支持, 位置信息]
        """
        try:
            response = self.get("https://cloudflare.com/cdn-cgi/trace", timeout=10)
            trace_text = response.text

            # 解析位置信息
            import re
            loc_match = re.search(r"loc=([A-Z]+)", trace_text)
            loc = loc_match.group(1) if loc_match else None

            # 检查是否支持
            if loc in ["CN", "HK", "MO", "TW"]:
                return False, loc
            return True, loc

        except Exception as e:
            logger.error(f"检查 IP 地理位置失败: {e}")
            return False, None

    def send_openai_request(
        self,
        endpoint: str,
        method: str = "POST",
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送 OpenAI API 请求

        Args:
            endpoint: API 端点
            method: HTTP 方法
            data: 表单数据
            json_data: JSON 数据
            headers: 请求头
            **kwargs: 其他参数

        Returns:
            响应 JSON 数据

        Raises:
            HTTPClientError: 请求失败
        """
        # 合并请求头
        request_headers = self.default_headers.copy()
        if headers:
            request_headers.update(headers)

        # 设置 Content-Type
        if json_data is not None and "Content-Type" not in request_headers:
            request_headers["Content-Type"] = "application/json"
        elif data is not None and "Content-Type" not in request_headers:
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            response = self.request(
                method,
                endpoint,
                data=data,
                json=json_data,
                headers=request_headers,
                **kwargs
            )

            # 检查响应状态码
            response.raise_for_status()

            # 尝试解析 JSON
            try:
                return response.json()
            except json.JSONDecodeError:
                return {"raw_response": response.text}

        except cffi_requests.RequestsError as e:
            raise HTTPClientError(f"OpenAI 请求失败: {endpoint} - {e}")

    def check_sentinel(self, did: str, proxies: Optional[Dict] = None, flow: str = "authorize_continue") -> Optional[str]:
        """
        检查 Sentinel 拦截（使用本地 PoW 生成 requirements token）

        Args:
            did: Device ID
            proxies: 代理配置
            flow: sentinel flow 类型

        Returns:
            完整 sentinel token JSON 字符串 或 None
        """
        import base64 as _b64
        import json as _json
        import random as _random
        import time as _time
        import uuid as _uuid
        import datetime as _dt

        USER_AGENT = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        )

        # ---- 本地 PoW SentinelTokenGenerator ----
        class _SentinelGen:
            MAX_ATTEMPTS = 500000
            ERROR_PREFIX = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D"

            def __init__(self, device_id: str):
                self.device_id = device_id
                self.requirements_seed = str(_random.random())
                self.sid = str(_uuid.uuid4())

            @staticmethod
            def _fnv1a_32(text: str) -> str:
                h = 2166136261
                for ch in text:
                    h ^= ord(ch)
                    h = (h * 16777619) & 0xFFFFFFFF
                h ^= (h >> 16)
                h = (h * 2246822507) & 0xFFFFFFFF
                h ^= (h >> 13)
                h = (h * 3266489909) & 0xFFFFFFFF
                h ^= (h >> 16)
                h &= 0xFFFFFFFF
                return format(h, "08x")

            @staticmethod
            def _b64enc(data) -> str:
                js = _json.dumps(data, separators=(",", ":"), ensure_ascii=False)
                return _b64.b64encode(js.encode("utf-8")).decode("ascii")

            def _get_config(self):
                now = _dt.datetime.now(_dt.timezone.utc).strftime("%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)")
                perf_now = _random.uniform(1000, 50000)
                time_origin = _time.time() * 1000 - perf_now
                return [
                    "1920x1080", now, 4294705152, _random.random(), USER_AGENT,
                    "https://sentinel.openai.com/sentinel/20260124ceb8/sdk.js",
                    None, None, "en-US", "en-US,en", _random.random(),
                    "vendorSub\u2212undefined", "location", "Object",
                    perf_now, self.sid, "", _random.choice([4, 8, 12, 16]), time_origin,
                ]

            def generate_requirements_token(self) -> str:
                cfg = self._get_config()
                cfg[3] = 1
                cfg[9] = round(_random.uniform(5, 50))
                return "gAAAAAC" + self._b64enc(cfg)

            def generate_token(self, seed=None, difficulty=None) -> str:
                if seed is None:
                    seed = self.requirements_seed
                    difficulty = difficulty or "0"
                cfg = self._get_config()
                start = _time.time()
                for i in range(self.MAX_ATTEMPTS):
                    cfg[3] = i
                    cfg[9] = round((_time.time() - start) * 1000)
                    data = self._b64enc(cfg)
                    if self._fnv1a_32(seed + data)[: len(difficulty or "0")] <= (difficulty or "0"):
                        return "gAAAAAB" + data + "~S"
                return "gAAAAAB" + self.ERROR_PREFIX + self._b64enc(str(None))

        from .constants import OPENAI_API_ENDPOINTS
        try:
            gen = _SentinelGen(device_id=did)
            req_token = gen.generate_requirements_token()
            body = _json.dumps({"p": req_token, "id": did, "flow": flow})

            response = self.post(
                OPENAI_API_ENDPOINTS["sentinel"],
                headers={
                    "origin": "https://sentinel.openai.com",
                    "referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html",
                    "content-type": "text/plain;charset=UTF-8",
                },
                data=body,
            )

            if response.status_code != 200:
                logger.warning(f"Sentinel 检查失败: {response.status_code}")
                return None

            data = response.json()
            c_value = data.get("token", "")
            pow_data = data.get("proofofwork", {})

            if isinstance(pow_data, dict) and pow_data.get("required") and pow_data.get("seed"):
                p_value = gen.generate_token(seed=pow_data.get("seed"), difficulty=pow_data.get("difficulty", "0"))
                logger.debug(f"Sentinel PoW 计算完成")
            else:
                p_value = gen.generate_requirements_token()

            return _json.dumps({"p": p_value, "t": "", "c": c_value, "id": did, "flow": flow})

        except Exception as e:
            logger.error(f"Sentinel 检查异常: {e}")
            return None


def create_http_client(
    proxy_url: Optional[str] = None,
    config: Optional[RequestConfig] = None
) -> HTTPClient:
    """
    创建 HTTP 客户端工厂函数

    Args:
        proxy_url: 代理 URL
        config: 请求配置

    Returns:
        HTTPClient 实例
    """
    return HTTPClient(proxy_url, config)


def create_openai_client(
    proxy_url: Optional[str] = None,
    config: Optional[RequestConfig] = None
) -> OpenAIHTTPClient:
    """
    创建 OpenAI HTTP 客户端工厂函数

    Args:
        proxy_url: 代理 URL
        config: 请求配置

    Returns:
        OpenAIHTTPClient 实例
    """
    return OpenAIHTTPClient(proxy_url, config)