"""
Sentinel Token PoW 生成器
=========================
逆向自 sentinel.openai.com SDK JS 的 PoW 算法：
  - FNV-1a 32位哈希 + xorshift 混合
  - 伪造浏览器环境数据数组
  - 暴力搜索直到哈希前缀 ≤ 难度阈值
  - t 字段传空字符串（服务端不校验），c 字段从 sentinel API 实时获取
"""
from __future__ import annotations

import base64
import json
import random
import secrets
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

# ── 常量 ──────────────────────────────────────────────

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)

OPENAI_AUTH_BASE = "https://auth.openai.com"

COMMON_HEADERS = {
    "accept": "application/json",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": OPENAI_AUTH_BASE,
    "user-agent": USER_AGENT,
    "sec-ch-ua": '"Google Chrome";v="145", "Not?A_Brand";v="8", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

NAVIGATE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": USER_AGENT,
    "sec-ch-ua": '"Google Chrome";v="145", "Not?A_Brand";v="8", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}

# ── 工具函数 ──────────────────────────────────────────

def generate_device_id() -> str:
    return str(uuid.uuid4())

def generate_pkce() -> tuple[str, str]:
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    digest = __import__("hashlib").sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge

def generate_datadog_trace() -> dict:
    trace_id = str(random.getrandbits(64))
    parent_id = str(random.getrandbits(64))
    trace_hex = format(int(trace_id), '016x')
    parent_hex = format(int(parent_id), '016x')
    return {
        "traceparent": f"00-0000000000000000{trace_hex}-{parent_hex}-01",
        "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum",
        "x-datadog-parent-id": parent_id,
        "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": trace_id,
    }

def generate_random_name() -> tuple[str, str]:
    first = ["James","Robert","John","Michael","David","William","Richard",
             "Mary","Jennifer","Linda","Elizabeth","Susan","Jessica","Sarah",
             "Emily","Emma","Olivia","Sophia","Liam","Noah","Oliver","Ethan"]
    last = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller",
            "Davis","Wilson","Anderson","Thomas","Taylor","Moore","Martin"]
    return random.choice(first), random.choice(last)

def generate_random_birthday() -> str:
    y = random.randint(1996, 2006)
    m = random.randint(1, 12)
    d = random.randint(1, 28)
    return f"{y:04d}-{m:02d}-{d:02d}"

def generate_random_password(length: int = 16) -> str:
    import string as _s
    chars = _s.ascii_letters + _s.digits + "!@#$%"
    pwd = [random.choice(_s.ascii_uppercase), random.choice(_s.ascii_lowercase),
           random.choice(_s.digits), random.choice("!@#$%")]
    pwd += [random.choice(chars) for _ in range(length - 4)]
    random.shuffle(pwd)
    return "".join(pwd)


# ── Sentinel Token Generator ─────────────────────────

class SentinelTokenGenerator:
    MAX_ATTEMPTS = 500_000
    ERROR_PREFIX = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D"

    def __init__(self, device_id: str | None = None):
        self.device_id = device_id or generate_device_id()
        self.requirements_seed = str(random.random())
        self.sid = str(uuid.uuid4())

    @staticmethod
    def _fnv1a_32(text: str) -> str:
        h = 2166136261
        for ch in text:
            h ^= ord(ch)
            h = ((h * 16777619) & 0xFFFFFFFF)
        h ^= (h >> 16)
        h = ((h * 2246822507) & 0xFFFFFFFF)
        h ^= (h >> 13)
        h = ((h * 3266489909) & 0xFFFFFFFF)
        h ^= (h >> 16)
        return format(h & 0xFFFFFFFF, '08x')

    def _get_config(self) -> list:
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)")
        nav_props = ["vendorSub","productSub","vendor","maxTouchPoints","scheduling",
                     "userActivation","doNotTrack","geolocation","connection","plugins",
                     "mimeTypes","pdfViewerEnabled","cookieEnabled","credentials",
                     "mediaDevices","permissions","locks","ink"]
        nav_prop = random.choice(nav_props)
        perf_now = random.uniform(1000, 50000)
        time_origin = time.time() * 1000 - perf_now
        return [
            "1920x1080",                          # [0]
            date_str,                              # [1]
            4294705152,                            # [2]
            random.random(),                       # [3] nonce placeholder
            USER_AGENT,                            # [4]
            "https://sentinel.openai.com/sentinel/20260124ceb8/sdk.js",  # [5]
            None,                                  # [6]
            None,                                  # [7]
            "en-US",                               # [8]
            "en-US,en",                            # [9] elapsed placeholder
            random.random(),                       # [10]
            f"{nav_prop}−undefined",               # [11]
            random.choice(["location","implementation","URL","documentURI","compatMode"]),
            random.choice(["Object","Function","Array","Number","parseFloat","undefined"]),
            perf_now,                              # [14]
            self.sid,                              # [15]
            "",                                    # [16]
            random.choice([4,8,12,16]),            # [17]
            time_origin,                           # [18]
        ]

    @staticmethod
    def _base64_json(data) -> str:
        raw = json.dumps(data, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        return base64.b64encode(raw).decode('ascii')

    def _run_check(self, start_time: float, seed: str, difficulty: str, config: list, nonce: int):
        config[3] = nonce
        config[9] = round((time.time() - start_time) * 1000)
        data = self._base64_json(config)
        hash_hex = self._fnv1a_32(seed + data)
        diff_len = len(difficulty)
        if hash_hex[:diff_len] <= difficulty:
            return data + "~S"
        return None

    def generate_token(self, seed: str | None = None, difficulty: str | None = None) -> str:
        if seed is None:
            seed = self.requirements_seed
        difficulty = difficulty or "0"
        start = time.time()
        config = self._get_config()
        for i in range(self.MAX_ATTEMPTS):
            result = self._run_check(start, seed, difficulty, config, i)
            if result:
                return "gAAAAAB" + result
        return "gAAAAAB" + self.ERROR_PREFIX + self._base64_json(str(None))

    def generate_requirements_token(self) -> str:
        config = self._get_config()
        config[3] = 1
        config[9] = round(random.uniform(5, 50))
        return "gAAAAAC" + self._base64_json(config)


# ── Sentinel API ─────────────────────────────────────

_SENTINEL_CACHE: dict[tuple, str] = {}

def fetch_sentinel_challenge(session, device_id: str, flow: str = "authorize_continue") -> dict | None:
    gen = SentinelTokenGenerator(device_id=device_id)
    body = {"p": gen.generate_requirements_token(), "id": device_id, "flow": flow}
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html",
        "User-Agent": USER_AGENT,
        "Origin": "https://sentinel.openai.com",
        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }
    try:
        resp = session.post(
            "https://sentinel.openai.com/backend-api/sentinel/req",
            data=json.dumps(body), headers=headers, timeout=15, verify=False,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def build_sentinel_token(session, device_id: str, flow: str = "authorize_continue") -> str | None:
    cache_key = (flow, device_id)
    challenge = fetch_sentinel_challenge(session, device_id, flow)
    if not challenge:
        return _SENTINEL_CACHE.get(cache_key)

    c_value = challenge.get("token", "")
    pow_data = challenge.get("proofofwork", {})
    gen = SentinelTokenGenerator(device_id=device_id)

    if pow_data.get("required") and pow_data.get("seed"):
        p_value = gen.generate_token(seed=pow_data["seed"], difficulty=pow_data.get("difficulty", "0"))
    else:
        p_value = gen.generate_requirements_token()

    token = json.dumps(
        {"p": p_value, "t": "", "c": c_value, "id": device_id, "flow": flow},
        separators=(",", ":"),
    )
    _SENTINEL_CACHE[cache_key] = token
    return token


def response_preview(resp, limit: int = 300) -> str:
    if not resp:
        return "无响应"
    try:
        text = (resp.text or "").strip()
    except Exception:
        text = ""
    if not text:
        try:
            text = json.dumps(resp.json(), ensure_ascii=False)
        except Exception:
            text = ""
    if not text:
        return f"HTTP {getattr(resp, 'status_code', '?')}"
    return text[:limit] + ("..." if len(text) > limit else "")


def extract_openai_error_code(resp) -> str | None:
    try:
        data = resp.json()
        err = data.get("error")
        if isinstance(err, dict):
            code = str(err.get("code") or "").strip()
            return code or None
    except Exception:
        pass
    return None
