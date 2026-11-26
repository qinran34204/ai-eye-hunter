# -*- coding: utf-8 -*-
"""拍卖站适配器配置。

可变项优先读环境变量（.env），分类等结构化规则可写到工程根目录
`auction_config.local.json`（不入库），启动时深合并覆盖默认值。
"""
import copy
import json
import os

# 工程根目录（src/auction/config.py → 上两级）
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL_CONFIG_PATH = os.path.join(ROOT_DIR, "auction_config.local.json")


def _env(name: str, default: str = "") -> str:
    val = os.environ.get(name)
    return val if val is not None else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


# ============================  默认配置  ============================
DEFAULTS = {
    # 总开关：False 时后台不启动拍卖站轮询
    "ENABLED": False,
    "BASE": "https://ypt.epetpet.cn/pet_auction/web/index.php",
    "CUSTOMER_ID": "",
    "APP_ID": "",
    "TOKEN": "",
    # 轮询间隔（秒）；失败时在此基础上退避
    "INTERVAL": 60,
    # 临期窗口（分钟）：只保留截止时间落在接下来 N 分钟内的拍品；0 = 不限制
    "NEAR_END_MINUTES": 0,
    "PAGE_SIZE": 30,
    "MAX_PAGES": 3,
    "LIST_TYPES": ["", "1", "2", "3"],
    "WORKERS": 4,
    "REQUEST_TIMEOUT": 12,
    "RETRIES": 2,
    "RETRY_DELAY": 1.0,
    "TOP_N_PER_CATEGORY": 5,
    # 关键词命中即推荐并通知；为空则只落库、不推荐、不通知
    "KEYWORD_RULES": [],
    # 分类规则：分类 ID 或名称关键词命中任一即归入该类
    "CATEGORIES": {
        "玉米蛇": {"two_type_id": "19", "keywords": ["玉米"]},
        "王蛇": {"two_type_id": "20", "keywords": ["王蛇", "黑王", "暴风雪王"]},
    },
}

# 环境变量映射到配置键（标量项）
_ENV_MAP = {
    "ENABLED": ("AUCTION_MONITOR_ENABLED", "false"),
    "BASE": ("AUCTION_BASE", ""),
    "CUSTOMER_ID": ("AUCTION_CUSTOMER_ID", ""),
    "APP_ID": ("AUCTION_APP_ID", ""),
    "TOKEN": ("AUCTION_TOKEN", ""),
    "INTERVAL": ("AUCTION_INTERVAL", ""),
    "NEAR_END_MINUTES": ("AUCTION_NEAR_END_MINUTES", ""),
    "TOP_N_PER_CATEGORY": ("AUCTION_TOP_N_PER_CATEGORY", ""),
}


def _deep_merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = copy.deepcopy(v)
    return base


def _parse_bool(text: str) -> bool:
    return str(text).strip().lower() in ("1", "true", "yes", "on", "开")


def _load_local_overrides() -> dict:
    if not os.path.exists(LOCAL_CONFIG_PATH):
        return {}
    try:
        with open(LOCAL_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _build_config() -> dict:
    cfg = copy.deepcopy(DEFAULTS)

    # 环境变量覆盖
    for key, (env_name, _default) in _ENV_MAP.items():
        raw = _env(env_name, "")
        if raw == "":
            continue
        if key == "ENABLED":
            cfg[key] = _parse_bool(raw)
        elif key in ("INTERVAL", "NEAR_END_MINUTES", "TOP_N_PER_CATEGORY"):
            cfg[key] = _env_int(env_name, cfg[key])
        else:
            cfg[key] = raw

    # 关键词规则：env 逗号/换行分隔
    kw_raw = _env("AUCTION_KEYWORD_RULES", "")
    if kw_raw:
        cfg["KEYWORD_RULES"] = [
            part.strip() for part in kw_raw.replace("\n", ",").split(",") if part.strip()
        ]

    # 本地 JSON 深合并覆盖
    _deep_merge(cfg, _load_local_overrides())
    return cfg


CONFIG = _build_config()

# ============================  字段口径  ============================
F = {
    "MARK": "mark",
    "ID": "id",
    "NAME": "name",
    "CATEGORY": "_category",
    "IMG": "img",
    "START_PRICE": "start_price",
    "BID_PRICE": "current_bid_price",
    "BID_PRICE_HIST": "current_bid",
    "BID_NUM": "bid_num",
    "EACH_ADD": "each_add",
    "FREIGHT": "freight",
    "DEPOSIT": "deposit",
    "OFF_TIME": "off_time",
    "STATUS": "status",
    "HAS_BID": "has_bid",
    "DEAL_PRICE": "deal_price",
}

STATUS_TEXT = {"1": "拍卖中", "0": "已结束", "2": "已成交", "3": "流拍"}

# 玉米蛇/王蛇基因归类规则（长词/复合名在前，通用词放最后）。
GENE_RULES = [
    ("显直", ["显直", "鱼直", "红直", "日直", "蛋显", "tessera"]),
    ("假面", ["假面", "masque"]),
    ("缓冲", ["缓冲", "buf"]),
    ("太妃", ["太妃", "toffee"]),
    ("棕榈", ["棕榈", "palmetto"]),
    ("白化红", ["白化红", "白化", "amel"]),
    ("炭黑", ["炭黑", "碳黑", "碳无", "anery"]),
    ("焦糖", ["焦糖", "糖显", "caramel"]),
    ("木炭", ["木炭", "charcoal"]),
    ("煤渣", ["煤渣", "煤渣直", "cinder"]),
    ("血红", ["血红", "血派", "血50", "bloodred", "diffused"]),
    ("稀释", ["稀释", "dilute"]),
    ("缺黑", ["缺黑", "hypo"]),
    ("七叶树", ["七叶树", "kastanie"]),
    ("熔岩", ["熔岩", "lava"]),
    ("薰衣草", ["薰衣草", "lavender"]),
    ("草莓", ["草莓", "strawberry"]),
    ("太阳之吻", ["太阳之吻", "sunkissed"]),
    ("黎明", ["黎明", "sunrise"]),
    ("超", ["超 ", "ultra"]),
    ("无磷", ["无磷", "无鳞", "微鳞", "scaleless"]),
    ("甜甜圈", ["甜甜圈", "甜圈", "鱼圈", "红显圈", "显圈", "motley"]),
    ("直线", ["直线", "stripe"]),
    ("水磨石", ["水磨石", "terrazzo"]),
    ("暴风雪", ["暴风雪", "暴雪", "大暴雪", "blizzard"]),
    ("牛油", ["牛油", "牛双", "牛直", "butter"]),
    ("火焰", ["火焰", "地狱火", "火直", "火日", "熔火", "地狱火直", "fire"]),
    ("柑橘", ["柑橘", "mandarin"]),
    ("蛋白石", ["蛋白石", "opal"]),
    ("雪白", ["雪白", "珊瑚雪", "雪崩", "雪显", "白圈", "雪直", "snow"]),
    ("薄荷", ["薄荷", "peppermint"]),
    ("幽灵", ["幽灵", "ghost"]),
    ("花岗岩", ["花岗岩", "granite"]),
    ("冰幽灵", ["冰幽灵", "ice ghost"]),
    ("月光石", ["月光石", "moonstone"]),
    ("珊瑚幽灵", ["珊瑚幽灵", "coral ghost"]),
    ("锡金", ["锡金", "pewter"]),
    ("幻影", ["幻影", "phantom"]),
    ("钻石", ["钻石", "diamond"]),
    ("杏色", ["杏色", "almond"]),
    ("血浆", ["血浆", "plasma"]),
    ("蝴蝶兰", ["蝴蝶兰", "orchid"]),
    ("琥珀", ["琥珀", "amber"]),
    ("黄玉", ["黄玉", "topaz"]),
    ("蜂蜜", ["蜂蜜", "honey"]),
    ("碎片", ["碎片", "shatter"]),
    ("橙柿", ["橙柿", "lava kastanie"]),
    ("糖果", ["糖果", "hazel"]),
    ("橘子", ["橘子", "orange"]),
    ("三文鱼", ["三文鱼", "salmon"]),
    ("北极", ["超北", "北极"]),
    ("黑王", ["墨西哥黑王", "黑王蛇", "黑王公", "黑王母", "黑王"]),
    ("黑背", ["黑背"]),
    ("加州王", ["加州王", "加洲"]),
    ("布鲁克", ["布鲁克", "brook"]),
    ("白边", ["白边", "white sided", "whitesided"]),
    ("缺黄AX", ["ax白", "ax-", "ax ", "缺黄"]),
    ("白化", ["白化", "albino"]),
    ("薰衣草", ["薰衣草", "lavender"]),
    ("佛罗里达王", ["佛罗里达", "佛王"]),
    ("沙漠王", ["沙漠王", "沙漠"]),
    ("丝带王", ["丝带王"]),
    ("SD/直线", ["直线王", "SD直", "SD王", "SD"]),
]

# 王蛇谱系规则：王蛇标题只在这套规则内归类，避免玉米蛇通用词误命中。
WANG_GENES = {
    "黑王", "黑背", "加州王", "布鲁克", "白边", "缺黄AX", "幽灵",
    "白化", "雪白", "薰衣草", "佛罗里达王", "沙漠王", "丝带王", "SD/直线",
}

# 修饰前缀：其后紧跟的基因视为携带/杂合，不作为本表基因收录。
MODIFIER_TOKENS = ("het", "ph", "h")
