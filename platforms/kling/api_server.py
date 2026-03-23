"""
Kling 视频生成 API 服务
提供 OpenAI 兼容的视频生成接口，对接 Kling cookie 池

启动: python -m platforms.kling.api_server
API: POST /v1/videos/generations
     GET  /v1/models
     POST /v1/checkin  (手动触发签到)
     GET  /v1/pool/stats
"""
from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .pool import KlingPool

# ── 配置 ──────────────────────────────────────────────
API_KEY = "bug_zip"           # 改成你想要的 key
PORT = 8088

BASE_KLING = "https://klingai.com"
HEADERS_BASE = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Origin": "https://klingai.com",
    "Referer": "https://klingai.com/global/",
}

# ── 启动 ──────────────────────────────────────────────
pool = KlingPool()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行一次签到
    asyncio.create_task(pool.run_daily_checkin())
    # 每 6 小时自动签到
    async def auto_checkin():
        while True:
            await asyncio.sleep(6 * 3600)
            await pool.run_daily_checkin()
    asyncio.create_task(auto_checkin())
    yield

app = FastAPI(title="Kling Video API", lifespan=lifespan)

# ── Auth ──────────────────────────────────────────────
def verify_key(authorization: str = Header(...)):
    key = authorization.replace("Bearer ", "").strip()
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return key

# ── Models ────────────────────────────────────────────
class VideoRequest(BaseModel):
    prompt: str = Field(..., description="视频描述")
    model: Optional[str] = Field("kling-v1", description="模型")
    size: Optional[str] = Field("16:9", description="宽高比: 16:9 / 9:16 / 1:1")
    n: Optional[int] = Field(1, ge=1, le=1)
    duration: Optional[int] = Field(5, description="时长(秒): 5 或 10")
    quality: Optional[str] = Field("standard", description="standard / high")
    image_url: Optional[str] = Field(None, description="参考图 URL（图生视频）")

# ── 视频生成 ──────────────────────────────────────────
async def generate_video_kling(
    cookie: str,
    prompt: str,
    aspect_ratio: str = "16:9",
    duration: int = 5,
    quality: str = "standard",
    image_url: Optional[str] = None,
    model_name: str = "1.0",
) -> dict:
    """
    调用 Kling API 生成视频
    返回 {url: str, id: str}
    """
    is_high = quality == "high"
    # 判断是否 CN 版 cookie
    is_cn = any(k.startswith("kuaishou") for k in cookie.split("; ") if "=" in k and k.split("=")[0].strip().startswith("kuaishou"))
    base = "https://klingai.kuaishou.com/" if is_cn else f"{BASE_KLING}/"
    submit_url = f"{base}api/task/submit"
    status_url_tpl = f"{base}api/task/status?taskId={{task_id}}"
    works_url_tpl = f"{base}api/works/batch_download_v2?workIds={{work_id}}"

    headers = {**HEADERS_BASE, "Cookie": cookie}

    if image_url:
        model_type = "m2v_img2video_hq" if is_high else "m2v_img2video"
        payload = {
            "type": model_type,
            "inputs": [{"name": "input", "inputType": "URL", "url": image_url}],
            "arguments": [
                {"name": "prompt", "value": prompt},
                {"name": "negative_prompt", "value": ""},
                {"name": "cfg", "value": "0.5"},
                {"name": "duration", "value": str(duration)},
                {"name": "kling_version", "value": model_name},
                {"name": "aspect_ratio", "value": aspect_ratio},
                {"name": "biz", "value": "klingai"},
            ],
        }
    else:
        model_type = "m2v_txt2video_hq" if is_high else "m2v_txt2video"
        payload = {
            "type": model_type,
            "arguments": [
                {"name": "prompt", "value": prompt},
                {"name": "negative_prompt", "value": ""},
                {"name": "cfg", "value": "0.5"},
                {"name": "duration", "value": str(duration)},
                {"name": "kling_version", "value": model_name},
                {"name": "aspect_ratio", "value": aspect_ratio},
                {"name": "biz", "value": "klingai"},
                {"name": "camera_type", "value": "empty_shot"},
                {"name": "camera_value", "value": "0"},
            ],
        }

    async with httpx.AsyncClient(headers=headers, timeout=300) as client:
        resp = await client.post(submit_url, json=payload)
        data = resp.json()
        if data.get("data", {}).get("status") == 7:
            raise Exception(f"Kling rejected: {data['data'].get('message')}")

        task_id = data.get("data", {}).get("task", {}).get("id")
        if not task_id:
            raise Exception(f"No task_id: {data}")

        # 轮询状态
        for _ in range(120):  # 最多 10 分钟
            await asyncio.sleep(5)
            poll = await client.get(status_url_tpl.format(task_id=task_id))
            poll_data = poll.json()
            task = poll_data.get("data", {}).get("task", {})
            status = task.get("status")

            if status == 99:  # 完成
                works = task.get("works", [])
                if works:
                    work_id = works[0].get("workId") or works[0].get("id")
                    # 获取 CDN URL
                    cdn_resp = await client.get(works_url_tpl.format(work_id=work_id))
                    cdn_data = cdn_resp.json().get("data", {})
                    video_url = cdn_data.get("cdnUrl") or works[0].get("resource", {}).get("resource", "")
                    return {"id": task_id, "url": video_url}
                raise Exception("No works in completed task")
            elif status in (50, -1, 7):
                raise Exception(f"Task failed status={status}: {task}")

        raise Exception("Timeout waiting for video")


# ── Routes ────────────────────────────────────────────
@app.get("/v1/models")
async def list_models(_: str = Depends(verify_key)):
    return JSONResponse({
        "object": "list",
        "data": [
            {"id": "kling-v1", "object": "model", "owned_by": "kling"},
            {"id": "kling-v1.5", "object": "model", "owned_by": "kling"},
        ]
    })


@app.get("/v1/pool/stats")
async def pool_stats(_: str = Depends(verify_key)):
    return JSONResponse(pool.stats())


@app.post("/v1/pool/add")
async def add_account(
    email: str,
    password: str,
    cookie: str = "",
    _: str = Depends(verify_key)
):
    """手动添加账号"""
    acc = pool.add_account(email, password, cookie)
    if not cookie:
        ok = await pool.login_account(acc)
        if ok:
            await pool.checkin_account(acc)
        pool.save()
    return JSONResponse({"ok": True, "email": email, "has_cookie": bool(acc.cookie)})


@app.post("/v1/checkin")
async def manual_checkin(_: str = Depends(verify_key)):
    """手动触发签到"""
    stats = await pool.run_daily_checkin()
    return JSONResponse({"ok": True, "stats": stats})


@app.post("/v1/videos/generations")
async def generate_video(
    request: VideoRequest,
    _: str = Depends(verify_key)
):
    """生成视频（OpenAI 兼容格式）"""
    cookie = pool.get_cookie()
    if not cookie:
        raise HTTPException(status_code=503, detail="No available Kling accounts")

    # 宽高比标准化
    size_map = {
        "1280x720": "16:9", "720x1280": "9:16", "1024x1024": "1:1",
        "16:9": "16:9", "9:16": "9:16", "1:1": "1:1",
    }
    aspect_ratio = size_map.get(request.size or "16:9", "16:9")
    quality = "high" if request.model == "kling-v1.5" else (request.quality or "standard")

    try:
        result = await generate_video_kling(
            cookie=cookie,
            prompt=request.prompt,
            aspect_ratio=aspect_ratio,
            duration=request.duration or 5,
            quality=quality,
            image_url=request.image_url,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    return JSONResponse({
        "created": int(time.time()),
        "data": [{
            "url": result["url"],
            "prompt": request.prompt,
            "aspect_ratio": aspect_ratio,
            "model": request.model,
            "task_id": result["id"],
        }],
        "id": f"video-{uuid.uuid4().hex[:16]}",
        "model": request.model,
    })


@app.get("/health")
async def health():
    return {"status": "ok", "accounts": pool.stats()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
