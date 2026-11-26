# -*- coding: utf-8 -*-
"""拍品归类、基因识别、标签提取与成交价口径（纯规则，无 IO）。"""
import datetime
import re

from . import config

F = config.F


def remain_seconds(off_time: str) -> int | None:
    """返回剩余秒数；已结束返回负数，解析失败返回 None。"""
    try:
        dt = datetime.datetime.strptime(off_time, "%Y-%m-%d %H:%M:%S")
        return int((dt - datetime.datetime.now()).total_seconds())
    except Exception:
        return None


def classify(it: dict) -> str | None:
    """返回拍品所属监控分类名；未命中返回 None。优先分类 ID，再名称兜底关键词。"""
    name = it.get("name", "") or ""
    two = str(it.get("two_type_id"))
    for cat_name, rule in config.CONFIG["CATEGORIES"].items():
        if two == str(rule["two_type_id"]):
            return cat_name
        if any(kw and kw in name for kw in rule.get("keywords", [])):
            return cat_name
    return None


def first_image(it: dict) -> str:
    imgs = it.get("img")
    if isinstance(imgs, list) and imgs:
        return str(imgs[0])
    if isinstance(imgs, str) and imgs:
        return imgs
    return ""


# 卖点关键词：命中标题或描述即打标签；"包开食"需先排除否定表述
TAG_KEYWORDS = [
    ("稳冻", ["稳冻", "稳定冻鼠", "冻鼠", "稳冻鼠"]),
    ("吃饭积极", ["吃饭很积极", "吃饭积极", "干饭", "吃东西积极", "食欲好"]),
]

_SEX_PATTERNS = [
    ("母", ["单母", "母！", "母 ", "母，", "母。", "母/", "母（", "新女", "母"]),
    ("公", ["单公", "公！", "公 ", "公，", "公。", "公/", "公（", "公"]),
]

_WEIGHT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:g|G|克)")


def _detect_sex(name: str, intro: str) -> str:
    if "一对" in name or "一对" in intro:
        return ""
    for text in (name, intro):
        for sex, kws in _SEX_PATTERNS:
            if any(k in text for k in kws):
                return sex
    return ""


def _has_open_food(name: str, intro: str) -> bool:
    text = name + " " + intro
    pos = ["包到家开食", "包开食", "包到手开食", "包开口", "到家开食"]
    neg = ["不包到家开食", "不包到手开食", "不包开口", "不包到手开口", "不包到家开口"]
    return any(k in text for k in pos) and not any(k in text for k in neg)


def extract_tags(it: dict) -> dict:
    """返回克重 / 性别 / 卖点标签。"""
    name = it.get("name", "") or ""
    intro = it.get("introduce", "") or ""
    text = "%s %s" % (name, intro)

    weight = ""
    pw = str(it.get("pet_weight") or "").strip()
    if pw and pw not in ("未知", "", "None"):
        weight = pw if pw.endswith(("克", "g", "G")) else pw + "克"
    else:
        m = _WEIGHT_RE.search(text)
        if m:
            weight = m.group(1) + "克"

    sex = str(it.get("pet_sex") or "").strip()
    if sex in ("未知", "", "None"):
        sex = _detect_sex(name, intro)

    tags = []
    if _has_open_food(name, intro):
        tags.append("包开食")
    for label, kws in TAG_KEYWORDS:
        if any(k in text for k in kws):
            tags.append(label)
    return {"weight": weight, "sex": sex, "tags": tags}


def _modifier_spans(text: str) -> list:
    """返回修饰词（het/ph/h）覆盖区间列表。"""
    marks = []
    i = 0
    n = len(text)
    while i < n:
        hit = None
        for tok in config.MODIFIER_TOKENS:
            if text.startswith(tok, i):
                if tok == "h":
                    left_ok = i == 0 or not text[i - 1].isalnum()
                    right = i + 1
                    right_ok = right >= n or not text[right].isalnum()
                    if not (left_ok and right_ok):
                        continue
                hit = tok
                break
        if hit:
            marks.append((i, i + len(hit)))
            i += len(hit)
        else:
            i += 1

    spans = []
    for k, (s, e) in enumerate(marks):
        next_s = marks[k + 1][0] if k + 1 < len(marks) else n
        spans.append((s, next_s))
    return spans


def _in_span(pos: int, spans: list) -> bool:
    return any(s <= pos < e for s, e in spans)


def _rules_for(category: str):
    if category == "王蛇":
        return [(g, kws) for g, kws in config.GENE_RULES if g in config.WANG_GENES]
    return config.GENE_RULES


def extract_genes(name: str, category: str | None = None) -> list:
    """从标题抽取命中的基因名列表（去重、保序、长词优先）。"""
    text = (name or "").lower()
    if not text:
        return []
    spans = _modifier_spans(text)

    expanded = []
    for gene, kws in _rules_for(category):
        for kw in kws:
            kw = kw.lower()
            if kw:
                expanded.append((gene, kw, len(kw)))
    expanded.sort(key=lambda x: -x[2])

    first_pos = {}
    for gene, kw, _ in expanded:
        if gene in first_pos:
            continue
        idx = text.find(kw)
        if idx >= 0 and not _in_span(idx, spans):
            first_pos[gene] = idx

    return [g for g, _ in sorted(first_pos.items(), key=lambda kv: kv[1])]


def classify_gene(name: str, category: str | None = None) -> str:
    genes = extract_genes(name, category)
    return genes[0] if genes else "其他"


def _to_float(v) -> float:
    try:
        return float(v) if v not in (None, "", "-") else 0.0
    except (TypeError, ValueError):
        return 0.0


def deal_price(it: dict) -> tuple[float, float, bool]:
    """成交价口径（含运费）：
    - 有人出价（出价人数>0 且最高价>0）：最高出价 + 运费
    - 无人出价：起拍价 + 运费
    返回 (成交价, 运费, 是否有人出价)。
    """
    start = _to_float(it.get(F["START_PRICE"]))
    bid = _to_float(it.get(F["BID_PRICE"]) or it.get(F["BID_PRICE_HIST"]))
    freight = _to_float(it.get(F["FREIGHT"]))
    bid_num = int(it.get(F["BID_NUM"]) or 0)
    if bid_num > 0 and bid > 0:
        return round(bid + freight, 2), freight, True
    return round(start + freight, 2), freight, False
