"""
MailServiceMailbox - 通用邮箱服务客户端适配器

让所有注册机（any-auto-register、ctf_ai 等）通过统一 HTTP 接口调用 mail 服务。

使用方式：
    from mail_service_mailbox import MailServiceMailbox

    mb = MailServiceMailbox(provider="moemail", base_url="http://10.10.10.8:5500")
    account = mb.get_email()              # 创建邮箱
    ids = mb.get_current_ids(account)     # 记录当前邮件 ID（注册前调用）
    code = mb.wait_for_code(
        account,
        before_ids=ids,
        keyword="openai",
        timeout=120,
    )
    mb.delete(account)                    # 用完释放
"""
from __future__ import annotations

import re
import time

import requests as _requests


class MailboxAccount:
    """轻量邮箱账号对象，兼容 any-auto-register 和 ctf_ai 的 dataclass 接口"""
    def __init__(self, email: str, account_id: str = "", extra: dict = None):
        self.email = email
        self.account_id = account_id
        self.extra = extra or {}

    def __repr__(self):
        return f"MailboxAccount(email={self.email!r})"


class MailServiceMailbox:
    """
    通用适配器：把 mail 服务（http://10.10.10.8:5500）封装成
    与 any-auto-register BaseMailbox 完全兼容的同步接口。

    参数：
        provider   - provider 名称，如 "moemail" / "mailtm" / "edumail" 等，
                     也可传列表 ["moemail", "mailtm"] 或 "all"
        base_url   - mail 服务地址，默认 http://10.10.10.8:5500
        timeout_per_req - 单次 HTTP 请求超时（秒）
    """

    DEFAULT_BASE_URL = "http://10.10.10.8:5500"
    DEFAULT_CODE_PATTERN = r'(?<!#)(?<!\d)(\d{6})(?!\d)'

    def __init__(
        self,
        provider: str | list = "moemail",
        base_url: str = None,
        timeout_per_req: int = 15,
    ):
        self.provider = provider
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self._req_timeout = timeout_per_req
        self._session = _requests.Session()

    def _post(self, path: str, **kwargs):
        return self._session.post(
            f"{self.base_url}{path}",
            timeout=self._req_timeout,
            **kwargs,
        )

    def _get(self, path: str, **kwargs):
        return self._session.get(
            f"{self.base_url}{path}",
            timeout=self._req_timeout,
            **kwargs,
        )

    def _delete(self, path: str, **kwargs):
        return self._session.delete(
            f"{self.base_url}{path}",
            timeout=self._req_timeout,
            **kwargs,
        )

    def get_email(self) -> MailboxAccount:
        """
        创建一个临时邮箱，返回 MailboxAccount。
        对应 BaseMailbox.get_email()。
        """
        r = self._post("/api/mail/create", json={"provider": self.provider})
        r.raise_for_status()
        data = r.json()
        created = data.get("created", [])
        if not created:
            errors = data.get("errors", [])
            raise RuntimeError(f"创建邮箱失败: {errors}")
        item = created[0]
        return MailboxAccount(
            email=item["email"],
            account_id=item.get("account_id", ""),
            extra={"provider": item.get("provider", "")},
        )

    def get_current_ids(self, account: MailboxAccount) -> set:
        """
        返回当前邮件 ID 集合（注册前调用，用于过滤旧邮件）。
        对应 BaseMailbox.get_current_ids()。
        """
        try:
            r = self._get(f"/api/mail/{account.email}/messages")
            if r.status_code == 200:
                return {str(m["id"]) for m in r.json() if "id" in m}
        except Exception:
            pass
        return set()

    def wait_for_code(
        self,
        account: MailboxAccount,
        keyword: str = "",
        timeout: int = 120,
        before_ids: set = None,
        code_pattern: str = None,
        interval: float = 4.0,
    ) -> str:
        """
        等待并返回验证码。
        优先调用服务端 /api/mail/{email}/code，失败降级为本地轮询。
        """
        # 方法1：服务端等待接口
        try:
            params = {"timeout": timeout}
            if keyword:
                params["keyword"] = keyword
            if code_pattern:
                params["pattern"] = code_pattern
            r = self._get(
                f"/api/mail/{account.email}/code",
                params=params,
                timeout=timeout + 10,
            )
            if r.status_code == 200:
                return r.json().get("code", "")
            elif r.status_code == 408:
                raise TimeoutError(f"等待验证码超时 ({timeout}s)")
        except TimeoutError:
            raise
        except Exception:
            pass

        # 方法2：本地轮询降级
        seen = set(before_ids or [])
        pattern = code_pattern or self.DEFAULT_CODE_PATTERN
        start = time.time()

        while time.time() - start < timeout:
            try:
                r = self._get(f"/api/mail/{account.email}/messages")
                if r.status_code == 200:
                    for msg in r.json():
                        mid = str(msg.get("id", ""))
                        if mid in seen:
                            continue
                        seen.add(mid)
                        try:
                            r2 = self._get(f"/api/mail/{account.email}/content/{mid}")
                            if r2.status_code == 200:
                                d = r2.json()
                                text = d.get("body", "") + " " + d.get("subject", "")
                                html = d.get("html", "")
                            else:
                                text = msg.get("preview", "") + " " + msg.get("subject", "")
                                html = ""
                        except Exception:
                            text = msg.get("preview", "") + " " + msg.get("subject", "")
                            html = ""

                        if keyword and keyword.lower() not in (text + html).lower():
                            continue

                        for content in [html, text]:
                            if not content:
                                continue
                            m = re.search(pattern, content, re.IGNORECASE)
                            if m:
                                return m.group(1) if m.lastindex else m.group(0)
            except Exception:
                pass
            time.sleep(interval)

        raise TimeoutError(f"等待验证码超时 ({timeout}s)")

    def delete(self, account: MailboxAccount) -> None:
        """释放/删除邮箱（用完调用）"""
        try:
            self._delete(f"/api/mail/{account.email}")
        except Exception:
            pass

    def create_mailbox(self):
        """别名 get_email()，兼容部分调用方"""
        return self.get_email()

    def delete_mailbox(self, account: MailboxAccount) -> None:
        """别名 delete()，兼容部分调用方"""
        self.delete(account)


def create_mail_service_mailbox(
    provider: str | list = "moemail",
    base_url: str = None,
) -> MailServiceMailbox:
    """快捷创建 MailServiceMailbox 实例"""
    return MailServiceMailbox(provider=provider, base_url=base_url)
