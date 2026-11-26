# -*- coding: utf-8 -*-
"""拍卖站适配器：采集 → 映射统一记录 → 关键词判定 → 落库 → 通知。"""
import asyncio
import datetime
import json
import urllib.parse

from . import collector, config, rules
from src.ai_handler import send_ntfy_notification
from src.keyword_rule_engine import evaluate_keyword_rules, build_search_text
from src.services.result_storage_service import load_visible_result_item_ids
from src.infrastructure.persistence.storage_names import build_result_filename
from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_connection import sqlite_connection
from src.utils import save_to_jsonl

KEYWORD = "拍卖站"
TASK_NAME = "拍卖站监控"
SOURCE = "auction"

F = config.F

# 最近一轮采集状态（内存缓存，供后台状态接口读取）
_state: dict = {
    "last_run": None,
    "last_total": 0,
    "last_saved": 0,
    "last_recommended": 0,
    "items": [],
}


# ============================ 任务表对接 ============================

def _load_auction_task_row() -> dict | None:
    """同步读取拍卖站监控任务记录；不存在返回 None。"""
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE source = ? ORDER BY id ASC LIMIT 1",
            (SOURCE,),
        ).fetchone()
    return dict(row) if row else None


def ensure_auction_task() -> dict:
    """确保拍卖站监控任务存在；不存在则写入种子记录。返回任务 dict。"""
    existing = _load_auction_task_row()
    if existing:
        return existing

    seed = {
        "task_name": TASK_NAME,
        "enabled": 0,
        "keyword": KEYWORD,
        "description": "监控易宠宝拍卖站在拍玉米蛇 / 王蛇，命中重点关键词的拍品会进入结果库并推送通知。",
        "analyze_images": 0,
        "max_pages": 0,
        "personal_only": 0,
        "min_price": None,
        "max_price": None,
        "cron": None,
        "ai_prompt_base_file": "prompts/base_prompt.txt",
        "ai_prompt_criteria_file": "",
        "account_state_file": None,
        "account_strategy": "auto",
        "free_shipping": 1,
        "new_publish_option": None,
        "region": None,
        "decision_mode": "keyword",
        "keyword_rules_json": "[]",
        "is_running": 0,
        "source": SOURCE,
    }
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), -1) AS max_id FROM tasks").fetchone()
        task_id = int(row["max_id"]) + 1
        conn.execute(
            """
            INSERT INTO tasks (
                id, task_name, enabled, keyword, description, analyze_images,
                max_pages, personal_only, min_price, max_price, cron,
                ai_prompt_base_file, ai_prompt_criteria_file, account_state_file,
                account_strategy, free_shipping, new_publish_option, region,
                decision_mode, keyword_rules_json, is_running, source
            ) VALUES (
                :id, :task_name, :enabled, :keyword, :description, :analyze_images,
                :max_pages, :personal_only, :min_price, :max_price, :cron,
                :ai_prompt_base_file, :ai_prompt_criteria_file, :account_state_file,
                :account_strategy, :free_shipping, :new_publish_option, :region,
                :decision_mode, :keyword_rules_json, :is_running, :source
            )
            """,
            {"id": task_id, **seed},
        )
        conn.commit()
    return _load_auction_task_row()


def _task_keyword_rules() -> list[str]:
    """读取任务配置的重点关键词；任务缺失时回退 .env 配置。"""
    row = _load_auction_task_row()
    if row is not None:
        try:
            rules = json.loads(row.get("keyword_rules_json") or "[]")
            if isinstance(rules, list):
                return [str(x).strip() for x in rules if str(x).strip()]
        except (ValueError, TypeError):
            pass
    return list(config.CONFIG["KEYWORD_RULES"])


def _task_enabled() -> bool:
    row = _load_auction_task_row()
    if row is None:
        return bool(config.CONFIG["ENABLED"])
    return bool(row.get("enabled"))


def _set_task_running(is_running: bool) -> None:
    """回写拍卖站任务的运行状态（不改动 enabled）。"""
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        conn.execute(
            "UPDATE tasks SET is_running = ? WHERE source = ?",
            (1 if is_running else 0, SOURCE),
        )
        conn.commit()



def _status_text(status: str) -> str:
    return config.STATUS_TEXT.get(str(status), str(status or ""))


def _proxy_image(url: str) -> str:
    """OSS 图片经本地代理加载，绕过 Referer 防盗链（本地域名不在白名单会被 403）。"""
    if not url:
        return ""
    return "/api/auction/image?url=" + urllib.parse.quote(url, safe="")


def map_record(it: dict) -> dict:
    """把拍卖站拍品映射为本工程统一的商品记录结构。"""
    mark = str(it.get(F["MARK"]) or it.get(F["ID"]) or "")
    name = it.get("name", "") or ""
    tags = rules.extract_tags(it)
    category = it.get(F["CATEGORY"], "")
    gene = rules.classify_gene(name, category)
    start = rules._to_float(it.get(F["START_PRICE"]))
    bid = rules._to_float(it.get(F["BID_PRICE"]) or it.get(F["BID_PRICE_HIST"]))
    each_add = rules._to_float(it.get(F["EACH_ADD"]))
    deposit = rules._to_float(it.get(F["DEPOSIT"]))
    bid_num = int(it.get(F["BID_NUM"]) or 0)
    deal, freight, has_bid = rules.deal_price(it)

    img = rules.first_image(it)
    # 拍卖站无公开详情页，用 mark 构造唯一占位链接，保证落库唯一键不冲突
    detail_link = f"{config.CONFIG['BASE']}?mark={mark}"
    item_data = {
        "商品ID": mark,
        "商品标题": name,
        "当前售价": str(deal),
        "当前拍价": bid,
        "起拍价": start,
        "运费": freight,
        "加价幅度": each_add,
        "保证金": deposit,
        "成交价": deal,
        "是否有人出价": bool(has_bid),
        "商品链接": detail_link,
        "商品图片列表": [_proxy_image(img)] if img else [],
        "卖家昵称": "",
        "基因": gene,
        "分类": category,
        "克重": tags["weight"],
        "性别": tags["sex"],
        "标签": "、".join(tags["tags"]),
        "标签列表": tags["tags"],
        "出价人数": bid_num,
        "剩余时间(秒)": it.get("_remain_sec", ""),
        "状态": _status_text(it.get(F["STATUS"], "")),
        "状态码": str(it.get(F["STATUS"], "")),
        "结束时间": it.get(F["OFF_TIME"], ""),
    }
    return {
        "爬取时间": datetime.datetime.now().isoformat(),
        "搜索关键字": KEYWORD,
        "任务名称": TASK_NAME,
        "商品信息": item_data,
        "卖家信息": {},
    }


def _evaluate(record: dict) -> dict:
    rules_kw = _task_keyword_rules()
    if not rules_kw:
        return {
            "analysis_source": "keyword",
            "is_recommended": False,
            "reason": "未配置拍卖站重点关键词，仅落库。",
            "matched_keywords": [],
            "keyword_hit_count": 0,
        }
    return evaluate_keyword_rules(rules_kw, build_search_text(record))


async def run_once() -> dict:
    """执行一轮拍卖站采集与入库。返回 {total, saved, recommended}。"""
    _set_task_running(True)
    try:
        items = collector.collect_watch_list()
        filename = build_result_filename(KEYWORD)
        existing_ids = load_visible_result_item_ids(filename)

        saved = 0
        recommended = 0
        records: list[dict] = []
        for it in items:
            mark = str(it.get(F["MARK"]) or it.get(F["ID"]) or "")

            record = map_record(it)
            analysis = _evaluate(record)
            record["ai_analysis"] = analysis
            records.append(record)

            if analysis.get("is_recommended"):
                recommended += 1
                if mark not in existing_ids:
                    try:
                        await send_ntfy_notification(record, analysis.get("reason", "无"))
                    except Exception as exc:  # noqa: BLE001
                        print(f"[拍卖站] 通知发送失败: {exc}")

            if mark and mark in existing_ids:
                continue

            if await save_to_jsonl(record, KEYWORD):
                saved += 1
                existing_ids.add(mark)

        _state["last_run"] = datetime.datetime.now().isoformat()
        _state["last_total"] = len(items)
        _state["last_saved"] = saved
        _state["last_recommended"] = recommended
        _state["items"] = records

        await upsert_history(records)

        print(f"[拍卖站] 本轮采集 {len(items)} 件，新增入库 {saved} 件，推荐 {recommended} 件。")
        return {"total": len(items), "saved": saved, "recommended": recommended}
    finally:
        _set_task_running(False)


def get_status() -> dict:
    """返回适配器当前状态（供后台接口读取）。"""
    row = _load_auction_task_row()
    task_id = row["id"] if row else None
    is_running = bool(row.get("is_running")) if row else False
    return {
        "enabled": _task_enabled(),
        "task_id": task_id,
        "is_running": is_running,
        "site_base": config.CONFIG["BASE"],
        "interval": config.CONFIG["INTERVAL"],
        "keyword_rules": _task_keyword_rules(),
        "categories": list(config.CONFIG["CATEGORIES"].keys()),
        "result_file": build_result_filename(KEYWORD),
        "last_run": _state["last_run"],
        "last_total": _state["last_total"],
        "last_saved": _state["last_saved"],
        "last_recommended": _state["last_recommended"],
        "item_count": len(_state["items"]),
    }


def get_items() -> list[dict]:
    """返回最近一轮映射后的拍品记录。"""
    return _state["items"]


# ============================ 历史行情 / 命中清单 ============================


def _upsert_history_sync(records: list[dict]) -> None:
    """把本轮拍品快照写入历史行情表（按 mark 覆盖最新一条），供基因价格曲线聚合。"""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with sqlite_connection() as conn:
        for rec in records:
            info = rec.get("商品信息", {}) or {}
            mark = str(info.get("商品ID") or "").strip()
            if not mark:
                continue
            tags = info.get("标签列表") or []
            images = info.get("商品图片列表") or []
            conn.execute(
                """
                INSERT INTO auction_history (
                    mark, gene, category, name, sex, weight, tags_json,
                    start_price, current_bid, bid_num, freight, deal_price,
                    has_bid, status, off_time, img, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mark) DO UPDATE SET
                    gene=excluded.gene, category=excluded.category, name=excluded.name,
                    sex=excluded.sex, weight=excluded.weight, tags_json=excluded.tags_json,
                    start_price=excluded.start_price, current_bid=excluded.current_bid,
                    bid_num=excluded.bid_num, freight=excluded.freight,
                    deal_price=excluded.deal_price, has_bid=excluded.has_bid,
                    status=excluded.status, off_time=excluded.off_time,
                    img=excluded.img, updated_at=excluded.updated_at
                """,
                (
                    mark, info.get("基因"), info.get("分类"), info.get("商品标题"),
                    info.get("性别"), info.get("克重"), json.dumps(tags, ensure_ascii=False),
                    info.get("起拍价"), info.get("当前拍价"), info.get("出价人数"),
                    info.get("运费"), info.get("成交价"),
                    1 if info.get("是否有人出价") else 0,
                    info.get("状态"), info.get("结束时间"),
                    images[0] if images else "", now,
                ),
            )
        conn.commit()


def _load_hits_sync() -> list[dict]:
    """按当前任务配置的重点关键词，对拍卖站记录实时重算，返回命中项。

    重点词可能后配，不能依赖入库时写入的推荐快照；规则为空时返回空。
    """
    rules_kw = _task_keyword_rules()
    if not rules_kw:
        return []
    filename = build_result_filename(KEYWORD)
    with sqlite_connection() as conn:
        rows = conn.execute(
            """
            SELECT raw_json FROM result_items
            WHERE result_filename = ?
            ORDER BY crawl_time DESC
            """,
            (filename,),
        ).fetchall()

    hits: list[dict] = []
    for row in rows:
        record = json.loads(str(row["raw_json"]))
        analysis = evaluate_keyword_rules(rules_kw, build_search_text(record))
        if analysis.get("is_recommended"):
            record["ai_analysis"] = analysis
            hits.append(record)
    return hits


def _load_series_sync(gene: str, category: str | None) -> list[dict]:
    """按基因返回历史结拍价曲线点（成交价口径：有人出价=出价+运费，无人出价=起拍价+运费）。"""
    sql = "SELECT * FROM auction_history WHERE gene = ?"
    params: list = [gene]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY off_time ASC, updated_at ASC"
    with sqlite_connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()

    points: list[dict] = []
    for row in rows:
        d = dict(row)
        points.append({
            "mark": d["mark"],
            "name": d["name"],
            "sex": d["sex"],
            "weight": d["weight"],
            "gene": d["gene"],
            "category": d["category"],
            "img": d["img"],
            "price": d["deal_price"],
            "start_price": d["start_price"],
            "current_bid": d["current_bid"],
            "bid_num": d["bid_num"],
            "freight": d["freight"],
            "has_bid": bool(d["has_bid"]),
            "status": d["status"],
            "off_time": d["off_time"],
            "date": d["off_time"],
        })
    return points


async def upsert_history(records: list[dict]) -> None:
    await asyncio.to_thread(_upsert_history_sync, records)


async def get_hits() -> list[dict]:
    return await asyncio.to_thread(_load_hits_sync)


async def get_history_series(gene: str, category: str | None) -> list[dict]:
    return await asyncio.to_thread(_load_series_sync, gene, category)


async def refresh_now() -> dict:
    """手动触发一轮采集（不受后台开关限制）。"""
    return await run_once()


async def start_background(stop_event: asyncio.Event) -> None:
    """后台轮询协程：按配置间隔循环执行；是否运行以任务表启用状态为准。"""
    print(f"[拍卖站] 后台轮询协程已启动，间隔 {config.CONFIG['INTERVAL']} 秒。")
    while not stop_event.is_set():
        if _task_enabled():
            try:
                await run_once()
            except Exception as exc:  # noqa: BLE001
                print(f"[拍卖站] 本轮采集异常: {exc}")

        interval = max(1, int(config.CONFIG["INTERVAL"]))
        for _ in range(interval):
            if stop_event.is_set():
                break
            await asyncio.sleep(1)

    print("[拍卖站] 后台轮询已停止。")
