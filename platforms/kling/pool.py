"""
Kling Cookie 池管理器
- 存储账号信息和 cookie
- 每日自动签到领积分
- 轮换 cookie 对外提供
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional

import httpx

from core.logger import get_logger

logger = get_logger(__name__)

BASE_ID = "https://id.klingai.com"
BASE_KLING = "https://klingai.com"
SID = "ksi18n.ai.portal"
APP_NAME = "ksi18n"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Origin": "https://klingai.com",
    "Referer": "https://klingai.com/global/",
}

DATA_FILE = Path(__file__).parent / "accounts.json"


class KlingAccount:
    def __init__(self, data: dict):
        self.email: str = data["email"]
        self.password: str = data["password"]
        self.cookie: str = data.get("cookie", "")
        self.credits: int = data.get("credits", 0)
        self.last_checkin: float = data.get("last_checkin", 0)
        self.last_login: float = data.get("last_login", 0)
        self.registered_at: float = data.get("registered_at", 0)
        self.active: bool = data.get("active", True)
        self.fail_count: int = data.get("fail_count", 0)

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "password": self.password,
            "cookie": self.cookie,
            "credits": self.credits,
            "last_checkin": self.last_checkin,
            "last_login": self.last_login,
            "registered_at": self.registered_at,
            "active": self.active,
            "fail_count": self.fail_count,
        }

    def needs_checkin(self) -> bool:
        """是否需要签到（超过 20 小时未签到）"""
        return time.time() - self.last_checkin > 20 * 3600

    def needs_login(self) -> bool:
        """cookie 是否可能过期（超过 6 小时）"""
        return not self.cookie or time.time() - self.last_login > 6 * 3600


class KlingPool:
    """Kling 账号池"""

    def __init__(self, data_file: Path = DATA_FILE):
        self.data_file = data_file
        self.accounts: list[KlingAccount] = []
        self._idx = 0
        self._load()

    def _load(self):
        if self.data_file.exists():
            try:
                raw = json.loads(self.data_file.read_text())
                self.accounts = [KlingAccount(a) for a in raw]
                logger.info(f"KlingPool: loaded {len(self.accounts)} accounts")
            except Exception as e:
                logger.error(f"KlingPool load error: {e}")

    def save(self):
        self.data_file.write_text(
            json.dumps([a.to_dict() for a in self.accounts], indent=2, ensure_ascii=False)
        )

    def add_account(self, email: str, password: str, cookie: str = "") -> KlingAccount:
        """添加账号"""
        for acc in self.accounts:
            if acc.email == email:
                if cookie:
                    acc.cookie = cookie
                    acc.last_login = time.time()
                self.save()
                return acc
        acc = KlingAccount({
            "email": email,
            "password": password,
            "cookie": cookie,
            "registered_at": time.time(),
        })
        self.accounts.append(acc)
        self.save()
        logger.info(f"KlingPool: added {email}")
        return acc

    def get_cookie(self) -> Optional[str]:
        """轮换获取 cookie"""
        active = [a for a in self.accounts if a.active and a.cookie]
        if not active:
            return None
        acc = active[self._idx % len(active)]
        self._idx += 1
        return acc.cookie

    def stats(self) -> dict:
        total = len(self.accounts)
        active = sum(1 for a in self.accounts if a.active and a.cookie)
        total_credits = sum(a.credits for a in self.accounts)
        return {"total": total, "active": active, "total_credits": total_credits}

    async def login_account(self, acc: KlingAccount) -> bool:
        """登录账号，更新 cookie"""
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
                resp = await client.post(
                    f"{BASE_ID}/pass/{APP_NAME}/web/login/emailPassword",
                    data={
                        "sid": SID,
                        "email": acc.email,
                        "password": acc.password,
                        "language": "en",
                        "isWebSig4": "false",
                    }
                )
                result = resp.json()
                if result.get(f"{SID}_st") or result.get("result") == 1:
                    cookie = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
                    acc.cookie = cookie
                    acc.last_login = time.time()
                    acc.fail_count = 0
                    logger.info(f"KlingPool: login OK {acc.email}")
                    return True
                else:
                    logger.warning(f"KlingPool: login fail {acc.email}: {result}")
                    acc.fail_count += 1
                    if acc.fail_count >= 5:
                        acc.active = False
                        logger.warning(f"KlingPool: disabled {acc.email}")
                    return False
        except Exception as e:
            logger.error(f"KlingPool: login error {acc.email}: {e}")
            return False

    async def checkin_account(self, acc: KlingAccount) -> bool:
        """签到领积分"""
        if not acc.cookie:
            return False
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{BASE_KLING}/global/api/pay/reward?activity=login_bonus_daily",
                    headers={**HEADERS, "Cookie": acc.cookie}
                )
                data = resp.json()
                logger.info(f"KlingPool: checkin {acc.email}: {data}")
                if data.get("result") in (1, 0) or "reward" in str(data).lower() or "success" in str(data).lower():
                    acc.last_checkin = time.time()
                    # 解析积分
                    reward = data.get("data", {}) or {}
                    if isinstance(reward, dict):
                        delta = reward.get("rewardAmount") or reward.get("amount") or 0
                        acc.credits += int(delta)
                    return True
                elif data.get("result") == 100110000:
                    # cookie 过期，重新登录
                    logger.info(f"KlingPool: cookie expired for {acc.email}, re-login")
                    await self.login_account(acc)
                return False
        except Exception as e:
            logger.error(f"KlingPool: checkin error {acc.email}: {e}")
            return False

    async def run_daily_checkin(self):
        """对所有账号执行每日签到"""
        logger.info(f"KlingPool: starting daily checkin for {len(self.accounts)} accounts")
        for acc in self.accounts:
            if not acc.active:
                continue
            if acc.needs_login():
                await self.login_account(acc)
                await asyncio.sleep(2)
            if acc.needs_checkin():
                await self.checkin_account(acc)
                await asyncio.sleep(2)
        self.save()
        stats = self.stats()
        logger.info(f"KlingPool: checkin done. Stats: {stats}")
        return stats
