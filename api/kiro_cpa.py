"""Kiro CPA 专用 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/kiro-cpa", tags=["kiro-cpa"])


class CpaTestRequest(BaseModel):
    api_url: str
    api_key: str
    proxy: Optional[str] = None


class CpaUploadRequest(BaseModel):
    account_id: int
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    proxy: Optional[str] = None


class CpaUploadRawRequest(BaseModel):
    """直接传 token 数据上传（无需数据库账号）"""
    token_data: dict
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    proxy: Optional[str] = None


@router.post("/test")
def test_connection(body: CpaTestRequest):
    """测试 CPA 连接"""
    from platforms.kiro.cpa_upload import test_cpa_connection
    ok, msg = test_cpa_connection(body.api_url, body.api_key, proxy=body.proxy)
    return {"ok": ok, "message": msg}


@router.post("/upload")
def upload_account(body: CpaUploadRequest):
    """将数据库中已注册的 Kiro 账号上传到 CPA"""
    from sqlmodel import Session, select
    from core.db import AccountModel, AccountCredentialModel, engine
    from platforms.kiro.cpa_upload import upload_to_cpa
    from datetime import datetime, timezone, timedelta

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

    now = datetime.now(tz=timezone(timedelta(hours=8)))
    expires_at = datetime.now(tz=timezone(timedelta(hours=8))) + timedelta(hours=1)

    token_data = {
        "access_token": cred_map.get("accessToken") or cred_map.get("access_token") or "",
        "auth_method": "builder-id",
        "client_id": cred_map.get("clientId") or cred_map.get("client_id") or "",
        "client_secret": cred_map.get("clientSecret") or cred_map.get("client_secret") or "",
        "disabled": False,
        "email": acc.email,
        "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "last_refresh": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "profile_arn": "",
        "provider": "AWS",
        "refresh_token": cred_map.get("refreshToken") or cred_map.get("refresh_token") or "",
        "region": "us-east-1",
        "start_url": "https://view.awsapps.com/start",
        "type": "kiro",
    }

    ok, msg = upload_to_cpa(token_data, api_url=body.api_url, api_key=body.api_key, proxy=body.proxy)
    return {"ok": ok, "message": msg, "email": acc.email}


@router.post("/upload-raw")
def upload_raw(body: CpaUploadRawRequest):
    """直接上传 token_data 到 CPA（供注册流程内部调用）"""
    from platforms.kiro.cpa_upload import upload_to_cpa
    ok, msg = upload_to_cpa(body.token_data, api_url=body.api_url, api_key=body.api_key, proxy=body.proxy)
    return {"ok": ok, "message": msg}


@router.get("/profiles")
def get_cpa_profiles():
    """从 8899 服务读取 pool_profiles 作为下拉选项（默认配置）"""
    import os, json
    config_path = "/home/projects/strange/openai/2026-02-25/ctf_ai/config.json"
    if not os.path.exists(config_path):
        return {"profiles": [], "active": ""}
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
        profiles = [
            {
                "id": p.get("id", p.get("name", "")),
                "name": p.get("name", ""),
                "base_url": p.get("base_url", ""),
                "token": p.get("token", ""),
                "target_type": p.get("target_type", "codex"),
            }
            for p in cfg.get("pool_profiles", [])
        ]
        return {
            "profiles": profiles,
            "active": cfg.get("pool_active", ""),
            "default_token": cfg.get("pool", {}).get("token", ""),
        }
    except Exception as e:
        return {"profiles": [], "active": "", "error": str(e)}
