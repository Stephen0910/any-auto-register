"""ChatGPT Keygen 注册 worker — 桥接 engine 到项目框架"""
from __future__ import annotations

from typing import Callable

from .engine import KeygenEngine


class ChatGPTKeygenWorker:
    """供 ProtocolMailboxAdapter 调用的 worker"""

    def __init__(
        self,
        *,
        proxy_url: str | None = None,
        mail_service_url: str = "http://10.10.10.8:5500",
        mail_provider: str = "tempmail_lol",
        log_fn: Callable[[str], None] = print,
    ):
        self.engine = KeygenEngine(
            proxy_url=proxy_url,
            mail_service_url=mail_service_url,
            mail_provider=mail_provider,
            log_fn=log_fn,
        )

    def run(self, *, email: str = "", password: str = ""):
        result = self.engine.run(email=email or None, password=password or None)
        if not result.success:
            raise RuntimeError(result.error_message or "注册失败")
        return result
