# -*- coding: utf-8 -*-
"""拍卖站接口请求封装（标准库 urllib，无第三方依赖）。"""
import http.client
import json
import ssl
import threading
import time
import urllib.parse

from . import config

_conn_cache = {}
_ssl_ctx = ssl.create_default_context()
_conn_lock = threading.Lock()


def _get_conn(host: str) -> http.client.HTTPSConnection:
    """每个线程持有独立连接，避免多线程共用一个 http.client 连接报错。"""
    ident = threading.get_ident()
    key = (host, ident)
    with _conn_lock:
        conn = _conn_cache.get(key)
        if conn is not None:
            try:
                conn.sock  # 探测连接是否还在
                return conn
            except Exception:
                _conn_cache.pop(key, None)
        conn = http.client.HTTPSConnection(
            host, timeout=config.CONFIG["REQUEST_TIMEOUT"], context=_ssl_ctx
        )
        _conn_cache[key] = conn
        return conn


def _post_once(module: str, action: str, extra_data: dict) -> dict:
    cfg = config.CONFIG
    data = {
        "customer_id": cfg["CUSTOMER_ID"],
        "app_id": cfg["APP_ID"],
        "token": cfg["TOKEN"],
    }
    data.update(extra_data)
    body = urllib.parse.urlencode(data).encode("utf-8")
    parsed = urllib.parse.urlparse(cfg["BASE"])
    host = parsed.netloc
    path = parsed.path + "?m=" + module + "&a=" + action

    conn = _get_conn(host)
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": cfg["BASE"],
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
        "Content-Length": str(len(body)),
        "Connection": "keep-alive",
    }
    try:
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="replace")
        if resp.status >= 500:
            raise RuntimeError("服务端 %d" % resp.status)
        return json.loads(raw)
    except Exception:
        with _conn_lock:
            _conn_cache.pop(host, None)
        raise


def post_api(module: str, action: str, extra_data: dict) -> dict:
    """表单 POST 调用站点接口，失败按配置重试，返回解析后的 dict。"""
    retries = config.CONFIG.get("RETRIES", 2)
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return _post_once(module, action, extra_data)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                time.sleep(config.CONFIG.get("RETRY_DELAY", 1.0) * (attempt + 1))
    raise last_exc


def fetch_details(mark: str) -> dict:
    """拉取拍品详情（补运费/押金等列表缺失字段），失败返回 {}。"""
    try:
        res = post_api("product", "product_details", {"mark": mark})
        return res.get("data") or {}
    except Exception:
        return {}


def fetch_bid_log(mark: str) -> dict:
    """拉取出价日志；返回 {count, list}。失败返回 {}。"""
    try:
        res = post_api("product", "get_bid_log", {"mark": mark})
        return {"count": res.get("count"), "list": res.get("list") or []}
    except Exception:
        return {}
