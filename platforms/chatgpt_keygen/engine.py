"""
ChatGPT Keygen 注册引擎
========================
纯协议实现（零浏览器），邮箱走独立邮件服务 (10.10.10.8:5500)。

流程：
  步骤0: GET  /oauth/authorize                    → login_session cookie
  步骤0: POST /api/accounts/authorize/continue     → 提交邮箱（需 sentinel）
  步骤2: POST /api/accounts/user/register          → 注册（username+password，需 sentinel）
  步骤3: GET  /api/accounts/email-otp/send         → 触发验证码
  步骤4: POST /api/accounts/email-otp/validate     → 提交 OTP
  步骤5: POST /api/accounts/create_account         → 姓名+生日
  登录:  consent 多步 → code → /oauth/token        → 换取 tokens
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import base64
from typing import Any, Callable
from urllib.parse import urlencode, urlparse, parse_qs, urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

from .sentinel import (
    COMMON_HEADERS, NAVIGATE_HEADERS, OPENAI_AUTH_BASE, USER_AGENT,
    generate_device_id, generate_pkce, generate_datadog_trace,
    generate_random_name, generate_random_birthday, generate_random_password,
    build_sentinel_token, fetch_sentinel_challenge, SentinelTokenGenerator,
    response_preview, extract_openai_error_code,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CHATGPT_BASE = "https://chatgpt.com"
OAUTH_ISSUER = "https://auth.openai.com"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OAUTH_REDIRECT_URI = "http://localhost:1455/auth/callback"


# ── HTTP 会话 ────────────────────────────────────────

def _create_session(proxy_url: str | None = None) -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    if proxy_url:
        s.proxies = {"http": proxy_url, "https": proxy_url}
    return s


# ── 邮件服务客户端 ──────────────────────────────────

class MailServiceClient:
    """通过 HTTP 调用 10.10.10.8:5500 的邮件服务"""

    def __init__(self, base_url: str = "http://10.10.10.8:5500", provider: str = "tempmail_lol"):
        self.base_url = base_url.rstrip("/")
        self.provider = provider

    def create_email(self) -> tuple[str, str]:
        """创建邮箱，返回 (email, account_id)"""
        resp = requests.post(
            f"{self.base_url}/api/mail/create",
            json={"provider": self.provider},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        created = data.get("created", [{}])[0]
        email = created.get("email", "")
        account_id = created.get("account_id", "")
        if not email:
            raise RuntimeError(f"邮件服务返回空邮箱: {data}")
        return email, account_id

    def wait_for_code(self, email: str, timeout: int = 120, keyword: str = "openai") -> str | None:
        """长轮询等待验证码"""
        resp = requests.get(
            f"{self.base_url}/api/mail/{email}/code",
            params={"timeout": timeout, "keyword": keyword},
            timeout=timeout + 10,
        )
        if resp.status_code == 200:
            data = resp.json()
            code = data.get("code")
            if code:
                return code
        return None

    def get_messages(self, email: str) -> list:
        resp = requests.get(f"{self.base_url}/api/mail/{email}/messages", timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return []

    def delete_email(self, email: str) -> bool:
        try:
            resp = requests.delete(f"{self.base_url}/api/mail/{email}", timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    def extract_code_from_messages(self, email: str) -> str | None:
        """从邮件内容中提取 6 位验证码（备用方案）"""
        msgs = self.get_messages(email)
        for msg in msgs:
            content = ""
            for key in ("raw", "subject", "text", "html", "source"):
                val = msg.get(key)
                if isinstance(val, str):
                    content += val
            codes = re.findall(r'\b(\d{6})\b', content)
            for c in codes:
                if c != "177010":
                    return c
        return None


# ── JWT 解码 ─────────────────────────────────────────

def decode_jwt_payload(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload_b64 = parts[1]
        pad = 4 - len(payload_b64) % 4
        if pad != 4:
            payload_b64 += "=" * pad
        raw = base64.urlsafe_b64decode(payload_b64)
        return json.loads(raw)
    except Exception:
        return {}


# ── 注册引擎 ────────────────────────────────────────

class KeygenResult:
    """注册结果"""
    def __init__(self):
        self.success = False
        self.email = ""
        self.password = ""
        self.access_token = ""
        self.refresh_token = ""
        self.id_token = ""
        self.session_token = ""
        self.account_id = ""
        self.chatgpt_account_id = ""
        self.chatgpt_user_id = ""
        self.plan_type = ""
        self.workspace_id = ""
        self.error_message = ""
        self.logs: list[str] = []

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "email": self.email,
            "password": self.password,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "id_token": self.id_token,
            "session_token": self.session_token,
            "account_id": self.account_id,
            "chatgpt_account_id": self.chatgpt_account_id,
            "chatgpt_user_id": self.chatgpt_user_id,
            "plan_type": self.plan_type,
            "workspace_id": self.workspace_id,
            "error_message": self.error_message,
        }


class KeygenEngine:
    """
    纯协议注册引擎
    全流程 HTTP，邮箱走独立邮件服务。
    """

    def __init__(
        self,
        proxy_url: str | None = None,
        mail_service_url: str = "http://10.10.10.8:5500",
        mail_provider: str = "tempmail_lol",
        log_fn: Callable[[str], None] = print,
    ):
        self.proxy_url = proxy_url
        self.log_fn = log_fn
        self.mail = MailServiceClient(base_url=mail_service_url, provider=mail_provider)
        self.result = KeygenResult()

        # HTTP 会话
        self.session = _create_session(proxy_url)
        self.device_id = generate_device_id()

        # 注册后复用
        self._post_create_continue_url = ""

    def _log(self, msg: str):
        self.result.logs.append(msg)
        self.log_fn(msg)

    def run(self, email: str | None = None, password: str | None = None) -> KeygenResult:
        """执行完整注册流程"""
        try:
            return self._run_inner(email, password)
        except Exception as e:
            self.result.error_message = str(e)
            self._log(f"❌ 注册异常: {e}")
            import traceback
            traceback.print_exc()
            return self.result

    def _run_inner(self, email: str | None, password: str | None) -> KeygenResult:
        # 1. 创建邮箱（如果未指定）
        if not email:
            self._log("📧 创建临时邮箱...")
            email, mail_account_id = self.mail.create_email()
            self._log(f"  ✅ 邮箱: {email}")
        else:
            mail_account_id = ""

        if not password:
            password = generate_random_password()

        self.result.email = email
        self.result.password = password

        first_name, last_name = generate_random_name()
        birthdate = generate_random_birthday()

        # 步骤0: OAuth 初始化 + 邮箱提交
        if not self._step0_oauth_and_email(email):
            return self.result

        time.sleep(1)

        # 步骤2: 注册用户
        step2 = self._step2_register(email, password)
        if not step2.get("ok"):
            self.result.error_message = "步骤2: 用户注册失败"
            return self.result

        time.sleep(1)

        # 步骤3: 触发 OTP
        if not self._step3_send_otp(step2.get("continue_url", "")):
            self.result.error_message = "步骤3: OTP 发送失败"
            return self.result

        # 等验证码
        self._log("⏳ 等待验证码...")
        code = self.mail.wait_for_code(email, timeout=120, keyword="openai")
        if not code:
            # 备用：从消息列表提取
            self._log("  ⚠️ 长轮询超时，尝试从消息列表提取...")
            code = self.mail.extract_code_from_messages(email)
        if not code:
            self.result.error_message = "未收到验证码"
            self._log("❌ 未收到验证码")
            return self.result
        self._log(f"  ✅ 验证码: {code}")

        # 步骤4: 验证 OTP
        if not self._step4_validate_otp(code):
            self.result.error_message = "步骤4: OTP 验证失败"
            return self.result

        time.sleep(1)

        # 步骤5: 创建账号
        if not self._step5_create_account(first_name, last_name, birthdate):
            self.result.error_message = "步骤5: 账号创建失败"
            return self.result

        # 登录获取 tokens
        tokens = self._login_get_tokens(email, password)
        if not tokens:
            self.result.error_message = "登录获取 token 失败"
            return self.result

        self.result.success = True
        self.result.access_token = tokens.get("access_token", "")
        self.result.refresh_token = tokens.get("refresh_token", "")
        self.result.id_token = tokens.get("id_token", "")
        self.result.session_token = tokens.get("session_token", "")
        self.result.account_id = tokens.get("account_id", "")
        self.result.chatgpt_account_id = tokens.get("chatgpt_account_id", "")
        self.result.chatgpt_user_id = tokens.get("chatgpt_user_id", "")
        self.result.plan_type = tokens.get("plan_type", "")

        self._log("🎉 注册成功！")
        return self.result

    # ── 步骤0: OAuth 初始化 + 邮箱提交 ──────────────

    def _step0_oauth_and_email(self, email: str) -> bool:
        self._log("🔗 [步骤0] OAuth 会话初始化 + 邮箱提交")

        self.session.cookies.set("oai-did", self.device_id, domain=".auth.openai.com")
        self.session.cookies.set("oai-did", self.device_id, domain="auth.openai.com")

        code_verifier, code_challenge = generate_pkce()
        self._code_verifier = code_verifier
        self._state = secrets.token_urlsafe(32)

        params = {
            "response_type": "code",
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "scope": "openid profile email offline_access",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": self._state,
            "screen_hint": "signup",
            "prompt": "login",
        }
        url = f"{OPENAI_AUTH_BASE}/oauth/authorize?{urlencode(params)}"

        try:
            resp = self.session.get(url, headers=NAVIGATE_HEADERS, allow_redirects=True, verify=False, timeout=30)
            self._log(f"  GET /oauth/authorize: {resp.status_code}")
        except Exception as e:
            self._log(f"  ❌ OAuth 请求失败: {e}")
            return False

        has_session = any(c.name == "login_session" for c in self.session.cookies)
        self._log(f"  login_session: {'✅' if has_session else '❌'}")
        if not has_session:
            return False

        # POST authorize/continue
        headers = dict(COMMON_HEADERS)
        headers["referer"] = f"{OPENAI_AUTH_BASE}/create-account"
        headers["oai-device-id"] = self.device_id
        headers.update(generate_datadog_trace())

        sentinel = build_sentinel_token(self.session, self.device_id, flow="authorize_continue")
        if not sentinel:
            self._log("  ❌ 获取 sentinel token 失败")
            return False
        headers["openai-sentinel-token"] = sentinel

        try:
            resp = self.session.post(
                f"{OPENAI_AUTH_BASE}/api/accounts/authorize/continue",
                json={"username": {"kind": "email", "value": email}, "screen_hint": "signup"},
                headers=headers, verify=False, timeout=30,
            )
        except Exception as e:
            self._log(f"  ❌ 邮箱提交失败: {e}")
            return False

        if resp.status_code != 200:
            self._log(f"  ❌ 邮箱提交失败: HTTP {resp.status_code}")
            return False

        try:
            data = resp.json()
            page_type = data.get("page", {}).get("type", "")
        except Exception:
            page_type = ""
        self._log(f"  ✅ 邮箱提交成功 → {page_type}")
        return True

    # ── 步骤2: 注册用户 ────────────────────────────

    def _step2_register(self, email: str, password: str) -> dict:
        self._log(f"🔑 [步骤2] 注册用户: {email}")

        headers = dict(COMMON_HEADERS)
        headers["referer"] = f"{OPENAI_AUTH_BASE}/create-account/password"
        headers["oai-device-id"] = self.device_id
        headers.update(generate_datadog_trace())
        sentinel = build_sentinel_token(self.session, self.device_id, flow="authorize_continue")
        if sentinel:
            headers["openai-sentinel-token"] = sentinel

        try:
            resp = self.session.post(
                f"{OPENAI_AUTH_BASE}/api/accounts/user/register",
                json={"username": email, "password": password},
                headers=headers, verify=False, timeout=30,
            )
        except Exception as e:
            self._log(f"  ❌ 请求异常: {e}")
            return {"ok": False}

        result = {"ok": False, "continue_url": "", "method": "", "page_type": ""}
        if resp.status_code == 200:
            try:
                data = resp.json()
                result["continue_url"] = str(data.get("continue_url", ""))
                page = data.get("page", {})
                result["page_type"] = str(page.get("type", "")) if isinstance(page, dict) else ""
            except Exception:
                pass
            result["ok"] = True
            self._log("  ✅ 注册成功")
        else:
            # 302 到 email-verification 也算成功
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("Location", "")
                result["continue_url"] = loc
                result["method"] = "GET"
                if "email-otp" in loc or "email-verification" in loc:
                    result["ok"] = True
                    self._log(f"  ✅ 注册成功（302 → {loc[:80]}）")
            if not result["ok"]:
                self._log(f"  ❌ 失败: HTTP {resp.status_code} {response_preview(resp)}")

        return result

    # ── 步骤3: 触发 OTP ────────────────────────────

    def _step3_send_otp(self, continue_url: str = "") -> bool:
        self._log("📬 [步骤3] 触发验证码发送")

        if continue_url:
            if continue_url.startswith("http"):
                url_send = continue_url
            else:
                url_send = urljoin(f"{OPENAI_AUTH_BASE}/", continue_url.lstrip("/"))
        else:
            url_send = f"{OPENAI_AUTH_BASE}/api/accounts/email-otp/send"

        referer = f"{OPENAI_AUTH_BASE}/create-account/password"
        headers = dict(NAVIGATE_HEADERS)
        headers["referer"] = referer

        resp = self.session.get(url_send, headers=headers, verify=False, timeout=30, allow_redirects=False)
        location = resp.headers.get("Location", "").strip()
        self._log(f"  send: {resp.status_code}")

        if resp.status_code >= 400:
            self._log(f"  ❌ send 失败: {response_preview(resp)}")
            return False

        url_verify = urljoin(f"{OPENAI_AUTH_BASE}/", location.lstrip("/")) if location else f"{OPENAI_AUTH_BASE}/email-verification"
        headers["referer"] = referer
        resp = self.session.get(url_verify, headers=headers, verify=False, timeout=30, allow_redirects=True)
        self._log(f"  email-verification: {resp.status_code}")
        if resp.status_code >= 400:
            return False

        self._log("  ✅ OTP 触发完成")
        return True

    # ── 步骤4: 验证 OTP ────────────────────────────

    def _step4_validate_otp(self, code: str) -> bool:
        self._log(f"🔢 [步骤4] 验证 OTP: {code}")

        sentinel = build_sentinel_token(self.session, self.device_id, flow="authorize_continue")
        candidates = [
            (f"{OPENAI_AUTH_BASE}/api/accounts",
             {"origin_page_type": "email_otp_verification", "data": {"intent": "validate", "code": code}}),
            (f"{OPENAI_AUTH_BASE}/api/accounts/email-otp/validate",
             {"code": code}),
        ]

        for url, payload in candidates:
            headers = dict(COMMON_HEADERS)
            headers["referer"] = f"{OPENAI_AUTH_BASE}/email-verification"
            headers["oai-device-id"] = self.device_id
            headers.update(generate_datadog_trace())
            if sentinel:
                headers["openai-sentinel-token"] = sentinel

            try:
                resp = self.session.post(url, headers=headers,
                    data=json.dumps(payload, separators=(",", ":")), verify=False, timeout=30)
            except Exception as e:
                self._log(f"  ⚠️ {url}: {e}")
                continue

            if resp.status_code == 200:
                self._log("  ✅ OTP 验证成功")
                return True
            self._log(f"  ⚠️ {url}: HTTP {resp.status_code}")

        self._log("  ❌ OTP 验证失败")
        return False

    # ── 步骤5: 创建账号 ────────────────────────────

    def _step5_create_account(self, first_name: str, last_name: str, birthdate: str) -> bool:
        name = f"{first_name} {last_name}"
        self._log(f"📝 [步骤5] 创建账号: {name}, {birthdate}")

        # 获取 sentinel tokens
        so_challenge = fetch_sentinel_challenge(self.session, self.device_id, flow="oauth_create_account")
        so_token = so_challenge.get("token", "") if so_challenge else ""
        sentinel = build_sentinel_token(self.session, self.device_id, flow="oauth_create_account")

        headers = dict(COMMON_HEADERS)
        headers["referer"] = f"{OPENAI_AUTH_BASE}/about-you"
        headers["oai-device-id"] = self.device_id
        headers.update(generate_datadog_trace())
        if so_token:
            headers["openai-sentinel-so-token"] = so_token
        if sentinel:
            headers["openai-sentinel-token"] = sentinel

        payload = {"name": name, "birthdate": birthdate}

        try:
            resp = self.session.post(
                f"{OPENAI_AUTH_BASE}/api/accounts/create_account",
                data=json.dumps(payload, separators=(",", ":")),
                headers=headers, verify=False, timeout=30,
            )
        except Exception as e:
            self._log(f"  ❌ 请求异常: {e}")
            return False

        if 200 <= resp.status_code < 300:
            try:
                data = resp.json()
                self._post_create_continue_url = str(data.get("continue_url", ""))
            except Exception:
                pass
            self._log("  ✅ 账号创建完成")
            return True

        err_code = extract_openai_error_code(resp)
        self._log(f"  ❌ 失败: HTTP {resp.status_code} {response_preview(resp)}")
        if err_code:
            self._log(f"  error.code: {err_code}")
        return False

    # ── 登录获取 tokens ────────────────────────────

    def _login_get_tokens(self, email: str, password: str) -> dict | None:
        self._log("🔐 登录获取 tokens...")

        session = _create_session(self.proxy_url)
        device_id = generate_device_id()
        session.cookies.set("oai-did", device_id, domain=".auth.openai.com")
        session.cookies.set("oai-did", device_id, domain="auth.openai.com")

        code_verifier, code_challenge = generate_pkce()
        state = secrets.token_urlsafe(32)

        # 步骤1: GET /oauth/authorize
        params = {
            "response_type": "code", "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "scope": "openid profile email offline_access",
            "code_challenge": code_challenge, "code_challenge_method": "S256",
            "state": state,
        }
        authorize_url = f"{OAUTH_ISSUER}/oauth/authorize?{urlencode(params)}"
        try:
            session.get(authorize_url, headers=NAVIGATE_HEADERS, allow_redirects=True, verify=False, timeout=30)
        except Exception as e:
            self._log(f"  ❌ authorize 失败: {e}")
            return None

        # 步骤2: POST authorize/continue (提交邮箱)
        h = dict(COMMON_HEADERS)
        h["referer"] = f"{OAUTH_ISSUER}/log-in"
        h["oai-device-id"] = device_id
        h.update(generate_datadog_trace())
        sentinel = build_sentinel_token(session, device_id, flow="authorize_continue")
        if not sentinel:
            self._log("  ❌ sentinel 获取失败")
            return None
        h["openai-sentinel-token"] = sentinel

        try:
            resp = session.post(f"{OAUTH_ISSUER}/api/accounts/authorize/continue",
                json={"username": {"kind": "email", "value": email}},
                headers=h, verify=False, timeout=30)
        except Exception as e:
            self._log(f"  ❌ authorize/continue 失败: {e}")
            return None
        if resp.status_code != 200:
            self._log(f"  ❌ authorize/continue: HTTP {resp.status_code}")
            return None

        # 步骤3: POST password/verify
        h["referer"] = f"{OAUTH_ISSUER}/log-in/password"
        h.update(generate_datadog_trace())
        sentinel_pwd = build_sentinel_token(session, device_id, flow="password_verify")
        if sentinel_pwd:
            h["openai-sentinel-token"] = sentinel_pwd

        try:
            resp = session.post(f"{OAUTH_ISSUER}/api/accounts/password/verify",
                json={"password": password},
                headers=h, verify=False, timeout=30, allow_redirects=False)
        except Exception as e:
            self._log(f"  ❌ password/verify 失败: {e}")
            return None
        if resp.status_code != 200:
            self._log(f"  ❌ password/verify: HTTP {resp.status_code} {response_preview(resp)}")
            return None

        continue_url = ""
        page_type = ""
        try:
            data = resp.json()
            continue_url = str(data.get("continue_url", ""))
            page = data.get("page", {})
            page_type = str(page.get("type", "")) if isinstance(page, dict) else ""
        except Exception:
            pass

        # 处理 email_otp_verification（新注册账号首次登录）
        if page_type == "email_otp_verification" or "email-verification" in continue_url:
            self._log("  首次登录触发邮箱验证...")
            # 触发 OTP 发送
            send_url = continue_url if continue_url.startswith("http") else f"{OAUTH_ISSUER}{continue_url}"
            try:
                session.get(send_url, headers=NAVIGATE_HEADERS, allow_redirects=False, verify=False, timeout=30)
            except Exception:
                pass
            # 等验证码
            code = self.mail.wait_for_code(email, timeout=120, keyword="openai")
            if not code:
                code = self.mail.extract_code_from_messages(email)
            if not code:
                self._log("  ❌ 登录验证码超时")
                return None
            self._log(f"  ✅ 登录验证码: {code}")

            h_val = dict(COMMON_HEADERS)
            h_val["referer"] = f"{OAUTH_ISSUER}/email-verification"
            h_val["oai-device-id"] = device_id
            h_val.update(generate_datadog_trace())
            try:
                resp = session.post(f"{OAUTH_ISSUER}/api/accounts/email-otp/validate",
                    json={"code": code}, headers=h_val, verify=False, timeout=30)
                if resp.status_code == 200:
                    d = resp.json()
                    continue_url = str(d.get("continue_url", ""))
                    page_type = str(d.get("page", {}).get("type", ""))
            except Exception:
                pass

            # 处理 about-you（首次登录可能需要填姓名生日）
            if "about-you" in continue_url:
                name = f"{generate_random_name()[0]} {generate_random_name()[1]}"
                bd = generate_random_birthday()
                h_ca = dict(COMMON_HEADERS)
                h_ca["referer"] = f"{OAUTH_ISSUER}/about-you"
                h_ca["oai-device-id"] = device_id
                h_ca.update(generate_datadog_trace())
                so_challenge = fetch_sentinel_challenge(session, device_id, flow="oauth_create_account")
                so_token = so_challenge.get("token", "") if so_challenge else ""
                if so_token:
                    h_ca["openai-sentinel-so-token"] = so_token
                sent_ca = build_sentinel_token(session, device_id, flow="oauth_create_account")
                if sent_ca:
                    h_ca["openai-sentinel-token"] = sent_ca
                try:
                    resp = session.post(f"{OAUTH_ISSUER}/api/accounts/create_account",
                        json={"name": name, "birthdate": bd},
                        headers=h_ca, verify=False, timeout=30)
                    if resp.status_code == 200:
                        d = resp.json()
                        continue_url = str(d.get("continue_url", ""))
                except Exception:
                    pass

        if "consent" in page_type:
            continue_url = f"{OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent"
        if not continue_url or "email-verification" in continue_url:
            self._log(f"  ❌ 无法确定下一步: page_type={page_type}, continue_url={continue_url}")
            return None

        # consent 多步流程 → auth_code
        auth_code = self._consent_to_code(session, device_id, continue_url)
        if not auth_code:
            return None

        return self._exchange_code(auth_code, code_verifier)

    def _consent_to_code(self, session, device_id: str, continue_url: str) -> str | None:
        """consent 多步流程提取 authorization code — 对齐原版 perform_codex_oauth_login_http"""
        if continue_url.startswith("/"):
            consent_url = f"{OAUTH_ISSUER}{continue_url}"
        else:
            consent_url = continue_url

        def _extract_code(url: str) -> str | None:
            if not url or "code=" not in url:
                return None
            try:
                return parse_qs(urlparse(url).query).get("code", [None])[0]
            except Exception:
                return None

        def _follow(session_obj, url, depth=10):
            """跟随 302 重定向链，从 Location header 或 ConnectionError 中提取 code"""
            if depth <= 0:
                return None
            try:
                r = session_obj.get(url, headers=NAVIGATE_HEADERS, verify=False, timeout=15, allow_redirects=False)
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("Location", "")
                    code = _extract_code(loc)
                    if code:
                        return code
                    if loc.startswith("/"):
                        loc = f"{OAUTH_ISSUER}{loc}"
                    return _follow(session_obj, loc, depth - 1)
                elif r.status_code == 200:
                    return _extract_code(r.url)
            except requests.exceptions.ConnectionError as e:
                m = re.search(r'(https?://localhost[^\s\'"]+)', str(e))
                if m:
                    return _extract_code(m.group(1))
            except Exception:
                pass
            return None

        def _decode_auth_session(session_obj) -> dict | None:
            for c in session_obj.cookies:
                if c.name == "oai-client-auth-session":
                    val = c.value.split(".")[0] if "." in c.value else c.value
                    pad = 4 - len(val) % 4
                    if pad != 4:
                        val += "=" * pad
                    try:
                        return json.loads(base64.urlsafe_b64decode(val).decode("utf-8"))
                    except Exception:
                        pass
            return None

        auth_code = None

        # 步骤4a: GET consent 页面
        try:
            resp = session.get(consent_url, headers=NAVIGATE_HEADERS, verify=False, timeout=30, allow_redirects=False)
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("Location", "")
                auth_code = _extract_code(loc)
                if not auth_code:
                    auth_code = _follow(session, loc)
            elif resp.status_code == 200:
                self._log("  consent 200，继续 workspace/select...")
        except requests.exceptions.ConnectionError as e:
            m = re.search(r'(https?://localhost[^\s\'"]+)', str(e))
            if m:
                auth_code = _extract_code(m.group(1))
        except Exception:
            pass

        # 步骤4b: 解码 session cookie → workspace select
        if not auth_code:
            session_data = _decode_auth_session(session)
            workspace_id = None
            if session_data:
                workspaces = session_data.get("workspaces", [])
                if workspaces:
                    workspace_id = workspaces[0].get("id")
                self._log(f"  session keys: {list(session_data.keys())}, workspaces: {len(workspaces)}")

            if workspace_id:
                h_ws = dict(COMMON_HEADERS)
                h_ws["referer"] = consent_url
                h_ws["oai-device-id"] = device_id
                h_ws.update(generate_datadog_trace())
                try:
                    resp = session.post(f"{OAUTH_ISSUER}/api/accounts/workspace/select",
                        json={"workspace_id": workspace_id},
                        headers=h_ws, verify=False, timeout=30, allow_redirects=False)
                    if resp.status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("Location", "")
                        auth_code = _extract_code(loc)
                        if not auth_code:
                            auth_code = _follow(session, loc)
                    elif resp.status_code == 200:
                        ws_data = resp.json()
                        orgs = ws_data.get("data", {}).get("orgs", [])
                        if orgs:
                            org_id = orgs[0].get("id")
                            projects = orgs[0].get("projects", [])
                            proj_id = projects[0].get("id") if projects else None
                            if org_id:
                                h_org = dict(COMMON_HEADERS)
                                h_org["referer"] = consent_url
                                h_org["oai-device-id"] = device_id
                                h_org.update(generate_datadog_trace())
                                body = {"org_id": org_id}
                                if proj_id:
                                    body["project_id"] = proj_id
                                resp2 = session.post(f"{OAUTH_ISSUER}/api/accounts/organization/select",
                                    json=body, headers=h_org, verify=False, timeout=30, allow_redirects=False)
                                if resp2.status_code in (301, 302, 303, 307, 308):
                                    loc2 = resp2.headers.get("Location", "")
                                    auth_code = _extract_code(loc2)
                                    if not auth_code:
                                        auth_code = _follow(session, loc2)
                                elif resp2.status_code == 200:
                                    org_next = resp2.json().get("continue_url", "")
                                    if org_next:
                                        full_next = org_next if org_next.startswith("http") else f"{OAUTH_ISSUER}{org_next}"
                                        auth_code = _follow(session, full_next)
                except Exception as e:
                    self._log(f"  ⚠️ workspace/select 异常: {e}")

            # 没有 workspace_id，仍然尝试 POST workspace/select（原版行为）
            if not auth_code and not workspace_id:
                h_ws = dict(COMMON_HEADERS)
                h_ws["referer"] = consent_url
                h_ws["oai-device-id"] = device_id
                h_ws.update(generate_datadog_trace())
                try:
                    resp = session.post(f"{OAUTH_ISSUER}/api/accounts/workspace/select",
                        json={},
                        headers=h_ws, verify=False, timeout=30, allow_redirects=False)
                    if resp.status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("Location", "")
                        auth_code = _extract_code(loc)
                        if not auth_code:
                            auth_code = _follow(session, loc)
                    elif resp.status_code == 200:
                        ws_data = resp.json()
                        ws_next = ws_data.get("continue_url", "")
                        if ws_next:
                            full_next = ws_next if ws_next.startswith("http") else f"{OAUTH_ISSUER}{ws_next}"
                            auth_code = _follow(session, full_next)
                except Exception as e:
                    self._log(f"  ⚠️ workspace/select (无ws) 异常: {e}")

        # 步骤4d: 备用 — allow_redirects=True
        if not auth_code:
            self._log("  备用: allow_redirects=True 跟踪...")
            try:
                resp = session.get(consent_url, headers=NAVIGATE_HEADERS, verify=False, timeout=30, allow_redirects=True)
                auth_code = _extract_code(resp.url)
                if not auth_code and resp.history:
                    for r in resp.history:
                        auth_code = _extract_code(r.headers.get("Location", ""))
                        if auth_code:
                            break
            except requests.exceptions.ConnectionError as e:
                m = re.search(r'(https?://localhost[^\s\'"]+)', str(e))
                if m:
                    auth_code = _extract_code(m.group(1))
            except Exception:
                pass

        if not auth_code:
            self._log("  ❌ consent 多步全部失败，未获取到 code")
        return auth_code

    def _exchange_code(self, auth_code: str, code_verifier: str) -> dict | None:
        """用 authorization code 换取 tokens"""
        try:
            resp = _create_session(self.proxy_url).post(
                f"{OAUTH_ISSUER}/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "redirect_uri": OAUTH_REDIRECT_URI,
                    "code_verifier": code_verifier,
                    "client_id": OAUTH_CLIENT_ID,
                },
                headers={"content-type": "application/x-www-form-urlencoded", "user-agent": USER_AGENT},
                verify=False, timeout=30,
            )
            if resp.status_code == 200:
                tokens = resp.json()
                access_token = tokens.get("access_token", "")
                payload = decode_jwt_payload(access_token)
                auth_info = payload.get("https://api.openai.com/auth", {}) if isinstance(payload, dict) else {}
                profile = payload.get("https://api.openai.com/profile", {}) if isinstance(payload, dict) else {}
                return {
                    "access_token": access_token,
                    "refresh_token": tokens.get("refresh_token", ""),
                    "id_token": tokens.get("id_token", ""),
                    "session_token": "",
                    "account_id": str(auth_info.get("chatgpt_account_id") or ""),
                    "chatgpt_account_id": str(auth_info.get("chatgpt_account_id") or ""),
                    "chatgpt_user_id": str(auth_info.get("chatgpt_user_id") or ""),
                    "plan_type": str(auth_info.get("plan_type") or ""),
                }
        except Exception as e:
            self._log(f"  ❌ token 换取失败: {e}")
        return None
