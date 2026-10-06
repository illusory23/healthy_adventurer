# -*- coding: utf-8 -*-
"""《健康的冒险者的一天》· 游戏核心（Python 移植版）

与单文件 HTML 原型逻辑保持一致；惰性补算引擎参考 09_技术方案.md 第五节。
状态为纯 dict，持久化交给 db.py（SQLite 单行 JSON）。
"""
import json
import random
import re
import time
from datetime import datetime, date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
DATA = json.loads((ROOT / "data" / "static_data.json").read_text(encoding="utf-8"))

C = DATA["C"]                    # 委托池 {"Lv1": [[名,标签,时间窗,耗时,难度,报酬,经验,精力,材料dict], ...]}
M = DATA["M"]                    # 材料 {名: [品类, 品阶, 卖出铜]}
GEAR = DATA["GEAR"]              # 装备 [名, 品质, 槽位, 主属性值, 副属性, 主材料]
LEGEND = DATA["LEGEND"]          # 传奇 [名, 标签, 天数, 难度, 报酬, 经验, 材料, 奖励, 条件]
REGIONS = DATA["REGIONS"]        # 探索区域
RARE = DATA["RARE"]              # 稀有事件
CFG = DATA["CFG"]
SHOP = DATA["SHOP"]
VIT_SHOP = DATA["VIT_SHOP"]
CON_SHOP = DATA["CON_SHOP"]
PLAT_SHOP = DATA["PLAT_SHOP"]      # v1.41 H1：铂金商店
BUY_TIERS = DATA["BUY_TIERS"]      # v1.41 H3：交易所可买入品阶
QUEST_REQ = DATA["QUEST_REQ"]      # v1.41 I1：委托链前置表 {委托名: 前置委托名}
QUEST_ITEM = DATA["QUEST_ITEM"]    # v1.46：任务门槛 {委托名: 准备物名}（接取消耗 1~3 个，按委托等级；v1.53）
CRAFT = DATA["CRAFT"]              # v1.46：炼金台配方 {准备物: {"ing": {材料: 数量}, "buy": 铜价}}
QUEST_LV_OF = {}                   # v1.53：委托名 → 等级档（Lv1~Lv5）
for _lvk, _lqs in DATA["C"].items():
    for _lq in _lqs:
        QUEST_LV_OF.setdefault(_lq[0], _lvk)


def quest_item_need(q):
    """v1.53：准备物需求量随委托等级递增（Lv3→1 / Lv4→2 / Lv5→3）——对齐前端 questItemNeed"""
    lv = QUEST_LV_OF.get(q[0])
    return 3 if lv == "Lv5" else (2 if lv == "Lv4" else 1)
MONTH_EVENTS = DATA["MONTH_EVENTS"]   # v1.41 I3：月度世界事件（12 条按月轮换）
QUEST_TURNIN = DATA["QUEST_TURNIN"]   # v1.41 I4：资源指定类 {委托名: 上交材料}
MASTER_SHOP = DATA["MASTER_SHOP"]     # v1.41 I6：大师商店（专属装备 / 传说材料 / 活力点）
CHARM = DATA["CHARM"]
SKILLS = DATA["SKILLS"]
SKILL_COST = DATA["SKILL_COST"]
ITEM_DESC = DATA["ITEM_DESC"]
QUEST_STORY = DATA["QUEST_STORY"]
EXPLORE_EVENT_CHANCE = DATA["EXPLORE_EVENT_CHANCE"]
REP_TABLE = DATA["REP_TABLE"]
LEGEND_GOLD = DATA["LEGEND_GOLD"]
REGION_EVENTS = DATA["REGION_EVENTS"]

LV_NAMES = CFG["levels"]

# v1.30：委托等级倒排索引（成功率参数按委托等级套用；混合池下玩家会遇到各级委托）
QUEST_LV = {}
for _i, _lv in enumerate(LV_NAMES):
    for _q in C.get(_lv, []):
        QUEST_LV[_q[0]] = _i
POOL_WINDOW_MS = 60 * 60 * 1000                # v1.38r：接取窗口 30 分钟 → 1 小时
LAST_POOL_WINDOW_MS = 150 * 60 * 1000          # v1.41f3：最后一次刷新点接取窗口 2.5 小时（21:00 → 23:30）
MAX_CATCHUP_DAYS = 7                      # 补算护栏（09_技术方案 第五节）
DAY_CUTOFF_HOUR = 6                       # 日界线：早 6 点刷新每日状态与结算（00:00~05:59 熬夜时段仍属前一天）
# ── v1.28：打卡时间窗（分钟制 (起, 止) 闭区间；仅限制「新打卡」，窗口外允许取消）──
TASK_WINDOWS = {0: (21 * 60, 23 * 60 + 30),       # 23:30 前入睡：21:00~23:30（v1.38r 调整）
                1: (6 * 60, 8 * 60)}              # 7:40 前起床：06:00~08:00
MEAL_WINDOWS = [(6 * 60, 10 * 60),                # 早餐 06:00~10:00
                (11 * 60, 14 * 60),               # 午餐 11:00~14:00
                (17 * 60, 21 * 60)]               # 晚餐 17:00~21:00
MEAL_NAMES = ["早餐", "午餐", "晚餐"]
# ── v1.41c：节日窗口扩展（假期区间见 FESTIVAL_RANGES；单日节日见 FESTIVALS）──
FEST_POOL_BONUS_MS = 60 * 60 * 1000     # 接取窗口 +1 小时
FEST_TASK_BONUS_MIN = 60                # 入睡/起床打卡窗口尾部 +1 小时
FEST_MEAL_PAD_MIN = 30                  # 三餐打卡窗口前后各 +30 分钟

# ══════════════ 工具 ══════════════


def now_ms():
    return int(time.time() * 1000)


def today_str(d=None):
    """当前「游戏日」（YYYY-MM-DD）。日界线为每天早上 6 点：
    00:00~05:59 视为前一天（熬夜时段不提前跨天），06:00 起进入新的一天。"""
    d = d or datetime.now()
    if isinstance(d, datetime) and d.hour < DAY_CUTOFF_HOUR:
        d = d - timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def next_day_str(s):
    return (parse_date(s) + timedelta(days=1)).strftime("%Y-%m-%d")


def week_key(d=None):
    """周一为一周开始，返回该周周一的日期串"""
    d = d or parse_date(today_str())          # 默认取当前「游戏日」（早 6 点日界线）
    monday = d - timedelta(days=d.weekday())
    return monday.strftime("%Y-%m-%d")


def _min_of_day(now=None):
    now = now or datetime.now()
    return now.hour * 60 + now.minute


def _win_str(w):
    a, b = w
    if b > 24 * 60:
        b -= 24 * 60                       # v1.41c：跨日窗口显示次日时刻（21:00-00:30）
    return "%02d:%02d-%02d:%02d" % (a // 60, a % 60, b // 60, b % 60)


def _in_win(w, now=None):
    """分钟窗判定（支持跨日：b>1440 时次日 00:00~b-1440 仍在窗内）——v1.41c"""
    c = _min_of_day(now)
    if w[0] <= c <= w[1]:
        return True
    return w[1] > 24 * 60 and c <= w[1] - 24 * 60


def task_window_of(i, d=None):
    """打卡项实际窗口（分钟对，尾部可 >1440 表跨日；节日入睡/起床尾部 +1 小时）——v1.41c"""
    w = TASK_WINDOWS.get(i)
    if not w:
        return None
    if i in (0, 1) and is_festival(d):
        return (w[0], w[1] + FEST_TASK_BONUS_MIN)
    return w


def meal_window_of(idx, d=None):
    """三餐实际窗口（节日前后各 +30 分钟）——v1.41c"""
    a, b = MEAL_WINDOWS[idx]
    if is_festival(d):
        return (max(0, a - FEST_MEAL_PAD_MIN), b + FEST_MEAL_PAD_MIN)
    return (a, b)


def in_task_window(i, now=None):
    """该打卡项当前是否在可打卡时段（无窗口的项恒为 True）——v1.28；v1.41c：节日扩展"""
    w = task_window_of(i, now)
    return True if not w else _in_win(w, now)


def _midnight_lock(i, now=None):
    """v1.50：00:00–05:59（日界线前）禁止补打「昨日」的无窗口打卡项——
       有窗口项仍走各自窗口判定（节日入睡跨日窗口 21:00–00:30 照常可用）"""
    if _min_of_day(now) >= DAY_CUTOFF_HOUR * 60:
        return False
    return task_window_of(i, now) is None


MIDNIGHT_LOCK_MSG = "已经过了 00:00——昨日的打卡已锁定，不再接受补打。早点休息，明天再来。"


def rand(n):
    return random.randint(1, n)


RUMOR_MOD = 30    # v1.48b：与前端 RUMORS 条数一致（酒馆传闻池长度）


def _rumor_pair(d):
    """v1.48b：每日 2 条酒馆传闻——idx / idx2 取模后互不相同"""
    a = random.randrange(3600)
    b = random.randrange(3600)
    while b % RUMOR_MOD == a % RUMOR_MOD:
        b = random.randrange(3600)
    return {"date": d, "idx": a, "idx2": b}


def fmt_money(c):
    c = int(round(c))
    if c < 0:
        return "-" + fmt_money(-c)
    if c >= 1000000 and c % 1000000 == 0:
        return str(c // 1000000) + " 铂金币"
    if c >= 10000:
        g = c / 10000
        return (str(int(g)) if g == int(g) else ("%.1f" % g)) + " 金币"
    if c >= 100:
        s = c / 100
        return (str(int(s)) if s == int(s) else ("%.1f" % s)) + " 银币"
    return str(c) + " 铜币"


def fmt_dur(minutes):
    if minutes >= 1440:                    # v1.41 I4：追踪类多日委托（3 天=4320）
        d = minutes / 1440
        return (str(int(d)) if d == int(d) else ("%.1f" % d)) + " 天"
    if minutes >= 60:
        h = minutes / 60
        return (str(int(h)) if h == int(h) else ("%.1f" % h)) + " 小时"
    return str(minutes) + " 分钟"


# ══════════════ 状态 ══════════════


def _blank_health(d):
    return {"date": d, "done": [0] * 7, "multi": [0, 0], "score": 0, "meals": [0, 0, 0],
            "vitOnce": [0] * 10}   # v1.50：元旦每项每日一次发放标记（7 单 + 3 餐）


def _blank_daily(d):
    return {"date": d, "done": 0, "gold": 0, "exp": 0, "rep": 0, "con": 0, "vit": 0,
            "quests": [], "mats": {}, "events": []}


def new_state():
    t = today_str()
    return {
        "name": "", "created": t, "last_tick": now_ms(), "last_day": t,
        "shield_month": "", "shield_days": [],            # v1.38：连击保险（每月 1 次，保住 ≥7 天早睡连击）
        "sick_days": [],                                  # v1.61：疗养圣所·病假覆盖日（无门槛，每月 3 天；该日评分锁定 59、打卡封存）
        "festival_shown": "", "anniv_last": 0,            # v1.38：节日提示 / 纪念日发放记录
        "carry_pet": "",                  # v1.38f：当前携带的宠物（"" = 未携带；陪同委托获成长）
        "lv_idx": 0, "exp": 0, "rep": 0, "con": 0, "vit": 0, "money": 0,
        "energy": CFG["energyMax"][0], "energy_restore_date": "",
        "last_meal": None, "meal_cap": {"date": "", "cap": 0},
        "meal_sp": {"date": "", "cnt": 0, "got": 0},      # v1.41f5：当日探索点料理（已用次数 / 累计恢复；上限 2 次·+5）
        "explore": 0, "explore_used": 0,
        "explore_active": None,           # 进行中的探索 {idx,n,c,h,startTs,finishTs}（现实时间 2~12 小时；中途可返回，无掉落）
        "items": {}, "gear": [],
        "blueprints": {"铜剑": True, "猎弓": True, "皮甲": True},
        "equipped": {"weapon": None, "armor": None, "accessory": None, "charmSlot": None},
        "skills": {s["n"]: 0 for s in SKILLS},
        "charm": 0,
        "legend_day": "", "legend_week": "", "legend_week_n": 0, "legend_active": None, "legend_name": "传奇事件",
        "legend_preview": False,          # 未解锁时的「预览」事件（仅可看，不能接取；次日消失）
        "pending_legend": None,           # 待前端弹窗提示的「⚡ 触发特殊事件！」{title, name, preview}
        "legend_done": [], "done_quests": {}, "done_below5": 0,
        "titles": [], "pets": [], "trophies": [],
        "seen_mats": [], "seen_items": [], "forged": [], "cooked": [],   # v1.35：图鉴；v1.38s：道具/旧宝箱"曾获得"（探索详情保密）
        "pet_data": {},                                     # v1.35：宠物成长数据
        "pet_walk": None, "pet_nick": {}, "walk_count": 0, "pet_night_date": "",   # v1.56：散步 / 昵称 / 散步累计 / 深夜提醒记账
        "echo": 0, "pending_pet": None, "pending_energy": None, "wolf_done": False,
        "health": _blank_health(t), "daily": _blank_daily(t),
        "yesterday": None, "yesterday_shown": True,
        "pending_festival": None,         # v1.41d：节日欢迎弹窗 {name, text, date}（前端展示后 festival_ack 清空）
        "pool": None, "pool_point": "", "accepted": 0, "bonus_today": False, "bonus_quests": None,
        "priv_quest": None, "priv_today": False,   # v1.38o：W 级公会特权委托（每日 08:00 必出） / 酒馆传闻见 rumor
        "glass_quest": None, "glass_today": False,  # v1.38o：时间沙漏委托（装备★每日接取上限+1 时每日必出）
        "rumor": None,                    # v1.38o：酒馆传闻 {date, idx}（每存档每日独立随机）
        "active": [], "mats": {}, "history": [], "log": [],
        "results": [],                    # 待前端展示的结算结果队列
        "levelups": [],                   # 待前端展示的升级详情队列（v1.38r）
        "pending_rare": [],               # 待前端展示的稀有事件队列
        "explore_result": None,           # 待展示的探索结果 {region, msg}
        "pending_event": None,            # 待玩家选择的探索事件 {name, title, text, options}
        "event_result": None,             # 探索事件选择后的结果展示 {title, text}
        # ── v1.19 ──
        "buff_next": None, "week_settled": "", "month_settled": "",
        "total_quests": 0, "achv": [], "perm_energy": 0, "train_energy": 0,
        "incense": 0, "heat_n": 0, "tim_titles": {}, "exempt": {"sleep": "", "early": "", "charmNight": None},
        "month_event": None,              # v1.41 I3：月度世界事件 {key:"YYYY-MM", cnt, done}
        "lib_date": "",
        "wolf": None,                     # v1.22：宠物·小狼成长链 {stage:1~4, growth}
        "sign": {"last": "", "streak": 0, "total": 0},   # v1.50：每日签到（游戏日首次打开自动签到；奖励 +1 活力点/天）
        # ── v1.38m：商店限购计数（跨天/跨周幂等重置） ──
        "shop_daily": {"date": t, "cnt": {}},          # 每日限购：{date, cnt:{商品名: 已购数}}
        "shop_weekly": {"week": week_key(), "cnt": {}},  # 每周限购：{week, cnt:{商品名: 已购数}}
    }


def add_log(s, msg, cls=""):
    s["log"].insert(0, {"ts": now_ms(), "msg": msg, "cls": cls})
    del s["log"][300:]


def migrate_state(s):
    """补齐旧存档缺失的字段（新增字段平滑迁移，对齐原型 migrate()）"""
    base = new_state()
    for k, v in base.items():
        if k not in s:
            s[k] = v
    s["gear"] = [x for x in (s.get("gear") or []) if x]   # v1.41 I5：清洗脏装备名（防旧存档残留 null → renderBag 崩溃）
    # v1.28：三餐拆分——health.meals 缺失时补；旧版「完整吃三餐」已勾选 → 视为三餐全点
    h = s.get("health")
    if isinstance(h, dict):
        if not isinstance(h.get("meals"), list) or len(h.get("meals", [])) != 3:
            done = h.get("done") or []
            h["meals"] = [1, 1, 1] if (len(done) > 5 and done[5]) else [0, 0, 0]
        if not isinstance(h.get("vitOnce"), list) or len(h.get("vitOnce", [])) != 10:
            h["vitOnce"] = [0] * 10            # v1.50：元旦每项每日一次发放标记
    ex = s.get("exempt")
    if isinstance(ex, dict) and "charmNight" not in ex:
        ex["charmNight"] = None   # v1.41 G6：入睡打卡佩戴快照
    # v1.22：旧档已获得小狼但无成长数据 → 补为小狼一阶；老版 wolf 字段补全
    if s.get("wolf") is None and "小狼" in (s.get("pets") or []):
        s["wolf"] = {"stage": 1, "growth": 0, "mutate": 0, "fedDate": "", "fedCount": 0}
    if s.get("wolf"):
        s["wolf"].setdefault("mutate", 0)
        s["wolf"].setdefault("fedDate", "")
        s["wolf"].setdefault("fedCount", 0)
    if not isinstance(s.get("carry_pet"), str):
        s["carry_pet"] = ""               # v1.38f：携带宠物
    if not isinstance(s.get("sign"), dict):
        s["sign"] = {"last": "", "streak": 0, "total": 0}   # v1.50：每日签到
    s["sign"].setdefault("last", "")
    s["sign"].setdefault("streak", 0)
    s["sign"].setdefault("total", 0)
    if "priv_quest" not in s:
        s["priv_quest"] = None            # v1.38o：公会特权委托
    if "priv_today" not in s:
        s["priv_today"] = False
    if "glass_quest" not in s:
        s["glass_quest"] = None           # v1.38o：时间沙漏委托
    if "glass_today" not in s:
        s["glass_today"] = False
    if not isinstance(s.get("rumor"), dict):
        s["rumor"] = None                 # v1.38o：酒馆传闻
    if s.get("bonus_quest") and not isinstance(s.get("bonus_quests"), list):
        s["bonus_quests"] = [s["bonus_quest"]]   # v1.38p：旧单委托转 6 选 1 列表
    if "bonus_quests" not in s:
        s["bonus_quests"] = None
    s.pop("bonus_quest", None)
    # v1.38m：商店限购字段嵌套防护
    if not isinstance(s.get("shop_daily"), dict):
        s["shop_daily"] = {"date": "", "cnt": {}}
    s["shop_daily"].setdefault("date", "")
    s["shop_daily"].setdefault("cnt", {})
    if not isinstance(s.get("shop_weekly"), dict):
        s["shop_weekly"] = {"week": "", "cnt": {}}
    s["shop_weekly"].setdefault("week", "")
    s["shop_weekly"].setdefault("cnt", {})
    # v1.40：历史档修复——传奇奖励中误入「藏品」的装备/图纸转入正式背包（世界树护符/时间沙漏/陨星武器图纸）
    tp = s.get("trophies") or []
    if tp:
        s.setdefault("gear", [])
        s.setdefault("blueprints", {})
        keep = []
        for tn in tp:
            if tn.endswith("图纸") and gear_def(tn[:-2]):
                s["blueprints"][tn[:-2]] = True
            elif gear_def(tn):
                if tn not in s["gear"]:
                    s["gear"].append(tn)
            else:
                keep.append(tn)
        s["trophies"] = keep
    return s


def import_save_state(raw):
    """v1.38d：导入原型 / 前端的 camel 存档（存档互通）
       - 顶层 camelKey → snake_case（嵌套层两端本就同构，不转）
       - 只保留 new_state 已知字段（丢弃 account / legendPool 等前端附加）
       - 日志两端格式不同 → 清空；瞬态结果队列一并清空
       返回迁移后的 state；非 dict 返回 None"""
    if not isinstance(raw, dict):
        return None
    base = new_state()
    s = {}
    for k, v in raw.items():
        nk = re.sub(r"(?<!^)(?=[A-Z])", "_", str(k)).lower()
        if nk in base:
            s[nk] = v
    s["log"] = []
    for k2 in ("results", "levelups", "pending_rare"):
        if k2 in s:
            s[k2] = []
    for k2 in ("explore_result", "pending_event", "event_result",
               "pending_legend", "pending_pet", "pending_energy", "pending_festival"):
        if k2 in s:
            s[k2] = None
    _coerce_import(s)
    return migrate_state(s)


def _coerce_import(s):
    """v1.50：导入档 schema 校验——关键字段类型不符即回退默认（宽松校正，防脏档拖垮服务端/前端渲染）"""
    base = new_state()
    for k in ("gear", "history", "active", "titles", "pets", "trophies", "log",
              "seen_mats", "seen_items", "forged", "cooked", "achv", "results", "levelups",
              "pending_rare", "shield_days", "legend_done"):
        if not isinstance(s.get(k), list):
            s[k] = list(base.get(k) or [])
    for k in ("mats", "items", "equipped", "blueprints", "skills", "done_quests", "pet_data",
              "tim_titles", "shop_daily", "shop_weekly", "health", "daily"):
        if not isinstance(s.get(k), dict):
            s[k] = dict(base[k])
    if not isinstance((s.get("health") or {}).get("done"), list) or len(s["health"]["done"]) != 7:
        s["health"] = dict(base["health"])
    if not isinstance((s.get("daily") or {}).get("quests"), list):
        s["daily"] = dict(base["daily"])
    if not isinstance(s.get("equipped"), dict) or any(
            not isinstance(v, (str, type(None))) for v in s["equipped"].values()):
        s["equipped"] = dict(base["equipped"])
    for k in ("lv_idx", "exp", "rep", "con", "vit", "money", "energy", "explore",
              "accepted", "total_quests", "heat_n", "echo", "incense"):
        v = s.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            s[k] = base.get(k, 0)
    s["lv_idx"] = max(0, min(4, s.get("lv_idx", 0)))
    for k in ("name", "created"):
        if not isinstance(s.get(k), str):
            s[k] = base.get(k, "")


# ══════════════ 等级 / 公会 ══════════════


def lv_name(s):
    return LV_NAMES[s["lv_idx"]]


def lv_num(s):
    return s["lv_idx"] + 1


def guild_idx(s):
    g = 0
    for i, req in enumerate(CFG["guildReq"]):
        if s["rep"] >= req:
            g = i
    return g


def guild_name(s):
    return CFG["guildName"][guild_idx(s)]


def exp_floor(s):
    i = s["lv_idx"]
    return 0 if i == 0 else CFG["expNeed"][i - 1]


def _push_capped(s, key, item, cap=50):
    """v1.39（B6）：队列字段（results / levelups / pending_rare）封顶，
       防"长期不消费 + 后台持续产出"时无限膨胀；只保留最近 cap 条。"""
    q = s.setdefault(key, [])
    q.append(item)
    if len(q) > cap:
        del q[:-cap]


def check_level_up(s):
    """经验达到累计门槛 → 升级"""
    while s["lv_idx"] < 4 and s["exp"] >= CFG["expNeed"][s["lv_idx"]]:
        s["lv_idx"] += 1
        s["energy"] = energy_max_now(s)                    # v1.38s2：升级补满当前精力（对齐原型与 01_基础框架「升级奖励」；原缺失导致"上限涨、当前不跟"）
        add_log(s, "⬆️ 升级！现在是 " + lv_name(s) + "（精力上限 " + str(energy_max_now(s)) + "）", "gold")
        _push_capped(s, "levelups", s["lv_idx"])   # v1.38r：升级详情（前端弹窗队列；v1.39 B6：封顶 50）


# ══════════════ 健康 ══════════════

SICK_LOCK_SCORE = 59                   # v1.61：疗养圣所·病假日评分锁定值
SICK_LOCK_MSG = "今日病假已封存——健康评分锁定 " + str(SICK_LOCK_SCORE) + "，本日无法打卡（好好休息）。"

# ══════════════ 探索 ══════════════
EV_ROB_CAP = 1000000                   # v1.61c：盗贼伏击抢夺上限 = 1 铂金币（1,000,000）——前端 EV_ROB_CAP 对齐


def sick_today(s):
    """v1.61：今日是否为病假日（评分锁定 59、打卡封存）"""
    return s["health"]["date"] in (s.get("sick_days") or [])


def calc_health(s):
    sc = 0
    h = s["health"]
    for i, t in enumerate(CFG["tasks"]):
        if h["done"][i]:
            sc += t[1]
    for i, t in enumerate(CFG["multiTasks"]):
        sc += min(h["multi"][i], t[2]) * t[1]
    h["score"] = min(sc, 100)
    if sick_today(s):                      # v1.61：疗养圣所·病假 → 本日评分锁定 59
        h["score"] = SICK_LOCK_SCORE
    return h["score"]


def grade(sc):
    for g in CFG["gradeTable"] if "gradeTable" in CFG else []:
        pass
    if sc >= 90:
        return "完美"
    if sc >= 75:
        return "优秀"
    if sc >= 60:
        return "良好"
    if sc >= 40:
        return "普通"
    return "虚弱"


def prev_health_score(s):
    """最近一次日结算的健康评分（v1.34：成功率/传奇事件按此口径；无记录 = 0）"""
    return (s["history"][-1].get("score", 0)) if s["history"] else 0


# ══════════════ 装备效果 ══════════════


def gear_def(name):
    for g in GEAR:
        if g[0] == name:
            return g
    return None


def gear_effects(s):
    e = {"rate": {}, "pay": {}, "enCut": {}, "enCutAll": 0, "nightCut": 0, "exp": 0,
         "con": 0, "rare": 0, "mat": 0, "legend": 0, "healthUp": 0,
         "simCap": 0, "dailyLimit": 0, "nightmare": 0, "vit": 0, "genesis": 0}   # nightmare：v1.32；vit：v1.41 I6 大师徽章；genesis：v1.41 H6 创世之印豁免 E 上限；v1.58：sp（探索点/天）通道移除
    for slot in ("weapon", "armor", "accessory", "charmSlot"):
        n = s["equipped"].get(slot)
        if not n:
            continue
        g = gear_def(n)
        if not g:
            continue
        sub = g[4]
        if not sub or sub == "—":
            continue
        for m in re.finditer(r"([^；;]+?)类(?:委托)?成功率\+(\d+)%", sub):   # v1.49：键不跨「；」（修复组合词条吞键 bug）
            e["rate"][m.group(1)] = e["rate"].get(m.group(1), 0) + int(m.group(2)) / 100
        m = re.search(r"全委托成功率\+(\d+)%", sub)
        if m:
            if n == "创世之印":                      # v1.41 H6：仅创世之印豁免 E 上限
                e["genesis"] += int(m.group(1)) / 100
            else:
                e["rate"]["全"] = e["rate"].get("全", 0) + int(m.group(1)) / 100
        for m in re.finditer(r"([^；;]+?)类(?:委托)?报酬\+(\d+)%", sub):   # v1.49：同上
            e["pay"][m.group(1)] = e["pay"].get(m.group(1), 0) + int(m.group(2)) / 100
        for m in re.finditer(r"([^；;]+?)类精力消耗-(\d+)%", sub):   # v1.49：同上
            e["enCut"][m.group(1)] = e["enCut"].get(m.group(1), 0) + int(m.group(2)) / 100
        m = re.search(r"全委托精力消耗-(\d+)%", sub)
        if m:
            e["enCutAll"] += int(m.group(1)) / 100
        m = re.search(r"熬夜惩罚-(\d+)%", sub)
        if m:
            e["nightCut"] += int(m.group(1)) / 100
        m = re.search(r"委托经验\+(\d+)%", sub)
        if m:
            e["exp"] += int(m.group(1)) / 100
        m = re.search(r"公会贡献\+(\d+)%", sub)
        if m:
            e["con"] += int(m.group(1)) / 100
        m = re.search(r"稀有事件概率\+(\d+)%", sub)
        if m:
            e["rare"] += int(m.group(1)) / 100
        m = re.search(r"材料获取\+(\d+)%", sub)
        if m:
            e["mat"] += int(m.group(1)) / 100
        m = re.search(r"传奇事件成功率\+(\d+)%", sub)
        if m:
            e["legend"] += int(m.group(1)) / 100
        m = re.search(r"活力点获取\+(\d+)%", sub)
        if m:
            e["vit"] += int(m.group(1)) / 100          # v1.41 I6：大师徽章
        m = re.search(r"健康加成上限\+(\d+)%", sub)
        if m:
            e["healthUp"] += int(m.group(1)) / 100
        m = re.search(r"★同时进行上限\+(\d+)", sub)
        if m:
            e["simCap"] += int(m.group(1))
        m = re.search(r"★每日接取上限\+(\d+)", sub)
        if m:
            e["dailyLimit"] += int(m.group(1))
        m = re.search(r"晨间(?:类|时段)?委托报酬\+(\d+)%", sub)
        if m:
            e["pay"]["晨间"] = e["pay"].get("晨间", 0) + int(m.group(1)) / 100
        m = re.search(r"噩梦难度成功率\+(\d+)%", sub)     # v1.32：修复死词条
        if m:
            e["nightmare"] += int(m.group(1)) / 100
    return e


def gear_rate(s):
    n = s["equipped"].get("weapon")
    g = gear_def(n) if n else None
    return g[3] if g else 0


def gear_en(s):
    n = s["equipped"].get("armor")
    g = gear_def(n) if n else None
    return g[3] if g else 0


def gear_bonus(s):
    n = s["equipped"].get("accessory")
    g = gear_def(n) if n else None
    return g[3] if g else 0


def gear_acc_bonus(s):
    n = s["equipped"].get("charmSlot")
    g = gear_def(n) if n else None
    return g[3] if g else 0


def gear_rate_for(s, tag):
    e = gear_effects(s)
    return e["rate"].get(tag, 0) + e["rate"].get("全", 0)


def gear_en_cut_for(s, tag):
    e = gear_effects(s)
    return e["enCut"].get(tag, 0) + e["enCutAll"]


# ══════════════ 技能 / 护符 / 称号 ══════════════


def skill_total(s):
    return sum(s["skills"].get(k["n"], 0) for k in SKILLS)


def skill_cap(s):
    caps = [0, 0, 5, 10, 15, 20, 25, 25, 25, 25]
    return caps[guild_idx(s)] or 0


def skill_rate(s, q):
    tag = q[1]
    r = 0
    for k in SKILLS:
        lv = s["skills"].get(k["n"], 0)
        if not lv or not k.get("tag"):
            continue
        if k["tag"] == tag or (isinstance(k["tag"], list) and tag in k["tag"]):
            r += lv * 0.01
    return r


def skill_pay(s, q):
    return s["skills"].get("社交", 0) * 0.02 if q[1] == "护送" else 0


def charm_rate(s):
    return CHARM[s["charm"] - 1]["rate"] if s["charm"] > 0 else 0


def charm_pay(s):
    return CHARM[s["charm"] - 1]["pay"] if s["charm"] > 0 else 0


def charm_vit(s):
    """活力点获取加成：冥念护符 + v1.41 I6 大师徽章「活力点获取+10%」（统一乘算通道，调用点均按 1+ 使用）"""
    base = CHARM[s["charm"] - 1]["vit"] if s["charm"] > 0 else 0
    return base + gear_effects(s)["vit"]


def check_guild_titles(s, msgs):
    """v1.40：W/H/P 公会里程碑称号（04 文档）——幂等授予"""
    for need, name in ((7, "世界行者"), (8, "英雄"), (9, "至尊")):
        if guild_idx(s) >= need and name not in s["titles"]:
            s["titles"].append(name)
            msgs.append("🏅 公会称号「" + name + "」已授予！")
            add_log(s, "🏅 公会称号「" + name + "」已授予！", "gold")


def charm_unlocked(s, i):
    if i == 4:                                     # v1.40：第 5 级条件=完成 ≥1 次传奇事件（对齐 04 设计；原 need:99 占位致永不可解锁）
        return len(s.get("legend_done") or []) >= 1
    need = CHARM[i]["need"]
    return guild_idx(s) >= need


def title_active(s, name):
    until = s["tim_titles"].get(name)
    return bool(until and until > now_ms())


def title_pay_bonus(s):
    b = 0
    if title_active(s, "作息守护者"):
        b += 0.05
    if title_active(s, "公会中坚"):
        b += 0.05
    return b


def title_own_bonus(s):
    # v1.41：永久称号收集加成——每 1 个 +1%，上限 +10%
    return min(0.10, len(s.get("titles") or []) * 0.01)


def heat_bonus(s):
    """安眠室：每累计 7 天早睡 → 健康加成 +1pp（加法，最高 +5pp；v1.40 由乘法改加法——原 ×1.05 满级仅 +1pp 无感）"""
    return min(5, s["heat_n"] // 7) * 0.01


def dinner_bonus(s):
    h = s["history"][-1] if s["history"] else None
    return bool(h and h.get("tasks") and h["tasks"][5])


# ══════════════ 精力 / 上限 ══════════════


def meal_cap_bonus(s):
    mc = s.get("meal_cap") or {}
    return mc.get("cap", 0) if mc.get("date") == today_str() else 0


INCENSE_BONUS = [0, 4, 9, 16, 26, 40]   # v1.50：安眠薰香 Ⅰ~Ⅴ 递增（+4/+5/+7/+10/+14，满级累计 +40）


def energy_base(s):
    m = CFG["energyMax"][s["lv_idx"]]
    if guild_idx(s) >= 9:
        m += 100
    m += gear_en(s)
    m += s["skills"].get("体能", 0) * 10
    m += s.get("perm_energy", 0) + s.get("train_energy", 0) + INCENSE_BONUS[min(5, s.get("incense", 0))]
    bn = s.get("buff_next")
    if bn and bn["date"] == today_str():
        m += bn.get("energy", 0)
        if bn.get("energyPct"):                    # v1.40：虚弱 → 上限 −10%
            m = max(1, round(m * (1 + bn["energyPct"])))
    return m


def energy_max_now(s):
    v = energy_base(s) + meal_cap_bonus(s)
    _pct = today_fest_eff().get("energy_max_pct", 0)   # v1.41f：冬幕节·精力上限 +20%
    return int(round(v * (1 + _pct))) if _pct else v


def daily_limit_now(s):
    n = CFG["dailyLimit"][s["lv_idx"]]
    if guild_idx(s) >= 7:
        n += 1
    n += gear_effects(s)["dailyLimit"]
    n += today_fest_eff().get("daily_limit", 0)        # v1.41f：小年·接取上限 +1
    return n


def sim_cap_now(s):
    base = [1, 1, 2, 2, 3][s["lv_idx"]]
    n = base + (1 if guild_idx(s) >= 8 else 0)
    return n + gear_effects(s)["simCap"]


def active_normal_count(s):
    # v1.41：传奇事件独立槽位——普通容量只计非传奇项（传奇与日常委托完全并行）
    return sum(1 for a in s["active"] if not a.get("legend"))


def active_meal(s):
    lm = s.get("last_meal")
    if not lm:
        return None
    return lm if lm.get("date") == today_str() else None


# ══════════════ 成功率 / 掉落 ══════════════


def is_morning_quest(q):
    tw = q[2]
    if tw == "全天":
        return True
    m = re.match(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", tw)
    if not m:
        return False
    st = int(m.group(1)) * 60 + int(m.group(2))
    en = int(m.group(3)) * 60 + int(m.group(4))
    return st < 9 * 60 and en > 6 * 60


def success_rate(s, q):
    qi = QUEST_LV.get(q[0], s["lv_idx"])   # v1.30：基础率/上限按委托等级套用
    B = CFG["sucBase"][qi]
    ov = CFG["diffModByLv"].get(str(qi + 1), {})
    diff = q[4]
    if diff in ov:
        D = 0 if ov[diff] is None else ov[diff]
    else:
        D = CFG["diffMod"].get(diff, 0)
    H = prev_health_score(s)                # v1.34：按昨日日结算评分（新号第一天 = 0）
    # v1.40：安眠室/称号改为加法百分点（原乘法满配仅多 +2pp，长期健康目标无感）
    health = H * 0.002 * (1 + gear_effects(s)["healthUp"]) + heat_bonus(s) \
             + (0.02 if title_active(s, "安眠守护者") else 0)
    E = gear_rate(s) + skill_rate(s, q) + gear_rate_for(s, q[1])
    if dinner_bonus(s):
        E += 0.02
    E = min(CFG["eCap"][qi], E)
    last_sleep = s["history"][-1]["sleep"] if s["history"] else True
    N = 0 if last_sleep else min(0, -0.15 + gear_effects(s)["nightCut"])   # v1.38o：减免封顶于惩罚本身，未熬夜不受益
    _fe = today_fest_eff()                 # v1.41f：节日专属效果
    if _fe.get("no_sleep_penalty"):
        N = 0                              # 端午·驱邪安康：当日免除熬夜惩罚
    cap, floor = CFG["hardCap"][qi], CFG["floor"][qi]
    m = active_meal(s)
    meal_r = (m.get("rate", 0) if m else 0) * _fe.get("cook_mul", 1)   # v1.41f：腊八·料理效果翻倍
    dLv = max(0, s["lv_idx"] - qi)          # v1.32：等级差修正（高等级做低等级委托 +12%/级，上限 +36%）
    delta = min(0.36, dLv * 0.12)
    nm = gear_effects(s)["nightmare"] if q[4] == "噩梦" else 0   # v1.32：噩梦难度成功率词条
    r = min(cap, max(floor, B + D + health + E + N + meal_r + charm_rate(s) + gear_effects(s)["genesis"] + delta + s.get("rare_next_rate", 0) + nm))   # v1.41 H6：创世之印独立通道
    fest = _fe.get("rate", 0) + _fe.get("rate_types", {}).get(q[1], 0)   # v1.41f：节日专属（全委托 / 按委托类型）
    return max(0.0, min(1.0, r + wolf_rate_bonus(s) + pet_bonus(s)["rate"] + fest))   # 宠物/节日加成：独立叠加（不受硬上限约束）


def legend_rate(s, sides):
    """传奇事件成功率：健康权重 ×2.5（健康系数 0.5%）；v1.34：按昨日日结算评分"""
    H = prev_health_score(s)
    D = -0.20 if sides == "噩梦" else (-0.10 if sides == "困难" else 0)
    E = min(0.10, gear_rate(s) + s["skills"].get("专注", 0) * 0.01 + s["skills"].get("生存", 0) * 0.01)
    _fe = today_fest_eff()
    last_sleep = s["history"][-1]["sleep"] if s["history"] else True
    N = 0
    if not last_sleep and not _fe.get("no_sleep_penalty"):
        N = min(0, -0.15 + gear_effects(s)["nightCut"])   # v1.50：熬夜惩罚——对齐普通委托（含装备减免与端午豁免）
    r = 0.05 + D + H * 0.005 + E + charm_rate(s) + gear_effects(s)["legend"] + N
    r += _fe.get("legend", 0)   # v1.41f：中秋·月华（传奇事件成功率 +10%）
    return max(0.05, min(0.65, r + wolf_rate_bonus(s) + pet_bonus(s)["rate"]))  # 宠物加成：独立叠加


# ── 宠物·小狼成长链（v1.22，出自探索事件「受伤小狼」）──
# 小狼 +1% 材料掉落率 → 成年狼 +3% → 巨狼 +5% +1% 成功率 → 远古魔狼 +8% +3% 成功率
# 加成均为「独立加成」：材料判定直接加点、成功率在常规公式（含 E 上限）之外叠加
WOLF_STAGES = [
    None,
    {"name": "小狼", "mat": 0.01, "rate": 0, "need": 60},        # need = 升至下一阶所需成长值
    {"name": "成年狼", "mat": 0.03, "rate": 0, "need": 200},
    {"name": "巨狼", "mat": 0.05, "rate": 0.01, "need": 300},    # 成长值满后进入「变异值」积累期
    {"name": "远古魔狼", "mat": 0.08, "rate": 0.03, "need": None},
]
WOLF_FEED_VALUE = {"普通": 1, "精良": 2, "稀有": 4, "史诗": 8, "传说": 15}
# 可喂食材料：全部食材 + 全部草药 + 高级特殊材料（龙血 / 龙心）——v1.56d：食材/草药全量开放，品阶越高营养越好
WOLF_FOODS = {"蘑菇", "河鱼", "泉水", "蜂蜜", "兽肉", "浆果", "南瓜", "香草", "雪盐", "山珍", "蜂王浆", "大块龙肉", "龙涎果", "星尘蜜",
              "止血草", "薄荷叶", "晨露花", "金盏花", "紫藤花", "月光草", "龙息草", "暗影草", "凤凰草", "世界树汁液", "星辉花", "龙血", "龙心"}
# 高级特殊材料：喂食时额外累积「变异值」——史诗（龙血 / 暗影草）+5；传说（龙心 / 世界树汁液）+12
WOLF_MUTATE_VALUE = {"龙血": 5, "暗影草": 5, "龙心": 12, "世界树汁液": 12}
WOLF_MUTATE_NEED = 300       # 变异值满值（巨狼的变异条件）
WOLF_DAILY_FEED = 3          # 每日喂食次数上限（每次 1 个食材）


def feed_left(s):
    """今日剩余喂食次数"""
    w = s.get("wolf")
    if not w:
        return 0
    used = w.get("fedCount", 0) if w.get("fedDate") == today_str() else 0
    return max(0, WOLF_DAILY_FEED - used)


def wolf_stage(s):
    w = s.get("wolf")
    return w["stage"] if w else 0


def wolf_mat_bonus(s):
    if (s.get("carry_pet") or "") != "小狼":
        return 0.0                      # v1.56c：携带才生效
    st = WOLF_STAGES[wolf_stage(s)]
    return st["mat"] if st else 0


def wolf_rate_bonus(s):
    if (s.get("carry_pet") or "") != "小狼":
        return 0.0                      # v1.56c：携带才生效
    st = WOLF_STAGES[wolf_stage(s)]
    return st["rate"] if st else 0


# ══════════════ v1.35：宠物养成扩充 ══════════════
# 可养成线（PET_LINES）：幼年→成年→终极；终极前积满「成长值 + 变异值」可变异（同小狼模式）
# 传奇宠物（PET_FIXED）：获得即提供固定小加成
# v1.55：4 只传奇伙伴（星界幼龙等）升级为完整养成线；月光狐改为阅读驱动（readDriven）
# v1.55b：品阶体系——普通（史莱姆）< 精良（绒球兽）< 稀有（捣蛋鬼）< 史诗（月光狐 / 小狼）< 传说（传奇 4 伙伴）
#        rank 字段仅用于展示（前端），加成高低与品阶对应
PET_LINES = {
    "月光狐": {"icon": "🦊", "from": "月卡·阅读黄金", "rank": "史诗", "need": 260, "readDriven": True, "readNeed": [45, 60],
              # v1.55：进化条件 = 累计阅读次数（与获得条件同为阅读）；变异仍靠喂食高级特殊材料
              "favs": {"星辉花": 17, "月长石": 10, "月光草": 8, "月影纱": 8, "晨露花": 6},
              "muts": {"月光草": 8, "世界树汁液": 15, "龙血": 4, "暗影草": 3, "龙心": 10},
              "stages": [
        {"name": "月光狐", "mat": 0.00, "rate": 0.00, "pay": 0.01, "need": 45},
        {"name": "月影狐", "mat": 0.02, "rate": 0.00, "pay": 0.02, "need": 60},
        {"name": "幻月九尾", "mat": 0.04, "rate": 0.01, "pay": 0.03, "need": None},  # 阅读驱动：三阶无成长要求
    ], "mut": {"name": "星月狐仙", "note": "材料+6%、成功率+2%、报酬+4%",
               "mat": 0.06, "rate": 0.02, "pay": 0.04}},
    "绒球兽": {"icon": "🐹", "from": "探索奇遇", "rank": "精良", "need": 220,
              "favs": {"山珍": 7, "香草": 6, "天鹅绒": 6, "蘑菇": 5, "止血草": 4, "兽肉": 0, "河鱼": 0},
              "muts": {"晨露花": 8, "世界树汁液": 15, "龙血": 4, "暗影草": 3, "龙心": 5},
              "stages": [
        {"name": "绒球兽", "mat": 0.01, "rate": 0.00, "pay": 0.01, "need": 40},
        {"name": "云绒兽", "mat": 0.03, "rate": 0.00, "pay": 0.02, "need": 120},
        {"name": "雪绒巨兽", "mat": 0.05, "rate": 0.01, "pay": 0.03, "need": 120},
    ], "mut": {"name": "虹绒兽", "note": "材料+6%、成功率+1%、报酬+3%",
               "mat": 0.06, "rate": 0.01, "pay": 0.03}},
    "史莱姆": {"icon": "🟢", "from": "探索奇遇", "rank": "普通", "need": 220,
              "favs": {"泉水": 6, "净化石": 6, "蜂蜜": 5, "石英": 5, "蘑菇": 4},
              "muts": {"世界树汁液": 15, "龙心": 12, "暗影草": 5, "龙血": 3},
              "stages": [
        {"name": "史莱姆", "mat": 0.01, "rate": 0.00, "need": 40},
        {"name": "大型史莱姆", "mat": 0.02, "rate": 0.00, "need": 120},
        {"name": "史莱姆之王", "mat": 0.03, "rate": 0.00, "need": 120},
    ], "mut": {"name": "黄金史莱姆", "note": "材料+4%、成功率+1%",
               "mat": 0.04, "rate": 0.01}},
    "捣蛋鬼": {"icon": "👻", "from": "探索奇遇", "rank": "稀有", "need": 220,
              "favs": {"蜂王浆": 8, "蜂蜜": 6, "山珍": 6, "古董钱币": 6, "哥布林图腾": 5},
              "muts": {"暗影草": 12, "龙心": 10, "龙血": 6, "世界树汁液": 5},
              "stages": [
        {"name": "捣蛋鬼", "exp": 0.05, "rate": 0.00, "need": 40},
        {"name": "恶作剧精", "exp": 0.08, "rate": 0.00, "need": 120},
        {"name": "捣蛋之王", "exp": 0.10, "rate": 0.01, "need": 120},
    ], "mut": {"name": "彩蛋大王", "note": "经验+12%、成功率+1%",
               "exp": 0.12, "rate": 0.01}},
    # ── v1.55：4 只传奇伙伴升级为完整养成线（可携带 / 喂食 / 进化 / 变异）──
    #    一阶加成 = 原固定加成（老档无损）；终阶略高于常规线，属传奇事件（终局内容）定位。
    "星界幼龙": {"icon": "🐲", "from": "传奇事件「星界远征」", "rank": "传说", "need": 300,
              "favs": {"星尘蜜": 18, "星辉花": 17, "星核": 17, "星陨岩": 16, "星尘": 8},
              "muts": {"世界树汁液": 15, "龙心": 12, "龙血": 5, "暗影草": 4},
              "stages": [
        {"name": "星界幼龙", "rate": 0.01, "need": 60},
        {"name": "星辉龙", "rate": 0.02, "need": 180},
        {"name": "星界巨龙", "rate": 0.03, "exp": 0.05, "need": 180},
    ], "mut": {"name": "星穹之龙", "note": "成功率+5%、经验+12%",
               "rate": 0.05, "exp": 0.12}},
    "龙神幼崽": {"icon": "🐉", "from": "传奇事件「龙神契约」", "rank": "传说", "need": 300,
              "favs": {"龙瞳结晶": 17, "大块龙肉": 10, "龙涎果": 9, "龙鳞": 9, "兽肉": 6},
              "muts": {"龙血": 10, "龙心": 12, "世界树汁液": 8, "暗影草": 3},
              "stages": [
        {"name": "龙神幼崽", "pay": 0.03, "need": 60},
        {"name": "龙神子嗣", "pay": 0.05, "need": 180},
        {"name": "龙神使者", "pay": 0.07, "rate": 0.01, "need": 180},
    ], "mut": {"name": "龙神化身", "note": "报酬+10%、材料+5%、成功率+1%",
               "pay": 0.10, "mat": 0.05, "rate": 0.01}},
    "幼龙群": {"icon": "🦎", "from": "传奇事件「万龙之宴」", "rank": "传说", "need": 300,
              "favs": {"大块龙肉": 10, "龙骨": 9, "巨人骨": 9, "兽肉": 6, "山珍": 6},
              "muts": {"龙心": 12, "龙血": 6, "世界树汁液": 8, "暗影草": 4},
              "stages": [
        {"name": "幼龙群", "mat": 0.03, "need": 60},
        {"name": "幼龙小队", "mat": 0.05, "need": 180},
        {"name": "龙群之首", "mat": 0.07, "rate": 0.01, "need": 180},
    ], "mut": {"name": "万龙之群", "note": "材料+12%、成功率+3%",
               "mat": 0.12, "rate": 0.03}},
    "深渊之眼": {"icon": "👁️", "from": "传奇事件「深渊回响」", "rank": "传说", "need": 300,
              "favs": {"暗影龙鳞": 17, "暗影草": 10, "虚空结晶": 10, "混沌碎片": 10, "河鱼": 5},
              "muts": {"暗影草": 15, "龙心": 10, "龙血": 5, "世界树汁液": 8},
              "stages": [
        {"name": "深渊之眼", "mat": 0.02, "need": 60},
        {"name": "深渊凝视者", "mat": 0.04, "need": 180},
        {"name": "深渊主宰之眼", "mat": 0.06, "rate": 0.01, "need": 180},
    ], "mut": {"name": "深渊之瞳·终焉", "note": "材料+12%、成功率+2%",
               "mat": 0.12, "rate": 0.02}},
}
PET_FIXED = {}   # v1.55：原 4 只传奇固定宠物已升级为完整养成线（见 PET_LINES）——此表保留，供未来单形态宠物使用

PET_MOOD_HAPPY = 70          # 心情 ≥ 此值 = 😊（连续 7 天触发心意事件）
PET_MOOD_LOW = 30            # 心情 < 此值 = 😴
PET_BOND_MILES = [7, 30, 100, 365]                     # 羁绊里程碑（天）→ 解锁专属故事
PET_WALK_MS = 30 * 60 * 1000                           # 散步约半小时后回来（下次打开结算）
PET_WALK_GIFT = ["蘑菇", "止血草", "香草", "晨露花", "河鱼", "泉水"]   # 散步可能带回的小礼物（普通/精良）

# v1.56：抚摸回复（每宠 3 条，按性格）
PET_PAT_TXT = {
    "小狼": ["它先绷紧了背，然后慢慢放松下来，把脑袋蹭进你手心。旧伤的那条腿轻轻搭在你腕上。",
             "你摸到它耳朵后面的软毛，它的尾巴敷衍地摇了两下——装酷，但没装住。",
             "它闭着眼任你揉，喉咙里滚出低低的呼噜声，像一小团闷雷。"],
    "月光狐": ["它矜持地让你摸了三下，然后主动把下巴搁在你手上——'再摸一会儿也不是不行'。",
               "尾巴尖勾住你的手指晃了晃。你沾了一手月色般的软毛。",
               "它眯起眼睛，月光下像一枚圆滚滚的、会呼吸的月亮。"],
    "绒球兽": ["手陷进去三厘米。拔出来时，它圆滚滚地弹了一下，弹回了原位。",
               "它主动滚到你脚边，示意你把它滚回去。你照做了，它满意地啵了一声。",
               "它被你摸得整个摊开，像一小片融化的云。"],
    "史莱姆": ["它在你手心颤了颤，啵地冒了个小泡——那是它开心的方式。",
               "滑溜溜，凉丝丝，摸完你手上留了一层淡淡的水光。",
               "它把自己团成球塞进你掌心里，凉凉地待了很久。"],
    "捣蛋鬼": ["你刚伸手它就笑了——然后把你袖子藏进了帽子里。",
               "它假装让你摸，趁你闭眼把发带换到了你头上。",
               "它难得安静地让你摸了三下，末了小声说：'……就今天。'"],
    "星界幼龙": ["它把头低下来给你摸，鳞片温温的，像刚晒过太阳的石头。",
                 "你顺了顺它颈后的鳞，一片星屑似的光落进你掌心里，一闪，没了。",
                 "它小声呜了一声，往你手心里又凑了凑。"],
    "龙神幼崽": ["它矜贵地偏了偏头——意思是准许。你摸了。它满意地哼了一声。",
                 "摸了三下，它别过脸去，尾巴尖却悄悄卷住了你的手指。",
                 "它把头搁上你的膝盖，就一小会儿，然后迅速恢复威严。"],
    "幼龙群": ["你只摸了一只，另外四只立刻挤过来排队，还插队。",
               "摸一只，飞起来五只。很公平——每只都被摸到了。",
               "它们围着你转圈，把你摸头的手当成了旋转的圆心。"],
    "深渊之眼": ["你伸手，它安静地浮低了一些。触到的一瞬，你看见了一片温柔的黑——和里面映着的自己。",
                 "它眨了眨。你手里那点凉意散开，像握了一把深夜。",
                 "它飘过来蹭了蹭你的指尖，很轻，像怕碰碎什么。"],
}
# v1.56：羁绊故事（7 / 30 / 100 天；365 天用通用仪式 + 纪念物）
PET_STORY = {
    "小狼": {7: "第七天。它不再睡在帐篷门口了——挪到了你的靴子旁边。你起夜时差点踢到它，它也不躲，只是迷迷糊糊挪了个位置，继续睡。",
             30: "它开始把'最好的东西'放在你床头：半只兔子、一颗圆石头、一根它认为很威风的羽毛。你不知道该怎么处理这些，但你全都收下了。",
             100: "一百天了。它的旧伤恢复得比任何人预想得都好。某夜你梦见它跑在前面，跑得像一道灰影子——醒来时它正蹲在床边看你，尾巴一摇一摇，像在问：梦见我了吗？"},
    "月光狐": {7: "第七天。它在你的书页上踩了三朵小梅花印，然后理直气壮地趴在书上睡着了——你只好换了一本书读。",
               30: "你读书的时候，它开始学你——把尾巴垫在身下，端端正正地'看书'。翻页的声音，它听得很认真。",
               100: "一百天。你发现它会在你读到深夜时用尾巴去够灯——够不着，但意思到了。你笑着合上书，它就满意地把你往被窝的方向拱。"},
    "绒球兽": {7: "第七天。它在你的枕头上掏出一个窝，宣布这块海拔归它了。你翻身时它会滚下去，然后爬回来，再滚下去。",
               30: "它把你散落的头发、没叠的披风、翻开的书全滚成了一个球——你发火前，它把球滚到你脚边，仰头看你。……行吧，是个好球。",
               100: "一百天。你已经习惯了它在你背上睡觉的分量。今天它滚得太靠边，差点滑下肩膀——被你反手捞住时，它轻轻震了震，蹭了蹭你的后颈。"},
    "史莱姆": {7: "第七天。它学会了在你洗手时蹲在盆边——因为它发现水流声会跟着它一起啵啵。",
               30: "它把收集的小石子排成一条线，从门口排到你的桌边。你看懂了：这是它画的路线图，终点是你。",
               100: "一百天。今天它不声不响地钻进你袖口待了整个下午。你说不清那是它怕冷，还是它觉得你怕冷。"},
    "捣蛋鬼": {7: "第七天。你的第二只袜子找到了——在锅里。它站在锅边笑，笑得岔了气。",
               30: "它在你的日记本上画了个歪歪扭扭的你，旁边画了很小很小的它。你把它装裱起来了。它假装不在意，但已经带着来访的邻居看过三回了。",
               100: "一百天。今天它一个恶作剧都没搞。你反而担心起来，它才小声说：'今天想当个好孩子。就一天。'——然后晚上把糖罐挪了位置。"},
    "星界幼龙": {7: "第七天。它终于不用对着星星学叫了——今晚它对着你叫了一声。很轻。你听懂了。",
                 30: "它开始把夜里最亮的那颗星'指'给你——用尾巴，用脑袋，用整个身体。有时候它指的是月亮。它觉得月亮也算。",
                 100: "一百天。它在你的帐篷顶上盘成了一小片星空。你躺在里面睡得很沉，梦见自己飘在星河里——醒来发现身上盖着它脱落的、还在微微发光的旧鳞。"},
    "龙神幼崽": {7: "第七天。它允许你整理它额角那撮翘起来的绒毛了。就一撮。多一根都不行。",
                 30: "它开始按龙神的规矩'巡视'你的营地：绕三圈，检查一遍你的靴子（闻一闻），然后正式地坐到你身边。这是它每天的仪式。",
                 100: "一百天。今天它让你看了它的'真名'——风里飘过的一个音节，你念不出来。但它听到你试着念时，龙神的幼崽第一次像普通的幼崽那样，笑了。"},
    "幼龙群": {7: "第七天。它们的排队巡逻又失败了。你数了数，还是五只，但插队的那只换了。",
               30: "它们把窝搭成了一个大大的圆形——中间给你留了块空地。你坐进去的瞬间，五只幼龙挤成一圈把你围住，呼噜声此起彼伏。",
               100: "一百天。今天它们'狩猎'回来了：五只幼龙，合力叼回一片大叶子，郑重地放在你门口。这是这个群体有史以来最大的猎物。你也郑重地收下了。"},
    "深渊之眼": {7: "第七天。它开始在你写字时飘在纸上方——你的字在它的注视下，好像不太敢写歪。",
                 30: "你发现它在夜里替你数星星。数着数着，它自己晃悠两下，也睡了。它不知道你睁眼看过这一幕。",
                 100: "一百天。它给你看了一次它'记得的深渊'——很黑，很远。然后它把视线转回你的脸上，像在说：这里更好。它选择留在这里。"},
}
PET_STORY_365 = "三百六十五天。「{N}」已经陪着你走过整整一年。它把一枚小小的印记放进你手心——不是什么宝物，是它自己刻的：它的名字和你的，挤在一起。"
PET_HEART_TXT = "「{N}」把攒了很久的宝贝送给了你——它一直在等一个合适的日子。今天就是。"

# v1.56：散步文本（{N} = 显示名）
PET_WALK_TXT = [
    "{N} 去了营地后面的小树林，回来时尾巴上挂了一片叶子，非常得意。",
    "{N} 沿河走了一圈，数了七只鸭子。它认为七只刚好是个好数字。",
    "{N} 爬上了营地最高的那块石头，对着远方看了很久——也许在看风景，也许在看路。",
    "{N} 在草坡上打了个滚，沾了一身草籽。它不觉得这是个问题。",
    "{N} 追着一只蝴蝶跑出去很远。回来时蝴蝶不见了，但它已经不在乎了。",
    "{N} 在树荫下睡了一觉。睡梦里尾巴一直轻轻摇着。",
    "{N} 和路过的商队打了个照面。商队的人说，那小家伙拦在路中间，要了块肉干才让路。",
    "{N} 找到了一个晒太阳的绝佳位置。它记住了，想下次带你去。",
    "{N} 叼回来一根树枝。非常直。它希望你和它一样欣赏这根树枝。",
    "{N} 巡视了整个营地边界——在每棵树下都留了记号。它认为营地的安全得到了充分保障。",
]
# v1.56：宠物小剧场（{A} / {B} = 两只随机宠物显示名）
PET_THEATER_TXT = [
    "{A} 和 {B} 围着你的靴子各占一头，谁都不肯挪窝——最后一起在里面睡到了中午。",
    "{A} 叼着 {B} 的后颈把它拎回了窝。{B} 一脸不情愿，尾巴却翘着。",
    "{A} 教 {B} 玩一个游戏，规则似乎只有它们俩懂。你看了十分钟，决定不懂也挺好。",
    "{B} 把 {A} 的尾巴当枕头。{A} 假装没发现，僵着坐了一下午。",
    "{A} 和 {B} 一起盯着窗外看了很久。你凑过去看——什么都没有。但它们很认真。",
    "{A} 偷吃了 {B} 的晚饭，{B} 追了它三圈营地，最后一起躺在草地上晒太阳。",
    "{A} 今天心情不太好，{B} 把自己藏起来的宝贝送给了它。{A} 的表情没变，但尾巴摇了一下。",
    "你回营地时，{A} 和 {B} 一左一右趴在门口等你——像两尊小小的、活的门神。",
    "{A} 和 {B} 比赛谁先爬到你的膝盖上。你被夹在中间，一动都不敢动。",
    "{A} 给 {B} 讲了个'故事'（也许是故事）。{B} 听得睡着了。",
    "{A} 把自己的窝往 {B} 的窝边挪了挪。就一点点。它假装只是随便挪挪。",
    "傍晚，{A} 和 {B} 一前一后跟着你走，影子拉得很长。这个画面你想记很久。",
]
# v1.56：深夜提醒（{A} = 随机宠物显示名；22:30 ~ 06:00 打开时每天一次）
PET_NIGHT_TXT = [
    "{A} 用脑袋顶了顶你的手——它困了，但它更想你睡。",
    "{A} 把窝拖到了你的灯下，趴进去，回头看你一眼。意思很明白。",
    "{A} 打了个哈欠，打得很大，故意让你看见。",
    "{A} 在你脚边来回踱步——它知道这个时间，你该去洗漱了。",
    "{A} 把爪子搭在床沿：'我先睡给你看。'",
    "{A} 轻轻地叫了一声。不是催，是心疼。",
]
# v1.56：节日宠物问候（按节日名；未列出的用通用句）
PET_FEST_SCENE = {
    "🎊 元旦": "新的一年——营地静立，静候今年的第一缕日出。",
    "💝 情人节": "营地里到处是心形装饰，连箭靶都画成了心。",
    "⚒️ 劳动节": "公会的劳动节大集开张，吆喝声一整天没停。",
    "🎈 儿童节": "公会今天给所有'小朋友'发糖——标准放得很宽。",
    "🎉 国庆": "满城彩旗招展，公会给每扇窗都挂了一面小旗。",
    "🎃 万圣夜": "南瓜灯在营地各处眨眼，糖果的香气一路飘。",
    "🎄 冬幕节": "壁炉烧得旺旺的，窗外飘起了今年的头一场雪。",
    "🎆 除夕": "营火通宵不灭——守岁的人，都能多喝一碗热汤。",
    "🧧 春节": "红灯笼一路挂到了公会门口，拜年的人踏破了门槛。",
    "🏮 元宵节": "灯谜挂了满满一廊，汤圆的香气盖都盖不住。",
    "🌿 清明节": "风很好，适合走远路——很多人去看了远处的山。",
    "🐉 端午节": "粽叶的清香飘满营地，河上的龙舟鼓声一阵阵传来。",
    "💫 七夕节": "今晚的星空格外清亮，营地安静得能听见银河。",
    "🌕 中秋节": "月亮升起来了——今晚的月光，是所有日子里最圆的一份。",
    "🍁 重阳节": "今天适合登高。山顶的风，比山脚的更清醒。",
    "🥣 腊八节": "粥香从清晨飘到黄昏，谁路过都能讨一碗。",
    "🧹 小年": "扫尘的日子——营地上下，连角落都在闪闪发光。",
}
PET_FEST_REACT = {
    "史莱姆": ["{A} 对节日的理解是：今天可以多蹭你三次。", "{A} 高兴地弹来弹去，把节日的气氛弹得更好了一点。"],
    "绒球兽": ["{A} 滚来滚去地庆祝——它庆祝的方式一直是滚来滚去。", "{A} 把最好的一口留给了你，然后眼巴巴看着你。"],
    "捣蛋鬼": ["{A} 宣布今天所有的恶作剧都叫'节日互动'。", "{A} 郑重地表示它什么都没干，身后飘着一条彩带。"],
    "月光狐": ["{A} 说节日也该读书，于是把故事读得比平时更慢一点。", "{A} 挑了个最高的位置看热闹，尾巴垂下来一晃一晃。"],
    "小狼": ["{A} 把尾巴摇出了节日的节奏，坚信今天是为它办的。", "{A} 一早就守在门口——它认为所有节日都该由它先迎接你。"],
    "星界幼龙": ["{A} 仰头看了很久的天——它想给你摘一颗节日的星星。", "{A} 把收集的小光点排成了节日的形状。"],
    "龙神幼崽": ["{A} 端坐了一整个上午，拿出了它最有仪式感的坐姿。", "{A} 威严地巡视了一圈，对节日的气氛表示满意。"],
    "幼龙群": ["{A} 围成了一圈。它们认为圆就是节日的形状。", "{A} 排着队绕营地走了一圈，队形比彩带还整齐。"],
    "深渊之眼": ["{A} 安静地看着热闹——它说，这颜色很好看。", "{A} 从暗处探出来看了看，又安心地缩了回去。"],
}
PET_FEST_REACT_DEFAULT = ["{A} 也感受到了节日的气氛，一整天都精神十足。", "{A} 跟在你身边寸步不离——它喜欢热闹的日子。"]


def pet_show_name(s, n):
    """展示名：昵称优先，否则本名"""
    nk = (s.get("pet_nick") or {}).get(n)
    return nk if nk else n


def pet_meta_of(s, n):
    """v1.56：陪伴公共数据（mood / gotDate / 抚摸计数 / 好心情连击 / 羁绊里程碑）——养成链在 pet_data，小狼在 wolf"""
    if n == "小狼":
        m = s.get("wolf")
    else:
        m = (s.get("pet_data") or {}).get(n)
    if not m:
        return None
    m.setdefault("mood", 50)
    m.setdefault("gotDate", today_str())     # 老档迁移：从本版本起算羁绊
    m.setdefault("ptDate", "")
    m.setdefault("ptCount", 0)
    m.setdefault("happyStreak", 0)
    m.setdefault("bondDone", [])
    return m


def pet_bond_days(s, n):
    m = pet_meta_of(s, n)
    if not m:
        return 0
    try:
        return (parse_date(today_str()) - parse_date(m["gotDate"])).days + 1
    except Exception:
        return 0


def pet_mood_label(mood):
    return "😊" if mood >= PET_MOOD_HAPPY else ("😴" if mood < PET_MOOD_LOW else "😐")


def pet_mood_daily(s, msgs, sc, slept):
    """v1.56：宠物心情日结算——由主人昨日的现实健康驱动（只反映，不惩罚数值）"""
    names = list(s.get("pets") or [])
    if s.get("wolf"):
        names.append("小狼")
    for n in set(names):
        m = pet_meta_of(s, n)
        if not m:
            continue
        dm = 10 if sc >= 90 else (5 if sc >= 60 else -5)
        if slept:
            dm += 5
        m["mood"] = max(0, min(100, m.get("mood", 50) + dm))
        if m["mood"] >= PET_MOOD_HAPPY:
            m["happyStreak"] = m.get("happyStreak", 0) + 1
        else:
            m["happyStreak"] = 0
        if m["happyStreak"] and m["happyStreak"] % 7 == 0:      # 连续 7 天好心情 → 心意事件
            gift = random.choice(PET_WALK_GIFT)
            s["mats"][gift] = (s.get("mats") or {}).get(gift, 0) + 1
            txt = PET_HEART_TXT.replace("{N}", pet_show_name(s, n))
            add_log(s, "💗 " + txt, "gold")
            msgs.append("💗 " + txt + "（" + gift + " ×1）")


def pet_bond_tick(s, msgs):
    """v1.56：羁绊里程碑（陪伴天数达标 → 解锁故事；幂等）"""
    names = list(s.get("pets") or [])
    if s.get("wolf"):
        names.append("小狼")
    for n in set(names):
        m = pet_meta_of(s, n)
        if not m:
            continue
        bd = pet_bond_days(s, n)
        for mile in PET_BOND_MILES:
            if bd >= mile and mile not in m["bondDone"]:
                m["bondDone"].append(mile)
                show = pet_show_name(s, n)
                if mile == 365:
                    s["items"]["羁绊印记"] = (s.get("items") or {}).get("羁绊印记", 0) + 1
                    msg = "💞 " + show + " 与你相伴了整整一年——它把亲手刻的「羁绊印记」放进了你的手心。"
                else:
                    msg = "💞 羁绊故事解锁：" + show + "（相伴 " + str(mile) + " 天）——去宠物页读读它的故事吧。"
                add_log(s, msg, "gold")
                msgs.append(msg)


def pet_pat(s, n, msgs):
    """v1.56：抚摸（每日 1 次/宠，+5 心情）"""
    if n == "小狼":
        if not s.get("wolf"):
            return "还没有小狼。"
    elif n not in (s.get("pets") or []):
        return "还没有这只宠物。"
    m = pet_meta_of(s, n)
    if not m:
        return "还没有这只宠物。"
    used = m.get("ptCount", 0) if m.get("ptDate") == today_str() else 0
    if used >= 1:
        return "今天已经摸过它了——它说：'明天再来。'（每只每天 1 次）"
    m["ptDate"] = today_str()
    m["ptCount"] = used + 1
    m["mood"] = min(100, m.get("mood", 50) + 5)
    txt = random.choice(PET_PAT_TXT.get(n, ["它开心地蹭了蹭你。"]))
    show = pet_show_name(s, n)
    add_log(s, "🤗 你摸了摸 " + show + "：" + txt, "ok")
    msgs.append("🤗 " + show + "\n" + txt)
    return None


def pet_walk_start(s, n, msgs):
    """v1.56：派宠物去散步（同时只能 1 只；约半小时后下次打开结算）"""
    if n == "小狼":
        if not s.get("wolf"):
            return "还没有小狼。"
    elif n not in (s.get("pets") or []):
        return "还没有这只宠物。"
    if s.get("carry_pet") == n:
        return "它正陪你冒险呢，没空去散步。"
    w = s.get("pet_walk")
    if w:
        return "「" + pet_show_name(s, w["n"]) + "」还在外面散步——等它回来再说吧。"
    s["pet_walk"] = {"n": n, "ts": now_ms()}
    show = pet_show_name(s, n)
    msgs.append("🐾 " + show + " 出发去散步了——大约半小时后回来（下次打开游戏时收获）。")
    return None


def pet_walk_settle(s, msgs):
    """散步结算：到点即回（幂等；由 catch_up / tick 调用）"""
    w = s.get("pet_walk")
    if not w:
        return
    if now_ms() - w.get("ts", 0) < PET_WALK_MS:
        return
    n = w["n"]
    s["pet_walk"] = None
    s["walk_count"] = (s.get("walk_count") or 0) + 1
    show = pet_show_name(s, n)
    txt = random.choice(PET_WALK_TXT).replace("{N}", show)
    extra = ""
    if random.random() < 0.30:
        gift = random.choice(PET_WALK_GIFT)
        cnt = random.randint(1, 2)
        s["mats"][gift] = (s.get("mats") or {}).get(gift, 0) + cnt
        extra = "\n它还带回来了：" + gift + " ×" + str(cnt) + "。"
    m = pet_meta_of(s, n)
    if m:
        m["mood"] = min(100, m.get("mood", 50) + 3)
    add_log(s, "🐾 " + txt + extra, "ok")
    msgs.append("🐾 散步归来！\n" + txt + extra)


def pet_theater(s, msgs):
    """v1.56：宠物小剧场（每天最多一次；需 ≥2 只）"""
    names = list(s.get("pets") or [])
    if s.get("wolf"):
        names.append("小狼")
    names = sorted(set(names))
    if len(names) < 2:
        return
    a, b = random.sample(names, 2)
    txt = random.choice(PET_THEATER_TXT).replace("{A}", pet_show_name(s, a)).replace("{B}", pet_show_name(s, b))
    add_log(s, "🎪 " + txt, "ok")
    msgs.append("🎪 宠物小剧场\n" + txt)


def pet_night_tip(s, msgs):
    """v1.56：深夜提醒（22:30 ~ 06:00 打开时，每天一次）"""
    if not (s.get("pets") or s.get("wolf")):
        return
    now = datetime.now()
    hm = now.hour * 60 + now.minute
    if not (hm >= 22 * 60 + 30 or now.hour < 6):
        return
    if s.get("pet_night_date") == today_str():
        return
    s["pet_night_date"] = today_str()
    names = list(s.get("pets") or [])
    if s.get("wolf"):
        names.append("小狼")
    a = random.choice(sorted(set(names)))
    txt = random.choice(PET_NIGHT_TXT).replace("{A}", pet_show_name(s, a))
    add_log(s, "🌙 " + txt, "ok")
    msgs.append("🌙 " + txt)


def pet_daily_checks(s, msgs, crossed):
    """v1.56：宠物日常总入口（散步结算 / 羁绊 / 小剧场 / 深夜）——挂 catch_up"""
    pet_walk_settle(s, msgs)
    pet_bond_tick(s, msgs)
    if crossed and random.random() < 0.4:
        pet_theater(s, msgs)
    pet_night_tip(s, msgs)


def set_pet_nick(s, n, nick, msgs):
    """v1.56：给宠物起昵称（≤6 字符；空 = 恢复本名）"""
    if n == "小狼":
        if not s.get("wolf"):
            return "还没有小狼。"
    elif n not in (s.get("pets") or []):
        return "还没有这只宠物。"
    nick = (nick or "").strip()
    if not s.get("pet_nick"):
        s["pet_nick"] = {}
    if not nick:
        s["pet_nick"].pop(n, None)
        msgs.append("它恢复了本名。")
        return None
    if len(nick) > 6:
        return "昵称最多 6 个字符。"
    s["pet_nick"][n] = nick
    msgs.append("从现在起，它叫「" + nick + "」了。")
    return None




def read_count(s):
    """v1.55：累计阅读次数（hist_stats.read 的服务端源）——阅读驱动宠物（月光狐）的进化依据"""
    return sum(((h.get("multi") or [0, 0])[1] or 0) for h in (s.get("history") or []))


def pet_read_need(n, stage):
    L = PET_LINES.get(n)
    if not L or not L.get("readDriven"):
        return None
    rn = L.get("readNeed") or []
    return rn[stage - 1] if 0 <= stage - 1 < len(rn) else None


def sync_read_pets(s, msgs):
    """v1.55：阅读次数达标 → 自动进化（幂等；对齐前端 syncReadPets）"""
    rc = read_count(s)
    for n, L in PET_LINES.items():
        if not L.get("readDriven") or n not in (s.get("pets") or []):
            continue
        pd = (s.get("pet_data") or {}).get(n)
        if not pd:
            continue
        guard = 0
        while pd.get("stage", 1) < 3 and rc >= (pet_read_need(n, pd["stage"]) or 0) and guard < 3:
            guard += 1
            pd["stage"] += 1
            st = L["stages"][pd["stage"] - 1]
            add_log(s, "🎉 宠物成长：「" + st["name"] + "」（累计阅读 " + str(rc) + " 次）", "gold")
            msgs.append("🎉 宠物「" + n + "」进化为「" + st["name"] + "」！（累计阅读 " + str(rc) + " 次）")


def pet_data_of(s, n):
    if not isinstance(s.get("pet_data"), dict):
        s["pet_data"] = {}
    if n in PET_LINES and n not in s["pet_data"]:
        s["pet_data"][n] = {"stage": 1, "growth": 0, "mutate": 0, "fedDate": "", "fedCount": 0}
    return s["pet_data"].get(n)


def grant_pet(s, n):
    if n not in s["pets"]:
        s["pets"].append(n)
    if n in PET_LINES:
        pet_data_of(s, n)


def pet_bonus(s):
    """v1.56c：只计算「携带中」的宠物加成（携带出门才生效；独立叠加小值）"""
    b = {"mat": 0.0, "rate": 0.0, "pay": 0.0, "exp": 0.0}   # v1.58：sp（探索点/天）通道已整体移除
    n = s.get("carry_pet") or ""
    L = PET_LINES.get(n)
    if L:
        pd = pet_data_of(s, n)
        if pd:
            c = L["mut"] if pd.get("stage", 1) >= 4 else L["stages"][pd.get("stage", 1) - 1]
            for k in ("mat", "rate", "pay", "exp"):
                b[k] += c.get(k, 0) or 0
    F = PET_FIXED.get(n)
    if F:
        for k in ("mat", "rate", "pay", "exp"):
            b[k] += F.get(k, 0) or 0
    _pm = today_fest_eff().get("pet_mul")   # v1.41f：情人节·宠物加成翻倍
    if _pm:
        for k in b:
            b[k] = b[k] * _pm
    return b


def pet_feed_value(n, food):
    """v1.35：每只宠物口味不同；v1.55c：品阶营养——未列出材料按品阶给成长（对齐小狼口径）；favs 值为 0 = 拒食"""
    L = PET_LINES.get(n)
    if not L:
        return {"v": 0, "mv": 0, "refuse": False}
    fv = (L.get("favs") or {}).get(food)
    mv = (L.get("muts") or {}).get(food)
    is_adv = food in WOLF_MUTATE_VALUE
    if fv == 0:
        return {"v": 0, "mv": 0, "refuse": True}
    if fv is None and food not in WOLF_FOODS:
        return {"v": 0, "mv": 0, "refuse": True}     # v1.56e：非基础材料的「本命材料」只有本宠能吃（如星核仅星界幼龙）
    base = WOLF_FEED_VALUE.get((M.get(food) or [None, None])[1], 2)   # 客观营养：品阶越高成长越多
    return {
        "v": 0 if L.get("readDriven") else max(fv if fv is not None else 0, base),   # 阅读驱动不涨成长；口味与品阶取较高者
        "mv": mv if mv is not None else (2 if is_adv else 0),
        "refuse": False,
    }


def feed_pet(s, n, food, msgs):
    L = PET_LINES.get(n)
    if not L:
        return "它不需要喂食。"
    pd = pet_data_of(s, n)
    if not pd:
        return "还没有这只宠物。"
    if not s["mats"].get(food):
        return "没有该材料。"
    if pd["stage"] >= 4:
        return "「" + L["mut"]["name"] + "」已是最终形态，不再需要喂食。"
    if food not in WOLF_FOODS and food not in (L.get("favs") or {}):
        return "「" + food + "」不能喂食——宠物吃：食材 / 草药、龙之精粹（龙血 / 龙心），以及各自的『本命材料』（见宠物详情）。"
    if pet_feed_value(n, food).get("refuse"):
        return "「" + food + "」不合「" + n + "」的口味——它不肯吃。"
    used = pd.get("fedCount", 0) if pd.get("fedDate") == today_str() else 0
    if used >= WOLF_DAILY_FEED:
        return "今天已经喂食 " + str(WOLF_DAILY_FEED) + " 次了，明天再喂吧。"
    need = L["stages"][pd["stage"] - 1].get("need")
    _pv = pet_feed_value(n, food)                        # v1.35：按宠物偏好计算成长值 / 变异值
    v = _pv["v"]
    mv = _pv["mv"]
    if L.get("readDriven") and not mv:                   # v1.55：阅读驱动——普通食材不涨成长（浪费一次喂食机会，先拦）
        if pd["stage"] >= 3:
            return "「" + L["stages"][2]["name"] + "」的成长已经完成——只需喂食高级特殊材料积累变异值。"
        return ("「" + n + "」的成长来自你的阅读——普通食材不再增加成长值。当前：" + str(read_count(s))
                + " / " + str(pet_read_need(n, pd["stage"])) + " 次。高级特殊材料仍可积累变异值（二阶起）。")
    if L.get("readDriven") and mv and pd["stage"] < 2:   # v1.55：一阶不积累变异值——别浪费高级材料
        return ("「" + L["stages"][0]["name"] + "」的变异值自二阶起才开始积累——现在喂会浪费。先陪它读书吧：阅读 "
                + str(read_count(s)) + " / " + str(pet_read_need(n, 1)) + " 次。")
    s["mats"][food] -= 1
    if s["mats"][food] <= 0:
        del s["mats"][food]
    pd["fedDate"] = today_str()
    pd["fedCount"] = used + 1
    if not L.get("readDriven") and need is not None and pd["growth"] < need:
        pd["growth"] += v
    if mv and pd["stage"] >= 2:
        pd["mutate"] = pd.get("mutate", 0) + mv
    if L.get("readDriven"):
        add_log(s, "🐾 喂食「" + food + "」→ " + L["stages"][pd["stage"] - 1]["name"]
                + " 变异 " + str(pd.get("mutate", 0)) + "/" + str(L["need"]), "ok")
    else:
        add_log(s, "🐾 喂食「" + food + "」→ " + L["stages"][pd["stage"] - 1]["name"]
                + " 成长 " + str(pd["growth"]) + "/" + str(need), "ok")
    if not L.get("readDriven") and need is not None and pd["stage"] < 3 and pd["growth"] >= need:
        pd["stage"] += 1
        pd["growth"] = 0
        st = L["stages"][pd["stage"] - 1]
        add_log(s, "🎉 宠物成长：「" + st["name"] + "」", "gold")
        msgs.append("🎉 宠物「" + n + "」成长为「" + st["name"] + "」！")
    return None


def evolve_pet(s, n, msgs):
    L = PET_LINES.get(n)
    pd = pet_data_of(s, n)
    if not L or not pd or pd["stage"] != 3:
        return "只有终极前一阶可以变异。"
    if not L.get("readDriven") and pd["growth"] < L["stages"][2]["need"]:   # v1.55：阅读驱动只看变异值
        return "成长值尚未积满（" + str(pd["growth"]) + " / " + str(L["stages"][2]["need"]) + "）。"
    if pd.get("mutate", 0) < L["need"]:
        return "变异值尚未积满（" + str(pd.get("mutate", 0)) + " / " + str(L["need"]) + "）。"
    pd["stage"] = 4
    pd["growth"] = 0
    pd["mutate"] = 0
    add_log(s, "🌌 宠物变异：「" + L["mut"]["name"] + "」", "gold")
    msgs.append("🌌 宠物「" + n + "」变异为「" + L["mut"]["name"] + "」！")
    return None


def pet_quest_gain(s, q, ok, qlv):
    """v1.38f：携带宠物陪同委托的成长值（成功 1~3 / 失败保底 1），返回提示文案或空串"""
    n = s.get("carry_pet") or ""
    if not n:
        return ""
    if ok:
        qi = qlv - 1
        g = 1 + (1 if qi >= 2 else 0) + (1 if q[4] in ("困难", "噩梦") else 0)
    else:
        g = 1
    if n == "小狼":
        w = s.get("wolf")
        if not w or w.get("stage", 1) >= 4:
            return ""
        w["growth"] = w.get("growth", 0) + g
        return "🐺 " + WOLF_STAGES[w["stage"] - 1]["name"] + " 成长 +" + str(g)
    L = PET_LINES.get(n)
    pd = (s.get("pet_data") or {}).get(n)
    if not L or not pd or pd.get("stage", 1) >= 4:
        return ""
    if L.get("readDriven"):                     # v1.55：阅读驱动宠物不吃委托成长
        return L["icon"] + " " + L["stages"][pd["stage"] - 1]["name"] + " 陪你完成了委托（成长来自阅读）"
    pd["growth"] = pd.get("growth", 0) + g
    return L["icon"] + " " + L["stages"][pd["stage"] - 1]["name"] + " 成长 +" + str(g)


def set_carry_pet(s, name, msgs):
    """v1.38f：设置 / 切换携带宠物（同名再设或 name 为空 = 看家）"""
    name = name or ""
    if name == (s.get("carry_pet") or ""):
        name = ""
    if name:
        if name == "小狼":
            if not s.get("wolf"):
                return "❌ 还没有小狼。"
        elif name not in (s.get("pets") or []):
            return "❌ 还没有这只宠物。"
    s["carry_pet"] = name
    msgs.append("📌 " + (name + " 开始陪同冒险——完成委托时会获得少量成长值。" if name else "🏠 宠物留在营地看家——加成暂停。"))
    return None


def mat_drop_rate(name):
    tier = M.get(name, ["", "普通"])[1]
    return CFG["matDrop"].get(tier, 1)


def roll_qty(lo, hi):
    if hi <= lo:
        return lo
    total = sum((hi - i + 1) for i in range(lo, hi + 1))
    r = random.random() * total
    for i in range(lo, hi + 1):
        r -= (hi - i + 1)
        if r < 0:
            return i
    return lo


def mat_qty_range(v):
    return v if isinstance(v, list) else [v, v]


# ══════════════ 委托池 ══════════════


def pool_point_key(d, h):
    return today_str(d) + "@" + str(h).zfill(2)


def latest_point(now=None):
    now = now or datetime.now()
    cur = now.hour + now.minute / 60
    best = None
    for rh in CFG["refreshHours"]:
        if cur >= rh:
            best = rh
    if best is None:
        y = now - timedelta(days=1)
        return y.date(), CFG["refreshHours"][-1]   # 今天还没到首个刷新点 → 用昨天最后一个刷新点（v1.41f3：21:00）
    return now.date(), best


def quest_req_ok(s, name):
    """v1.41 I1：链前置判定（无前置或前置已完成 → True）"""
    r = QUEST_REQ.get(name)
    if not r:
        return True
    return (s.get("done_quests") or {}).get(r, 0) > 0


def mix_pool(s):
    """混合委托池（v1.30 修复）：Lv_n 玩家可遇到 Lv1~Lv_n 的全部委托（原实现误为只抽同级池）
    v1.41 I1：链前置过滤（过滤后兜底防空池）"""
    lst = []
    for i in range(s["lv_idx"] + 1):
        lst.extend(C.get(LV_NAMES[i], []))
    flt = [q for q in lst if quest_req_ok(s, q[0])]
    return flt if flt else lst


# ══════════════ v1.41 I3：月度世界事件 ══════════════
def _next_month_ts():
    """下月 1 日 00:00 的毫秒时间戳（当月称号轮换到期）"""
    n = datetime.now()
    y, m = (n.year + 1, 1) if n.month == 12 else (n.year, n.month + 1)
    return int(datetime(y, m, 1).timestamp() * 1000)


def month_event_expired():
    """v1.48e：整月有效——截止当月最后一天 23:30（跨月由 key 轮换自然作废）"""
    return False


def month_event_now(s):
    """当前生效的月度事件（未生成/已换月 → None；结构对齐原型 monthEventNow；v1.48f：Lv1 起全员解锁）"""
    mk = today_str()[:7]
    me = s.get("month_event")
    if not me or me.get("key") != mk:
        return None
    ev = MONTH_EVENTS[int(mk[5:7]) - 1]
    done = bool(me.get("done"))
    return {"ev": ev, "cnt": me.get("cnt", 0), "done": done,
            "expired": False if done else month_event_expired()}


def month_event_tick(s, msgs):
    """v1.48f：Lv1 起全员解锁；每月 1 号生成（换月自动轮换；上月未完成自然作废）"""
    mk = today_str()[:7]
    me = s.get("month_event")
    if me and me.get("key") == mk:
        return
    s["month_event"] = {"key": mk, "cnt": 0, "done": False}
    ev = MONTH_EVENTS[int(mk[5:7]) - 1]
    add_log(s, "🌍 本月世界事件：「" + ev["n"] + "」——" + ev["desc"] + "　截止当月最后一天 23:30（奖励：金币 + 材料 + 当月称号）", "gold")


def month_event_add(s, msgs, typ, n=1):
    """进度累加 + 达成发奖（金币×lv_gold_mul + 材料 + 当月轮换称号）"""
    cur = month_event_now(s)
    if not cur or cur["done"] or cur["expired"]:
        return
    if cur["ev"]["t"] != typ:
        return
    s["month_event"]["cnt"] = s["month_event"].get("cnt", 0) + (n or 1)
    if s["month_event"]["cnt"] >= cur["ev"]["need"]:
        s["month_event"]["done"] = True
        ev = cur["ev"]
        g = int(round(ev["gold"] * lv_gold_mul(s)))
        s["money"] += g
        for mk, r in ev["mats"].items():
            s["mats"][mk] = s["mats"].get(mk, 0) + random.randint(r[0], r[1])
        tt = s.setdefault("tim_titles", {})
        tt[ev["title"]] = max(_next_month_ts(), tt.get(ev["title"], 0))
        add_log(s, "🌍 世界事件「" + ev["n"] + "」达成！+" + fmt_money(g) + "　称号「" + ev["title"] + "」（本月有效）", "gold")
        msgs.append("🌍 世界事件达成：「" + ev["n"] + "」→ 称号「" + ev["title"] + "」")


def draw_pool(s, point):
    li = s["lv_idx"]
    n = CFG["drawCount"][li]
    lst = mix_pool(s)
    now = point[0]
    hh, mm = point[1], 0
    cur_min = hh * 60 + mm

    def in_window(q):
        w = q[2]
        if w == "全天":
            return True
        a, b = w.split("-")
        ah = int(a.split(":")[0]) * 60 + int(a.split(":")[1])
        bh = int(b.split(":")[0]) * 60 + int(b.split(":")[1])
        return ah <= cur_min <= bh

    ok = [q for q in lst if in_window(q)]
    src = ok if len(ok) >= n else lst
    if not src:
        return []
    k = min(n, len(src))
    return random.sample(src, k)


def pool_base_window_ms(s=None):
    """基础接取窗口（未计节日）：最后一次刷新点（按 pool.point 的班次）2.5 小时，其余 1 小时——v1.41f3"""
    if s:
        p = s.get("pool") or {}
        pt = str(p.get("point") or "")
        try:
            if int(pt.split("@")[1]) == CFG["refreshHours"][-1]:
                return LAST_POOL_WINDOW_MS
        except (IndexError, ValueError):
            pass
    return POOL_WINDOW_MS


def pool_window_ms(s=None):
    """接取窗口时长（最后一次刷新点 2.5 小时；节日 +1 小时）——v1.41f3"""
    return pool_base_window_ms(s) + (FEST_POOL_BONUS_MS if is_festival() else 0)


def _fmt_hours_txt(ms):
    """毫秒 → 小时文本（1 / 2.5 / 3.5）——v1.41f3"""
    h = ms / 3600000.0
    return str(int(h)) if h == int(h) else ("%.1f" % h)


def pool_expired(s):
    p = s.get("pool")
    if not p or not p.get("bornTs"):
        return False
    return now_ms() >= p["bornTs"] + pool_window_ms(s)


def pool_left_ms(s):
    p = s.get("pool")
    if not p or not p.get("bornTs"):
        return 0
    return max(0, p["bornTs"] + pool_window_ms(s) - now_ms())


# ══════════════ 传奇 ══════════════


def avg_health_last(s, n):
    hist = s["history"][-n:]
    if not hist:
        return 0
    return sum(h["score"] for h in hist) / len(hist)


def sleep_days_last(s, n):
    return sum(1 for h in s["history"][-n:] if h["sleep"])


def sleep_streak(s, n):
    sh = set(s.get("shield_days") or []) | set(s.get("sick_days") or [])   # v1.60：病假日与连击保险同为保护日
    def _ok(h):
        return h["sleep"] or h["date"] in sh                # v1.40：连击保险日计入（保险真正保住连击，不再只是显示）
    hist = s["history"][-n:]
    if len(hist) < n:
        return len(hist) > 0 and all(_ok(h) for h in hist)
    return sum(1 for h in hist if _ok(h)) >= n - 3          # 断连保护（每月 3 次容错）


def legend_unlocked(s):
    return (s["lv_idx"] >= 4 and s["exp"] >= 30000 and guild_idx(s) >= 5
            and avg_health_last(s, 7) >= 60 and sleep_days_last(s, 30) >= 25)


def legend_eligible(s, L):
    c = L[8] or {}
    if c.get("q") and s["done_quests"].get(c["q"], 0) <= 0:
        return False
    if c.get("q40") and s["done_below5"] < 250:   # v1.60：40 → 250（对齐前端 legendEligible）
        return False
    if c.get("sleep30") and not sleep_streak(s, 30):
        return False
    if c.get("legend") and c["legend"] not in s["legend_done"]:
        return False
    if c.get("gear") and c["gear"] not in s.get("gear", []):      # v1.51 A3：需拥有指定传说装备
        return False
    if c.get("allLegend"):
        for x in LEGEND:
            if x is L or (x[8] or {}).get("allLegend"):
                continue
            if x[0] not in s["legend_done"]:
                return False
    return True


LEGEND_CON = 150        # v1.51：传奇事件贡献奖励（原 50 → 150）——前端 LEGEND_CON 对齐


def legend_rep(s, L):
    """v1.50：按报酬面额对齐原型 legendRep——400 + 每铂金币 +100 + 噩梦 +200
       （原实现按难度固定 1100/1800，与 03 文档 / 前端 / 对拍锚点全部不符）"""
    copper = LEGEND_GOLD.get(L[4]) or 1000000
    return 400 + int(round(copper / 1000000 * 100)) + (200 if L[3] == "噩梦" else 0)


def roll_legend(s, msgs):
    t = today_str()
    if s["legend_day"] == t:
        return
    # 新的一天：清除昨日遗留的「预览」事件（正式事件保留至接取）
    if s.get("legend_preview"):
        s["legend_active"] = None
        s["legend_preview"] = False
        if s.get("pending_legend") and s["pending_legend"].get("preview"):
            s["pending_legend"] = None            # 旧预览的提示一并作废
    s["legend_day"] = t
    if not legend_unlocked(s):
        # 未达参与条件：每日 2% 极低概率「窥见」传奇事件——仅可看，不能接取/参与
        # （v1.24；v1.41 用户指定保留：给玩家盼头与兴趣）
        if random.random() < 0.02:
            s["legend_active"] = random.choice(LEGEND)
            s["legend_preview"] = True
            s["legend_name"] = "传奇事件" if random.random() < 0.5 else "世界级事件"
            msgs.append("🔮 " + s["legend_name"] + "的低语：「" + s["legend_active"][0] + "」——尚未达到参与条件，只能远远望见（预览）")
            s["pending_legend"] = {"title": s["legend_name"], "name": s["legend_active"][0], "preview": True}
            if s.get("daily"):
                s["daily"]["events"].append("🔮 " + s["legend_name"] + "低语（预览）：" + s["legend_active"][0])
        return
    p = 0.15 + (0.05 if s["charm"] >= 5 else 0)
    if random.random() < p:
        pool = [L for L in LEGEND if legend_eligible(s, L)]
        if not pool:
            return
        s["legend_active"] = random.choice(pool)
        s["legend_preview"] = False
        s["legend_name"] = "传奇事件" if random.random() < 0.5 else "世界级事件"
        msgs.append("🌍 " + s["legend_name"] + "出现：「" + s["legend_active"][0] + "」")
        s["pending_legend"] = {"title": s["legend_name"], "name": s["legend_active"][0], "preview": False}
        if s.get("daily"):
            s["daily"]["events"].append("🌍 " + s["legend_name"] + "出现：" + s["legend_active"][0])


def grant_legend_reward(s, L):
    for p in (L[7] or "").split("；"):
        if not p:
            continue
        m = re.search(r"称号「(.+?)」", p)
        if m:
            if m.group(1) not in s["titles"]:
                s["titles"].append(m.group(1))
            continue
        m = re.search(r"宠物「(.+?)」", p)
        if m:
            if m.group(1) not in s["pets"]:
                s["pets"].append(m.group(1))
            continue
        m = re.match(r"^(.+?)图纸$", p)
        if m and gear_def(m.group(1)):
            s["blueprints"][m.group(1)] = True     # v1.40：图纸类奖励入图纸库（原误入藏品 → 陨星武器图纸拿不到）
            continue
        if gear_def(p):
            if p not in s["gear"]:
                s["gear"].append(p)                # v1.40：装备类奖励入装备背包（原误入藏品 → 世界树护符/时间沙漏永远拿不到）
            continue
        if p not in s["trophies"]:
            s["trophies"].append(p)


def take_legend(s, msgs):
    L = s.get("legend_active")
    if not L:
        return "当前没有可接取的传奇事件。"
    if s.get("legend_preview"):
        return "🔮 这只是低语中的幻影——尚未达到参与条件，传奇事件无法接取，也无法参与。"
    _wk = week_key()
    _lwN = s.get("legend_week_n", 0) if s["legend_week"] == _wk else 0
    _cap = 2 if guild_idx(s) >= 9 else 1           # v1.40：P 级「至尊」特权——传奇每周可接 2 次（原未实现）
    if _lwN >= _cap:
        return ("本周已经接取过 " + str(_lwN) + " 次" + s["legend_name"] + "了。"
                + ("至尊每周最多 2 次。" if _cap > 1 else "每周最多接取 1 次。"))
    if any(a.get("legend") for a in s.get("active", [])):        # v1.51 A3：传奇事件同时最多 1 个（对齐 01 文档）
        return "已有传奇事件进行中——传奇事件同时最多 1 个，先完成它再来。"
    # v1.41：传奇事件独立槽位——不再占用普通「同时进行」上限
    rate = legend_rate(s, L[3])
    s["legend_active"] = None
    s["legend_week"] = _wk
    s["legend_week_n"] = _lwN + 1
    s["active"].append({
        "q": [L[0], L[1], "传奇", 0, L[3], 0, L[4], 0, {}],
        "rate": rate, "qlv": lv_num(s), "meal": active_meal(s),
        "legend": L, "days": L[2], "lname": s["legend_name"],
        "acceptTs": now_ms(), "finishTs": now_ms() + L[2] * 86400000, "name": L[0],
    })
    msgs.append("🌍 接取" + s["legend_name"] + "「" + L[0] + "」耗时 " + str(L[2]) + " 天，成功率 " + str(round(rate * 100)) + "%")
    return None


# ══════════════ 稀有事件 ══════════════


def rare_chance(s):
    p = 0.05 + s["skills"].get("幸运", 0) * 0.01 + gear_effects(s)["rare"] + s.get("echo", 0) * 0.01
    return min(0.25, p)


def try_rare_event(s, quest_tag, quest_name, msgs, explore_mode=False):
    if random.random() >= rare_chance(s):
        return None
    total = sum(r[1] for r in RARE)
    roll = random.random() * total
    picked = RARE[0]
    for r in RARE:
        roll -= r[1]
        if roll <= 0:
            picked = r
            break
    name, _w, typ, val, _desc = picked
    msg = ""
    if typ == "gold":
        s["money"] += val * 10000
        msg = "+" + str(val) + " 金币"
    elif typ == "silver":
        s["money"] += val * 100
        msg = "+" + str(val) + " 银币"
    elif typ == "exp":
        s["exp"] += val
        msg = "+" + str(val) + " 经验"
    elif typ == "con":
        s["con"] += val
        msg = "+" + str(val) + " 贡献"
    elif typ == "sp":
        s["explore"] += val
        msg = "+" + str(val) + " 探索点"
    elif typ == "vit":
        s["vit"] += val
        msg = "+" + str(val) + " 活力点"
    elif typ == "pay":
        if quest_name:
            msg = "「" + quest_name + "」报酬 +50%"
        else:
            s["money"] += 5000
            msg = "探索触发 → 改为获得 50 银币"
    elif typ == "pay25":
        s["rare_next_pay"] = s.get("rare_next_pay", 0) + val
        msg = "下一次委托报酬 +25%"
    elif typ == "rate":
        s["rare_next_rate"] = s.get("rare_next_rate", 0) + val
        msg = "下一次委托成功率 +5%"
    elif typ == "mat3":
        got = {}
        for _ in range(val):
            mm = random_mat(s, "普通" if random.random() < 0.7 else "精良")
            s["mats"][mm] = s["mats"].get(mm, 0) + 1
            got[mm] = got.get(mm, 0) + 1
        msg = " ".join(k + "×" + str(v) for k, v in got.items())
    elif typ == "gear":
        pool = [g for g in GEAR if g[1] in ("普通", "精良")]
        g = random.choice(pool)
        if g[0] not in s["gear"]:
            s["gear"].append(g[0])
        msg = "获得装备「" + g[0] + "」"
    elif typ == "item":
        items = ["清醒符咒", "安眠护符", "活力药水", "疾风符咒", "时之怀表", "幸运币"]
        it = random.choice(items)
        s["items"][it] = s["items"].get(it, 0) + 1
        msg = "获得「" + it + "」"
    add_log(s, "✨ 稀有事件「" + name + "」→ " + msg, "gold")
    if s.get("daily"):
        s["daily"]["events"].append("✨ 稀有事件：" + name + "（" + msg + "）")
    _push_capped(s, "pending_rare", {"name": name, "msg": msg})   # v1.39（B6）：封顶 50
    check_level_up(s)
    return {"name": name, "msg": msg}


def random_mat(s, tier):
    pool = [k for k, v in M.items() if v[1] == tier]
    return random.choice(pool)


# ══════════════ 结算 ══════════════


def quest_rep(s, q, lv):
    if lv <= 2:
        return lv * 5
    return REP_TABLE.get(str(lv), {}).get(q[4], lv * 5)


def settle(s, a, msgs):
    """结算（同步版；3D 骰子动画由前端拿到 roll 后播放）"""
    q = a["q"]
    rate = a["rate"]

    # 传奇事件分支
    if a.get("legend"):
        L = a["legend"]
        lname = a.get("lname") or s.get("legend_name") or "传奇事件"
        base = LEGEND_GOLD.get(L[4], 1000000)
        roll2 = rand(100)
        ok2 = roll2 <= round(rate * 100)
        g2 = int(round(base * (1 + gear_bonus(s) + gear_acc_bonus(s) + charm_pay(s)))) if ok2 else max(1, int(round(base * 0.3)))
        e2 = L[5] if ok2 else max(1, int(round(L[5] * 0.3)))   # v1.48d：传奇失败得 30% 经验（至少 1）
        r2 = legend_rep(s, L) if ok2 else 0
        s["money"] += g2
        s["exp"] += e2
        if ok2 and L[6]:
            for pair in L[6].split("、"):
                m = re.match(r"^(.+?)×(\d+)$", pair)
                if m and m.group(1) in M:
                    s["mats"][m.group(1)] = s["mats"].get(m.group(1), 0) + int(m.group(2))
        if ok2:
            s["rep"] += r2
            s["con"] += LEGEND_CON                  # v1.51：贡献 50 → 150（与前端 LEGEND_CON 对齐）
            grant_legend_reward(s, L)
            if L[0] not in s["legend_done"]:
                s["legend_done"].append(L[0])   # v1.50：去重——防重复完成同一传奇刷「大师」成就 / 重复入档
            check_achievements(s, msgs)
        res = {"name": L[0], "type": (L[1] or "精英").split("+")[0], "roll": roll2, "need": round(rate * 100),
               "title": (lname + "完成！") if ok2 else "失败",
               "gold": g2, "exp": e2, "got": [L[7]] if ok2 else [], "cls": "gold" if ok2 else "bad"}
        _push_capped(s, "results", res)   # v1.39（B6）：封顶 50
        add_log(s, "🌍 " + lname + "「" + L[0] + "」掷出 " + str(roll2) + " → " + ("成功" if ok2 else "失败")
                + "（+" + fmt_money(g2) + " / +" + str(e2) + "经验"
                + (" / +" + str(r2) + "声望" if r2 else "") + "）", "gold" if ok2 else "bad")   # v1.53：补声望显示（对齐前端）
        check_level_up(s)
        return res

    # v1.53：常规委托掷骰移到传奇分支之后——传奇只掷 roll2，避免多消耗一个随机数（对齐前端随机流）
    roll = rand(100)
    ok = roll <= round(rate * 100)
    crit = roll <= 5
    fumble = roll >= 96

    _eff = gear_effects(s)
    _fe = today_fest_eff()                    # v1.41f：节日专属效果
    gold = 0
    exp = 0
    if ok:
        gold = q[5]
        if crit:
            gold = int(round(gold * 1.2))
        m = a.get("meal")
        pay_mul = 1 + gear_bonus(s) + gear_acc_bonus(s) + _eff["pay"].get(q[1], 0) + pet_bonus(s)["pay"]
        if _eff["pay"].get("晨间") and is_morning_quest(q):
            pay_mul += _eff["pay"]["晨间"]
        bn = s.get("buff_next")
        if bn and bn["date"] == today_str():
            pay_mul += bn.get("pay", 0)
        pay_mul += title_pay_bonus(s)
        pay_mul += title_own_bonus(s)                 # v1.41：称号收集（每 1 个 +1%，上限 +10%）
        pay_mul += _fe.get("pay", 0)                  # v1.41f：节日报酬（国庆 +20% / 春节 +30%）
        if q[1] == "精英" and guild_idx(s) >= 3 and s.get("lib_date") == today_str():
            pay_mul += 0.10
        pay_mul += s.get("rare_next_pay", 0)      # 稀有事件·商队搭伙（下一次委托报酬 +25%）
        if m and m.get("bonus"):
            pay_mul += m["bonus"] * _fe.get("cook_mul", 1)   # v1.41f：腊八·料理效果翻倍
        pay_mul += charm_pay(s)
        pay_mul += skill_pay(s, q)
        gold = int(round(gold * pay_mul))
        exp = int(round(q[6] * (1 + _eff["exp"] + pet_bonus(s)["exp"] + _fe.get("exp", 0))))   # v1.41f：劳动节·经验 +50%
    else:
        # v1.48d：失败得 30% 报酬 + 30% 经验（各至少 1），无掉落
        gold = max(1, int(round(q[5] * 0.3)))
        exp = max(1, int(round(q[6] * 0.3 * (1 + _eff["exp"] + pet_bonus(s)["exp"] + _fe.get("exp", 0)))))
    # v1.41 I4：资源指定类——持有指定材料（≥1）→ 自动上交 1 个，本次报酬翻倍
    if ok and QUEST_TURNIN.get(q[0]) and (s["mats"].get(QUEST_TURNIN[q[0]], 0) >= 1):
        _tn = QUEST_TURNIN[q[0]]
        s["mats"][_tn] -= 1
        add_log(s, "📦 上交「" + _tn + "」×1 → 「" + q[0] + "」本次报酬翻倍", "gold")
        gold *= 2
    s["money"] += gold
    s["exp"] += exp

    got = []
    got_obj = {}
    if ok and q[8]:
        for idx, k in enumerate(q[8].keys()):
            _drop = (mat_drop_rate(k) + wolf_mat_bonus(s) + pet_bonus(s)["mat"]) * _fe.get("mat_drop_mul", 1)   # v1.41f：万圣夜·掉率翻倍
            if idx == 0 or random.random() < min(1, _drop):
                lo, hi = mat_qty_range(q[8][k])
                n2 = roll_qty(lo, hi)
                if _eff["mat"] > 0 and idx > 0:
                    n2 = max(1, int(round(n2 * (1 + _eff["mat"]))))
                if _fe.get("mat_qty_pct"):                     # v1.41f：七夕·乞巧（数量 +50%）
                    n2 = max(1, int(round(n2 * (1 + _fe["mat_qty_pct"]))))
                s["mats"][k] = s["mats"].get(k, 0) + n2
                got.append(k + "×" + str(n2))
                got_obj[k] = n2

    q_lv = QUEST_LV.get(q[0], s["lv_idx"]) + 1            # v1.51 A4：声望 / 贡献均按「委托等级」（不再按玩家等级）
    rep = quest_rep(s, q, q_lv) if ok else 0
    if ok and crit:
        rep += 5
    con = int(round(q_lv * (1 + _eff["con"]))) if ok else 0
    s["rep"] += rep
    s["con"] += con

    if not s.get("daily") or s["daily"].get("date") != today_str():
        s["daily"] = _blank_daily(today_str())
    s["daily"]["done"] += 1 if ok else 0
    s["daily"]["gold"] += gold
    s["daily"]["exp"] += exp
    s["daily"]["rep"] += rep
    s["daily"]["con"] += con
    s["daily"]["quests"].append({"name": q[0], "grade": q[4], "ok": ok})
    for k, v in got_obj.items():
        s["daily"]["mats"][k] = s["daily"]["mats"].get(k, 0) + v
    if ok:
        s["done_quests"][q[0]] = s["done_quests"].get(q[0], 0) + 1
        # v1.41 I1：链推进提示（该委托是某链节点的前置时，提示后续线索）
        _nxt = [k2 for k2, v2 in QUEST_REQ.items() if v2 == q[0]]
        if _nxt:
            add_log(s, "🔗 传闻：完成「" + q[0] + "」后，「" + _nxt[0] + "」的线索已出现，将可能出现在委托栏中", "gold")
        month_event_add(s, msgs, "quest")   # v1.41 I3：月度世界事件·委托进度
        if a.get("qlv", s["lv_idx"] + 1) <= 4:
            s["done_below5"] += 1
        s["total_quests"] = s.get("total_quests", 0) + 1
        check_achievements(s, msgs)

    # 稀有事件「下一次委托」加成：本次结算即消费（无论成败）
    s["rare_next_rate"] = 0
    s["rare_next_pay"] = 0

    pet_note = pet_quest_gain(s, q, ok, a.get("qlv", s["lv_idx"] + 1))   # v1.38f：携带宠物成长
    title = "大失败" if (not ok and fumble) else ("大成功！" if (ok and crit) else ("成功" if ok else "失败"))
    cls = "bad" if not ok else ("gold" if crit else "ok")
    res = {"name": q[0], "type": q[1], "roll": roll, "need": round(rate * 100), "title": title,
           "gold": gold, "exp": exp, "got": got, "cls": cls,
           "icon": "✅" if ok else "❌", "grade": q[4], "pet": pet_note}
    _push_capped(s, "results", res)   # v1.39（B6）：封顶 50
    add_log(s, ("✅" if ok else "❌") + " 结算「" + q[0] + "」掷出 " + str(roll) + " / 需要 ≤" + str(round(rate * 100))
            + " → " + title + "（+" + fmt_money(gold) + " / +" + str(exp) + "经验" + (" / " + " ".join(got) if got else "") + "）"
            + (" " + pet_note if pet_note else ""),
            "gold" if ok else "bad")
    check_level_up(s)
    # v1.50：稀有事件判定（每次委托结算、成败都判）——对齐原型（原缺失；探索模式另有独立触发）
    try_rare_event(s, q[1], q[0], msgs)
    return res


# ══════════════ 日结算 / 周月结算 / 区间奖励 / 成就 ══════════════


def apply_buff_claim(s, msgs):
    bn = s.get("buff_next")
    if not bn or bn.get("claimed"):
        return
    if bn["date"] > today_str():
        return
    msg = []
    if bn.get("con"):
        s["con"] += bn["con"]
        msg.append("贡献 +" + str(bn["con"]))
    if bn.get("vit"):
        v = int(round(bn["vit"] * (1 + charm_vit(s))))
        s["vit"] += v
        msg.append("活力点 +" + str(v))
    bn["claimed"] = True
    if msg:
        add_log(s, "🌟 区间奖励到账：" + "、".join(msg), "gold")
        msgs.append("🌟 区间奖励到账：" + "、".join(msg))


def day_settle(s, msgs):
    """结算 s['health'] 所指的那一天（含豁免 → 区间奖励 → 归档 → 周月结算 → 成就）"""
    hd = s["health"]["done"]
    d_str = s["health"]["date"]
    ym = d_str[:7]
    # v1.40：删除「安神吊坠·早睡豁免」残留——v1.38p 已将该词条从装备移除，此处硬编码漏删；普通装备不再提供健康豁免
    _cn = s["exempt"].get("charmNight") or {}
    if not hd[1] and _cn.get("date") == d_str and _cn.get("slot") == "晨曦之冠" and s["exempt"].get("early") != week_key(parse_date(d_str)):   # v1.41 G6：依据睡前佩戴快照
        hd[1] = 1
        s["exempt"]["early"] = week_key(parse_date(d_str))
        msgs.append("🌅 晨曦之冠·早起豁免生效：本日「7:40 前起床」视为达成（每周 1 次）")
    sc = calc_health(s)
    if sick_today(s):                      # v1.61：疗养圣所·病假 → 该日按 59 分锁定结算
        msgs.append("🕊️ 疗养圣所·病假：本日评分按 " + str(SICK_LOCK_SCORE) + " 分锁定结算")
    # v1.41 I3：月度世界事件·规律打卡日（当日 7 项完成 ≥6，豁免已计）
    if sum(1 for x in hd if x) >= 6:
        month_event_add(s, msgs, "task")
    rep = con = vit = 0
    if sc >= 90:
        rep, con, vit = 8, 6, 5
    elif sc >= 75:
        rep, con, vit = 5, 3, 3
    elif sc >= 60:
        rep, con, vit = 2, 1, 1   # v1.59b：良好档（第三档）追加 活力点 +1（用户指定）
    if vit:
        vit = int(round(vit * (1 + charm_vit(s))))
    if rep or con or vit:
        s["rep"] += rep
        s["con"] += con
        s["vit"] += vit
        if s.get("daily"):
            s["daily"]["rep"] += rep
            s["daily"]["con"] += con
            s["daily"]["vit"] = s["daily"].get("vit", 0) + vit
        msgs.append("📊 日结算：" + d_str + " 健康 " + str(sc) + " 分 → 声望+" + str(rep) + " 贡献+" + str(con) + " 活力点+" + str(vit))
    else:
        msgs.append("📊 日结算：" + d_str + " 健康 " + str(sc) + " 分，无额外奖励")
    # 安眠室累计
    if hd[0]:
        s["heat_n"] = s.get("heat_n", 0) + 1
        if s["heat_n"] % 7 == 0:
            msgs.append("🛏️ 安眠室：累计早睡 " + str(s["heat_n"]) + " 天 → 健康加成 +" + str(min(5, s["heat_n"] // 7)) + "pp")
    # 次日区间奖励
    nxt = next_day_str(d_str)
    nb = {"date": nxt, "pay": 0, "energy": 0, "con": 0, "vit": 0, "claimed": False, "score": sc}
    if sc >= 90:
        nb.update(pay=0.15, con=6, vit=5, energy=10)
    elif sc >= 75:
        nb.update(pay=0.10, con=3, vit=3)
    elif sc >= 60:
        nb.update(pay=0.05, con=1, vit=1)   # v1.59b：良好档（第三档）追加 活力点 +1（与结算表同步）
    elif sc < 40:                       # v1.40：虚弱 → 次日精力上限 −10%（原固定 −10 对高等级无感）；40–59「普通」档无额外奖励
        nb.update(energyPct=-0.10)
    # v1.40：补发未领取的旧区间奖励（玩家生效日未上线时，贡献/活力点不再被覆盖丢失；报酬与精力有时效，过期作废）
    ob = s.get("buff_next")
    if ob and not ob.get("claimed") and ob.get("date", "") <= d_str:
        bm = []
        if ob.get("con"):
            s["con"] += ob["con"]
            bm.append("贡献 +" + str(ob["con"]))
        if ob.get("vit"):
            v = int(round(ob["vit"] * (1 + charm_vit(s))))
            s["vit"] += v
            bm.append("活力点 +" + str(v))
        if bm:
            msgs.append("🌟 补发 " + ob["date"] + " 的区间奖励：" + "、".join(bm) + "（当时未上线，报酬与精力已过期）")
            add_log(s, "🌟 补发 " + ob["date"] + " 的区间奖励：" + "、".join(bm), "ok")
        ob["claimed"] = True
    s["buff_next"] = nb
    # 归档
    h = {"date": d_str, "score": sc, "sleep": bool(hd[0]),
         "done": s["daily"]["done"] if s.get("daily") else 0,
         "gold": s["daily"]["gold"] if s.get("daily") else 0,
         "tasks": list(hd), "multi": list(s["health"]["multi"])}
    s["history"].append(h)
    pet_mood_daily(s, msgs, sc, bool(hd[0]))      # v1.56：宠物心情日结算（现实作息驱动）
    del s["history"][:-400]
    # 周/月结算 + 成就
    dd = parse_date(d_str)
    if dd.weekday() == 6:            # 周日
        weekly_settle(s, d_str, msgs)
    if parse_date(nxt).month != dd.month:
        monthly_settle(s, d_str, msgs)
    check_achievements(s, msgs)
    # 昨日快照
    d = s.get("daily") or {}
    s["yesterday"] = {
        "date": d_str, "score": sc, "rep": rep, "con": con, "vit": vit,
        "tasks": [{"n": t[0], "p": t[1], "ok": bool(hd[i])} for i, t in enumerate(CFG["tasks"])],
        "multiTasks": [{"n": t[0], "p": t[1], "cnt": s["health"]["multi"][i], "max": t[2]} for i, t in enumerate(CFG["multiTasks"])],
        "doneCount": d.get("done", 0), "quests": list(d.get("quests", [])),
        "exp": d.get("exp", 0), "gold": d.get("gold", 0),
        "rep2": d.get("rep", 0), "con2": d.get("con", 0),
        "mats": dict(d.get("mats", {})), "events": list(d.get("events", [])),
        "exploreNext": sc // 10,
    }
    s["yesterday_shown"] = False


def tier3(v, a, b, c):
    return 3 if v >= c else (2 if v >= b else (1 if v >= a else 0))


def lv_gold_mul(s):   # v1.41 H4：周/月结算金币随等级缩放（贡献/探索点/声望/道具不缩放）
    return [1, 1.5, 2, 3, 4][s["lv_idx"]]


def lv_vit_mul(s):    # v1.41 H4：活力点随等级缩放
    return [1, 1.25, 1.5, 1.75, 2][s["lv_idx"]]


def weekly_settle(s, end_date_str, msgs):
    mk = week_key(parse_date(end_date_str))
    if s.get("week_settled") == mk:
        return None
    s["week_settled"] = mk
    days = [h for h in s["history"] if h.get("date") and week_key(parse_date(h["date"])) == mk]
    n = max(1, len(days))
    avg = sum(h["score"] for h in days) / n
    sleep_n = sum(1 for h in days if h["sleep"])
    sport_n = sum(1 for h in days if h.get("tasks") and h["tasks"][4])
    read_n = sum((h.get("multi") or [0, 0])[1] for h in days)
    quest_n = sum(h.get("done", 0) for h in days)
    t_avg = tier3(avg, 60, 75, 90)
    t_sleep = tier3(sleep_n, 5, 6, 7)
    t_sport = tier3(sport_n, 3, 5, 7)
    t_read = tier3(read_n, 2, 4, 6)
    t_quest = tier3(quest_n, 5, 10, 15)
    got = []
    if t_avg:
        c = int(round([1000, 3000, 10000][t_avg - 1] * lv_gold_mul(s)))
        s["money"] += c
        got.append("平均健康 " + str(round(avg)) + " → " + fmt_money(c))
    if t_sleep:
        v = int(round([10, 20, 40][t_sleep - 1] * lv_vit_mul(s) * (1 + charm_vit(s))))
        s["vit"] += v
        got.append("早睡 " + str(sleep_n) + " 天 → 活力点 +" + str(v))
    if t_sport:
        c = [20, 50, 100][t_sport - 1]
        s["con"] += c
        got.append("运动 " + str(sport_n) + " 天 → 贡献 +" + str(c))
    if t_read:
        e = [5, 10, 20][t_read - 1]
        s["explore"] += e
        got.append("阅读 " + str(read_n) + " 次 → 探索点 +" + str(e))
    if t_quest:
        c = int(round([2000, 5000, 10000][t_quest - 1] * lv_gold_mul(s)))
        s["money"] += c
        got.append("完成委托 " + str(quest_n) + " 次 → " + fmt_money(c))
    if sleep_n >= 6:
        c = int(round(500 * lv_gold_mul(s)))
        s["money"] += c
        s["con"] += 50
        got.append("连续早睡（周保护）→ " + fmt_money(c) + " + 贡献50")
    if quest_n >= 10:
        c = int(round(2000 * lv_gold_mul(s)))
        s["money"] += c
        s["con"] += 80
        got.append("完成 10 次委托 → " + fmt_money(c) + " + 贡献80")
    if sport_n >= 5:
        c = int(round(1500 * lv_gold_mul(s)))
        s["money"] += c
        s["con"] += 60
        got.append("运动 5 天 → " + fmt_money(c) + " + 贡献60")
    if got:
        msgs.append("📅 周结算（" + mk + " 当周）：" + "｜".join(got))
    return got


def monthly_settle(s, end_date_str, msgs):
    ym = end_date_str[:7]
    if s.get("month_settled") == ym:
        return None
    s["month_settled"] = ym
    days = [h for h in s["history"] if h.get("date") and h["date"][:7] == ym]
    n = max(1, len(days))
    avg = sum(h["score"] for h in days) / n
    sleep_n = sum(1 for h in days if h["sleep"])
    sport_n = sum(1 for h in days if h.get("tasks") and h["tasks"][4])
    read_n = sum((h.get("multi") or [0, 0])[1] for h in days)
    quest_n = sum(h.get("done", 0) for h in days)
    t_avg = tier3(avg, 70, 80, 90)
    t_sleep = tier3(sleep_n, 20, 23, 25)
    t_sport = tier3(sport_n, 12, 18, 24)
    t_read = tier3(read_n, 10, 20, 30)
    t_quest = tier3(quest_n, 20, 40, 60)
    got = []
    if t_avg:
        c = int(round([10000, 30000, 100000][t_avg - 1] * lv_gold_mul(s)))
        s["money"] += c
        got.append("平均健康 " + str(round(avg)) + " → " + fmt_money(c))
    if t_sleep:
        v = int(round([50, 100, 200][t_sleep - 1] * lv_vit_mul(s) * (1 + charm_vit(s))))
        s["vit"] += v
        got.append("早睡 " + str(sleep_n) + " 天 → 活力点 +" + str(v))
    if t_sport:
        add = [5, 10, 20][t_sport - 1]                 # v1.40：可累积、上限 50（原「取历史最高」首金后归零）
        if s.get("perm_energy", 0) < 50:
            s["perm_energy"] = min(50, s.get("perm_energy", 0) + add)
            got.append("运动 " + str(sport_n) + " 天 → 永久精力上限 +" + str(add)
                       + "（累计 " + str(s["perm_energy"]) + "/50）")
    if t_read == 1:
        pool = [g[0] for g in GEAR if g[5] != "—" and g[0] not in s["blueprints"]]
        if pool:
            bp = random.choice(pool)
            s["blueprints"][bp] = True
            got.append("阅读 " + str(read_n) + " 次 → 图纸「" + bp + "」")
    elif t_read == 2:
        pool = [g for g in GEAR if g[1] == "稀有"]
        g = random.choice(pool)
        if g and g[0] not in s["gear"]:
            s["gear"].append(g[0])
            got.append("阅读 " + str(read_n) + " 次 → 装备「" + g[0] + "」")
    elif t_read == 3:
        if "月光狐" not in s["pets"]:
            s["pets"].append("月光狐")
            got.append("阅读 " + str(read_n) + " 次 → 宠物「月光狐」")
    if t_quest:
        c = int(round([50000, 150000, 500000][t_quest - 1] * lv_gold_mul(s)))
        rp = [20, 60, 150][t_quest - 1]
        s["money"] += c
        s["rep"] += rp
        got.append("完成委托 " + str(quest_n) + " 次 → " + fmt_money(c) + " + 声望" + str(rp))
    until = now_ms() + 30 * 86400000
    if t_sleep == 3:
        s["tim_titles"]["安眠守护者"] = until
        got.append("早睡黄金 → 称号「安眠守护者」（30 天）")
    if t_quest == 3:
        s["tim_titles"]["公会中坚"] = until
        got.append("委托黄金 → 称号「公会中坚」（30 天）")
    if sleep_streak(s, 30):
        c = int(round(10000 * lv_gold_mul(s)))
        s["money"] += c
        s["tim_titles"]["作息守护者"] = until
        got.append("连续 30 天规律作息（含保护）→ " + fmt_money(c) + " + 称号「作息守护者」")
    if quest_n >= 40:
        c = int(round(30000 * lv_gold_mul(s)))
        s["money"] += c
        s["rep"] += 200
        got.append("完成 40 次委托 → " + fmt_money(c) + " + 声望200")
    if got:
        msgs.append("🗓️ 月结算（" + ym + "）：" + "｜".join(got))
    return got


ACHV = [
    ("晨曦之约", "晨曦之冠"),
    ("百炼成钢", "百炼徽记"),
    ("屠龙者", "龙血指环"),
    ("深渊归来", "深渊之瞳"),
    ("创世者", "创世之印"),
    # v1.35：5→10 —— 长期健康习惯向成就（累计口径）
    ("夜之安眠", "安眠坠"),
    ("晨间行者", "晨行者徽章"),
    ("身强体健", "健行者护腕"),
    ("博览群书", "藏书家之冕"),
    ("百战之躯", "百战护符"),
    ("大师", "大师徽章"),          # v1.41 I6：完成 ≥4 个不同传奇事件（解锁大师商店）
    # v1.41 I5：隐藏成就（达成前不显示于成就列表；gear=None → 奖励永久称号见 ACHV_TITLE）
    ("周全绿", None),
    ("夜猫子的救赎", None),
    ("滴水穿石", None),
    ("书中自有", None),
    ("传奇之旅", None),
    ("囤积家", None),
    # v1.56：宠物向隐藏成就
    ("蜕变之始", None),
    ("形影不离", None),
    ("林间常客", None),
]
ACHV_TITLE = {                                     # v1.41 I5：隐藏成就 → 永久称号
    "周全绿": "常青", "夜猫子的救赎": "归夜者", "滴水穿石": "恒行者",
    "书中自有": "万卷", "传奇之旅": "传奇旅人", "囤积家": "满仓",
    "蜕变之始": "破茧", "形影不离": "形影", "林间常客": "林客",
}


def _achv_cond(s, name):
    if name == "晨曦之约":
        last = s["history"][-30:]
        return len(last) >= 30 and sum(1 for h in last if h.get("tasks") and h["tasks"][1]) >= 27
    if name == "百炼成钢":
        return s.get("total_quests", 0) >= 100
    if name == "屠龙者":
        return "屠龙传说" in s["legend_done"]
    if name == "深渊归来":
        return s["done_quests"].get("深渊领主封印", 0) > 0
    if name == "创世者":
        return "创世碎片" in s["legend_done"]
    # v1.35：5→10 新增判定
    if name == "夜之安眠":
        return sum(1 for h in s["history"] if h.get("sleep")) >= 60
    if name == "晨间行者":
        return sum(1 for h in s["history"] if len(h.get("tasks") or []) > 1 and h["tasks"][1]) >= 60
    if name == "身强体健":
        return sum(1 for h in s["history"] if len(h.get("tasks") or []) > 4 and h["tasks"][4]) >= 60
    if name == "博览群书":
        c = 0
        for h in s["history"]:
            mm = h.get("multi") or []
            if len(mm) > 1:
                c += mm[1] or 0
        return c >= 100
    if name == "百战之躯":
        return s.get("total_quests", 0) >= 300
    if name == "大师":
        return len(set(s.get("legend_done") or [])) >= 4     # v1.41 I6；v1.50：按不同事件数（旧档重复兜底）
    # v1.41 I5：隐藏成就判定
    if name == "周全绿":
        hs = s["history"][-14:]
        return len(hs) >= 14 and all((h.get("score") or 0) >= 80 for h in hs)
    if name == "夜猫子的救赎":
        hs = s["history"]
        miss = sum(1 for h in hs if not h.get("sleep"))
        last20 = hs[-20:]
        return miss >= 10 and len(last20) >= 20 and all(h.get("sleep") for h in last20)
    if name == "滴水穿石":
        return sum(1 for h in s["history"] if len(h.get("tasks") or []) > 1 and h["tasks"][1]) >= 200
    if name == "书中自有":
        c = 0
        for h in s["history"]:
            mm = h.get("multi") or []
            if len(mm) > 1:
                c += mm[1] or 0
        return c >= 500
    if name == "传奇之旅":
        return len(set(s.get("legend_done") or [])) >= 6     # v1.53：去重（对齐「大师」口径）
    if name == "囤积家":
        return len(s.get("mats") or {}) >= 50
    # v1.56：宠物向
    if name == "蜕变之始":
        if (s.get("wolf") or {}).get("stage", 0) >= 4:
            return True
        return any((s.get("pet_data") or {}).get(n, {}).get("stage", 0) >= 4 for n in (s.get("pets") or []))
    if name == "形影不离":
        names = list(s.get("pets") or [])
        if s.get("wolf"):
            names.append("小狼")
        return any(pet_bond_days(s, n) >= 100 for n in set(names))
    if name == "林间常客":
        return (s.get("walk_count") or 0) >= 10
    return False


def check_achievements(s, msgs):
    for name, gear in ACHV:
        if name in s["achv"]:
            continue
        if not _achv_cond(s, name):
            continue
        s["achv"].append(name)
        if gear:                                       # 常规成就：奖励成就饰品
            if gear not in s["gear"]:
                s["gear"].append(gear)
            add_log(s, "🏅 成就达成「" + name + "」→ 成就饰品「" + gear + "」已放入装备背包", "gold")
            msgs.append("🏅 成就达成「" + name + "」→ 获得「" + gear + "」")
        else:                                          # v1.41 I5：隐藏成就：奖励永久称号
            _t = ACHV_TITLE.get(name)
            if _t and _t not in s["titles"]:
                s["titles"].append(_t)
                add_log(s, "🏅 成就达成「" + name + "」→ 称号「" + _t + "」已入档", "gold")
                msgs.append("🏅 成就达成「" + name + "」→ 称号「" + _t + "」")
    _check_gallery_titles(s, msgs)                    # v1.38：图鉴集齐称号


def _check_gallery_titles(s, msgs):
    """v1.38：图鉴四类集齐 → 授予称号（纯荣誉，冒险者信息页「称号」栏展示）"""
    seen = set(s.get("seen_mats") or []) | set((s.get("mats") or {}).keys())
    owned = set(s.get("forged") or []) | set(s.get("gear") or [])
    for slot in (s.get("equipped") or {}).values():
        if slot:
            owned.add(slot)
    done = s.get("done_quests") or {}
    # v1.41 I5：收集分层——材料/装备 50%/80% 银/金称号（100% 为原有「博物学家」「军械大师」）
    _m_all = len(M)
    _m_have = sum(1 for k in M if k in seen)
    _g_all = len(GEAR)
    _g_have = sum(1 for g in GEAR if g[0] in owned)
    checks = [
        ("博物学家·银", _m_all > 0 and _m_have * 2 >= _m_all),
        ("博物学家·金", _m_all > 0 and _m_have * 5 >= _m_all * 4),
        ("军械大师·银", _g_all > 0 and _g_have * 2 >= _g_all),
        ("军械大师·金", _g_all > 0 and _g_have * 5 >= _g_all * 4),
        ("博物学家", bool(M) and set(M.keys()) <= seen),
        ("军械大师", bool(GEAR) and {g[0] for g in GEAR} <= owned),
        ("宫廷主厨", bool(CFG["recipes"]) and {r["n"] for r in CFG["recipes"]} <= set(s.get("cooked") or [])),
        ("传说冒险者", bool(C) and all(done.get(q[0], 0) > 0 for lv in C.values() for q in lv)),
    ]
    for name, ok in checks:
        if ok and name not in (s.get("titles") or []):
            s.setdefault("titles", []).append(name)
            add_log(s, "📖 图鉴集齐！获得称号「" + name + "」（冒险者信息页可见）", "gold")
            msgs.append("📖 图鉴集齐！获得称号「" + name + "」")


# ══════════════ 补算引擎（09_技术方案 第五节） ══════════════


FESTIVALS = {                     # v1.38c：公历节日（当天委托报酬 +20%、成功率 +10%，打开当天提示一次）
    "01-01": ("🎊 元旦", "新的一年，冒险者！愿你的健康与冒险并进。"),
    "02-14": ("💝 情人节", "把好好照顾自己，当作今天的第一份心意。"),
    "05-01": ("⚒️ 劳动节", "为自己的坚持也放个假——休息是冒险的一部分。"),
    "06-01": ("🎈 儿童节", "像孩子一样轻快地跑起来吧。"),
    "10-31": ("🎃 万圣夜", "糖果可以拿，早睡不能丢。"),
    "12-25": ("🎄 冬幕节", "风雪夜，一杯热汤，一份好眠。"),
}
# v1.41c：假期区间（区间内每天按节日生效——国庆 10-01~10-07）。
# 节日窗口机制：接取窗口 +1 小时、三餐窗口前后各 +30 分钟、入睡/起床打卡尾部 +1 小时
FESTIVAL_RANGES = [
    ("10-01", "10-07", "🎉 国庆", "举国欢庆的日子，也别忘了好好吃饭、早点睡。"),
]
# v1.41e：中国传统节日（农历）——公历日期表 2025~2040（`数据表/_生成农历节日.py` 生成；过期后重跑该脚本扩表）
# 名称 → (显示名, 问候语, 风味文案)；春节含除夕~初六假期区间（生成时已逐日展开，除夕单列）
CN_FEST_META = {
    "除夕":     ("🎆 除夕", "阖家团圆", "爆竹声里辞旧岁——今晚守岁可以，别熬太狠。"),
    "春节":     ("🧧 春节", "新年大吉", "新春快乐！新的一年，好好吃饭、好好睡觉，冒险才有劲。"),
    "元宵节":   ("🏮 元宵节", "节日快乐", "汤圆甜又圆——赏灯可以，23:30 前记得回家睡。"),
    "清明节":   ("🌿 清明节", "清明安康", "清明时节——踏青之余，也照顾好自己。"),
    "端午节":   ("🐉 端午节", "端午安康", "粽叶飘香——粽子好吃，肠胃和作息更要紧。"),
    "七夕节":   ("💫 七夕节", "节日快乐", "今夜星河灿烂——有人相伴很好，独善其身也很好。"),
    "中秋节":   ("🌕 中秋节", "节日快乐", "月圆人团圆——掰块月饼，今晚早点睡。"),
    "重阳节":   ("🍁 重阳节", "重阳安康", "登高望远，敬老思亲——秋深处，添衣保暖。"),
    "腊八节":   ("🥣 腊八节", "节日快乐", "一碗腊八粥，暖到心里——年味开始了。"),
    "小年":     ("🧹 小年", "节日快乐", "掸尘扫房，辞旧迎新——小年到，过年不远了。"),
}
CN_LUNAR_FEST = {   # 公历年 → 年内农历节日（MM-DD 名称，| 分隔；2025~2040 表）
    "2025": "01-07 腊八节|01-22 小年|01-28 除夕|01-29 春节|01-30 春节|01-31 春节|02-01 春节|02-02 春节|02-03 春节|02-12 元宵节|04-04 清明节|05-31 端午节|08-29 七夕节|10-06 中秋节|10-29 重阳节",
    "2026": "01-26 腊八节|02-10 小年|02-16 除夕|02-17 春节|02-18 春节|02-19 春节|02-20 春节|02-21 春节|02-22 春节|03-03 元宵节|04-05 清明节|06-19 端午节|08-19 七夕节|09-25 中秋节|10-18 重阳节",
    "2027": "01-15 腊八节|01-30 小年|02-05 除夕|02-06 春节|02-07 春节|02-08 春节|02-09 春节|02-10 春节|02-11 春节|02-20 元宵节|04-05 清明节|06-09 端午节|08-08 七夕节|09-15 中秋节|10-08 重阳节",
    "2028": "01-04 腊八节|01-19 小年|01-25 除夕|01-26 春节|01-27 春节|01-28 春节|01-29 春节|01-30 春节|01-31 春节|02-09 元宵节|04-04 清明节|05-28 端午节|08-26 七夕节|10-03 中秋节|10-26 重阳节",
    "2029": "01-22 腊八节|02-06 小年|02-12 除夕|02-13 春节|02-14 春节|02-15 春节|02-16 春节|02-17 春节|02-18 春节|02-27 元宵节|04-04 清明节|06-16 端午节|08-16 七夕节|09-22 中秋节|10-16 重阳节",
    "2030": "01-11 腊八节|01-26 小年|02-02 除夕|02-03 春节|02-04 春节|02-05 春节|02-06 春节|02-07 春节|02-08 春节|02-17 元宵节|04-05 清明节|06-05 端午节|08-05 七夕节|09-12 中秋节|10-05 重阳节",
    "2031": "01-01 腊八节|01-16 小年|01-22 除夕|01-23 春节|01-24 春节|01-25 春节|01-26 春节|01-27 春节|01-28 春节|02-06 元宵节|04-05 清明节|06-24 端午节|08-24 七夕节|10-01 中秋节|10-24 重阳节",
    "2032": "01-20 腊八节|02-04 小年|02-10 除夕|02-11 春节|02-12 春节|02-13 春节|02-14 春节|02-15 春节|02-16 春节|02-25 元宵节|04-04 清明节|06-12 端午节|08-12 七夕节|09-19 中秋节|10-12 重阳节",
    "2033": "01-08 腊八节|01-23 小年|01-30 除夕|01-31 春节|02-01 春节|02-02 春节|02-03 春节|02-04 春节|02-05 春节|02-14 元宵节|04-04 清明节|06-01 端午节|08-01 七夕节|09-08 中秋节|10-01 重阳节",
    "2034": "01-27 腊八节|02-11 小年|02-18 除夕|02-19 春节|02-20 春节|02-21 春节|02-22 春节|02-23 春节|02-24 春节|03-05 元宵节|04-05 清明节|06-20 端午节|08-20 七夕节|09-27 中秋节|10-20 重阳节",
    "2035": "01-16 腊八节|01-31 小年|02-07 除夕|02-08 春节|02-09 春节|02-10 春节|02-11 春节|02-12 春节|02-13 春节|02-22 元宵节|04-05 清明节|06-10 端午节|08-10 七夕节|09-16 中秋节|10-09 重阳节",
    "2036": "01-05 腊八节|01-20 小年|01-27 除夕|01-28 春节|01-29 春节|01-30 春节|01-31 春节|02-01 春节|02-02 春节|02-11 元宵节|04-04 清明节|05-30 端午节|08-28 七夕节|10-04 中秋节|10-27 重阳节",
    "2037": "01-23 腊八节|02-07 小年|02-14 除夕|02-15 春节|02-16 春节|02-17 春节|02-18 春节|02-19 春节|02-20 春节|03-01 元宵节|04-04 清明节|06-18 端午节|08-17 七夕节|09-24 中秋节|10-17 重阳节",
    "2038": "01-12 腊八节|01-27 小年|02-03 除夕|02-04 春节|02-05 春节|02-06 春节|02-07 春节|02-08 春节|02-09 春节|02-18 元宵节|04-05 清明节|06-07 端午节|08-07 七夕节|09-13 中秋节|10-07 重阳节",
    "2039": "01-02 腊八节|01-17 小年|01-23 除夕|01-24 春节|01-25 春节|01-26 春节|01-27 春节|01-28 春节|01-29 春节|02-07 元宵节|04-05 清明节|05-27 端午节|08-26 七夕节|10-02 中秋节|10-26 重阳节",
    "2040": "01-21 腊八节|02-05 小年|02-11 除夕|02-12 春节|02-13 春节|02-14 春节|02-15 春节|02-16 春节|02-17 春节|02-26 元宵节|04-04 清明节|06-14 端午节|08-14 七夕节|09-20 中秋节|10-14 重阳节",
}


# v1.41f：节日专属效果表（键 = 节日显示名，与 _fest_norm 的 name 对应）
# 各字段为机制参数（缺省 = 无该效果）；desc 为弹窗 / 事件日志的展示文案
FEST_EFF = {
    "🎊 元旦":   {"desc": "健康打卡每项额外 +1 活力点", "vit_per_task": 1},
    "💝 情人节": {"desc": "宠物加成翻倍", "pet_mul": 2.0},
    "⚒️ 劳动节": {"desc": "委托经验 +50%", "exp": 0.5},
    "🎈 儿童节": {"desc": "委托耗时 −30%", "dur": -0.3},
    "🎉 国庆":   {"desc": "委托报酬 +20%、成功率 +10%", "pay": 0.2, "rate": 0.1},
    "🎃 万圣夜": {"desc": "材料掉落概率翻倍", "mat_drop_mul": 2.0},
    "🎄 冬幕节": {"desc": "精力上限 +20%", "energy_max_pct": 0.2},
    "🎆 除夕":   {"desc": "压岁钱：上线活力点 +20；守岁：今夜免除熬夜惩罚", "login_vit": 20, "no_sleep_penalty": True},
    "🧧 春节":   {"desc": "红包：委托报酬 +30%、成功率 +10%、上线活力点 +30",
                  "pay": 0.3, "rate": 0.10, "login_vit": 30},
    "🏮 元宵节": {"desc": "赏灯出游：今日探索点 +50%", "explore_gain": 0.5},
    "🌿 清明节": {"desc": "踏青：采集 / 探索类委托成功率 +10%", "rate_types": {"采集": 0.10, "探索": 0.10}},
    "🐉 端午节": {"desc": "粽香满堂：酒馆料理效果 +50%", "cook_mul": 1.5},
    "💫 七夕节": {"desc": "乞巧：材料获取数量 +50%", "mat_qty_pct": 0.5},
    "🌕 中秋节": {"desc": "月华：传奇事件成功率 +10%", "legend": 0.1},
    "🍁 重阳节": {"desc": "登高：今日探索点翻倍", "explore_gain": 1.0},
    "🥣 腊八节": {"desc": "腊八粥：酒馆料理效果翻倍", "cook_mul": 2.0},
    "🧹 小年":   {"desc": "辞旧迎新：每日接取上限 +1", "daily_limit": 1},
}


def _fest_norm(f):
    """节日条目归一化为 {name, greet, text, eff}——兼容元组 / 列表 / 字典（测试与创造模式特例）"""
    if isinstance(f, dict):
        d = dict(f)
        d.setdefault("greet", "节日快乐")
        d.setdefault("text", "")
    elif len(f) >= 3:
        d = {"name": f[0], "greet": f[1], "text": f[2]}
        if len(f) > 3:
            d["eff"] = f[3]
    else:
        d = {"name": f[0], "greet": "节日快乐", "text": f[1]}
    if not d.get("eff"):
        d["eff"] = FEST_EFF.get(d["name"], {})
    return d


def fest_eff_of(f):
    """节日 dict → 专属效果 dict（v1.41f）"""
    return (f or {}).get("eff") or {}


def today_fest_eff(d=None):
    """该游戏日的节日效果 dict（无节日 → {}）——各机制落点统一入口（v1.41f）"""
    return fest_eff_of(festival_of(d))


def festival_of(d=None):
    """该游戏日命中的节日 (名, 问候语, 文案)；无 → None。
       顺序：单日公历表（含测试/模拟特例覆盖）→ 农历节日表（2025~2040）→ 假期区间（国庆等）"""
    full = d if isinstance(d, str) else today_str(d)
    ds = full[5:]
    f = FESTIVALS.get(ds)
    if f:
        return _fest_norm(f)
    row = CN_LUNAR_FEST.get(full[:4], "")
    if row:
        for item in row.split("|"):
            if item[:5] == ds:
                meta = CN_FEST_META.get(item[6:])
                if meta:
                    return _fest_norm(meta)
    for a, b, nm, tx in FESTIVAL_RANGES:
        if a <= ds <= b:
            return _fest_norm((nm, tx))
    return None


def is_festival(d=None):
    return festival_of(d) is not None

COMBO_SHIELD_MIN = 7              # v1.38：连击保险门槛（连续早睡天数）


def _sleep_streak(s):
    """当前连续早睡天数（被「连击保险」/「疗养圣所病假」覆盖的断档日视为保持）"""
    shielded = set(s.get("shield_days") or []) | set(s.get("sick_days") or [])
    n = 0
    for h in reversed(s.get("history") or []):
        if h.get("sleep") or h.get("date") in shielded:
            n += 1
        else:
            break
    return n


def _try_combo_shield(s, msgs, combo_before):
    """v1.38：连击保险——连续早睡 ≥7 天时，断档一天自动消耗保险保住连击（每月 1 次）"""
    if combo_before < COMBO_SHIELD_MIN:
        return False
    d = s["health"]["date"]
    if s.get("shield_month") == d[:7]:             # 本月已用过
        return False
    s["shield_month"] = d[:7]
    days = s.setdefault("shield_days", [])
    days.append(d)
    if len(days) > 60:                             # 防无限膨胀
        del days[:-60]
    msgs.append("🛡️ 连击保险生效！连续早睡 " + str(combo_before) + " 天，昨夜断档已被保护（每月 1 次）")
    add_log(s, "🛡️ 连击保险：连续早睡 " + str(combo_before) + " 天，昨夜断档被保险覆盖，连击保留", "gold")
    return True


SICK_MONTHLY = 3                       # v1.61：疗养圣所·每月病假天数（v1.60 原 医务室·2 天）


def take_sick_leave(s, day, msgs):
    """v1.61：疗养圣所——生病请假（无门槛）：today 请今日 / yesterday 补请昨日。
    病假日 = 封存日：评分锁定 59（calc_health 覆盖）、当天无法打卡（打卡与打卡类道具同封存）；
    覆盖日计入「保护日」：sleep_streak / _sleep_streak 视为保持连击（不抵消熬夜惩罚与其他结算）。"""
    catch_up(s)
    d = s["health"]["date"]
    ym = d[:7]
    used = sum(1 for x in (s.get("sick_days") or []) if x[:7] == ym)
    if used >= SICK_MONTHLY:
        return "本月病假已用完（每月 " + str(SICK_MONTHLY) + " 天）。"
    target = d
    if day == "yesterday":
        target = (parse_date(d) - timedelta(days=1)).strftime("%Y-%m-%d")
        hist = s.get("history") or []
        last = hist[-1] if hist else None
        if not last or last.get("date") != target:
            return "没有找到昨日的结算记录，无法补请。"
        if (s.get("sick_days") or []).count(target):
            return "昨日已请过病假。"
        if target in (s.get("shield_days") or []):
            return "昨日已被连击保险覆盖，无需补请。"
        if last.get("sleep"):
            return "昨日已正常早睡，无需补请。"
        last["score"] = SICK_LOCK_SCORE            # v1.61：补请昨日 → 昨日记录评分改写为 59
    else:
        if (s.get("sick_days") or []).count(target):
            return "今日已请过病假。"
    days = s.setdefault("sick_days", [])
    days.append(target)
    if len(days) > 60:
        del days[:-60]
    calc_health(s)                                  # v1.61：今日病假 → 立即锁定 59
    msgs.append("🕊️ 疗养圣所：已请病假（" + ("今日" if day != "yesterday" else "补请 " + target) + "）——该日评分锁定 " + str(SICK_LOCK_SCORE) + "，断档不计入连续记录")
    add_log(s, "🕊️ 疗养圣所：病假覆盖 " + target + "（评分锁定 " + str(SICK_LOCK_SCORE) + "，本月已用 " + str(used + 1) + "/" + str(SICK_MONTHLY) + "）", "gold")
    return None


def _skip_settle_range(s, t, msgs):
    """v1.39（B1）：超过补算护栏时，跳过区间 [last_day, t) 内跨过的周/月结算补跑。
       幂等：weekly/monthly_settle 内部按已结算键去重；无打卡数据的周月不发奖、无消息。"""
    d = parse_date(s["last_day"])
    end = parse_date(t)
    marks = set()
    dd = d + timedelta(days=(6 - d.weekday()) % 7)     # 区间内首个周日（含 d 当天）
    while dd < end:
        marks.add(dd)
        dd += timedelta(days=7)
    dd = d
    while dd < end:                                    # 区间内每个月末
        nx = dd + timedelta(days=1)
        if nx.month != dd.month:
            marks.add(dd)
            dd = nx.replace(day=1)
        else:
            dd = nx
    for m in sorted(marks):
        ds = m.strftime("%Y-%m-%d")
        if m.weekday() == 6:
            weekly_settle(s, ds, msgs)
        if (m + timedelta(days=1)).month != m.month:
            monthly_settle(s, ds, msgs)


def sign_tick(s, msgs):
    """v1.50：每日签到——每个游戏日首次打开游戏时自动签到（幂等）。
       奖励：每日 +1 活力点；连续 7 / 14 / 30 天（此后每再满 30 天）额外 +3 / +5 / +10。"""
    t = today_str()
    sg = s.setdefault("sign", {"last": "", "streak": 0, "total": 0})
    if sg.get("last") == t:
        return
    yest = (parse_date(t) - timedelta(days=1)).strftime("%Y-%m-%d")
    sg["streak"] = (sg.get("streak", 0) + 1) if sg.get("last") == yest else 1
    sg["total"] = sg.get("total", 0) + 1
    sg["last"] = t
    bonus = 0
    if sg["streak"] == 7:
        bonus = 3
    elif sg["streak"] == 14:
        bonus = 5
    elif sg["streak"] >= 30 and sg["streak"] % 30 == 0:
        bonus = 10                                    # 30 / 60 / 90…天循环
    s["vit"] += 1 + bonus
    if s.get("daily") and s["daily"].get("date") == t:
        s["daily"]["vit"] = s["daily"].get("vit", 0) + 1 + bonus
    msg = "📅 每日签到：活力点 +1（连续 " + str(sg["streak"]) + " 天 · 累计 " + str(sg["total"]) + " 天）"
    if bonus:
        msg += "　🎁 连续 " + str(sg["streak"]) + " 天里程碑：活力点 +" + str(bonus)
    add_log(s, msg, "gold")
    msgs.append(msg)


def catch_up(s, now=None):
    """惰性补算：跨天逐日结算 / 精力恢复 / 刷新点 / 委托完成。
       返回消息列表。护栏：单次最多补 7 天；幂等（重复调用无副作用）。
       日界线为每天早上 6 点：00:00~05:59 熬夜时段仍属前一天，6 点后首次访问才跨天结算。"""
    msgs = []
    now = now or datetime.now()
    t = today_str(now)

    # ① 跨天：逐日结算（护栏：最多 7 天，超过直接对齐）
    guard = 0
    while s["last_day"] != t and guard < MAX_CATCHUP_DAYS:
        guard += 1
        if s["health"]["date"] != s["last_day"]:      # 空白日（当天未打开）
            s["health"] = _blank_health(s["last_day"])
            s["daily"] = _blank_daily(s["last_day"])
        _combo = _sleep_streak(s)                      # v1.38：day_settle 前取（此时 history 尚未含该日）
        day_settle(s, msgs)
        # v1.28：熬夜惩罚提示（豁免道具已在 day_settle 中把 done[0] 置 1，此处读的是最终判定）
        if not s["health"]["done"][0]:
            msgs.append("⚠️ 昨夜未在 23:30 前入睡——今日委托成功率 −15%（装备可减免）")
            _try_combo_shield(s, msgs, _combo)         # v1.38：连击保险（保连击，不抵消熬夜惩罚）
        s["last_day"] = next_day_str(s["last_day"])
        s["health"] = _blank_health(s["last_day"])
        s["daily"] = _blank_daily(s["last_day"])
        s["accepted"] = 0
        s["bonus_today"] = False
        s["bonus_quests"] = None
        s["priv_quest"] = None
        s["priv_today"] = False           # v1.38o：昨日未接的公会特权委托作废
        s["glass_quest"] = None
        s["glass_today"] = False          # v1.38o：昨日未接的时间沙漏委托作废
        s["rumor"] = _rumor_pair(s["last_day"])   # v1.48b：每存档每日随机 2 条传闻（前端按 idx/idx2 取词）
        s["explore"] = max(0, int(prev_health_score(s) // 10))   # v1.58：装备/宠物的「探索点/天」词条已移除——探索点只由健康评分 + 料理/商店/节日产出
        _eg = today_fest_eff(s["last_day"]).get("explore_gain", 0)   # v1.41f：元宵 / 重阳·"今日探索点"加成
        if _eg:
            s["explore"] = int(round(s["explore"] * (1 + _eg)))
            msgs.append("🧭 节日加成：今日探索点 " + ("翻倍！" if _eg >= 1 else "+" + str(int(_eg * 100)) + "%"))
        s["explore_used"] = 0
        msgs.append("—— 新的一天开始（" + s["last_day"] + "）——")
        roll_legend(s, msgs)
    if guard >= MAX_CATCHUP_DAYS and s["last_day"] != t:
        # v1.39（B1）：超过护栏 → 中间日直接跳过（防大量结算刷奖励），但必须：
        # ① health/daily 重建为"今天"（否则停留在补算最后一天，打卡会写进旧日期）；
        # ② 补跑跳过区间跨过的周/月结算（幂等）；③ 今日传说事件照常 roll。
        skip_n = (parse_date(t) - parse_date(s["last_day"])).days
        msgs.append("（超过 " + str(MAX_CATCHUP_DAYS) + " 天未上线：中间 " + str(skip_n)
                    + " 天未逐日结算，已直接对齐到今日）")
        _skip_settle_range(s, t, msgs)
        s["last_day"] = t
        s["health"] = _blank_health(t)
        s["daily"] = _blank_daily(t)
        s["accepted"] = 0
        s["bonus_today"] = False
        s["bonus_quests"] = None
        s["priv_quest"] = None
        s["priv_today"] = False
        s["glass_quest"] = None
        s["glass_today"] = False
        s["rumor"] = _rumor_pair(t)
        s["explore"] = max(0, int(prev_health_score(s) // 10))   # v1.58：装备/宠物的「探索点/天」词条已移除（同前）
        _eg2 = today_fest_eff(s["last_day"]).get("explore_gain", 0)   # v1.41f：元宵 / 重阳·"今日探索点"加成
        if _eg2:
            s["explore"] = int(round(s["explore"] * (1 + _eg2)))
        s["explore_used"] = 0
        roll_legend(s, msgs)

    # ①.35 v1.41 I3：月度世界事件（每月 1 号生成 / 换月自动轮换）——放跨天段之后（当日打卡日已按旧月结算）
    month_event_tick(s, msgs)

    # ①.5 商店限购重置（v1.38m：跨游戏日 / 跨周幂等重置）
    if (s.get("shop_daily") or {}).get("date") != t:
        s["shop_daily"] = {"date": t, "cnt": {}}
    if (s.get("shop_weekly") or {}).get("week") != week_key():
        s["shop_weekly"] = {"week": week_key(), "cnt": {}}

    # ①.6 酒馆传闻补齐（v1.38o：每存档每日随机——跨天段未覆盖时（如老档首日）当日缺失即补生成，幂等）
    if (s.get("rumor") or {}).get("date") != t:
        s["rumor"] = _rumor_pair(t)

    # ② 区间奖励领取
    apply_buff_claim(s, msgs)

    # ③ 精力恢复（每日 08:00）
    if s["energy_restore_date"] != t and now.hour >= 8:
        was = s["energy"]
        s["energy"] = energy_max_now(s)
        s["energy_restore_date"] = t
        pe = s.get("pending_energy")
        if pe and pe.get("date") == t:
            s["energy"] += pe["amount"]
            msgs.append("💧 山泉水生效：精力 +" + str(pe["amount"]))
            s["pending_energy"] = None
        if was < s["energy"]:
            msgs.append("⚡ 精力已恢复至 " + str(s["energy"]))

    # ③.5 节日（v1.38c 基础；v1.41c 假期区间与窗口延长；v1.41d 欢迎弹窗；v1.41f 专属效果）
    fest = festival_of(t)
    if fest and s.get("festival_shown") != t:
        s["festival_shown"] = t
        _fe = fest.get("eff") or {}
        if _fe.get("login_vit"):               # v1.41f：除夕压岁钱 / 春节红包（上线红利）
            s["vit"] += _fe["login_vit"]
            add_log(s, fest["name"] + " 上线红包：活力点 +" + str(_fe["login_vit"]), "gold")
        s["pending_festival"] = {"name": fest["name"], "greet": fest["greet"], "text": fest["text"],
                                 "eff": _fe, "date": t}   # 前端在结算 / 昨日弹窗之后展示（festival_ack 清空）
        add_log(s, fest["name"] + "：" + (_fe.get("desc") or "节日基础机制生效"), "gold")

    # ③.6 纪念日（v1.38：每 30 天 → 活力点 +20）
    try:
        _days = (datetime.strptime(t, "%Y-%m-%d")
                 - datetime.strptime(s.get("created") or t, "%Y-%m-%d")).days
    except ValueError:
        _days = 0
    if _days > 0 and _days % 30 == 0 and s.get("anniv_last") != _days:
        s["anniv_last"] = _days
        s["vit"] += 20
        s["daily"]["vit"] = s["daily"].get("vit", 0) + 20
        msgs.append("🎂 冒险者纪念日：来到这个世界 " + str(_days) + " 天！奖励活力点 +20")
        add_log(s, "🎂 冒险者纪念日：" + str(_days) + " 天，活力点 +20", "gold")

    # ④ 刷新点
    lp = latest_point(now)
    pk = pool_point_key(lp[0], lp[1])
    if s["pool_point"] != pk:
        if s.get("pool") and not s["pool"].get("taken"):
            msgs.append("上一个刷新点的委托已作废")
        born = int(datetime(lp[0].year, lp[0].month, lp[0].day, lp[1], 0, 0).timestamp() * 1000)
        s["pool"] = {"point": pk, "list": draw_pool(s, lp), "taken": False,
                     "bornTs": born, "expiredLogged": False}
        s["pool_point"] = pk
        msgs.append("🔄 " + str(lp[1]).zfill(2) + ":00 刷新，抽 " + str(len(s["pool"]["list"])) + " 选 1（接取窗口 " + _fmt_hours_txt(pool_window_ms(s)) + " 小时）")
        if s["lv_idx"] >= 2 and not s["bonus_today"]:
            first_key = today_str(now) + "@" + str(CFG["refreshHours"][0]).zfill(2)
            if pk == first_key and random.random() < 0.20:
                s["bonus_today"] = True
                bp = mix_pool(s).copy()
                random.shuffle(bp)
                s["bonus_quests"] = (bp[:6] or None)
                if s["bonus_quests"]:
                    msgs.append("📜 触发公会额外委托！今日随机 6 个委托任选 1 个接取（不占每日接取上限）")
        # v1.38o：W 级公会特权委托（每日首次刷新：必出）——「今日接取 x/5」第 5 次名额的委托来源
        if guild_idx(s) >= 7 and not s.get("priv_today"):
            first_key = today_str(now) + "@" + str(CFG["refreshHours"][0]).zfill(2)
            if pk == first_key:
                s["priv_today"] = True
                pp = mix_pool(s)
                if pp:
                    s["priv_quest"] = random.choice(pp)
                    msgs.append("🎖 公会特权委托出现！今日可接取「" + s["priv_quest"][0] + "」（计入每日接取次数）")
        # v1.38o：时间沙漏委托（装备★每日接取上限+1：每日首次刷新必出）——多出接取名额的委托来源
        if gear_effects(s)["dailyLimit"] > 0 and not s.get("glass_today"):
            first_key = today_str(now) + "@" + str(CFG["refreshHours"][0]).zfill(2)
            if pk == first_key:
                s["glass_today"] = True
                gp = mix_pool(s)
                if gp:
                    s["glass_quest"] = random.choice(gp)
                    msgs.append("⏳ 时间沙漏委托出现！今日可接取「" + s["glass_quest"][0] + "」（计入每日接取次数）")

    # ⑤ 委托完成判定
    still = []
    for a in s["active"]:
        if a.get("pending"):
            if now.hour >= 12:
                settle(s, a, msgs)
                msgs.append("⏰ 「" + a["name"] + "」跨天委托已自动结算")
            else:
                still.append(a)
        elif now_ms() >= a["finishTs"]:
            same = (today_str(datetime.fromtimestamp(a["acceptTs"] / 1000))
                    == today_str(datetime.fromtimestamp(a["finishTs"] / 1000)))
            if same:
                settle(s, a, msgs)
            else:
                a["pending"] = True
                msgs.append("⏳ 「" + a["name"] + "」已完成，次日打卡时结算（最迟 12:00 自动结算）")
                still.append(a)
        else:
            still.append(a)
    s["active"] = still

    # ⑤.5 探索完成判定（现实时间探索到点结算）
    explore_finish_check(s, msgs)

    # ⑥ 待获得宠物
    pp = s.get("pending_pet")
    if pp and now_ms() >= pp["ts"]:
        s["pending_pet"] = None
        if pp["name"] not in s["pets"]:
            s["pets"].append(pp["name"])
        if pp["name"] == "小狼" and not s.get("wolf"):     # v1.22：小狼成长链初始化
            s["wolf"] = {"stage": 1, "growth": 0, "mutate": 0, "fedDate": "", "fedCount": 0}
        msgs.append("🐺 你救下的小狼伤好了，正式成为你的伙伴！")

    check_guild_titles(s, msgs)          # v1.40：W/H/P 公会称号（幂等）
    sync_read_pets(s, msgs)              # v1.55：阅读驱动宠物（月光狐）——阅读次数达标自动进化（幂等；对齐前端 syncReadPets）
    s.setdefault("pet_walk", None); s.setdefault("pet_nick", {}); s.setdefault("walk_count", 0); s.setdefault("pet_night_date", "")   # v1.56：老档字段迁移
    pet_daily_checks(s, msgs, guard > 0)   # v1.56：散步结算 / 羁绊里程碑 / 小剧场 / 深夜提醒
    sign_tick(s, msgs)                   # v1.50：每日签到（游戏日首次打开自动签到，幂等）
    s["last_tick"] = now_ms()
    return msgs


# ══════════════ 动作 ══════════════


def take_name(s, name):
    name = (name or "").strip()
    if not name:
        return "请输入冒险者之名。"
    s["name"] = name[:12]
    add_log(s, "🧙 冒险者「" + s["name"] + "」开始了一天的旅程", "gold")
    return None


def toggle_task(s, i, msgs, now=None):
    try:
        i = int(i)
    except (TypeError, ValueError):
        return "无效的打卡项。"
    if not (0 <= i < len(CFG["tasks"])):          # v1.50：索引边界校验（原负索引可绕窗口）
        return "无效的打卡项。"
    if sick_today(s):                              # v1.61：病假封存——本日无法打卡
        return SICK_LOCK_MSG
    h = s["health"]["done"]
    if _midnight_lock(i, now):                     # v1.50：00:00 后锁定补打卡（无窗口项）
        return MIDNIGHT_LOCK_MSG
    # v1.32：时间窗——窗口外禁止修改任何打卡状态（防误触：原来窗口外可取消，误触后无法恢复）
    if not in_task_window(i, now):
        return "「" + CFG["tasks"][i][0] + "」不在打卡时段（" + _win_str(task_window_of(i, now)) + "），窗口外不可修改打卡。"
    h[i] = 0 if h[i] else 1
    _fvt = today_fest_eff().get("vit_per_task", 0)   # v1.41f：元旦·健康打卡每项 +3 活力点
    if h[i] and _fvt:
        _vo = s["health"].setdefault("vitOnce", [0] * 10)
        if not _vo[i]:                             # v1.50：每项每日仅首次打卡发放（取消再点不重复）
            _vo[i] = 1
            s["vit"] += _fvt
    if i == 0 and h[0]:
        s["exempt"]["charmNight"] = {"date": s["health"]["date"], "slot": s["equipped"].get("charmSlot")}   # v1.41 G6：入睡打卡佩戴快照
    if i == 4 and h[i] and guild_idx(s) >= 2 and not s.get("train_energy"):
        s["train_energy"] = 15
        msgs.append("🏋️ 训练场生效（公会 D）：坚持运动 → 永久精力上限 +15")
    calc_health(s)
    return None


def toggle_meal(s, idx, msgs, now=None):
    """三餐打卡（v1.28）：早/午/晚各一个按钮，三项全点才得「完整吃三餐」15 分（全有全无）"""
    idx = int(idx)
    if idx < 0 or idx > 2:
        return "无效的餐次。"
    if sick_today(s):                              # v1.61：病假封存——本日无法打卡
        return SICK_LOCK_MSG
    h = s["health"]
    meals = h.setdefault("meals", [0, 0, 0])
    # v1.32：窗口外禁止修改任何打卡状态（防误触：原来窗口外可取消，误触后无法恢复）
    w = meal_window_of(idx, now)          # v1.41c：节日前后各 +30 分钟
    if not _in_win(w, now):
        return "「" + MEAL_NAMES[idx] + "」不在打卡时段（" + _win_str(w) + "），窗口外不可修改打卡。"
    meals[idx] = 0 if meals[idx] else 1
    _fvt2 = today_fest_eff().get("vit_per_task", 0)   # v1.41f：元旦·打卡活力点（三餐同享）
    if meals[idx] and _fvt2:
        _vo = s["health"].setdefault("vitOnce", [0] * 10)
        if not _vo[7 + idx]:                       # v1.50：每餐每日仅首次打卡发放（取消再点不重复）
            _vo[7 + idx] = 1
            s["vit"] += _fvt2
    h["done"][5] = 1 if all(meals) else 0     # 「完整吃三餐」= 早午晚三项全点
    calc_health(s)
    return None


def add_multi(s, i, delta, msgs, now=None):
    try:
        i = int(i)
    except (TypeError, ValueError):
        return "无效的多次任务项。"
    if not (0 <= i < len(CFG["multiTasks"])):      # v1.50：索引边界校验
        return "无效的多次任务项。"
    if sick_today(s):                              # v1.61：病假封存——本日无法打卡
        return SICK_LOCK_MSG
    if _min_of_day(now) < DAY_CUTOFF_HOUR * 60:    # v1.50：00:00 后锁定补打卡
        return MIDNIGHT_LOCK_MSG
    try:
        d = int(delta)
    except (TypeError, ValueError):
        d = 1
    d = max(-9, min(9, d))                         # v1.50：增量钳位
    t = CFG["multiTasks"][i]
    s["health"]["multi"][i] = max(0, min(t[2], s["health"]["multi"][i] + d))
    if i == 1 and int(delta) > 0 and guild_idx(s) >= 3:
        s["lib_date"] = today_str()
    calc_health(s)
    return None


def _prep_check(s, q, msgs):
    """v1.46：任务门槛——接取消耗准备物；v1.53：数量随委托等级 1~3；返回错误文案（None = 通过）"""
    _p = QUEST_ITEM.get(q[0])
    if not _p:
        return None
    _pn = quest_item_need(q)
    if s["items"].get(_p, 0) < _pn:
        return ("接取「" + q[0] + "」需要准备物：" + _p + " ×" + str(_pn) + "（当前 "
                + str(s["items"].get(_p, 0)) + "）。可在商店购买，或在背包炼金台用材料合成。")
    s["items"][_p] -= _pn
    if s["items"][_p] <= 0:
        del s["items"][_p]
    msgs.append("🧪 消耗「" + _p + "」×" + str(_pn) + "（「" + q[0] + "」的准备物）")
    return None


def accept_quest(s, idx, msgs, name=None, point=None):
    catch_up(s)
    try:
        idx = int(idx)
    except (TypeError, ValueError):
        return "该委托不存在。"
    p = s.get("pool")
    if not p or not (0 <= idx < len(p["list"])):      # v1.50：索引边界校验（原负索引可绕锁）
        return "该委托不存在。"
    if point and p.get("point") != point:             # v1.50：池身份校验（防跨刷新点接错委托）
        return "委托栏已刷新——请重新查看后再接取。"
    q = p["list"][idx]
    if name and q[0] != name:                         # v1.50：所见即所接（前端传名字核对）
        return "委托栏已刷新——请重新查看后再接取。"
    if p["taken"]:
        return "本次刷新已接取过了。"
    if pool_expired(s):
        return "本批委托已失效（接取窗口为刷新后 " + _fmt_hours_txt(pool_window_ms(s)) + " 小时内）。"
    if s["accepted"] >= daily_limit_now(s):
        return "今日接取已达上限（" + str(daily_limit_now(s)) + " 个）。"
    if active_normal_count(s) >= sim_cap_now(s):
        return "同时进行的委托已达上限 " + str(sim_cap_now(s)) + " 个。"
    en_cost = max(1, int(round(q[7] * (1 - gear_en_cut_for(s, q[1])))))
    if s["energy"] < en_cost:
        return "精力不足：需要 " + str(en_cost) + "，当前 " + str(s["energy"]) + "。"
    _perr = _prep_check(s, q, msgs)          # v1.46：任务门槛（准备物）
    if _perr:
        return _perr
    s["energy"] -= en_cost
    s["accepted"] += 1
    p["taken"] = True
    rate = success_rate(s, q)
    _dur = int(round(q[3] * (1 + today_fest_eff().get("dur", 0))))   # v1.41f：儿童节·委托耗时 −30%
    s["active"].append({"q": q, "rate": rate, "qlv": lv_num(s), "meal": active_meal(s), "dur": _dur,
                        "acceptTs": now_ms(), "finishTs": now_ms() + _dur * 60 * 1000, "name": q[0]})
    msgs.append("📥 接取「" + q[0] + "」耗时 " + fmt_dur(q[3]) + "，成功率 " + str(round(rate * 100)) + "%")
    return None


def accept_bonus(s, idx, msgs):
    """v1.38p：公会额外委托接取（独立槽位 · 随机 6 个任选 1 个）——任意时段可接 · 不占每日接取上限"""
    catch_up(s)
    lst = s.get("bonus_quests") or []
    try:
        idx = int(idx)
    except (TypeError, ValueError):
        idx = 0
    if not (0 <= idx < len(lst)):
        return "当前没有公会额外委托。"
    q = lst[idx]
    en_cost = max(1, int(round(q[7] * (1 - gear_en_cut_for(s, q[1])))))
    if s["energy"] < en_cost:
        return "精力不足：需要 " + str(en_cost) + "，当前 " + str(s["energy"]) + "。"
    _perr = _prep_check(s, q, msgs)          # v1.46：任务门槛（准备物）
    if _perr:
        return _perr
    s["energy"] -= en_cost
    rate = success_rate(s, q)
    _dur = int(round(q[3] * (1 + today_fest_eff().get("dur", 0))))   # v1.41f：儿童节·委托耗时 −30%
    s["active"].append({"q": q, "rate": rate, "qlv": lv_num(s), "meal": active_meal(s), "dur": _dur,
                        "acceptTs": now_ms(), "finishTs": now_ms() + _dur * 60 * 1000, "name": q[0]})
    s["bonus_quests"] = None
    msgs.append("📜 接取公会额外委托「" + q[0] + "」，成功率 " + str(round(rate * 100)) + "%")
    return None


def accept_priv(s, msgs):
    """v1.38o：公会特权委托接取（W 级 · 第 5 次名额）——计入每日接取次数 · 占同时进行上限"""
    catch_up(s)
    q = s.get("priv_quest")
    if not q:
        return "当前没有公会特权委托。"
    limit = daily_limit_now(s)
    if s["accepted"] >= limit:
        return "今日接取已达上限（" + str(limit) + " 个）。"
    cap = sim_cap_now(s)
    if active_normal_count(s) >= cap:
        return "同时进行的委托已达上限 " + str(cap) + " 个。"
    en_cost = max(1, int(round(q[7] * (1 - gear_en_cut_for(s, q[1])))))
    if s["energy"] < en_cost:
        return "精力不足：需要 " + str(en_cost) + "，当前 " + str(s["energy"]) + "。"
    _perr = _prep_check(s, q, msgs)          # v1.46：任务门槛（准备物）
    if _perr:
        return _perr
    s["energy"] -= en_cost
    s["accepted"] += 1
    rate = success_rate(s, q)
    _dur = int(round(q[3] * (1 + today_fest_eff().get("dur", 0))))   # v1.41f：儿童节·委托耗时 −30%
    s["active"].append({"q": q, "rate": rate, "qlv": lv_num(s), "meal": active_meal(s), "dur": _dur,
                        "acceptTs": now_ms(), "finishTs": now_ms() + _dur * 60 * 1000, "name": q[0]})
    s["priv_quest"] = None
    msgs.append("🎖 接取公会特权委托「" + q[0] + "」，成功率 " + str(round(rate * 100)) + "%")
    return None


def accept_glass(s, msgs):
    """v1.38o：时间沙漏委托接取（装备★每日接取上限+1）——计入每日接取次数 · 占同时进行上限"""
    catch_up(s)
    q = s.get("glass_quest")
    if not q:
        return "当前没有时间沙漏委托。"
    limit = daily_limit_now(s)
    if s["accepted"] >= limit:
        return "今日接取已达上限（" + str(limit) + " 个）。"
    cap = sim_cap_now(s)
    if active_normal_count(s) >= cap:
        return "同时进行的委托已达上限 " + str(cap) + " 个。"
    en_cost = max(1, int(round(q[7] * (1 - gear_en_cut_for(s, q[1])))))
    if s["energy"] < en_cost:
        return "精力不足：需要 " + str(en_cost) + "，当前 " + str(s["energy"]) + "。"
    _perr = _prep_check(s, q, msgs)          # v1.46：任务门槛（准备物）
    if _perr:
        return _perr
    s["energy"] -= en_cost
    s["accepted"] += 1
    rate = success_rate(s, q)
    _dur = int(round(q[3] * (1 + today_fest_eff().get("dur", 0))))   # v1.41f：儿童节·委托耗时 −30%
    s["active"].append({"q": q, "rate": rate, "qlv": lv_num(s), "meal": active_meal(s), "dur": _dur,
                        "acceptTs": now_ms(), "finishTs": now_ms() + _dur * 60 * 1000, "name": q[0]})
    s["glass_quest"] = None
    msgs.append("⏳ 接取时间沙漏委托「" + q[0] + "」，成功率 " + str(round(rate * 100)) + "%")
    return None


def abandon_quest(s, i, name=None):
    i = int(i)
    if name and (i < 0 or i >= len(s["active"]) or s["active"][i]["name"] != name):
        i = next((k for k, a in enumerate(s["active"]) if a["name"] == name), -1)
    if i < 0 or i >= len(s["active"]):
        return "委托不存在。"
    name = s["active"][i]["name"]
    del s["active"][i]
    add_log(s, "🗑 放弃委托「" + name + "」（不返还次数与精力）", "bad")
    return None


def use_gale(s, i, msgs):
    i = int(i)
    if i < 0 or i >= len(s["active"]):
        return "委托不存在。"
    if not s["items"].get("疾风符咒"):
        return "没有疾风符咒。"
    s["items"]["疾风符咒"] -= 1
    if s["items"]["疾风符咒"] <= 0:
        del s["items"]["疾风符咒"]
    a = s["active"][i]
    add_log(s, "💨 使用疾风符咒 → 立即完成「" + a["name"] + "」", "gold")
    settle(s, a, msgs)
    del s["active"][i]
    return None


def use_item(s, name, msgs):
    if not s["items"].get(name):
        return "没有该道具。"
    if name in ("安眠护符", "清醒符咒", "活力药水") and sick_today(s):   # v1.61：病假封存——打卡类道具不可用
        return "今日病假已封存——评分锁定 " + str(SICK_LOCK_SCORE) + "，打卡类道具无法使用。"
    if name == "清醒符咒":
        if _min_of_day() < DAY_CUTOFF_HOUR * 60:   # v1.50：00:00 后锁定补打卡（道具同规则）
            return MIDNIGHT_LOCK_MSG
        if s["health"]["done"][1]:
            return "今天已经打过「7:40 前起床」的卡了。"
        s["health"]["done"][1] = 1
        s["items"][name] -= 1
        if s["items"][name] <= 0:
            del s["items"][name]
        calc_health(s)
        msgs.append("🪄 使用清醒符咒 → 「7:40 前起床」视为达成")
        return None
    if name == "安眠护符":
        if _min_of_day() < DAY_CUTOFF_HOUR * 60:   # v1.50：00:00 后锁定补打卡（道具同规则）
            return MIDNIGHT_LOCK_MSG
        if s["health"]["done"][0]:
            return "今天已经打过「23:30 前入睡」的卡了。"
        s["health"]["done"][0] = 1
        s["items"][name] -= 1
        if s["items"][name] <= 0:
            del s["items"][name]
        calc_health(s)
        msgs.append("🪄 使用安眠护符 → 「23:30 前入睡」视为达成")
        return None
    if name == "活力药水":
        if _min_of_day() < DAY_CUTOFF_HOUR * 60:   # v1.50：00:00 后锁定补打卡（道具同规则）
            return MIDNIGHT_LOCK_MSG
        s["health"]["done"] = [1] * 7
        s["health"]["meals"] = [1, 1, 1]           # v1.50：三餐一并补上（原缺失——界面「0/3」与 100 分矛盾）
        s["health"]["multi"] = [4, 2]
        calc_health(s)
        s["health"]["score"] = 100
        s["items"][name] -= 1
        if s["items"][name] <= 0:
            del s["items"][name]
        msgs.append("🧪 使用活力药水 → 当日健康评分锁定为 100")
        return None
    if name == "命运骰子":
        err = reroll_pool_now(s)                       # v1.41 H2：重抽逻辑抽为公共函数（重掷券共用）
        if err:
            return err
        s["items"][name] -= 1
        if s["items"][name] <= 0:
            del s["items"][name]
        msgs.append("🎲 命运骰子掷出——当前委托栏已重新刷新")
        return None
    if name == "时之怀表":
        p = s.get("pool")
        if not p or not p["list"]:
            return "当前没有可用的委托栏。"
        if p["taken"]:
            return "本次刷新已经接取过委托了，无需重置窗口。"
        p["bornTs"] = now_ms()
        p["expiredLogged"] = False
        s["items"][name] -= 1
        if s["items"][name] <= 0:
            del s["items"][name]
        msgs.append("⌛ 使用时之怀表 → 本批委托接取窗口重置为 " + _fmt_hours_txt(pool_window_ms(s)) + " 小时")
        return None
    if name == "幸运币":
        s["rare_next_rate"] = max(s.get("rare_next_rate", 0), 0.05)
        s["items"][name] -= 1
        if s["items"][name] <= 0:
            del s["items"][name]
        msgs.append("🍀 使用幸运币 → 下一次委托成功率 +5%")
        return None
    # ── v1.32 新增四道具 ──
    if name == "专注药剂":
        s["rare_next_rate"] = max(s.get("rare_next_rate", 0), 0.03)
        s["items"][name] -= 1
        if s["items"][name] <= 0:
            del s["items"][name]
        msgs.append("🎯 使用专注药剂 → 下一次委托成功率 +3%")
        return None
    if name == "谈判卷轴":
        s["rare_next_pay"] = max(s.get("rare_next_pay", 0), 0.15)
        s["items"][name] -= 1
        if s["items"][name] <= 0:
            del s["items"][name]
        msgs.append("📜 使用谈判卷轴 → 下一次委托报酬 +15%")
        return None
    if name == "旅行干粮":
        before = s["energy"]
        s["energy"] = min(energy_max_now(s), s["energy"] + 30)   # v1.38m：25 → 30
        s["items"][name] -= 1
        if s["items"][name] <= 0:
            del s["items"][name]
        msgs.append("🍞 使用旅行干粮 → 精力 " + str(before) + " → " + str(s["energy"]))
        return None
    if name == "神秘地图":
        s["explore"] += 2                                        # v1.38m：4 → 2
        s["items"][name] -= 1
        if s["items"][name] <= 0:
            del s["items"][name]
        msgs.append("🗺️ 使用神秘地图 → 探索点 +2")
        return None
    if name == "疾风符咒":
        return "请选择要立即完成的委托（use_gale）。"
    return "该道具暂时无法使用。"


def in_region_time(t):
    """区域开放时间判定（"08:00-18:00"）"""
    now = datetime.now()
    cur = now.hour * 60 + now.minute
    try:
        a, b = str(t).split("-")
        ah = int(a.split(":")[0]) * 60 + int(a.split(":")[1])
        bh = int(b.split(":")[0]) * 60 + int(b.split(":")[1])
        return ah <= cur <= bh
    except (ValueError, IndexError):
        return True


PET_EVENT_POOL = [                                # v1.35：宠物奇遇（未拥有时进入事件池）
    ("毛球来访", "绒球兽"),
    ("黏糊糊的果冻", "史莱姆"),
    ("捣蛋小鬼", "捣蛋鬼"),
]


def pet_event_pool(s):
    out = []
    pp = s.get("pending_pet")
    for ev, pet in PET_EVENT_POOL:
        if pet in s["pets"]:
            continue
        if pp and pp.get("name") == pet:
            continue
        out.append(ev)
    return out


def explore_event_available(s, name):
    """区域事件是否仍可触发（一次性事件完成后不再出现）"""
    if name == "受伤小狼":
        return not (s.get("wolf_done") or s.get("pending_pet") or "小狼" in s["pets"])
    if name == "古代石碑":
        return not s["blueprints"].get("安神吊坠")
    if name == "裂痕回响":
        return s.get("echo", 0) < 3
    return True


def ev_log(s, msg):
    """探索事件记录（对齐原型 evLog）"""
    add_log(s, "🧭 探索事件：" + msg, "gold")
    if s.get("daily"):
        s["daily"]["events"].append("🧭 探索事件：" + msg)


def region_gate(s, r):
    """v1.41 I1/I2：区域进入门槛（委托解锁 / 公会等级 / 等级）——返回 None 可进，否则为原因文案"""
    if r.get("unlock") and not (s.get("done_quests") or {}).get(r["unlock"]["quest"], 0) > 0:
        return "需完成委托「" + r["unlock"]["quest"] + "」"
    if r.get("g") is not None and guild_idx(s) < r["g"]:
        return "需公会 " + CFG["guildName"][r["g"]] + " 级"
    if r.get("lv") and s["lv_idx"] < r["lv"] - 1:
        return "等级不足（Lv" + str(r["lv"]) + " 开放）"
    return None


def _lv2_done(s):
    """v1.60：累计完成 12 次 Lv2 委托（自由探索解锁条件；按委托名统计，旧档可追溯）"""
    dq = s.get("done_quests") or {}
    return sum(dq.get(q[0], 0) for q in C.get("Lv2", []))


EXPLORE_LV2_NEED = 12


def do_explore(s, i, msgs):
    catch_up(s)
    i = int(i)
    r = REGIONS[i]
    if s["lv_idx"] < 1:
        return "自由探索需要达到 Lv2 后解锁。"
    if _lv2_done(s) < EXPLORE_LV2_NEED:
        return "自由探索需要完成 " + str(EXPLORE_LV2_NEED) + " 次 Lv2 委托后解锁（当前 " + str(_lv2_done(s)) + "/" + str(EXPLORE_LV2_NEED) + "）。"
    if s.get("explore_active"):
        return "已经有一次探索正在进行中——先等它完成，或中途返回（不会有任何收获）。"
    gate = region_gate(s, r)      # v1.41 I1/I2：委托解锁 / 公会等级 / 等级
    if gate:
        return "「" + r["n"] + "」尚未开放。" + gate + "。"
    if prev_health_score(s) < 60:
        return "前一日健康评分低于 60，今天不能探索。"
    if s["explore_used"] >= 2:
        return "今天已经探索 2 次了，明天再来。"
    if s["explore"] < r["c"]:
        return "探索点不足（需要 " + str(r["c"]) + "，当前 " + str(s["explore"]) + "）。"
    if not in_region_time(r["t"]):
        return "「" + r["n"] + "」不在开放时间内（" + r["t"] + "）。"
    # 出发：占探索点与次数，进入现实时间探索（2~12 小时，到点后结算）
    s["explore"] -= r["c"]
    s["explore_used"] += 1
    hh = r.get("h", 2)
    s["explore_active"] = {"idx": i, "n": r["n"], "c": r["c"], "h": hh,
                           "startTs": now_ms(), "finishTs": now_ms() + hh * 3600000}
    add_log(s, "🧭 开始探索「" + r["n"] + "」（-" + str(r["c"]) + "点，需 " + str(hh) + " 小时）", "")
    msgs.append("🧭 开始探索「" + r["n"] + "」——约需 " + str(hh) + " 小时（中途返回将没有任何收获）")
    return None


def explore_finish_check(s, msgs):
    """探索完成判定：到点后结算掉落与事件（幂等——结算即清空 explore_active）"""
    ea = s.get("explore_active")
    if not ea:
        return
    if now_ms() < ea["finishTs"]:
        return
    s["explore_active"] = None
    month_event_add(s, msgs, "explore")   # v1.41 I3：月度世界事件·探索进度
    # v1.50：按区域名查找（表序变动不再错位）；旧档无 name 时回退下标
    r = next((x for x in REGIONS if x["n"] == ea.get("n")), None)
    if r is None:
        try:
            r = REGIONS[int(ea.get("idx", 0))]
        except (TypeError, ValueError, IndexError):
            msgs.append("🧭 探索记录已失效（区域数据变动），本次探索无法结算。")
            return
    gains = []
    for pair in r["d"]:
        name = pair[0]
        if not name:
            continue
        if random.random() * 100 >= pair[1]:
            continue
        if name == "旧宝箱":
            s.setdefault("seen_items", [])
            if "旧宝箱" not in s["seen_items"]:
                s["seen_items"].append("旧宝箱")     # v1.38s：探索详情保密·开出过即展示
            sub = random.random()
            if sub < 0.4:
                c = 20 + random.randint(0, 30)
                s["money"] += c
                gains.append("铜币 " + str(c))
            elif sub < 0.7:
                mm = random_mat(s, "普通")
                s["mats"][mm] = s["mats"].get(mm, 0) + 3
                gains.append("旧宝箱开出 " + mm + " ×3")
            elif sub < 0.9:
                mm = random_mat(s, "精良")
                s["mats"][mm] = s["mats"].get(mm, 0) + 2
                gains.append("旧宝箱开出 " + mm + " ×2")
            else:                                 # 10%：随机普通~精良装备 ×1（尚未拥有；全拥有则空箱）
                eqd = [s["equipped"].get(k) for k in ("weapon", "armor", "accessory", "charmSlot")]
                pool = [g for g in GEAR if g[1] in ("普通", "精良")
                        and g[0] not in s["gear"] and g[0] not in eqd]
                if pool:
                    g = random.choice(pool)
                    s["gear"].append(g[0])
                    gains.append("旧宝箱开出 装备「" + g[0] + "」")
                else:
                    gains.append("旧宝箱（空的）")
        elif name in ITEM_DESC:
            s["items"][name] = s["items"].get(name, 0) + 1
            gains.append("规则道具「" + name + "」×1")
        else:
            n = 1 + random.randint(0, 2)
            s["mats"][name] = s["mats"].get(name, 0) + n
            gains.append(name + " ×" + str(n))
    msg = "获得：" + "、".join(gains) if gains else "空手而归……什么都没找到。"
    add_log(s, "🧭 探索「" + r["n"] + "」完成 → " + msg, "gold" if gains else "")
    s["explore_result"] = {"region": r["n"], "msg": msg}
    # 探索事件判定（20% 触发；区域事件 / 盗贼伏击 70/30）——结果交给前端展示/选择
    s["pending_event"] = roll_explore_event(s, r)
    # 稀有事件（探索模式）
    try_rare_event(s, "", "", msgs, explore_mode=True)
    msgs.append("🧭 探索完成：「" + r["n"] + "」")


def explore_return(s, msgs):
    """中途返回退出探索：不获得任何材料掉落（探索点与次数不退还）"""
    ea = s.get("explore_active")
    if not ea:
        return "当前没有进行中的探索。"
    s["explore_active"] = None
    add_log(s, "🚶 放弃了「" + ea["n"] + "」的探索——没有任何收获", "")
    msgs.append("🚶 已返回：放弃探索「" + ea["n"] + "」，没有任何掉落。")
    return None


def roll_explore_event(s, r):
    """探索事件判定（对齐原型）：
       - 20% 触发；区域事件与「盗贼伏击」按 70 / 30 抽取；区域事件不可用时只出盗贼
       - 非交互事件当场结算并返回展示结构；交互事件（迷路商人 / 受伤小狼）等待玩家选择"""
    if random.random() >= EXPLORE_EVENT_CHANCE:
        return None
    bound = REGION_EVENTS.get(r["n"])
    pe = pet_event_pool(s)                       # v1.35：宠物奇遇（25% 事件位）
    if pe and random.random() < 0.25:
        ev = random.choice(pe)
    elif not bound or not explore_event_available(s, bound):
        ev = "盗贼伏击"
    else:
        ev = "盗贼伏击" if random.random() < 0.30 else bound

    if ev == "迷路商人":
        return {"name": "迷路商人", "title": "🧭 迷路商人",
                "text": "林间小路上，你遇到一位迷路的商人。他翻了翻货箱：<br><br>「这张清醒符咒 10 铜币卖你，就当带个路。」",
                "options": [{"label": "花 10 铜购买", "accept": 1, "pri": 1},
                            {"label": "不买", "accept": 0}]}
    if ev == "受伤小狼":
        return {"name": "受伤小狼", "title": "🐺 受伤小狼",
                "text": "山丘背风处，一只后腿受伤的小狼正瑟缩着看你。它没有逃走，只是低低地呜咽……<br><br>要帮它包扎吗？",
                "options": [{"label": "救治它", "accept": 1, "pri": 1},
                            {"label": "悄悄离开", "accept": 0}]}
    if ev == "毛球来访":                          # v1.35：宠物奇遇
        return {"name": "毛球来访", "title": "🐹 毛球来访",
                "text": "林间空地，一颗圆滚滚的「毛球」滚到你脚边，眨巴着黑豆似的眼睛——是一只绒球兽。它蹭了蹭你的靴子，看起来饿坏了。",
                "options": [{"label": "收留它", "accept": 1, "pri": 1},
                            {"label": "放它回林间", "accept": 0}]}
    if ev == "黏糊糊的果冻":
        return {"name": "黏糊糊的果冻", "title": "🟢 黏糊糊的果冻",
                "text": "你的靴子上粘了一团果冻状的东西——一只史莱姆。它「啵」地弹了一下，似乎在打招呼，又像想跟你走。",
                "options": [{"label": "带着它", "accept": 1, "pri": 1},
                            {"label": "掰下来扔掉", "accept": 0}]}
    if ev == "捣蛋小鬼":
        return {"name": "捣蛋小鬼", "title": "👻 捣蛋小鬼",
                "text": "干粮袋破了！你循着碎屑追过去——一只小鬼正冲着你的方向做鬼脸。被抓个正着后，它愣住了，可怜巴巴地举起了你的干粮。",
                "options": [{"label": "算了，留下你吧", "accept": 1, "pri": 1},
                            {"label": "追回干粮教训它", "accept": 0}]}
    if ev == "盗贼伏击":
        s["energy"] = max(0, s["energy"] - 10)
        if rand(100) <= 60:
            ev_log(s, "盗贼伏击 → 击退盗贼（消耗 10 精力）")
            text = "回程路上，几名盗贼从岩石后窜出！<br><br>你消耗 <b>10 精力</b> 与他们周旋……<b>成功击退了他们。</b>"
        else:
            loss = min(int(s["money"] * 0.10), EV_ROB_CAP)   # v1.61c：抢夺上限 1 铂金币
            s["money"] -= loss
            ev_log(s, "盗贼伏击 → 被抢走 " + fmt_money(loss) + "（当前钱币的 10%，上限 1 铂金币，消耗 10 精力）")
            text = "回程路上，几名盗贼从岩石后窜出！<br><br>你消耗 <b>10 精力</b> 与他们周旋，却寡不敌众——<br><b>损失当前钱币的 10%（上限 1 铂金币，实损 " + fmt_money(loss) + "）。</b>"
        return {"name": ev, "title": "🗡 盗贼伏击", "text": text,
                "options": [{"label": "确定", "accept": 1, "pri": 1}]}
    if ev == "隐藏泉眼":
        s["pending_energy"] = {"date": next_day_str(today_str()), "amount": 10}
        ev_log(s, "隐藏泉眼 → 获得山泉水，明日精力 +10")
        return {"name": ev, "title": "💧 隐藏泉眼",
                "text": "溪谷深处传来水声——你拨开藤蔓，发现一处隐蔽的泉眼。<br><br>你喝下清冽的山泉水，疲惫一扫而空。<br><b>明日精力恢复时额外 +10。</b>",
                "options": [{"label": "确定", "accept": 1, "pri": 1}]}
    if ev == "古代石碑":
        if rand(100) <= 60:
            s["blueprints"]["安神吊坠"] = True
            ev_log(s, "古代石碑 → 解谜成功，获得图纸「安神吊坠」")
            text = "洞窟深处立着一块刻满古老文字的石碑。<br><br>你借着月光逐字推演——谜题解开了！<br><br>石碑底座弹开一个暗格：<b>图纸「安神吊坠」</b>"
        else:
            ev_log(s, "古代石碑 → 碑文晦涩难懂，未能解开")
            text = "洞窟深处立着一块刻满古老文字的石碑。<br><br>你推演了许久……<b>碑文晦涩难懂，什么都没得到。</b>"
        return {"name": ev, "title": "🗿 古代石碑", "text": text,
                "options": [{"label": "确定", "accept": 1, "pri": 1}]}
    if ev == "净化成功":
        s["rep"] += 20
        ev_log(s, "净化成功 → 声望 +20")
        return {"name": ev, "title": "🌿 净化成功",
                "text": "你在腐化森林深处发现一株被暗影侵蚀的古树。<br><br>你清除了缠绕它的腐化——古树抖落一片叶子落在你手心。<br><b>声望 +20</b>",
                "options": [{"label": "确定", "accept": 1, "pri": 1}]}
    if ev == "裂痕回响":
        s["echo"] = min(3, s.get("echo", 0) + 1)
        ev_log(s, "裂痕回响 → 稀有事件概率永久 +1%（当前 +" + str(s["echo"]) + "%）")
        return {"name": ev, "title": "🌌 裂痕回响",
                "text": "虚空裂痕深处传来一阵回响，仿佛有什么在回应你……<br><br><b>稀有事件概率永久 +1%</b>（当前 +" + str(s["echo"]) + "%，最多 3%）",
                "options": [{"label": "确定", "accept": 1, "pri": 1}]}
    return None


def explore_choice(s, accept, msgs):
    """探索事件交互选择（迷路商人 / 受伤小狼）；非交互事件 accept 仅为确认关闭"""
    pe = s.get("pending_event")
    if not pe:
        return "没有待处理的探索事件。"
    name = pe.get("name")
    if name == "迷路商人":
        if accept:
            if s["money"] < 10:
                s["event_result"] = {"title": "迷路商人",
                                     "text": "铜币不足（需要 10，当前 " + fmt_money(s["money"]) + "）。"}
            else:
                s["money"] -= 10
                s["items"]["清醒符咒"] = s["items"].get("清醒符咒", 0) + 1
                ev_log(s, "迷路商人 → 花 10 铜买到 清醒符咒 ×1")
                s["event_result"] = {"title": "交易完成", "text": "获得「清醒符咒」×1"}
    elif name == "受伤小狼":
        if accept:
            s["wolf_done"] = True
            s["pending_pet"] = {"name": "小狼", "ts": now_ms() + 3 * 86400000}
            ev_log(s, "受伤小狼 → 选择救治，3 天后它会成为伙伴")
            s["event_result"] = {"title": "受伤小狼",
                                 "text": "你包扎了小狼的伤口，把口粮分给它。<br><br>它远远地跟着你——<b>3 天后</b>会成为你的伙伴。"}
        else:
            ev_log(s, "受伤小狼 → 你悄悄离开了")
    elif name == "毛球来访":                      # v1.35：宠物奇遇
        if accept:
            grant_pet(s, "绒球兽")
            ev_log(s, "毛球来访 → 绒球兽加入了你的队伍")
            s["event_result"] = {"title": "新伙伴",
                                 "text": "你把口粮分给它。它开心地打了个滚——<br><br><b>绒球兽</b>成为了你的伙伴！<br>到「冒险背包 · 宠物」可以喂食培养它。"}
        else:
            ev_log(s, "毛球来访 → 你放它回了林间")
    elif name == "黏糊糊的果冻":
        if accept:
            grant_pet(s, "史莱姆")
            ev_log(s, "黏糊糊的果冻 → 史莱姆加入了你的队伍")
            s["event_result"] = {"title": "新伙伴",
                                 "text": "史莱姆高兴地在你背包上安了家——<br><br><b>史莱姆</b>成为了你的伙伴！"}
        else:
            ev_log(s, "黏糊糊的果冻 → 你把它留在了原地")
    elif name == "捣蛋小鬼":
        if accept:
            grant_pet(s, "捣蛋鬼")
            ev_log(s, "捣蛋小鬼 → 捣蛋鬼加入了你的队伍")
            s["event_result"] = {"title": "新伙伴",
                                 "text": "小鬼把干粮还给你，然后理直气壮地住进了你的背包——<br><br><b>捣蛋鬼</b>成为了你的伙伴！"}
        else:
            s["mats"]["蜂蜜"] = s["mats"].get("蜂蜜", 0) + 1
            ev_log(s, "捣蛋小鬼 → 你追回了干粮（蜂蜜 ×1）")
            s["event_result"] = {"title": "捣蛋小鬼",
                                 "text": "你追回了干粮，小鬼一溜烟跑了——<br><br>获得「蜂蜜」×1"}
    # 其余为非交互事件：效果已在 roll_explore_event 中结算，这里仅确认关闭
    s["pending_event"] = None
    return None


def sell_mat(s, name, cnt=None):
    if not s["mats"].get(name):
        return "没有该材料。"
    if s["lv_idx"] < 1:
        return "交易所尚未开放（升到 Lv2 解锁卖出）。"
    n = 1 if cnt is None else min(int(cnt), s["mats"][name])      # 原型：单次卖出 1 个
    total = M[name][2] * n
    s["mats"][name] -= n
    if s["mats"][name] <= 0:
        del s["mats"][name]
    s["money"] += total
    add_log(s, "💱 卖出 " + name + " ×" + str(n) + " → +" + fmt_money(total), "")
    return None


def sell_all(s, msgs):
    """一键卖出全部材料（对齐原型 sellAll）"""
    if s["lv_idx"] < 1:
        return "交易所尚未开放。"
    total = 0
    cnt = 0
    for k, v in s["mats"].items():
        total += M[k][2] * v
        cnt += v
    if not cnt:
        return "背包里没有材料。"
    s["mats"] = {}
    s["money"] += total
    add_log(s, "💱 一键卖出 " + str(cnt) + " 个材料 → +" + fmt_money(total), "")
    return None


def _shop_lim_key(cur, it):
    return cur + ":" + it["n"]              # v1.38m：渠道前缀——同商品跨店限购独立


def _shop_lim_used(s, it, cur):
    lim = it.get("lim")
    if not lim:
        return 0
    box = s.get("shop_weekly" if lim[0] == "周" else "shop_daily") or {}
    return (box.get("cnt") or {}).get(_shop_lim_key(cur, it), 0)


def _shop_lim_check(s, it, n, cur):
    """v1.38m：限购校验——返回错误文案（None = 通过）"""
    lim = it.get("lim")
    if not lim:
        return None
    left = max(0, lim[1] - _shop_lim_used(s, it, cur))
    if left >= n:
        return None
    return ((("本周" if lim[0] == "周" else "今日") + "限购 " + str(lim[1]) + " 个")
            + ("（还剩 " + str(left) + " 个，本次买 " + str(n) + " 个超了）" if left > 0 else "（已购满）") + "。")


def _shop_lim_add(s, it, n, cur):
    lim = it.get("lim")
    if not lim:
        return
    box = s.setdefault("shop_weekly" if lim[0] == "周" else "shop_daily", {"cnt": {}})
    box.setdefault("cnt", {})
    k = _shop_lim_key(cur, it)
    box["cnt"][k] = box["cnt"].get(k, 0) + n


def buy(s, i, msgs, n=1):
    i = int(i)
    n = max(1, min(int(n or 1), 9999))          # v1.38k：批量购买（上限防误传）
    it = SHOP[i]
    bad = _shop_lim_check(s, it, n, "c")        # v1.38m：限购
    if bad:
        return bad
    total = it["c"] * n
    if s["money"] < total:
        return "钱币不足（需要 " + fmt_money(total) + "）。"
    s["money"] -= total
    _shop_lim_add(s, it, n, "c")
    if it.get("item"):
        s["items"][it["item"]] = s["items"].get(it["item"], 0) + n
        msgs.append("🛒 购买「" + it["n"] + "」" + ("×" + str(n) if n > 1 else ""))
    else:
        # 材料包：普通 ×5 / 精良 ×3（按商品名推断）× n
        tier = "精良" if "精良" in it["n"] else "普通"
        cnt = (3 if tier == "精良" else 5) * n
        got = {}
        for _ in range(cnt):
            mm = random_mat(s, tier)
            s["mats"][mm] = s["mats"].get(mm, 0) + 1
            got[mm] = got.get(mm, 0) + 1
        msgs.append("🛒 购买「" + it["n"] + "」" + ("×" + str(n) if n > 1 else "")
                    + " → " + " ".join(k + "×" + str(v) for k, v in got.items()))
    return None


def buy_vit(s, i, msgs, n=1):
    i = int(i)
    n = max(1, min(int(n or 1), 9999))          # v1.38k：批量兑换
    it = VIT_SHOP[i]
    if it.get("incense"):
        n = 1                                   # 薰香逐级升级，固定单次
    if it.get("incense") and s.get("incense", 0) + 1 != it["incense"]:
        return "安眠薰香需要按顺序逐级升级（当前 " + str(s.get("incense", 0)) + " 级）。"
    bad = _shop_lim_check(s, it, n, "vit")      # v1.38m：限购
    if bad:
        return bad
    total = it["vit"] * n
    if s["vit"] < total:
        return "活力点不足（需要 " + str(total) + "，当前 " + str(s["vit"]) + "）。"
    s["vit"] -= total
    _shop_lim_add(s, it, n, "vit")
    if it.get("item"):
        s["items"][it["item"]] = s["items"].get(it["item"], 0) + n
    if it.get("sp"):
        s["explore"] += it["sp"] * n
    if it.get("con"):
        s["con"] += it["con"] * n
    if it.get("incense"):
        s["incense"] = it["incense"]
    msgs.append("🌙 活力点兑换：「" + it["n"] + "」" + ("×" + str(n) if n > 1 else ""))
    return None


def buy_con(s, i, msgs, n=1, mat=None):
    i = int(i)
    n = max(1, min(int(n or 1), 9999))          # v1.38k：批量兑换
    it = CON_SHOP[i]
    if it.get("g") and guild_idx(s) < it["g"]:   # v1.41 H2：B 级解锁项（精英委托重掷券）
        return "尚未解锁（需公会 " + CFG["guildName"][it["g"]] + " 级）。"
    bad = _shop_lim_check(s, it, n, "con")      # v1.38m：限购
    if bad:
        return bad
    if it.get("reroll"):
        n = 1                                    # v1.41 H2：重掷券单次
    total = it["con"] * n
    if s["con"] < total:
        return "贡献不足（需要 " + str(total) + "，当前 " + str(s["con"]) + "）。"
    if it.get("reroll"):                         # v1.41 H2：重新抽取当前委托栏（与命运骰子同机制）
        err = reroll_pool_now(s)
        if err:
            return err
        s["con"] -= total
        _shop_lim_add(s, it, n, "con")
        msgs.append("🛒 贡献兑换：使用「精英委托重掷券」→ 当前委托栏已重新抽取")
        return None
    if it.get("matSel"):                         # v1.41 H2：材料改真自选（06 设计：「指定」= 可自选）
        if not mat or M.get(mat, [None, None])[1] != it["matSel"][0]:
            return "请先选择具体材料（" + it["matSel"][0] + "档）。"
        cnt = it["matSel"][1] * n
        s["con"] -= total
        _shop_lim_add(s, it, n, "con")
        s["mats"][mat] = s["mats"].get(mat, 0) + cnt
        if mat not in s.get("seen_mats", []):
            s.setdefault("seen_mats", []).append(mat)
        msgs.append("🛒 贡献兑换：自选 " + mat + "×" + str(cnt))
        return None
    s["con"] -= total
    _shop_lim_add(s, it, n, "con")
    if it.get("item"):
        s["items"][it["item"]] = s["items"].get(it["item"], 0) + n
    if it.get("sp"):
        s["explore"] += it["sp"] * n
    msgs.append("🛒 贡献兑换：「" + it["n"] + "」" + ("×" + str(n) if n > 1 else ""))
    return None


def reroll_pool_now(s):
    """v1.41 H2：重掷当前委托栏（命运骰子 / 精英委托重掷券共用）——返回错误文案或 None"""
    p = s.get("pool")
    if not p or not p["list"]:
        return "当前没有可刷新的委托栏。"
    if p["taken"]:
        return "本次刷新已经接取过委托了，无需刷新。"
    if pool_expired(s):
        return "本批委托已失效，刷新也没有意义了。"
    lp = latest_point()
    p["list"] = draw_pool(s, lp)
    return None


def master_unlocked(s):
    """v1.41 I6：大师商店解锁 = 成就「大师」（完成 ≥4 个不同传奇事件）"""
    return "大师" in (s.get("achv") or [])


def buy_master_gear(s, msgs, idx):
    """v1.41 I6：大师商店·专属装备（一次性；铂金币 + 传说材料）"""
    if not master_unlocked(s):
        return "大师商店需先达成成就「大师」（完成 ≥4 个不同传奇事件）。"
    try:
        it = MASTER_SHOP["gear"][int(idx)]
    except (TypeError, ValueError, IndexError):
        return "商品不存在。"
    eqd = (s.get("equipped") or {}).values()
    if it["n"] in (s.get("gear") or []) or it["n"] in eqd:
        return "「" + it["n"] + "」已拥有。"
    if s["money"] < it["platC"] * 1000000:
        return "铂金币不足（需要 " + str(it["platC"]) + "）。"
    for mk, mv in it["mats"].items():
        if s["mats"].get(mk, 0) < mv:
            return "材料不足：「" + mk + "」×" + str(mv) + "。"
    s["money"] -= it["platC"] * 1000000
    for mk, mv in it["mats"].items():
        s["mats"][mk] -= mv
    s["gear"].append(it["n"])
    add_log(s, "🎓 大师商店：「" + it["n"] + "」入手（-" + str(it["platC"]) + " 铂金币）", "gold")
    msgs.append("🎓 大师商店：「" + it["n"] + "」已购入")
    return None


def buy_master_mat(s, msgs, mat=None):
    """v1.41 I6：大师商店·指定传说材料 ×2（6 铂金币 / 周 1）"""
    if not master_unlocked(s):
        return "大师商店需先达成成就「大师」。"
    it = {"n": "指定传说材料", "lim": ["周", 1]}
    bad = _shop_lim_check(s, it, 1, "master")
    if bad:
        return bad
    if mat not in PLAT_SHOP[0]["sel"]:
        return "请先选择一位传说材料。"
    if s["money"] < 6000000:
        return "铂金币不足（需要 6）。"
    s["money"] -= 6000000
    _shop_lim_add(s, it, 1, "master")
    s["mats"][mat] = s["mats"].get(mat, 0) + 2
    if mat not in s.get("seen_mats", []):
        s.setdefault("seen_mats", []).append(mat)
    msgs.append("🎓 大师商店：指定「" + mat + "」×2（-6 铂金币）")
    return None


def buy_master_vit(s, msgs):
    """v1.41 I6：大师商店·大师的馈赠（20 铂金币 → 活力点 +500，无限兑换）"""
    if not master_unlocked(s):
        return "大师商店需先达成成就「大师」。"
    if s["money"] < MASTER_SHOP["vitC"] * 1000000:
        return "铂金币不足（需要 " + str(MASTER_SHOP["vitC"]) + "）。"
    s["money"] -= MASTER_SHOP["vitC"] * 1000000
    s["vit"] += MASTER_SHOP["vitN"]
    add_log(s, "🎓 大师商店：活力点 +" + str(MASTER_SHOP["vitN"]) + "（-" + str(MASTER_SHOP["vitC"]) + " 铂金币）", "gold")
    msgs.append("🎓 大师商店：活力点 +" + str(MASTER_SHOP["vitN"]))
    return None


PLAT_UNLOCK_MONEY = 1000000       # v1.61d：铂金商店解锁 = 当前持有 ≥1 铂金币（前端 PLAT_UNLOCK_MONEY 对齐）

def buy_plat(s, msgs, i=0, mat=None):
    """v1.50：铂金商店·统一购买（全部以铂金币结算）
       v1.61d：解锁 = 当前持有 ≥1 铂金币（不看历史获得总量）
       —— 自选类（matSel）需先选定具体材料；道具类按 itemN 数量发放"""
    if s["money"] < PLAT_UNLOCK_MONEY:
        return "铂金商店需持有 ≥1 铂金币（100 万铜）。"
    try:
        it = PLAT_SHOP[int(i)]
    except (TypeError, ValueError, IndexError):
        return "商品不存在。"
    bad = _shop_lim_check(s, it, 1, "plat")
    if bad:
        return bad
    if it.get("matSel"):
        if not mat or M.get(mat, [None, None])[1] != it["matSel"][0]:
            return "请先选择具体材料（" + it["matSel"][0] + "档）。"
    if s["money"] < it["platC"] * 1000000:
        return "铂金币不足（需要 " + str(it["platC"]) + "）。"
    s["money"] -= it["platC"] * 1000000
    _shop_lim_add(s, it, 1, "plat")
    if it.get("matSel"):
        cnt = it["matSel"][1]
        s["mats"][mat] = s["mats"].get(mat, 0) + cnt
        if mat not in s.get("seen_mats", []):
            s.setdefault("seen_mats", []).append(mat)
        msgs.append("🏛 铂金商店：自选「" + mat + "」×" + str(cnt) + "（-" + str(it["platC"]) + " 铂金币）")
    else:
        cnt = int(it.get("itemN", 1))
        s["items"][it["item"]] = s["items"].get(it["item"], 0) + cnt
        msgs.append("🏛 铂金商店：「" + it["n"] + "」（-" + str(it["platC"]) + " 铂金币）")
    return None


def buy_mat(s, name, msgs):
    """v1.41 H3：交易所买入（卖出价 ×3；E 级解锁；普通/精良/稀有）"""
    if s["lv_idx"] < 1:
        return "交易所尚未开放。"
    if guild_idx(s) < 1:
        return "买入需公会 E 级。"
    m = M.get(name)
    if not m:
        return "没有该材料。"
    if m[1] not in BUY_TIERS:
        return "「" + m[1] + "」材料不在交易所买入范围（史诗走贡献商店 / 传说走铂金商店）。"
    price = m[2] * 3
    if s["money"] < price:
        return "铜币不足（需要 " + str(price) + "）。"
    s["money"] -= price
    s["mats"][name] = s["mats"].get(name, 0) + 1
    if name not in s.get("seen_mats", []):
        s.setdefault("seen_mats", []).append(name)
    msgs.append("💱 买入 " + name + " ×1")
    return None


def recipe_ing(r):
    """v1.50：料理材料合并（主材 main + 辅材 sub）——校验 / 扣除 / 展示共用"""
    d = {}
    d.update(r.get("main") or {})
    d.update(r.get("sub") or {})
    return d


def cook_tier_open(s, r):
    # v1.41：厨房按玩家等级分阶段开放——Lv1 普通 / Lv2 精良及以下 / Lv3 稀有及以下 / Lv4 史诗及以下 / Lv5 全部
    # v1.50：品级以「主材」为准（main）
    t = "普通"
    for k in (r.get("main") or {}):
        q = M[k][1] if k in M else "普通"
        if QUALITY_ORDER.index(q) > QUALITY_ORDER.index(t):
            t = q
    return QUALITY_ORDER.index(t) <= s.get("lv_idx", 0)


def cook(s, i, msgs):
    try:
        i = int(i)
    except (TypeError, ValueError):
        return "料理不存在。"
    if not (0 <= i < len(CFG["recipes"])):
        return "料理不存在。"
    r = CFG["recipes"][i]
    if not cook_tier_open(s, r):
        return "「" + r["n"] + "」尚未开放——料理按品阶随冒险者等级逐步解锁。"
    for k, v in recipe_ing(r).items():
        if s["mats"].get(k, 0) < v:
            return "材料不足，无法烹饪「" + r["n"] + "」。需要：" + "、".join(
                k + " ×" + str(v) for k, v in recipe_ing(r).items())
    t = today_str()
    if r.get("sp"):                        # v1.41f5：探索点料理——每日最多 2 次 + 当日累计上限 +5（挡在扣料前）
        _ms0 = s.get("meal_sp")
        if not isinstance(_ms0, dict) or _ms0.get("date") != t:
            _ms0 = s["meal_sp"] = {"date": t, "cnt": 0, "got": 0}
        if _ms0.get("cnt", 0) >= 2:
            return "今日恢复探索点的料理已经用过 2 次了，明天再来。（探索点料理每日最多 2 次——v1.41f5）"
        if _ms0.get("got", 0) >= 5:
            return "今日料理恢复的探索点已达上限（+5 点）。（v1.41f5）"
    for k, v in recipe_ing(r).items():
        s["mats"][k] -= v
        if s["mats"][k] <= 0:
            del s["mats"][k]
    parts = []
    if r.get("cap"):                       # v1.32：先扩展上限，再回精力（否则精力已满时回精被吞）
        if not s.get("meal_cap") or s["meal_cap"].get("date") != t:
            s["meal_cap"] = {"date": t, "cap": 0}
        s["meal_cap"]["cap"] += r["cap"]
        parts.append("当日精力上限 +" + str(r["cap"]))
    if r.get("en") or r.get("enPct"):      # v1.42：enPct = 按精力上限的百分比恢复（巨龙盛宴 50%）
        before = s["energy"]
        _add = int(energy_max_now(s) * r["enPct"] + 0.5) if r.get("enPct") else r["en"]
        s["energy"] = min(energy_max_now(s), s["energy"] + _add)
        parts.append("精力 " + str(before) + " → " + str(s["energy"]))
    if r["n"] not in s.setdefault("cooked", []):        # v1.35：图鉴·料理记录
        s["cooked"].append(r["n"])
    if r.get("sp"):                        # v1.41f5：当日累计 +5 封顶（前段已挡；此处兜底截断）
        _ms1 = s["meal_sp"]
        _gain = min(r["sp"], max(0, 5 - _ms1.get("got", 0)))
        s["explore"] += _gain
        _ms1["cnt"] = _ms1.get("cnt", 0) + 1
        _ms1["got"] = _ms1.get("got", 0) + _gain
        parts.append("探索点 +" + str(_gain) + "（今日第 " + str(_ms1["cnt"]) + "/2 次）")
    if r.get("bonus") or r.get("rate"):
        s["last_meal"] = {"date": t, "name": r["n"], "bonus": r.get("bonus", 0), "rate": r.get("rate", 0)}
        parts.append("✅ 「" + r["n"] + "」生效，下次接取的委托享受加成")
    msgs.append("🍲 烹饪「" + r["n"] + "」→ " + "、".join(parts))
    return None


def equip_item(s, name, msgs):
    g = gear_def(name)
    if not g or name not in s["gear"]:
        return "背包里没有这件装备。"
    slot = "charmSlot" if g[2] == "成就饰品槽" else ("weapon" if g[2] == "武器" else ("armor" if g[2] == "护甲" else "accessory"))
    m0 = energy_max_now(s)                          # v1.38o：穿脱精力规则
    old = s["equipped"].get(slot)
    if old:
        s["gear"].append(old)
    s["gear"].remove(name)
    s["equipped"][slot] = name
    m1 = energy_max_now(s)
    d = m1 - m0
    s["energy"] = min(m1, s["energy"] + (d if d > 0 else 0))   # 上限提高：当前同步 +差值；下降：收敛
    msgs.append("🎽 装备「" + name + "」")
    return None


def unequip(s, slot, msgs):
    n = s["equipped"].get(slot)
    if not n:
        return "该槽位没有装备。"
    s["gear"].append(n)
    s["equipped"][slot] = None
    s["energy"] = min(s["energy"], energy_max_now(s))   # v1.38o：卸下收敛至新上限
    msgs.append("👕 卸下「" + n + "」")
    return None


def craft_item(s, name, msgs):
    """v1.46：炼金台合成（任务准备物）——消耗材料 → +1 准备物"""
    r = CRAFT.get(name)
    if not r:
        return "没有这个配方。"
    for k, v in r["ing"].items():
        if s["mats"].get(k, 0) < v:
            return "材料不足：需要 " + k + "×" + str(v) + "（当前 " + str(s["mats"].get(k, 0)) + "）。"
    for k, v in r["ing"].items():
        s["mats"][k] -= v
        if s["mats"][k] <= 0:
            del s["mats"][k]
    s["items"][name] = s["items"].get(name, 0) + 1
    msgs.append("⚗️ 合成「" + name + "」×1（消耗 "
                + "、".join(k + "×" + str(v) for k, v in r["ing"].items()) + "）")
    return None


def craft(s, name, msgs):
    g = gear_def(name)
    if not g:
        return "没有这件装备。"
    if g[5] == "—":
        return "「" + name + "」不能打造，只能通过成就或事件获得。"
    if name not in s["blueprints"]:
        return "没有「" + name + "」图纸。"
    mm = craft_main_mat(name)
    cost = craft_cost(g[1])
    sub_cnt = sub_mat_count(g[1], g[2])
    if s["mats"].get(mm["mat"], 0) < mm["cnt"]:
        return "主材料不足（需要 " + mm["mat"] + "×" + str(mm["cnt"]) + "）。"
    subs = pick_sub_mats(s, g[1], mm["mat"], sub_cnt)
    if not subs:
        return ("副材料不足（需要 " + "/".join(sub_cats_for(mm["mat"]))
                + " 类「" + " 或 ".join(sub_tiers(g[1])) + "」品阶 ×" + str(sub_cnt) + "）。")
    if s["money"] < cost:
        return "加工费不足（需要 " + fmt_money(cost) + "）。"
    s["mats"][mm["mat"]] -= mm["cnt"]
    if s["mats"][mm["mat"]] <= 0:
        del s["mats"][mm["mat"]]
    used = []
    for k, v in subs.items():
        s["mats"][k] -= v
        used.append(k + "×" + str(v))
        if s["mats"][k] <= 0:
            del s["mats"][k]
    s["money"] -= cost
    if name not in s["gear"]:
        s["gear"].append(name)
    if name not in s.setdefault("forged", []):          # v1.35：图鉴·打造记录
        s["forged"].append(name)
    msgs.append("🔨 打造「" + name + "」→ " + mm["mat"] + "×" + str(mm["cnt"]) + " + " + " ".join(used))
    return None


def craft_main_mat(name):
    """解析装备数据中的主材料串 "龙心×6" → {mat, cnt}"""
    g = gear_def(name)
    matstr = g[5]
    m = re.match(r"^(.+?)×(\d+)", matstr)
    if m:
        return {"mat": m.group(1), "cnt": int(m.group(2))}
    return {"mat": None, "cnt": 0}


QUALITY_ORDER = ["普通", "精良", "稀有", "史诗", "传说"]


# v1.38c：副材料品类联动——由主材料品类推导允许的副材料品类（食材不可作打造材料）
SUB_CATS = {
    "木材": ["木材", "兽材", "织物"],      # 弓弩杖：兽筋弓弦、皮绳缠柄
    "兽材": ["兽材", "织物", "木材"],      # 皮革甲：布衬缝线、木扣
    "矿石": ["矿石", "木材", "兽材"],      # 剑斧铠：木柄、皮缠
    "石材": ["石材", "矿石", "木材"],      # 石锤：金属箍、木柄
    "宝石": ["宝石", "矿石"],              # 饰品：宝石与金属底托
    "织物": ["织物", "兽材"],              # 布甲法袍：皮革束带
    "草药": ["草药", "织物", "木材"],      # 植物系：藤蔓、丝带、木芯
    "特殊": ["特殊", "宝石", "矿石"],      # 龙鳞魔晶：秘银、魔晶镶嵌
}
_SUB_CATS_DEFAULT = ["木材", "石材", "矿石", "宝石", "草药", "织物", "兽材", "特殊"]


def mat_cats(name):
    """v1.48：材料全品类（主品类 + 附加品类）；M 第 4 位为附加品类数组"""
    m = M.get(name)
    if not m:
        return []
    return [m[0]] + list(m[3]) if len(m) > 3 and m[3] else [m[0]]


def sub_cats_for(main_mat):
    """v1.38c / v1.48：该主材料对应的副材料品类集合（多品类主材 → 合并各品类集合）"""
    out = []
    for c in mat_cats(main_mat):
        for x in SUB_CATS.get(c, _SUB_CATS_DEFAULT):
            if x not in out:
                out.append(x)
    return out or list(_SUB_CATS_DEFAULT)


def sub_tiers(quality):
    i = QUALITY_ORDER.index(quality)
    return [q for q in [QUALITY_ORDER[i], QUALITY_ORDER[i - 1] if i > 0 else None] if q]


def craft_cost(quality):
    """加工费（铜）：普通 50银 / 精良 3金 / 稀有 15金 / 史诗 60金 / 传说 300金"""
    return int({"普通": 0.5, "精良": 3, "稀有": 15, "史诗": 60, "传说": 300}.get(quality, 0) * 10000)


def sub_mat_count(quality, slot):
    base = {"普通": 2, "精良": 3, "稀有": 4, "史诗": 6, "传说": 8}.get(quality, 3)
    return base + (1 if slot == "护甲" else 0)


def pick_sub_mats(s, quality, main_mat, need):
    """v1.38c：品阶（同阶/低一阶）× 品类（随主材料联动）双约束；优先消耗低品阶、低价材料"""
    tiers = sub_tiers(quality)
    cats = sub_cats_for(main_mat)
    pool = [k for k, v in M.items()
            if any(c in cats for c in mat_cats(k)) and v[1] in tiers and k != main_mat and s["mats"].get(k, 0) > 0]
    pool.sort(key=lambda k: (-tiers.index(M[k][1]), M[k][2]))   # 低品阶优先；同阶低价优先
    picked = {}
    left = need
    for k in pool:
        if left <= 0:
            break
        take = min(s["mats"][k], left)
        picked[k] = take
        left -= take
    return picked if left <= 0 else None


def buy_blueprint(s, name, msgs):
    g = gear_def(name)
    if not g or g[5] == "—":
        return "该图纸不存在。"
    if name in s["blueprints"]:
        return "已掌握该图纸。"
    # 价格与公会门槛对齐原型 BP_SHOP（普通 20 银 / 精良 1.5 金 / 稀有 9 金 / 史诗 42 金 / 传说 5 铂金币）
    cost = {"普通": 2000, "精良": 15000, "稀有": 90000, "史诗": 420000, "传说": 5000000}.get(g[1], 15000)
    need = {"普通": 1, "精良": 1, "稀有": 3, "史诗": 5, "传说": 6}.get(g[1], 1)
    if guild_idx(s) < need:
        return "公会等级不足（需要 " + CFG["guildName"][need] + " 级）。"
    if s["money"] < cost:
        return "钱币不足（需要 " + fmt_money(cost) + "）。"
    s["money"] -= cost
    s["blueprints"][name] = True
    msgs.append("📜 购买图纸「" + name + "」")
    return None


def up_skill(s, name, msgs):
    cur = s["skills"].get(name, 0)
    if cur >= 5:
        return "「" + name + "」已经满级了。"
    if skill_total(s) >= skill_cap(s):
        return "技能树总级数已达当前公会等级上限（" + str(skill_cap(s)) + " 级）。"
    cost = SKILL_COST[cur]
    if s["con"] < cost:
        return "贡献不足（需要 " + str(cost) + "）。"
    s["con"] -= cost
    s["skills"][name] = cur + 1
    msgs.append("🌳 技能「" + name + "」升至 " + str(s["skills"][name]) + " 级")
    return None


def buy_charm(s, msgs):
    i = s["charm"]
    if i >= 5:
        return "冥念护符已满级。"
    c = CHARM[i]
    if not charm_unlocked(s, i):
        return "尚未解锁第 " + str(i + 1) + " 级（需要：" + c["req"] + "）。"
    if s["vit"] < c["cost"]:
        return "活力点不足（需要 " + str(c["cost"]) + "）。"
    s["vit"] -= c["cost"]
    s["charm"] = i + 1
    msgs.append("🌙 冥念护符升至 " + str(s["charm"]) + " 级 → 报酬 +" + str(round(c["pay"] * 100)) + "%、成功率 +" + str(round(c["rate"] * 100)) + "%")
    return None


# ══════════════ 宠物养成 · 小狼成长链（v1.22） ══════════════


def feed_wolf(s, name, msgs):
    w = s.get("wolf")
    if not w:
        return "还没有小狼伙伴。"
    if not s["mats"].get(name):
        return "没有该材料。"
    if w["stage"] >= 4:
        return "远古魔狼已是最终形态，不再需要喂食。"
    if name not in WOLF_FOODS:
        return ("「" + name + "」不能喂食，小狼不吃这个。"
                "可喂食：食材（蘑菇 / 河鱼 / 泉水 / 蜂蜜 / 兽肉 / 香草 / 山珍）、"
                "草药（止血草 / 晨露花 / 月光草 / 暗影草 / 世界树汁液）及高级特殊材料（龙血 / 龙心）。")
    if feed_left(s) <= 0:
        return "今天已经喂食 " + str(WOLF_DAILY_FEED) + " 次了，小狼吃饱啦——明天再喂吧。"
    need = WOLF_STAGES[w["stage"]]["need"]
    growth_full = w["growth"] >= need                  # 本阶段成长值已满
    v = WOLF_FEED_VALUE.get(M[name][1], 2)
    mv = WOLF_MUTATE_VALUE.get(name, 0)                # 高级特殊材料 → 变异值
    s["mats"][name] -= 1
    if s["mats"][name] <= 0:
        del s["mats"][name]
    w["fedDate"] = today_str()
    w["fedCount"] = w.get("fedCount", 0) + 1
    if not growth_full:
        w["growth"] += v                               # 成长值满后不再增加（但仍可继续喂食）
    if mv:
        w["mutate"] = w.get("mutate", 0) + mv
    parts = []
    if not growth_full:
        parts.append("成长值 +" + str(v))
    if mv:
        parts.append("变异值 +" + str(mv))
    if not parts:
        parts.append("成长值已满，未获得加成")
    add_log(s, "🐺 喂食「" + name + "」（" + "，".join(parts) + "）→ " + WOLF_STAGES[w["stage"]]["name"]
            + " 成长 " + str(w["growth"]) + "/" + str(need), "ok")
    if w["stage"] == 1 and w["growth"] >= WOLF_STAGES[1]["need"]:
        w["stage"] = 2
        w["growth"] = 0
        add_log(s, "🎉 小狼成长为「成年狼」：所有委托材料掉落率 +3%", "gold")
        if s.get("daily"):
            s["daily"]["events"].append("🐺 宠物成长：成年狼")
        msgs.append("🎉 小狼长大了！成为「成年狼」——所有委托材料掉落率 +3%")
    elif w["stage"] == 2 and w["growth"] >= WOLF_STAGES[2]["need"]:
        w["stage"] = 3
        w["growth"] = 0
        add_log(s, "🎉 成年狼成长为「巨狼」：材料掉落率 +5%、委托成功率 +1%", "gold")
        if s.get("daily"):
            s["daily"]["events"].append("🐺 宠物成长：巨狼")
        msgs.append("🎉 它变得更加强壮——成为「巨狼」：材料掉落率 +5%、委托成功率 +1%")
    return None


def evolve_wolf(s, msgs):
    w = s.get("wolf")
    if not w or w["stage"] != 3:
        return "只有巨狼可以进化为远古魔狼。"
    if w["growth"] < WOLF_STAGES[3]["need"]:
        return "成长值尚未积满（" + str(w["growth"]) + " / " + str(WOLF_STAGES[3]["need"]) + "）。先用食材把成长值喂满吧。"
    if w.get("mutate", 0) < WOLF_MUTATE_NEED:
        return ("变异值尚未积满（" + str(w.get("mutate", 0)) + " / " + str(WOLF_MUTATE_NEED)
                + "）。继续喂食高级特殊材料：龙血 / 暗影草 +5、龙心 / 世界树汁液 +12 变异值。")
    s["wolf"] = {"stage": 4, "growth": 0, "mutate": 0, "fedDate": "", "fedCount": 0}
    add_log(s, "🌌 巨狼变异为「远古魔狼」：材料掉落率 +8%、委托成功率 +3%", "gold")
    if s.get("daily"):
        s["daily"]["events"].append("🐺 宠物变异：远古魔狼")
    msgs.append("🌌 变异成功！远古魔狼：材料掉落率 +8%、委托成功率 +3%")
    return None
