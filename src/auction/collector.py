# -*- coding: utf-8 -*-
"""拍卖站在拍名单采集：并发拉取、归类、补详情与出价、提取标签/基因。"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import client, config, rules

F = config.F


def _fetch_page(tab: str, page: int) -> list:
    try:
        res = client.post_api("product", "product_list", {
            "type": tab,
            "p_name": "",
            "one_type_id": "",
            "two_type_id": "",
            "page": page,
            "page_size": config.CONFIG["PAGE_SIZE"],
            "sort_field": "",
            "sort_order": "",
        })
        return res.get("list") or []
    except Exception as exc:  # noqa: BLE001
        print(f"[拍卖站] 标签 {tab!r} 第 {page} 页拉取失败: {exc}")
        return []


def fetch_all_products() -> list:
    """并发遍历标签页 + 分页拉取全部在拍商品（按 mark 去重）。"""
    cfg = config.CONFIG
    tasks = [(tab, page) for tab in cfg["LIST_TYPES"]
             for page in range(1, cfg["MAX_PAGES"] + 1)]
    seen = {}
    with ThreadPoolExecutor(max_workers=cfg["WORKERS"]) as pool:
        futures = {pool.submit(_fetch_page, tab, page): (tab, page)
                   for tab, page in tasks}
        for fut in as_completed(futures):
            for it in fut.result():
                mark = it.get("mark") or str(it.get("id"))
                seen[mark] = it
    return list(seen.values())


def _fill_extra(it: dict) -> dict:
    """补取列表缺失的运费/押金/描述/性别/体重/出价；命中详情则回填。"""
    mark = it.get(F["MARK"]) or str(it.get(F["ID"]))
    detail = client.fetch_details(mark)
    if detail:
        it.setdefault(F["FREIGHT"], detail.get(F["FREIGHT"]))
        it.setdefault(F["DEPOSIT"], detail.get(F["DEPOSIT"]))
        it.setdefault("introduce", detail.get("introduce") or "")
        pi = detail.get("pet_info") or {}
        it.setdefault("pet_sex", pi.get("sex") or "")
        it.setdefault("pet_weight", pi.get("weight") or "")

        detail_bid = detail.get(F["BID_PRICE"])
        try:
            if detail_bid not in (None, "", "0", "0.00") and float(detail_bid) > 0:
                it[F["BID_PRICE"]] = detail_bid
        except (TypeError, ValueError):
            pass

        detail_num = detail.get(F["BID_NUM"])
        if detail_num not in (None, ""):
            try:
                if int(detail_num) > int(it.get(F["BID_NUM"]) or 0):
                    it[F["BID_NUM"]] = detail_num
            except (TypeError, ValueError):
                pass

        log = client.fetch_bid_log(mark)
        log_list = log.get("list") or []
        if log_list:
            cnt = log.get("count")
            try:
                it[F["BID_NUM"]] = int(cnt) if cnt not in (None, "") else len(log_list)
            except (TypeError, ValueError):
                it[F["BID_NUM"]] = len(log_list)
        else:
            it[F["BID_NUM"]] = 0
    return it


def collect_watch_list() -> list:
    """全量拉取后按本地分类归类、临期过滤，并发补详情，返回待入库拍品列表。"""
    by_cat = {name: [] for name in config.CONFIG["CATEGORIES"]}
    for it in fetch_all_products():
        cat = rules.classify(it)
        if cat:
            by_cat[cat].append(it)

    merged = []
    for cat_name, items in by_cat.items():
        items.sort(key=lambda x: rules.remain_seconds(x.get(F["OFF_TIME"]) or "") or 10 ** 12)
        merged.extend(items[:config.CONFIG["TOP_N_PER_CATEGORY"]])

    near = []
    for it in merged:
        sec = rules.remain_seconds(it.get(F["OFF_TIME"]) or "")
        if sec is None or sec < 0:
            continue
        if config.CONFIG["NEAR_END_MINUTES"] > 0 and sec > config.CONFIG["NEAR_END_MINUTES"] * 60:
            continue
        it["_remain_sec"] = sec
        near.append(it)

    if near:
        with ThreadPoolExecutor(max_workers=config.CONFIG["WORKERS"]) as pool:
            near = list(pool.map(_fill_extra, near))

    for it in near:
        it[F["CATEGORY"]] = rules.classify(it)
    near.sort(key=lambda x: rules.remain_seconds(x.get(F["OFF_TIME"]) or "") or 10 ** 12)
    return near
