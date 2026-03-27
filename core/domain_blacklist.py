"""域名黑名单管理 - tempmail_lol 域名被 OpenAI 拉黑后自动跳过"""
import json, os, threading
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_BLACKLIST_FILE = _DATA_DIR / "tempmail_domain_blacklist.json"
_lock = threading.Lock()


def _load() -> set:
    try:
        with open(_BLACKLIST_FILE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save(blacklist: set):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_BLACKLIST_FILE, "w") as f:
        json.dump(sorted(blacklist), f, indent=2)


def add(domain: str) -> None:
    """把一个域名加入黑名单"""
    domain = (domain or "").strip().lower()
    if not domain:
        return
    with _lock:
        bl = _load()
        if domain not in bl:
            bl.add(domain)
            _save(bl)
            print(f"[DomainBlacklist] 已拉黑: {domain}")


def is_blacklisted(domain: str) -> bool:
    """判断一个域名是否在黑名单中"""
    return (domain or "").strip().lower() in _load()


def get_all() -> set:
    """返回全部黑名单域名"""
    return _load()


def clear() -> None:
    """清空黑名单（调试用）"""
    with _lock:
        _save(set())
