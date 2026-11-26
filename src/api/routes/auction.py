"""
拍卖站（易宠宝）监控后台接口。

提供适配器状态、最近一轮名单、手动触发一轮采集，以及绕过 OSS 防盗链的图片代理。
落库、关键词判定、通知复用现有结果库与通知服务。
"""
import ssl
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from src.auction import adapter

router = APIRouter(prefix="/api/auction", tags=["auction"])

# 仅允许代理该 OSS 域名，避免被当作开放代理
_ALLOWED_IMAGE_HOST = "yichongbao.oss-cn-shenzhen.aliyuncs.com"
_SSL_CTX = ssl.create_default_context()
_IMAGE_TIMEOUT = 10


@router.get("/status")
async def get_auction_status():
    """拍卖站适配器状态：开关、间隔、关键词、分类与最近一轮统计。"""
    return adapter.get_status()


@router.get("/items")
async def get_auction_items():
    """最近一轮采集到的拍卖站拍品记录（映射后的统一结构）。"""
    return {"items": adapter.get_items()}


@router.get("/hits")
async def get_auction_hits():
    """命中重点关键词的拍卖站拍品（结果查看“重点检查内容”区块使用）。"""
    return {"items": await adapter.get_hits()}


@router.get("/history/series")
async def get_auction_history_series(gene: str, category: str | None = None):
    """某基因标签下的历史结拍价曲线点。"""
    if not gene:
        raise HTTPException(status_code=400, detail="缺少基因标签")
    return {"gene": gene, "category": category, "points": await adapter.get_history_series(gene, category)}


@router.post("/refresh")
async def refresh_auction():
    """手动触发一轮拍卖站采集并入库。"""
    try:
        return await adapter.refresh_now()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"拍卖站采集失败: {exc}")


@router.get("/image")
async def proxy_image(url: str):
    """代理 OSS 图片：本地页面 Referer 不在 OSS 白名单会被 403，由服务端带站点 Referer 拉取后回传。"""
    if not url:
        raise HTTPException(status_code=400, detail="缺少图片地址")

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != _ALLOWED_IMAGE_HOST:
        raise HTTPException(status_code=403, detail="图片域名不在允许列表")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
            "Referer": adapter.config.CONFIG["BASE"],
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_IMAGE_TIMEOUT, context=_SSL_CTX) as resp:
            body = resp.read()
            content_type = resp.headers.get("Content-Type", "image/jpeg")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"图片拉取失败: {exc}")

    return Response(
        content=body,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
