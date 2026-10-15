# -*- coding: utf-8 -*-
"""devops —— 存档「开发者操作」纯函数库（v1.69 交互式改档工具的共用底座）

设计：每个操作 = 纯函数 op_xxx(s, **kw) → 结果文案；只依赖 game.py，**不做 I/O、不加锁**。
  · 离线入口：`存档工具.py`（无参数 → 交互菜单；需先停服，改完重启生效）
  · 在线入口：`app.py` 的 `POST /admin/dev`（**仅本机**；在账号锁内改，改完即时生效）

约定：
  · 操作失败一律 `raise OpError(文案)`，调用方负责展示（不会写坏档）
  · 骰值可控：`roll` 参数留空 = 真实随机；1~100 = 锁定该值（1 = 大成功 / 96~100 = 大失败）
  · 结算走真实 game.settle（结果入 results 队列，玩家下次打开能看到掷骰弹窗）；
    不想弹动画就传 silent=True（结算后清空 results 队列）
"""
import contextlib
import random
import re

import game


class OpError(Exception):
    """操作失败（文案直接展示给用户）"""


def _need(cond, msg):
    if not cond:
        raise OpError(msg)


def _int(v, default=None, name="参数"):
    if v is None or v == "":
        if default is None:
            raise OpError(name + "不能为空")
        return default
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        raise OpError(name + "必须是整数：" + str(v))


def _bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "y", "是", "开", "on")


def _pick_idx(which, n):
    """把 all / 0,2 / 单个序号 解析成下标列表"""
    w = str(which or "all").strip().lower()
    if w in ("all", "全部", "*", ""):
        return list(range(n))
    out = []
    for part in w.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        i = _int(part, name="序号")
        _need(0 <= i < n, "序号 " + str(i) + " 超出范围（0~" + str(n - 1) + "）")
        if i not in out:
            out.append(i)
    _need(out, "没解析出任何序号")
    return out


def _roll_of(v):
    """骰值参数：空 = 随机（返回 None）；否则 1~100"""
    if v is None or str(v).strip() == "":
        return None
    r = _int(v, name="骰值")
    _need(1 <= r <= 100, "骰值范围 1~100")
    return r


@contextlib.contextmanager
def fixed_roll(roll):
    """临时把 game.rand 固定为 roll（None = 不干预）——settle 内的掷骰即锁定值"""
    if roll is None:
        yield
        return
    orig = game.rand
    game.rand = lambda n=100: roll
    try:
        yield
    finally:
        game.rand = orig


# ══════════════════ 操作注册表 ══════════════════
OPS = {}          # name → {label, group, args:[(key, 提示, 默认)], fn}


def op(name, label, group, args=None):
    def deco(fn):
        OPS[name] = {"label": label, "group": group, "args": args or [], "fn": fn}
        return fn
    return deco


# ────────── 1 数值 ──────────
SET_KEYS = {
    "money": (0, None, "铜币（1 银 = 100 / 1 金 = 10000 / 1 铂金 = 1000000）"),
    "lv_idx": (0, 4, "等级下标（0 = Lv1 … 4 = Lv5）"),
    "exp": (0, None, "累计经验"),
    "rep": (0, None, "声望（决定公会等级）"),
    "con": (0, None, "贡献"),
    "vit": (0, None, "活力点"),
    "energy": (0, None, "当前精力（会按当前上限截断）"),
    "explore": (0, None, "探索点"),
    "perm_energy": (0, 50, "安眠薰香永久精力"),
    "train_energy": (0, 200, "训练场永久精力"),
    "incense": (0, 5, "薰香等级"),
    "charm": (0, 5, "冥念护符等级"),
    "echo": (0, 3, "裂痕回响"),
    "heat_n": (0, None, "安眠室累计早睡天数"),
    "done_below5": (0, None, "Lv5 以下委托完成数"),
    "total_quests": (0, None, "累计完成委托数"),
}


@op("set", "设置某个数值（钱 / 等级 / 经验 / 声望 / 贡献 / 活力 / 精力 / 探索点 …）", "1 数值",
    [("key", "字段名", "money"), ("value", "新值", "")])
def op_set(s, key="money", value=""):
    key = str(key).strip()
    _need(key in SET_KEYS, "未知字段「" + key + "」；可选：" + " / ".join(SET_KEYS))
    lo, hi, desc = SET_KEYS[key]
    v = _int(value, name="新值")
    _need(v >= lo, key + " 不能小于 " + str(lo))
    if hi is not None:
        _need(v <= hi, key + " 不能大于 " + str(hi))
    old = s.get(key)
    s[key] = v
    if key == "energy":
        s["energy"] = min(v, game.energy_max_now(s))
    if key == "exp":
        game.check_level_up(s)
    return "%s：%s → %s（%s）" % (key, old, s.get(key), desc)


@op("max_level", "一键满级（Lv5 + 经验拉满）", "1 数值")
def op_max_level(s):
    old = (s.get("lv_idx"), s.get("exp"))
    s["lv_idx"] = 4
    s["exp"] = max(s.get("exp", 0), game.CFG["expNeed"][3] if len(game.CFG["expNeed"]) > 3 else 30000)
    s["energy"] = game.energy_max_now(s)
    return "等级 %s → Lv5（lv_idx 4）、经验 %s → %s；精力已回满至上限 %s" % (
        old[0], old[1], s["exp"], s["energy"])


@op("add_exp", "增加经验（自动处理升级）", "1 数值", [("n", "增加多少经验", "100")])
def op_add_exp(s, n="100"):
    n = _int(n, name="经验")
    before = (s["lv_idx"], s["exp"])
    s["exp"] += n
    game.check_level_up(s)
    return "经验 %s → %s；等级下标 %s → %s" % (before[1], s["exp"], before[0], s["lv_idx"])


# ────────── 2 委托 ──────────
@op("pool_refresh", "立即刷新委托栏（当前刷新点重抽，窗口从此刻重新计时）", "2 委托",
    [("also_extra", "是否顺带重掷「额外 / 特权 / 沙漏」委托（1=是 / 0=否）", "0")])
def op_pool_refresh(s, also_extra="0"):
    lp = game.latest_point()
    pk = game.pool_point_key(lp[0], lp[1])
    s["pool"] = {"point": pk, "list": game.draw_pool(s, lp), "taken": False,
                 "bornTs": game.now_ms(), "expiredLogged": False}
    s["pool_point"] = pk
    tail = ""
    if _bool(also_extra):
        s["bonus_quests"] = None
        s["priv_quest"] = None
        s["glass_quest"] = None
        s["bonus_today"] = False
        s["priv_today"] = False
        s["glass_today"] = False
        tail = _roll_extras(s)
    return "委托栏已刷新：%d 个委托（刷新点 %s，窗口重置）%s" % (len(s["pool"]["list"]), pk, tail)


def _roll_extras(s):
    """重掷公会额外委托 / W 级特权委托 / 时间沙漏委托（照 catch_up ④ 的口径，跳过概率直接给）"""
    got = []
    if s["lv_idx"] >= 2:
        bp = game.mix_pool(s).copy()
        random.shuffle(bp)
        s["bonus_quests"] = (bp[:6] or None)
        s["bonus_today"] = bool(s["bonus_quests"])
        if s["bonus_quests"]:
            got.append("额外委托 6 选 1")
    if game.guild_idx(s) >= 7:
        pp = game.mix_pool(s)
        if pp:
            s["priv_quest"] = random.choice(pp)
            s["priv_today"] = True
            got.append("特权委托「" + s["priv_quest"][0] + "」")
    if game.gear_effects(s)["dailyLimit"] > 0:
        gp = game.mix_pool(s)
        if gp:
            s["glass_quest"] = random.choice(gp)
            s["glass_today"] = True
            got.append("沙漏委托「" + s["glass_quest"][0] + "」")
    return ("；已重掷：" + "、".join(got)) if got else ""


@op("pool_show", "查看当前委托栏（只读）", "2 委托")
def op_pool_show(s):
    p = s.get("pool")
    if not p:
        return "当前没有委托栏（下次上线会自动抽）。"
    lines = ["刷新点 " + str(p.get("point")) + "（已接取：" + ("是" if p.get("taken") else "否") + "）"]
    for i, q in enumerate(p.get("list") or []):
        lines.append("  [%d] %s｜%s｜%s｜报酬 %s｜%d 精力" % (
            i, q[0], q[1], q[4], game.fmt_money(q[5]), q[7]))
    return "\n".join(lines)


@op("finish", "立即完成进行中的委托（可指定骰值：1 = 大成功）", "2 委托",
    [("which", "完成哪些：all = 全部 / 序号（0 起，逗号分隔）", "all"),
     ("roll", "骰值：留空 = 真实随机 / 1 = 大成功 / 96 = 大失败 / 1~100", ""),
     ("silent", "静默完成（清空结算弹窗动画队列，1=是 / 0=否）", "0")])
def op_finish(s, which="all", roll="", silent="0"):
    act = s.get("active") or []
    _need(act, "当前没有进行中的委托。")
    idxs = _pick_idx(which, len(act))
    r = _roll_of(roll)
    msgs = []
    done = []
    with fixed_roll(r):
        for i in sorted(idxs, reverse=True):
            a = act[i]
            res = game.settle(s, a, msgs)
            done.append("「%s」%s（+%s）" % (a.get("name"), res.get("title"), game.fmt_money(res.get("gold", 0))))
            act.pop(i)
    if _bool(silent):
        s["results"] = []
        s["levelups"] = []
        s["pending_rare"] = []
        s["pending_event"] = None
    head = ("已按骰值 %d 结算：" % r) if r else "已按真实掷骰结算："
    return head + "；".join(done) + ("" if _bool(silent) else "（玩家下次打开会看到结算弹窗）")


@op("settle_pending", "结算「跨天待结算」的委托", "2 委托")
def op_settle_pending(s):
    n = game.settle_pending_on_checkin(s, [])
    return ("已结算 %d 个跨天待结算委托。" % n) if n else "没有跨天待结算的委托。"


@op("reset_limit", "重置今日接取名额（把已接取数清零）", "2 委托",
    [("n", "清零后的已接取数（一般填 0）", "0")])
def op_reset_limit(s, n="0"):
    old = s.get("accepted", 0)
    s["accepted"] = _int(n, name="数值")
    return "今日已接取：%s → %s（上限 %s 次）" % (old, s["accepted"], game.daily_limit_now(s))


@op("reroll_extra", "重掷「额外 / 特权 / 沙漏」委托", "2 委托")
def op_reroll_extra(s):
    got = _roll_extras(s)
    return "重掷完成" + (got if got else "（当前等级 / 装备 / 公会条件没有这类委托）")


@op("clear_active", "清空进行中的委托（不结算、不退精力）", "2 委托")
def op_clear_active(s):
    n = len(s.get("active") or [])
    s["active"] = []
    return "已清空 %d 个进行中的委托（未结算）。" % n


@op("unlock_chain", "解锁全部委托链（所有委托的完成次数记为 1）", "2 委托")
def op_unlock_chain(s):
    n = 0
    for lv in ("Lv1", "Lv2", "Lv3", "Lv4", "Lv5"):
        for q in game.C.get(lv) or []:
            if s["done_quests"].get(q[0], 0) < 1:
                s["done_quests"][q[0]] = 1
                n += 1
    return "已解锁 / 标记 %d 个委托（链前置条件满足；原已完成的未改动）" % n


# ────────── 3 健康 ──────────
@op("health_tasks", "设置今日打卡（7 位 0/1，对应 入睡/起床/午休/喝水/运动/三餐/不刷手机）", "3 健康",
    [("mask", "7 位掩码，如 1111111 或 1010100", "1111111")])
def op_health_tasks(s, mask="1111111"):
    m = str(mask).strip().replace(",", "").replace(" ", "")
    _need(len(m) == 7 and all(c in "01" for c in m), "掩码要 7 位 0/1，例如 1111111")
    h = s["health"]
    h["done"] = [int(c) for c in m]
    game.calc_health(s)
    return "今日打卡：" + m + " → 健康分 " + str(h["score"])


@op("health_multi", "设置「久坐起身 / 阅读」次数", "3 健康",
    [("sedentary", "久坐起身次数（上限 %d）" % game.CFG["multiTasks"][0][2], "4"),
     ("read", "阅读次数（上限 %d）" % game.CFG["multiTasks"][1][2], "2")])
def op_health_multi(s, sedentary="4", read="2"):
    a = _int(sedentary, name="久坐次数")
    b = _int(read, name="阅读次数")
    _need(a >= 0 and b >= 0, "次数不能为负")
    s["health"]["multi"] = [a, b]
    game.calc_health(s)
    return "久坐起身 %d 次 / 阅读 %d 次 → 健康分 %d" % (a, b, s["health"]["score"])


@op("health_meals", "设置三餐（3 位 0/1：早/午/晚）", "3 健康",
    [("mask", "3 位掩码，如 111", "111")])
def op_health_meals(s, mask="111"):
    m = str(mask).strip().replace(",", "").replace(" ", "")
    _need(len(m) == 3 and all(c in "01" for c in m), "掩码要 3 位 0/1，例如 111")
    s["health"]["meals"] = [int(c) for c in m]
    game.calc_health(s)
    return "三餐：" + m + " → 健康分 " + str(s["health"]["score"])


@op("health_clear", "清空今日打卡（全部归零）", "3 健康")
def op_health_clear(s):
    h = s["health"]
    h["done"] = [0] * 7
    h["multi"] = [0, 0]
    h["meals"] = [0, 0, 0]
    game.calc_health(s)
    return "今日打卡已清空，健康分 → " + str(h["score"])


@op("history_fix", "修正健康历史（委托成功率取最后一条的分数）", "3 健康",
    [("score", "分数（留空 = 不改）", ""), ("sleep", "入睡时间（如 23:10，留空 = 不改）", "")])
def op_history_fix(s, score="", sleep=""):
    hist = s.get("history") or []
    _need(hist, "还没有健康历史（先跑一天日结算）")
    last = hist[-1]
    old = (last.get("score"), last.get("sleep"))
    if str(score).strip():
        last["score"] = _int(score, name="分数")
    if str(sleep).strip():
        last["sleep"] = str(sleep).strip()
    return "历史最后一条（%s）：score %s → %s，sleep %s → %s（下次委托成功率按此分）" % (
        last.get("date"), old[0], last.get("score"), old[1], last.get("sleep"))


@op("sick", "病假开 / 关（开启则今日评分锁定 %d）" % game.SICK_LOCK_SCORE, "3 健康",
    [("on", "1 = 请病假 / 0 = 取消病假", "1")])
def op_sick(s, on="1"):
    d = game.today_str()
    days = s.setdefault("sick_days", [])
    if _bool(on):
        if d not in days:
            days.append(d)
        game.calc_health(s)
        return "已请病假（今日 %s）：评分锁定 %d" % (d, game.SICK_LOCK_SCORE)
    if d in days:
        days.remove(d)
    game.calc_health(s)
    return "已取消今日病假：评分按实际打卡重算 = " + str(s["health"]["score"])


@op("shield", "重置连击保险（下一次断天不扣连击）", "3 健康")
def op_shield(s):
    s["shield_month"] = game.today_str()[:7]
    s["shield_days"] = []
    return "连击保险已重置（本月 " + s["shield_month"] + " 内断天可用 1 次）"


# ────────── 4 资产 ──────────
@op("mat", "加 / 减材料（负数为扣除）", "4 资产",
    [("name", "材料名", ""), ("n", "数量（负数 = 扣除）", "1")])
def op_mat(s, name="", n="1"):
    name = str(name).strip()
    _need(name in game.M, "没有这种材料：" + name)
    k = _int(n, name="数量")
    cur = s["mats"].get(name, 0)
    new = cur + k
    _need(new >= 0, "「" + name + "」当前只有 " + str(cur) + " 个，不够扣 " + str(-k))
    if new:
        s["mats"][name] = new
        if name not in s.get("seen_mats", []):
            s.setdefault("seen_mats", []).append(name)
    else:
        s["mats"].pop(name, None)
    return "材料「%s」：%d → %d（%s）" % (name, cur, new, game.M[name][1])


@op("mat_fill", "全部材料 ×N（图鉴同步解锁）", "4 资产", [("n", "每种材料的数量", "99")])
def op_mat_fill(s, n="99"):
    k = _int(n, name="数量")
    _need(k >= 0, "数量不能为负")
    for name in game.M:
        s["mats"][name] = k
    s["seen_mats"] = sorted(set(s.get("seen_mats", [])) | set(game.M))
    return "已把 %d 种材料全部设为 ×%d（含图鉴解锁）" % (len(game.M), k)


@op("item", "加道具（规则道具 / 准备物）", "4 资产",
    [("name", "道具名", ""), ("n", "数量（负数 = 扣除）", "1")])
def op_item(s, name="", n="1"):
    name = str(name).strip()
    _need(name in game.ITEM_DESC, "没有这种道具：" + name + "（可选：" + " / ".join(sorted(game.ITEM_DESC)) + "）")
    k = _int(n, name="数量")
    cur = s["items"].get(name, 0)
    new = cur + k
    _need(new >= 0, "「" + name + "」当前只有 " + str(cur) + " 个")
    if new:
        s["items"][name] = new
        if name not in s.get("seen_items", []):
            s.setdefault("seen_items", []).append(name)
    else:
        s["items"].pop(name, None)
    return "道具「%s」：%d → %d" % (name, cur, new)


@op("gear", "加装备（可选直接穿上：武器/护甲/饰品/护符）", "4 资产",
    [("name", "装备名", ""), ("slot", "槽位（留空 = 只入背包）", "")])
def op_gear(s, name="", slot=""):
    name = str(name).strip()
    g = game.gear_def(name)
    _need(g, "没有这件装备：" + name)
    added = name not in s["gear"]
    if added:
        s["gear"].append(name)
    tail = ""
    if str(slot).strip():
        slot_map = {"武器": "weapon", "护甲": "armor", "饰品": "accessory",
                    "护符": "charmSlot", "成就饰品": "charmSlot", "成就饰品槽": "charmSlot"}
        key = slot_map.get(str(slot).strip())
        _need(key, "槽位只能是：武器 / 护甲 / 饰品 / 护符")
        old = s["equipped"].get(key)
        s["equipped"][key] = name
        if name in s["gear"]:
            s["gear"].remove(name)
        tail = "，已穿上（%s 槽：%s → %s）" % (key, old, name)
    return "%s「%s」（%s）%s" % ("已加入背包" if added else "背包已有", name, g[1], tail)


@op("unequip", "卸下装备（放回背包）", "4 资产",
    [("slot", "槽位：武器 / 护甲 / 饰品 / 护符 / all", "all")])
def op_unequip(s, slot="all"):
    slot_map = {"武器": "weapon", "护甲": "armor", "饰品": "accessory",
                "护符": "charmSlot", "成就饰品": "charmSlot", "成就饰品槽": "charmSlot"}
    want = list(slot_map.values()) if str(slot).strip().lower() in ("all", "全部", "") else [slot_map.get(str(slot).strip())]
    _need(all(want), "槽位只能是：武器 / 护甲 / 饰品 / 护符 / all")
    out = []
    for k in want:
        n = s["equipped"].get(k)
        if n:
            s["equipped"][k] = None
            if n not in s["gear"]:
                s["gear"].append(n)
            out.append(k + "：" + n)
    return ("已卸下 " + "；".join(out)) if out else "这些槽位本来就没有装备。"


def _all_blueprints(s):
    """图纸键 = 装备名（g[5] != "—" 表示有图纸）"""
    n = 0
    for g in game.GEAR:
        if g[5] != "—" and g[0] not in s["blueprints"]:
            s["blueprints"][g[0]] = True
            n += 1
    return n


@op("blueprint", "加图纸（图纸 = 装备名；all = 全部）", "4 资产", [("name", "装备名（或 all）", "all")])
def op_blueprint(s, name="all"):
    if str(name).strip().lower() in ("all", "全部", ""):
        return "已解锁 %d 张新图纸（全库共 %d 张）" % (_all_blueprints(s), len(s["blueprints"]))
    name = str(name).strip()
    g = game.gear_def(name)
    _need(g, "没有这件装备：" + name)
    _need(g[5] != "—", "「" + name + "」没有图纸（特殊获得）。")
    if name in s["blueprints"]:
        return "已掌握图纸「" + name + "」。"
    s["blueprints"][name] = True
    return "已解锁图纸「" + name + "」（" + g[1] + "）"


@op("skill", "技能等级（all = 全满 5 级 / 或指定单项）", "4 资产",
    [("name", "技能名（或 all）", "all"), ("lv", "等级 0~5", "5")])
def op_skill(s, name="all", lv="5"):
    v = _int(lv, name="等级")
    _need(0 <= v <= 5, "技能等级 0~5")
    if str(name).strip().lower() in ("all", "全部", ""):
        for k in s["skills"]:
            s["skills"][k] = v
        return "全部技能 → %d 级" % v
    _need(name in s["skills"], "技能只能是：" + " / ".join(s["skills"]))
    old = s["skills"][name]
    s["skills"][name] = v
    return "技能「%s」：%d → %d 级" % (name, old, v)


@op("shop_reset", "重置商店限购（今日 / 本周 + 交易所买入计数）", "4 资产")
def op_shop_reset(s):
    s["shop_daily"] = {"date": "", "cnt": {}}
    s["shop_weekly"] = {"week": "", "cnt": {}}
    s["exbuy"] = {"date": "", "n": 0}
    return "商店日 / 周限购与交易所买入计数已重置。"


# ────────── 5 养成 ──────────
@op("pet_get", "获得宠物（可选直接携带）", "5 养成",
    [("name", "宠物名（或 all）", "all"), ("carry", "是否携带（1=是 / 0=否）", "0")])
def op_pet_get(s, name="all", carry="0"):
    names = list(game.PET_LINES) if str(name).strip().lower() in ("all", "全部", "") else [str(name).strip()]
    if names == ["all"]:
        names = list(game.PET_LINES)
    got = []
    for n in names:
        _need(n in game.PET_LINES, "没有这条宠物养成线：「" + n + "」（可选：" + " / ".join(game.PET_LINES) + "）")
        game.grant_pet(s, n)
        got.append(n)
    tail = ""
    if _bool(carry) and got:
        s["carry_pet"] = got[0]
        tail = "，已携带「" + got[0] + "」"
    return "已获得：" + "、".join(got) + tail


@op("pet_set", "改宠物数值（阶段 / 成长 / 变异 / 心情 / 羁绊天数）", "5 养成",
    [("name", "宠物名", ""), ("field", "字段：stage/growth/mutate/mood/gotDate 或 all", "all"),
     ("value", "值（stage 1~4、growth/mutate 数值、mood 0~100、gotDate 为日期 or 天数前）", "")])
def op_pet_set(s, name="", field="all", value=""):
    name = str(name).strip()
    _need(name in s.get("pet_data", {}), "档案里没有这只宠物的养成数据：" + name + "（可先「获得宠物」）")
    pd = s["pet_data"][name]
    f = str(field).strip()
    out = []
    if f in ("all", "全部", ""):
        pd["stage"] = 4
        pd["growth"] = int(pd.get("growth", 0)) or 0
        pd["mutate"] = 300
        pd["mood"] = 100
        return "「" + name + "」→ 4 阶 / 变异值 300 / 心情 100（成长值 %s 未变）" % pd.get("growth")
    if f == "stage":
        v = _int(value, name="阶段")
        _need(1 <= v <= 4, "阶段 1~4")
        pd["stage"] = v
    elif f in ("growth", "mutate", "mood"):
        v = _int(value, name="值")
        _need(v >= 0, "不能为负")
        if f == "mood":
            _need(v <= 100, "心情 0~100")
        pd[f] = v
    elif f == "gotDate":
        v = str(value).strip()
        if v.isdigit():
            import datetime as _dt
            pd["gotDate"] = (game.datetime.now() - _dt.timedelta(days=int(v))).strftime("%Y-%m-%d")
        else:
            _need(len(v) == 10 and v[4] == "-", "gotDate 需要 YYYY-MM-DD 或「N 天前」的 N")
            pd["gotDate"] = v
    else:
        raise OpError("字段只能是 stage / growth / mutate / mood / gotDate / all")
    return "「%s」%s = %s" % (name, f, pd.get(f))


@op("wolf_set", "改小狼（阶段 / 成长 / 变异 / 心情）", "5 养成",
    [("field", "字段：stage/growth/mutate/mood", "stage"), ("value", "值", "4")])
def op_wolf_set(s, field="stage", value="4"):
    _need(s.get("wolf"), "档案里还没有小狼（先推进小狼线）")
    w = s["wolf"]
    f = str(field).strip()
    _need(f in ("stage", "growth", "mutate", "mood"), "字段只能是 stage / growth / mutate / mood")
    v = _int(value, name="值")
    if f == "stage":
        _need(1 <= v <= 4, "阶段 1~4")
    w[f] = v
    return "小狼 %s = %s（阶段 %s）" % (f, v, w.get("stage"))


@op("carry", "设置携带宠物（留空 = 全部看家）", "5 养成", [("name", "宠物名（留空 = 看家）", "")])
def op_carry(s, name=""):
    name = str(name).strip()
    if not name:
        s["carry_pet"] = ""
        return "已让伙伴们全部看家。"
    pool = list(game.PET_LINES) + (["小狼"] if s.get("wolf") else [])
    _need(name in pool or name in s.get("pets", []), "没有这只伙伴：" + name)
    old = s.get("carry_pet")
    s["carry_pet"] = name
    return "携带宠物：%s → %s" % (old or "（无）", name)


# ────────── 6 收集 ──────────
@op("unlock_all", "全面解锁：称号 / 成就 / 图纸 / 图鉴 / 传奇 / 链（一次到位）", "6 收集")
def op_unlock_all(s):
    msgs = []
    n_bp = _all_blueprints(s)
    for name, _g in game.ACHV:
        if name not in s["achv"]:
            s["achv"].append(name)
    game.check_achievements(s, msgs)
    for t in getattr(game, "ACHV_TITLE", []) or []:
        if t not in s["titles"]:
            s["titles"].append(t)
    for lv in ("Lv1", "Lv2", "Lv3", "Lv4", "Lv5"):
        for q in game.C.get(lv) or []:
            if s["done_quests"].get(q[0], 0) < 1:
                s["done_quests"][q[0]] = 1
    s["seen_mats"] = sorted(set(s.get("seen_mats", [])) | set(game.M))
    s["seen_items"] = sorted(set(s.get("seen_items", [])) | set(game.ITEM_DESC))
    s["forged"] = sorted(set(s.get("forged", [])) | {g[0] for g in game.GEAR})
    s["cooked"] = sorted(set(s.get("cooked", [])) | {r["n"] for r in game.CFG.get("recipes", [])})
    game.check_guild_titles(s, msgs)
    game.check_level_up(s)
    return "已解锁：图纸 %d 张、成就 %d 个、称号 %d 个、委托链全开、图鉴 / 锻造 / 料理全记录" % (
        n_bp, len(s["achv"]), len(s["titles"]))


@op("titles_all", "补全称号（含成就称号）", "6 收集")
def op_titles_all(s):
    msgs = []
    for t in getattr(game, "ACHV_TITLE", []) or []:
        if t not in s["titles"]:
            s["titles"].append(t)
    game.check_guild_titles(s, msgs)
    return "当前称号 %d 个：%s" % (len(s["titles"]), "、".join(s["titles"]) or "（无）")


@op("achv_all", "补全成就（连奖励一起发）", "6 收集")
def op_achv_all(s):
    msgs = []
    for name, _g in game.ACHV:
        if name not in s["achv"]:
            s["achv"].append(name)
    game.check_achievements(s, msgs)
    return "成就 %d / %d：%s" % (len(s["achv"]), len(game.ACHV), "、".join(s["achv"]))


# ────────── 7 探索与世界 ──────────
@op("explore_now", "立刻完成一次探索（可选区域序号；不扣探索点）", "7 探索与世界",
    [("idx", "区域序号（留空 = 随机挑一个已解锁的）", "")])
def op_explore_now(s, idx=""):
    regions = game.REGIONS
    i = _int(idx) if str(idx).strip() else random.randrange(len(regions))
    _need(0 <= i < len(regions), "区域序号 0~" + str(len(regions) - 1))
    r = regions[i]
    msgs = []
    s["explore_active"] = {"idx": i, "n": r["n"], "c": r["c"], "h": r.get("h", 2),
                           "startTs": game.now_ms() - 10 ** 7, "finishTs": game.now_ms() - 1}
    game.explore_finish_check(s, msgs)
    return "探索「%s」已完成结算%s" % (r["n"], ("；" + "；".join(msgs)) if msgs else "")


@op("explore_clear", "取消进行中的探索（不结算）", "7 探索与世界")
def op_explore_clear(s):
    had = bool(s.get("explore_active"))
    s["explore_active"] = None
    s["explore_result"] = None
    return "已取消进行中的探索。" if had else "当前没有进行中的探索。"


@op("month_event", "推进月度世界事件进度", "7 探索与世界", [("n", "加多少进度", "999")])
def op_month_event(s, n="999"):
    msgs = []
    game.month_event_tick(s, msgs) if hasattr(game, "month_event_tick") else None
    cur = game.month_event_now(s)
    _need(cur, "本月没有世界事件（或已过期）")
    game.month_event_add(s, msgs, "quest", _int(n, name="进度"))
    return "月度事件「%s」进度已推进%s" % (cur.get("key"), ("；" + "；".join(msgs)) if msgs else "")


# ────────── 8 复位 ──────────
@op("clear_transient", "清空瞬态队列（结算弹窗 / 升级提示 / 待领奖励）", "8 复位")
def op_clear_transient(s):
    s["results"] = []
    s["levelups"] = []
    s["pending_rare"] = []
    s["pending_event"] = None
    s["pending_legend"] = None
    s["pending_pet"] = None
    s["pending_energy"] = None
    s["pending_festival"] = None
    s["explore_result"] = None
    s["event_result"] = None
    s["explore_active"] = None
    return "瞬态队列已清空（不弹结算动画 / 升级提示 / 各种待领）。"


@op("clear_log", "清空事件日志（内存 + event_log 表由调用方落库）", "8 复位")
def op_clear_log(s):
    n = len(s.get("log") or [])
    s["log"] = []
    return "日志已清空（内存 %d 条）。" % n


@op("reset_settles", "重置周 / 月结算标记（可重跑结算领奖）", "8 复位")
def op_reset_settles(s):
    old = (s.get("week_settled"), s.get("month_settled"))
    s["week_settled"] = ""
    s["month_settled"] = ""
    return "周结算标记 %s → 空；月结算标记 %s → 空（下次跨天会重跑，注意可能重复发奖）" % old


# ────────── 9 高级 ──────────
@op("raw_replace", "整档替换（JSON 文本；走 import_save_state 校验清洗）", "9 高级",
    [("json", "完整存档 JSON（建议先「导出」一份备份）", "")])
def op_raw_replace(s, json=""):
    text = str(json).strip()
    _need(text, "JSON 不能为空")
    try:
        import json as _json
        raw = _json.loads(text)
    except ValueError as e:
        raise OpError("JSON 解析失败：" + str(e))
    _need(isinstance(raw, dict), "存档 JSON 的顶层必须是对象 {…}。")
    # v1.69：防手滑——import_save_state 对陌生字段是「全丢 + 补默认」，随手贴个 {...} 也能过，
    #         结果整档被抹成新号（要靠备份回滚）。这里先数认得出的字段，太少就拒绝。
    base = game.new_state()
    known = sum(1 for k in raw
                if re.sub(r"(?<!^)(?=[A-Z])", "_", str(k)).lower() in base)
    _need(known >= 8, "这不像一份完整存档：%d 个字段里只认出 %d 个（完整档约 100 个）。"
                      "整档替换请用「导出」出来的 JSON，或游戏里「导出快照」的文件。"
                      % (len(raw), known))
    new = game.import_save_state(raw)
    s.clear()
    s.update(new)
    return "整档已替换（字段 %d 个，昵称：%s）" % (len(s), s.get("name"))


def run_op(s, op_name, **kw):
    """执行操作（s 原地修改）；返回结果文案；失败抛 OpError
       注：形参名不能用 name —— 材料 / 道具 / 装备 / 宠物 等操作的参数就叫 name，
           会撞成「got multiple values for argument 'name'」（v1.69 实测）"""
    _need(op_name in OPS, "未知操作：" + str(op_name) + "（可用：" + " / ".join(sorted(OPS)) + "）")
    return OPS[op_name]["fn"](s, **kw)


def op_list():
    """按分组列出全部操作（供菜单 / 帮助）"""
    groups = {}
    for name, meta in OPS.items():
        groups.setdefault(meta["group"], []).append((name, meta))
    return groups
