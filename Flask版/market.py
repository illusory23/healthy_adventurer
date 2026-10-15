# -*- coding: utf-8 -*-
"""v1.66（社交 P3）：材料市场业务逻辑

- 仅存在于 Flask 版（社交层）；原型保持单机、体验版不含社交层（见 11_社交与协作.md 11.1）
- 解锁 = Lv3 且公会 C；可交易品阶 = 普通 / 精良 / 稀有 / 史诗（**传说 / 道具 / 装备 / 图纸不可**）
- 挂单即托管：上架先从背包扣除 → 成交交付 / 卖家下架原样退回（退回直入本人存档——本人请求锁内）
  / 3 天到期由 sweep 下架 → **退回邮件**（不跨账号写档）
- 定价：单价 ∈ [商店价×0.9, 商店价×3.0]；商店价 = 基准价×3（全品阶统一）；参考价 = 基准价；免手续费
- 买入：每人每日 ≤5 个、每周 ≤20 个；可部分购买；禁止买自己的单；史诗需 Lv4
- 结算：买家扣款入包 + 记流水；卖家货款进**邮件**（kind=proceeds，P1 底座）+ 双方日志
- global_sweep 处理器：挂单到期下架（退回邮件，幂等）
"""
import json
import time
from datetime import datetime, timedelta

import db
import game
import sweep


def cfg(key, default):
    return (game.CFG.get("market") or {}).get(key, default)


def _now_ms():
    return int(time.time() * 1000)


def _lv(s):
    return int(s.get("lv_idx", 0)) + 1


def _day_start_ms(now=None):
    d = (now or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(d.timestamp() * 1000)


def _week_start_ms(now=None):
    d = (now or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    d -= timedelta(days=d.weekday())
    return int(d.timestamp() * 1000)


def _load(uid):
    raw, _ = db.load_user_state(uid)
    return game.migrate_state(raw) if raw else game.new_state()


def _guild_ok(s):
    """公会 ≥ C（CFG.guildName 索引：F0 E1 D2 C3）"""
    return game.guild_idx(s) >= cfg("unlockGuild", 3)


def unlocked(s):
    return _lv(s) >= cfg("unlockLv", 3) and _guild_ok(s)


def _tier(mat):
    return (game.M.get(mat) or ["", ""])[1]


def _shop_price(mat):
    """商店价 = 基准价 × shopMul（全品阶统一口径）"""
    return int(game.M[mat][2]) * cfg("shopMul", 3)


def _price_bounds(mat):
    shop = _shop_price(mat)
    return int(round(shop * cfg("priceMin", 0.9))), int(round(shop * cfg("priceMax", 3.0)))


def _tradable(mat):
    return mat in game.M and _tier(mat) in cfg("tiers", [])


# ══════════════ 概览（市场页一次拉取）══════════════

def overview(uid, me_s):
    lv = _lv(me_s)
    on = []
    for r in db.market_on():
        if r["mat"] not in game.M:        # v1.67：未知材料名的残留行不展示（原直取 game.M 会 KeyError 崩概览）
            continue
        on.append({"id": r["id"], "mat": r["mat"], "qty": r["qty"], "price": r["price"],
                   "seller": r["seller"], "seller_name": r["seller_name"] or "（未命名）",
                   "tier": _tier(r["mat"]), "base": game.M[r["mat"]][2], "shop": _shop_price(r["mat"]),
                   "expire_in": max(0, r["expire_at"] - _now_ms()), "mine": r["seller"] == uid})
    mine = []
    for r in db.market_mine(uid):
        mine.append({"id": r["id"], "mat": r["mat"], "qty": r["qty"], "price": r["price"],
                     "status": r["status"], "sold": r["sold"], "off_reason": r["off_reason"],
                     "tier": _tier(r["mat"]),
                     "expire_in": max(0, r["expire_at"] - _now_ms()) if r["status"] == "on" else 0})
    day0, week0 = _day_start_ms(), _week_start_ms()
    mats = []
    if unlocked(me_s):
        for k in sorted((me_s.get("mats") or {}).keys()):
            if _tradable(k) and (_tier(k) != "史诗" or lv >= cfg("epicLv", 4)):
                lo, hi = _price_bounds(k)
                mats.append({"mat": k, "have": me_s["mats"][k], "tier": _tier(k),
                             "base": game.M[k][2], "shop": _shop_price(k), "lo": lo, "hi": hi})
    return {
        "unlock": unlocked(me_s),
        "unlock_txt": "需 Lv" + str(cfg("unlockLv", 3)) + " 且公会 C 级",
        "me": {"lv": lv, "guild": game.CFG["guildName"][game.guild_idx(me_s)],
               "epic_ok": lv >= cfg("epicLv", 4),
               "list_active": db.market_active_count(uid),
               "list_today": db.market_day_listings(uid, day0),
               "buy_today": db.market_buys_since(uid, day0),
               "buy_week": db.market_buys_since(uid, week0)},
        "limits": {"maxListings": cfg("maxListings", 3), "dailyListings": cfg("dailyListings", 3),
                   "listingDays": cfg("listingDays", 3), "buyDaily": cfg("buyDaily", 5),
                   "buyWeekly": cfg("buyWeekly", 20), "epicLv": cfg("epicLv", 4),
                   "priceMin": cfg("priceMin", 0.9), "priceMax": cfg("priceMax", 3.0),
                   "shopMul": cfg("shopMul", 3)},
        "on": on,
        "mine": mine,
        "mats": mats,
    }


def dot(uid):
    """市场页签红点：有他人挂单在售（可买）"""
    try:
        return db.market_on_by_others(uid)
    except Exception:
        return 0


# ══════════════ 上架 / 下架 / 买入 ══════════════

def list_mat(uid, me_s, mat, qty, price, msgs):
    if not unlocked(me_s):
        return "材料市场需 Lv" + str(cfg("unlockLv", 3)) + " 且公会 C 级才能使用"
    if not _tradable(mat):
        return "该品阶不可上架（可交易：普通 / 精良 / 稀有 / 史诗；传说与道具 / 装备 / 图纸不可）"
    if _tier(mat) == "史诗" and _lv(me_s) < cfg("epicLv", 4):
        return "史诗材料需 Lv" + str(cfg("epicLv", 4)) + " 才能上架"
    try:
        qty = int(qty)
        price = int(price)
    except (TypeError, ValueError):
        return "数量或价格不正确"
    if qty < 1 or qty > 999:
        return "上架数量须为 1~999 个"
    lo, hi = _price_bounds(mat)
    if price < lo or price > hi:
        return ("单价须在 " + game.fmt_money(lo) + " ~ " + game.fmt_money(hi)
                + " 之间（商店价 " + game.fmt_money(_shop_price(mat)) + " 的 90% ~ 300%）")
    if db.market_active_count(uid) >= cfg("maxListings", 3):
        return "同时挂单已达上限（" + str(cfg("maxListings", 3)) + " 单）——先等成交或下架"
    if db.market_day_listings(uid, _day_start_ms()) >= cfg("dailyListings", 3):
        return "今日上架次数已达上限（" + str(cfg("dailyListings", 3)) + " 次）"
    have = (me_s.get("mats") or {}).get(mat, 0)
    if have < qty:
        return "背包里的「" + mat + "」不足（现有 " + str(have) + " 个）"
    # 托管：先从背包扣除
    me_s["mats"][mat] = have - qty
    if me_s["mats"][mat] <= 0:
        del me_s["mats"][mat]
    days = cfg("listingDays", 3)
    db.market_create(uid, mat, qty, price, _now_ms() + days * 86400000)
    game.add_log(me_s, "🛒 上架「" + mat + "」×" + str(qty) + " @ " + game.fmt_money(price)
                 + "（" + str(days) + " 天未售出自动下架退回）", "gold")
    msgs.append("🛒 已上架 " + mat + "×" + str(qty) + "，单价 " + game.fmt_money(price)
                + "（挂单即托管；免手续费）")
    return None


def cancel(uid, me_s, lid, msgs):
    r = db.market_get(lid)
    if not r or r["seller"] != uid:
        return "挂单不存在"
    left = db.market_take_off(lid, "off", "cancel")   # v1.67：原子收摊 + 按剩余数量退回（防与部分买入竞态多退）
    if left is None:
        return "该挂单已结束"
    me_s.setdefault("mats", {})
    me_s["mats"][r["mat"]] = me_s["mats"].get(r["mat"], 0) + left
    game.add_log(me_s, "🛒 下架「" + r["mat"] + "」×" + str(left) + "（原样退回）", "gold")
    msgs.append("已下架 " + r["mat"] + "×" + str(left) + "——材料已退回背包")
    return None


def buy(uid, me_s, lid, qty, msgs):
    if not unlocked(me_s):
        return "材料市场需 Lv" + str(cfg("unlockLv", 3)) + " 且公会 C 级才能使用"
    r = db.market_get(lid)
    if not r or r["status"] != "on":
        return "该挂单已售罄或下架"
    if r["seller"] == uid:
        return "不能购买自己的挂单"
    if r["expire_at"] and r["expire_at"] <= _now_ms():
        return "该挂单已到期"
    tier = _tier(r["mat"])
    if tier == "史诗" and _lv(me_s) < cfg("epicLv", 4):
        return "史诗材料需 Lv" + str(cfg("epicLv", 4)) + " 才能购买"
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        return "数量不正确"
    if qty < 1:
        return "数量不正确"
    if qty > r["qty"]:
        return "该挂单只剩 " + str(r["qty"]) + " 个"
    day0, week0 = _day_start_ms(), _week_start_ms()
    used_d, used_w = db.market_buys_since(uid, day0), db.market_buys_since(uid, week0)
    if used_d + qty > cfg("buyDaily", 5):
        return "今日买入限额为 " + str(cfg("buyDaily", 5)) + " 个（已买 " + str(used_d) + " 个）"
    if used_w + qty > cfg("buyWeekly", 20):
        return "本周买入限额为 " + str(cfg("buyWeekly", 20)) + " 个（已买 " + str(used_w) + " 个）"
    total = r["price"] * qty
    if me_s.get("money", 0) < total:
        return "金币不足（需要 " + game.fmt_money(total) + "，当前 " + game.fmt_money(me_s.get("money", 0)) + "）"
    left = db.market_take(lid, qty)
    if left is None:
        return "手慢了——该挂单数量刚刚变化，请刷新"
    me_s["money"] = me_s.get("money", 0) - total
    me_s.setdefault("mats", {})
    me_s["mats"][r["mat"]] = me_s["mats"].get(r["mat"], 0) + qty
    db.market_buy_add(uid, lid, qty, r["price"])
    game.add_log(me_s, "🛒 买入「" + r["mat"] + "」×" + str(qty) + "（-" + game.fmt_money(total) + "）", "gold")
    # 货款 → 卖家邮件（P1 底座；货款领取在卖家锁内）
    db.mail_create(r["seller"], "proceeds",
                   title="💰 市场货款到账",
                   body="你挂出的「" + r["mat"] + "」售出 " + str(qty) + " 个（单价 "
                        + game.fmt_money(r["price"]) + "）",
                   money=total, expire_at=0)   # v1.67：货款不设期限（原 30 天标记不生效且易误导；保持永久可领）
    msgs.append("🛒 买入 " + r["mat"] + "×" + str(qty) + "（-" + game.fmt_money(total)
                + "）——货款已寄给卖家")
    return None


# ══════════════ global_sweep：挂单到期 ══════════════

def sweep_market(now_ms=None):
    """挂单到期下架（幂等）：原样退回 → 退回邮件（不跨账号写档）。返回处理条数"""
    now = int(now_ms if now_ms is not None else _now_ms())
    n = 0
    for r in db.market_expired(now):
        left = db.market_take_off(r["id"], "expired", "expire")   # v1.67：原子收摊 + 按剩余数量退回（防竞态多退）
        if left is None:
            continue
        if left > 0:
            db.mail_create(r["seller"], "return", title="↩️ 挂单到期退回",
                           body="挂出的「" + r["mat"] + "」×" + str(left)
                                + " 三天未售出，已自动下架退回，请领取。",
                           mat=r["mat"], qty=left, expire_at=0)
        n += 1
    return n


sweep.register(sweep_market)
