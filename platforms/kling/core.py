"""
Kling AI 国际版自动注册机

流程：
1. moemail 生成临时邮箱
2. checkEmailExist（带 yescaptcha 过滑块）
3. 发送验证码 email/code（带滑块 token）
4. 读取验证码
5. registerByEmail 注册
6. emailPasswordLogin 登录拿 cookie
7. 每日签到领积分
"""
from __future__ import annotations

import asyncio
import random
import string
import time
from typing import Optional

import httpx

from core.base_mailbox import MoEmailMailbox
from core.config import get_config
from core.logger import get_logger

logger = get_logger(__name__)

# Kling ksi18n 接口
BASE_ID = "https://id.klingai.com"
BASE_KLING = "https://klingai.com"
SID = "ksi18n.ai.portal"
APP_NAME = "ksi18n"

YESCAPTCHA_KEY = "94863bbd87706b4b2c641d8ead72c058d4d81ecc37630"
YESCAPTCHA_API = "https://api.yescaptcha.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Origin": "https://klingai.com",
    "Referer": "https://klingai.com/",
    "Content-Type": "application/x-www-form-urlencoded",
}


def random_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + "!@#$"
    pwd = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
        random.choice("!@#$"),
    ]
    pwd += random.choices(chars, k=length - 4)
    random.shuffle(pwd)
    return "".join(pwd)


class YesCaptchaSolver:
    """yescaptcha 滑块验证码解决器"""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.key = YESCAPTCHA_KEY

    async def solve_captcha_url(self, captcha_url: str, website_url: str = "https://klingai.com") -> Optional[str]:
        """
        提交滑块验证码任务，返回 checkToken
        captcha_url: Kling 返回的 captchaSession URL
        """
        # 提取 captchaSession
        session_param = ""
        if "captchaSession=" in captcha_url:
            session_param = captcha_url.split("captchaSession=")[1].split("&")[0]

        # 提交任务（使用 GeeTestTaskProxyless 或 CustomCaptchaTask）
        # Kling 用的是 uvfuns.com 滑块，尝试 AntiKasadaTask 或 CustomCaptchaTask
        payload = {
            "clientKey": self.key,
            "task": {
                "type": "AntiKasadaTask",
                "websiteURL": website_url,
                "captchaUrl": captcha_url,
                "captchaSession": session_param,
            }
        }
        try:
            resp = await self.client.post(f"{YESCAPTCHA_API}/createTask", json=payload, timeout=30)
            data = resp.json()
            if data.get("errorId") != 0:
                logger.warning(f"YesCaptcha createTask error: {data}")
                # 回退到 CustomCaptchaTask
                payload["task"]["type"] = "CustomCaptchaTask"
                resp = await self.client.post(f"{YESCAPTCHA_API}/createTask", json=payload, timeout=30)
                data = resp.json()

            task_id = data.get("taskId")
            if not task_id:
                return None

            # 轮询结果
            for _ in range(30):
                await asyncio.sleep(3)
                poll = await self.client.post(
                    f"{YESCAPTCHA_API}/getTaskResult",
                    json={"clientKey": self.key, "taskId": task_id},
                    timeout=15
                )
                result = poll.json()
                status = result.get("status")
                if status == "ready":
                    solution = result.get("solution", {})
                    token = solution.get("token") or solution.get("checkToken") or solution.get("gRecaptchaResponse")
                    logger.info(f"YesCaptcha solved: token={str(token)[:30]}")
                    return token
                elif status == "failed":
                    logger.warning(f"YesCaptcha failed: {result}")
                    return None
        except Exception as e:
            logger.error(f"YesCaptcha error: {e}")
        return None


class KlingRegister:
    """Kling 国际版注册机"""

    def __init__(self):
        self.client = httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True)
        self.solver = YesCaptchaSolver(self.client)
        self.mailbox: Optional[MoEmailMailbox] = None

    async def close(self):
        await self.client.aclose()

    async def _post_id(self, path: str, data: dict) -> dict:
        url = f"{BASE_ID}{path}"
        resp = await self.client.post(url, data=data)
        return resp.json()

    async def check_email_exist(self, email: str) -> dict:
        """检查邮箱是否存在（会触发滑块）"""
        result = await self._post_id(
            f"/pass/{APP_NAME}/web/account/checkEmailExist",
            {"sid": SID, "email": email}
        )
        return result

    async def request_email_code(self, email: str, zt_token: str = None, zt_type: int = None) -> dict:
        """发送注册验证码"""
        data = {"sid": SID, "email": email, "type": 1}
        if zt_token:
            data["ztIdentityVerificationCheckToken"] = zt_token
            data["ztIdentityVerificationType"] = zt_type or 1
        result = await self._post_id(f"/pass/{APP_NAME}/web/email/code", data)
        return result

    async def register(self, email: str, email_code: str, password: str) -> dict:
        """注册账号"""
        result = await self._post_id(
            f"/pass/{APP_NAME}/web/register/emailPassword",
            {
                "sid": SID,
                "email": email,
                "emailCode": email_code,
                "password": password,
                "setCookie": "true",
            }
        )
        return result

    async def login(self, email: str, password: str) -> Optional[str]:
        """登录，返回 cookie 字符串"""
        result = await self._post_id(
            f"/pass/{APP_NAME}/web/login/emailPassword",
            {"sid": SID, "email": email, "password": password, "language": "en", "isWebSig4": "false"}
        )
        if result.get("result") == 1 or result.get(f"{SID}_st"):
            # 从响应 cookie 里拿
            cookies = dict(self.client.cookies)
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            logger.info(f"Login success: {email}")
            return cookie_str
        logger.warning(f"Login failed: {result}")
        return None

    async def daily_checkin(self, cookie_str: str) -> dict:
        """每日签到"""
        headers = {"Cookie": cookie_str, "Referer": "https://klingai.com/global/"}
        resp = await self.client.get(
            f"{BASE_KLING}/global/api/pay/reward?activity=login_bonus_daily",
            headers=headers
        )
        return resp.json()

    async def run_register(self) -> Optional[dict]:
        """完整注册流程"""
        # 1. 生成临时邮箱
        mail_url = get_config("mail_url") or "https://sall.cc"
        self.mailbox = MoEmailMailbox(base_url=mail_url)
        email = await self.mailbox.create_email()
        if not email:
            logger.error("Failed to create temp email")
            return None
        logger.info(f"Temp email: {email}")

        password = random_password()

        # 2. 检查邮箱（获取滑块挑战）
        check_result = await self.check_email_exist(email)
        logger.info(f"checkEmailExist: {check_result}")

        zt_token = None
        zt_type = None
        if check_result.get("result") == 400002:
            # 需要过滑块
            captcha_url = check_result.get("url", "")
            logger.info(f"Solving captcha: {captcha_url[:80]}")
            zt_token = await self.solver.solve_captcha_url(captcha_url)
            if not zt_token:
                logger.error("Failed to solve captcha")
                return None
            zt_type = 1

        # 3. 发验证码
        code_result = await self.request_email_code(email, zt_token, zt_type)
        logger.info(f"requestEmailCode: {code_result}")
        if code_result.get("result") not in (0, 1, None) and "success" not in str(code_result).lower():
            if code_result.get("result") != 0:
                logger.warning(f"Send code unexpected result: {code_result}")

        # 4. 等待验证码
        logger.info("Waiting for email code...")
        code = None
        for _ in range(24):
            await asyncio.sleep(5)
            messages = await self.mailbox.get_messages(email)
            for msg in (messages or []):
                content = str(msg.get("content", "") or msg.get("body", ""))
                import re
                m = re.search(r'\b(\d{6})\b', content)
                if m:
                    code = m.group(1)
                    logger.info(f"Got email code: {code}")
                    break
            if code:
                break
        if not code:
            logger.error("No email code received")
            return None

        # 5. 注册
        reg_result = await self.register(email, code, password)
        logger.info(f"register: {reg_result}")

        # 6. 登录
        cookie = await self.login(email, password)
        if not cookie:
            # 注册可能直接返回了 token
            cookie = dict(self.client.cookies)
            if cookie:
                cookie = "; ".join(f"{k}={v}" for k, v in cookie.items())
            else:
                cookie = None

        return {
            "email": email,
            "password": password,
            "cookie": cookie,
            "registered_at": int(time.time()),
        }
