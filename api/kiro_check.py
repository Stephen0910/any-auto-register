"""
Kiro 账号状态验证接口
直接调用 AWS Q API 验证 token 有效性
"""
from __future__ import annotations
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter(prefix="/kiro-check", tags=["kiro-check"])


class KiroCheckRequest(BaseModel):
    account_id: int
    proxy: Optional[str] = None


def _check_token(access_token: str, proxy: str = None) -> dict:
    """直接调用 AWS Q API 验证 token 状态"""
    from curl_cffi import requests as cffi_requests
    import json

    url = "https://q.us-east-1.amazonaws.com/getUsageLimits?origin=AI_EDITOR&resourceType=AGENTIC_REQUEST"
    headers = {
        "content-type": "application/x-amz-json-1.0",
        "x-amz-target": "AmazonCodeWhispererStreamingService.GenerateAssistantResponse",
        "user-agent": "aws-sdk-rust/1.3.9 ua/2.1 api/codewhispererstreaming/0.1.11582 os/windows lang/rust/1.87.0 md/appVersion-1.19.4 app/AmazonQ-For-CLI",
        "x-amz-user-agent": "aws-sdk-rust/1.3.9 ua/2.1 api/codewhispererstreaming/0.1.11582 os/windows lang/rust/1.87.0 m/F app/AmazonQ-For-CLI",
        "x-amzn-codewhisperer-optout": "false",
        "authorization": f"Bearer {access_token}",
        "amz-sdk-request": "attempt=1; max=3",
        "amz-sdk-invocation-id": str(uuid.uuid4()),
    }
    proxies = {"https": proxy, "http": proxy} if proxy else {}
    try:
        resp = cffi_requests.get(url, headers=headers, proxies=proxies, verify=False,
                                  timeout=15, impersonate="chrome110")
        body = resp.text
        status_code = resp.status_code

        if "TEMPORARILY_SUSPENDED" in body:
            return {"status": "suspended", "status_code": status_code, "detail": "账号已被临时封禁"}
        elif status_code == 401 or "ExpiredToken" in body or "UnauthorizedException" in body:
            return {"status": "expired", "status_code": status_code, "detail": "Token 已过期"}
        elif "AccessDeniedException" in body or "ValidationException" in body or status_code == 403:
            return {"status": "invalid", "status_code": status_code, "detail": "Token 无效"}
        elif 200 <= status_code < 300:
            return {"status": "valid", "status_code": status_code, "detail": "账号正常"}
        else:
            return {"status": "error", "status_code": status_code, "detail": body[:200]}
    except Exception as e:
        return {"status": "error", "status_code": -1, "detail": str(e)}


@router.post("/check")
def check_account(body: KiroCheckRequest):
    """验证 Kiro 账号 token 状态"""
    from sqlmodel import Session, select
    from core.db import AccountModel, AccountCredentialModel, engine

    with Session(engine) as s:
        acc = s.get(AccountModel, body.account_id)
        if not acc or acc.platform != "kiro":
            raise HTTPException(404, "Kiro 账号不存在")
        creds = s.exec(
            select(AccountCredentialModel).where(
                AccountCredentialModel.account_id == body.account_id,
                AccountCredentialModel.scope == "platform",
            )
        ).all()
        cred_map = {c.key: c.value for c in creds}

    access_token = cred_map.get("accessToken") or ""
    if not access_token:
        return {"ok": False, "email": acc.email, "status": "no_token", "detail": "无 accessToken"}

    result = _check_token(access_token, proxy=body.proxy)
    return {"ok": True, "email": acc.email, **result}
