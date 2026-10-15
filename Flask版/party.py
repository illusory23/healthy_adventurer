# -*- coding: utf-8 -*-
"""v1.65（社交 P2）：组队副本业务逻辑

- 仅存在于 Flask 版（社交层）；原型保持单机、体验版不含社交层（见 11_社交与协作.md 11.1）
- 流程：每日 08:00 惰性抽 1 个 offer（只抽本人可参与的品阶，当日有效、可放弃）
        → 组建（扣发起人精力，offer → open）→ 邀请 → 满 3 人队长开启（open → running）
        → 每人 3 次掷骰（成功 +1 格、掷 1~5 大成功 +2 格）→ 达标立即结算；
        到期未达标按失败结算（安慰奖 ≈1/4 必得材料）
- 一切存档修改都在本人请求的锁内：精力在本人组建 / 接受时扣；**退还（未开启作废）与
  奖励领取都记为「待处理标记」，由本人下次打开时在其锁内入账**——不跨账号写档
- global_sweep 处理器：offer/open 到期作废（退还精力）、running 到期按失败结算（幂等）
"""
import json
import math
import random
import time
from datetime import datetime, timedelta

import db
import game
import sweep


def cfg(key, default):
    return (game.CFG.get("party") or {}).get(key, default)


def _now_ms():
    return int(time.time() * 1000)


def _lv(s):
    return int(s.get("lv_idx", 0)) + 1


def _day_key(now=None):
    """副本日：以 08:00 为界（yyyymmdd 整数）——当日 offer 的有效期到「次日 08:00」"""
    d = now or datetime.now()
    if d.hour < cfg("refHour", 8):
        d = d - timedelta(days=1)
    return int(d.strftime("%Y%m%d"))


def _day_end_ms(day):
    d = datetime.strptime(str(day), "%Y%m%d").replace(hour=cfg("refHour", 8), minute=0,
                                                      second=0, microsecond=0) + timedelta(days=1)
    return int(d.timestamp() * 1000)


def _week_start_ms(now=None):
    d = (now or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    d -= timedelta(days=d.weekday())          # 周一 00:00（与 social.py 同口径）
    return int(d.timestamp() * 1000)


def _load(uid):
    raw, _ = db.load_user_state(uid)
    return game.migrate_state(raw) if raw else game.new_state()


def _goal(n):
    return int(math.ceil(round(n * 3 * cfg("goalMul", 0.6), 6)))


def _rate_now(me_s, tier):
    """本人成功率（按副本等级档套用常规公式；接取时锁定）"""
    qi = cfg("tierLv", {}).get(tier, 5) - 1
    q = ["", "冒险", "全天", 0, "普通", 0, 0, 0, {}]
    return game.success_rate(me_s, q, qi)


def _eligible_tiers(me_s):
    """本人当前可参与的品阶（等级 + 昨日健康分双门槛）"""
    lv = _lv(me_s)
    ph = game.prev_health_score(me_s)
    out = []
    for tier in ("精良", "稀有", "史诗", "传说"):
        if lv >= cfg("tierLv", {}).get(tier, 9) and ph >= cfg("gate", {}).get(tier, 999):
            out.append(tier)
    return out


# ══════════════ 概览（组队副本卡一次拉取）══════════════

def _brief_fields(idx, pid, status, expire_in):
    p = game.PARTY[idx]
    return {"id": pid, "idx": idx, "name": p[0], "tier": p[1], "diff": p[2],
            "energy": p[3], "money": p[4], "drops": p[5],
            "dur": cfg("durH", {}).get(p[1], 8), "txt": game.PARTY_TXT.get(p[0], []),
            "status": status, "expire_in": expire_in}


def _brief(row):
    return _brief_fields(row["idx"], row["id"], row["status"],
                         max(0, row["expire_at"] - _now_ms()) if row["expire_at"] else 0)


def _view(row, uid):
    v = _brief(row)
    mem = db.party_members(row["id"])
    v["members"] = [{"uid": m["uid"], "name": m["name"] or "（未命名）", "status": m["status"],
                     "leader": m["uid"] == row["uid"], "actions_left": m["actions_left"],
                     "rate": round(m["rate"] * 100), "me": m["uid"] == uid,
                     "claim": m["claim"]} for m in mem]
    v["count"] = len([m for m in mem if m["status"] == "in"])
    v["goal"] = row["goal"]
    v["progress"] = row["progress"]
    v["started"] = row["started_at"]
    v["ends_at"] = row["ends_at"]
    v["leader"] = row["uid"] == uid
    v["invites"] = db.party_invites_sent(row["id"]) if (row["uid"] == uid and row["status"] == "open") else []
    v["can_start"] = (row["status"] == "open" and row["uid"] == uid
                      and v["count"] >= cfg("startMin", 3))
    mine = db.party_member_get(row["id"], uid)
    v["my_reward"] = (json.loads(mine["reward"]) if mine and mine["reward"] else None)
    v["my_claim"] = (mine["claim"] if mine else "")
    return v


def apply_refunds(uid, me_s):
    """把「未开启作废」的退还精力入账（本人请求的锁内调用）；返回提示文案列表"""
    out = []
    for r in db.party_refunds_pending(uid):
        if r["spent"]:
            me_s["energy"] = me_s.get("energy", 0) + r["spent"]
            name = game.PARTY[r["idx"]][0]
            game.add_log(me_s, "↩️ 组队副本「" + name + "」未开启作废——退还精力 " + str(r["spent"]), "gold")
            out.append("↩️「" + name + "」未开启已作废，退还精力 " + str(r["spent"]))
        db.party_member_set(r["party_id"], uid, refund=0)
    return out


def draw_offer(uid, me_s):
    """惰性抽当日 offer（只从本人可参与的品阶中随机）；无可参与品阶 → None"""
    tiers = _eligible_tiers(me_s)
    if not tiers:
        return None
    tier = random.choice(tiers)
    cands = [i for i, p in enumerate(game.PARTY) if p[1] == tier]
    idx = random.choice(cands)
    day = _day_key()
    pid = db.party_create(uid, idx, tier, game.PARTY[idx][2], day, _day_end_ms(day))
    return db.party_get(pid)


def overview(uid, me_s, msgs=None):
    now = _now_ms()
    notes = apply_refunds(uid, me_s)
    if msgs is not None:
        msgs.extend(notes)
    for x in db.party_running_expired(now):        # 兜底：本人相关/全局的到期副本按失败结算（幂等）
        _settle_row(x, ok=False)
    day = _day_key()
    row = db.party_offer_of_day(uid, day)
    if row is None and not db.party_leader_active(uid):
        row = draw_offer(uid, me_s)
    offer = None
    if row and row["day"] == day:
        offer = _brief(row)
    active = db.party_leader_active(uid) or db.party_member_active(uid)
    current = _view(active, uid) if active and active["status"] in ("open", "running") else None
    claims = []
    for c in db.party_claims_pending(uid):
        rw = json.loads(c["reward"] or "{}")
        claims.append({"pid": c["party_id"], "ok": bool(rw.get("ok")), "reward": rw,
                       "name": game.PARTY[c["idx"]][0]})
    # 邀请候选：好友优先 + 其他已命名账号（排除自己 / 已在队 / 已邀请 / 被拉黑）
    candidates = []
    if active and active["status"] == "open" and active["uid"] == uid:
        fid = set(db.friends_of(uid))
        in_party = {m["uid"] for m in db.party_members(active["id"])}
        invited = {x["uid"] for x in db.party_invites_sent(active["id"])}
        blocked = {b["uid"] for b in db.block_list_of(uid)}
        cand = [(i, True) for i in fid] + [(u["id"], False) for u in db.list_users()]
        seen = set()
        for uid2, fr in cand:
            if uid2 == uid or uid2 in seen or uid2 in in_party or uid2 in invited or uid2 in blocked:
                continue
            if db.is_blocked(uid, uid2):          # 对方拉黑了我 → 不出现在候选里
                continue
            u2 = db.get_user(uid2)
            if not u2 or not u2.get("name") or u2.get("migrated") or u2.get("banned"):
                continue
            seen.add(uid2)
            candidates.append({"uid": uid2, "name": u2["name"], "friend": fr,
                               "friend_code": u2.get("friend_code") or ""})
        candidates.sort(key=lambda x: (not x["friend"], x["name"]))
    invites = []
    lv, ph = _lv(me_s), game.prev_health_score(me_s)
    for inv in db.party_invites_of(uid):
        b = _brief_fields(inv["idx"], inv["party_id"], inv["p_status"], 0)
        b["leader_uid"] = inv["leader_uid"]
        b["leader_name"] = inv["leader_name"] or "（未命名）"
        b["gate_ok"] = (lv >= cfg("tierLv", {}).get(b["tier"], 9)
                        and ph >= cfg("gate", {}).get(b["tier"], 999))
        b["gate_txt"] = ("需 Lv" + str(cfg("tierLv", {}).get(b["tier"], 9))
                         + " · 昨日健康分 ≥" + str(cfg("gate", {}).get(b["tier"], 0)))
        invites.append(b)
    return {
        "offer": offer,
        "current": current,
        "invites": invites,
        "claims": claims,
        "candidates": candidates,
        "me": {"week_used": db.party_week_count(uid, _week_start_ms()),
               "week_max": cfg("weeklyMax", 3),
               "energy": me_s.get("energy", 0), "lv": lv, "score": ph,
               "unlock": lv >= cfg("unlockLv", 2),
               "can_tiers": _eligible_tiers(me_s)},
    }


def dot(uid):
    """委托页签红点：待处理邀请 + 待领取结算 + 进行中且还有行动次数"""
    n = len(db.party_invites_of(uid)) + len(db.party_claims_pending(uid))
    m = db.party_member_active(uid)
    if m and m["status"] == "running":
        mm = db.party_member_get(m["id"], uid)
        if mm and mm["actions_left"] > 0:
            n += 1
    return n


# ══════════════ 队伍动作 ══════════════

def _busy(uid, exclude_pid=None):
    la = db.party_leader_active(uid)
    if la and la["id"] != exclude_pid and la["status"] in ("open", "running"):
        return "你正在带领一支队伍——先解散或等它结束"
    ma = db.party_member_active(uid)
    if ma and ma["id"] != exclude_pid:
        return "你已在另一支队伍中——先退出"
    return None


def create(uid, me_s, msgs):
    """组建：offer → open（扣发起人精力）"""
    day = _day_key()
    row = db.party_offer_of_day(uid, day)
    if not row or row["status"] != "offer":
        return "今天没有可组建的副本——每天 08:00 刷新 1 个"
    busy = _busy(uid)
    if busy:
        return busy
    p = game.PARTY[row["idx"]]
    if _lv(me_s) < cfg("tierLv", {}).get(p[1], 9):
        return "等级不足——" + p[1] + "副本需 Lv" + str(cfg("tierLv", {}).get(p[1], 9))
    if me_s.get("energy", 0) < p[3]:
        return "精力不足（需要 " + str(p[3]) + "，当前 " + str(me_s.get("energy", 0)) + "）"
    if db.party_week_count(uid, _week_start_ms()) >= cfg("weeklyMax", 3):   # v1.67：组建同样计入周次数（原可绕过周限）
        return "本周参与次数已达上限（" + str(cfg("weeklyMax", 3)) + " 次）——下周再来"
    if not db.party_set_status(row["id"], "open", expect="offer"):
        return "该副本已处理过了"
    me_s["energy"] -= p[3]
    db.party_member_upsert(row["id"], uid, "in", _week_start_ms(), _rate_now(me_s, p[1]),
                           cfg("actions", 3), p[3])
    game.add_log(me_s, "⚔️ 发起了组队副本「" + p[0] + "」（" + p[1] + " · 已扣精力 " + str(p[3]) + "）", "gold")
    msgs.append("⚔️ 已组建「" + p[0] + "」——邀请好友，满 " + str(cfg("startMin", 3))
                + " 人即可开启（当日 24h 内有效）")
    return None


def invite(uid, to_uid, msgs):
    row = db.party_leader_active(uid)
    if not row or row["status"] != "open":
        return "当前没有可邀请的队伍——先组建"
    to = db.get_user(to_uid)
    if not to or not to.get("name"):
        return "账号不存在"
    if to_uid == uid:
        return "不能邀请自己"
    if db.is_blocked(to_uid, uid) or db.is_blocked(uid, to_uid):
        return "对方暂不接受邀请"
    busy = _busy(to_uid)
    if busy:
        return "对方已在别的队伍中"
    mem = db.party_members(row["id"])
    if len([m for m in mem if m["status"] == "in"]) >= cfg("sizeMax", 6):
        return "队伍已满（" + str(cfg("sizeMax", 6)) + " 人）"
    if db.party_member_get(row["id"], to_uid):
        return "对方已在本队中"
    db.party_invite_add(row["id"], to_uid)
    msgs.append("📨 已邀请「" + to["name"] + "」加入「" + game.PARTY[row["idx"]][0] + "」")
    return None


def accept(uid, me_s, pid, msgs):
    """接受邀请（确认弹窗在客户端）：扣精力入队；未开启作废时全额退还"""
    inv = db.party_invite_get(pid, uid)
    if not inv or inv["status"] != "pending":
        return "邀请不存在或已处理"
    row = db.party_get(pid)
    if not row or row["status"] != "open":
        return "该队伍已结束邀请"
    if row["expire_at"] and row["expire_at"] <= _now_ms():
        return "该副本已过期作废"
    busy = _busy(uid, exclude_pid=pid)
    if busy:
        return busy
    p = game.PARTY[row["idx"]]
    need_lv = cfg("tierLv", {}).get(p[1], 9)
    gate = cfg("gate", {}).get(p[1], 999)
    if _lv(me_s) < need_lv:
        return "你的等级不足（" + p[1] + "副本需 Lv" + str(need_lv) + "）"
    ph = game.prev_health_score(me_s)
    if ph < gate:
        return "你昨日健康分不足（需 ≥" + str(gate) + "，当前 " + str(ph) + "）"
    if db.party_week_count(uid, _week_start_ms()) >= cfg("weeklyMax", 3):
        return "本周参与次数已达上限（" + str(cfg("weeklyMax", 3)) + " 次）"
    mem = db.party_members(pid)
    if len([m for m in mem if m["status"] == "in"]) >= cfg("sizeMax", 6):
        return "队伍已满（" + str(cfg("sizeMax", 6)) + " 人）"
    if me_s.get("energy", 0) < p[3]:
        return "精力不足（需要 " + str(p[3]) + "，当前 " + str(me_s.get("energy", 0)) + "）"
    if not db.party_invite_set(pid, uid, "accepted", expect="pending"):
        return "邀请已处理过了"
    me_s["energy"] -= p[3]
    db.party_member_upsert(pid, uid, "in", _week_start_ms(), _rate_now(me_s, p[1]),
                           cfg("actions", 3), p[3])
    game.add_log(me_s, "⚔️ 加入组队副本「" + p[0] + "」（已扣精力 " + str(p[3]) + "）", "gold")
    msgs.append("🤝 已加入「" + p[0] + "」（已扣精力 " + str(p[3]) + "）——等队长开启")
    return None


def decline(uid, pid, msgs):
    if not db.party_invite_set(pid, uid, "declined", expect="pending"):
        return "邀请不存在或已处理"
    msgs.append("已婉拒了这次邀请")
    return None


def start(uid, msgs):
    row = db.party_leader_active(uid)
    if not row or row["status"] != "open":
        return "当前没有组建中的队伍"
    mem = [m for m in db.party_members(row["id"]) if m["status"] == "in"]
    if len(mem) < cfg("startMin", 3):
        return "至少 " + str(cfg("startMin", 3)) + " 人才能开启（当前 " + str(len(mem)) + " 人）"
    p = game.PARTY[row["idx"]]
    dur = cfg("durH", {}).get(row["tier"], 8)
    goal = _goal(len(mem))
    now = _now_ms()
    if not db.party_set_status(row["id"], "running", expect="open",
                               started_at=now, ends_at=now + dur * 3600000, goal=goal):
        return "该队伍已开启了"
    for inv in db.party_invites_sent(row["id"]):
        if inv["status"] == "pending":
            db.party_invite_set(row["id"], inv["uid"], "expired", expect="pending")
    msgs.append("🗡️「" + p[0] + "」出发！目标 " + str(goal) + " 格 · 限时 " + str(dur)
                + " 小时——每人 " + str(cfg("actions", 3)) + " 次行动，随时来掷")
    return None


def act(uid, msgs):
    """掷一次（随时掷、可连掷）"""
    row = db.party_member_active(uid)
    if not row or row["status"] != "running":
        return "当前没有进行中的副本"
    if row["ends_at"] and row["ends_at"] <= _now_ms():
        _settle_row(row, ok=False)
        return "副本已到时限——按失败结算（安慰奖待领取）"
    m = db.party_member_get(row["id"], uid)
    if m["actions_left"] <= 0:
        return "你的行动次数已用完——等队友或到时限结算"
    rate = m["rate"]
    roll = game.rand(100)
    ok = roll <= round(rate * 100)
    gain = (2 if roll <= cfg("critRoll", 5) else 1) if ok else 0
    if not db.party_member_set(row["id"], uid, expect="in", actions_left=m["actions_left"] - 1):
        return "行动失败——请重试"
    res = db.party_add_progress(row["id"], gain)
    if res is None:
        return "副本状态已变化——请刷新查看"
    title = "大成功！" if (ok and gain == 2) else ("成功" if ok else "失败")
    msgs.append("🎲 掷出 " + str(roll) + "（成功率 " + str(round(rate * 100, 1)) + "%）→ " + title
                + "　+" + str(gain) + " 格（" + str(res["progress"]) + " / " + str(res["goal"]) + "）")
    if res["progress"] >= res["goal"]:
        _settle_row(db.party_get(row["id"]), ok=True)
        msgs.append("🏆 目标达成——副本通关！结算奖励已放入「组队副本」面板（离线队友下次打开时领取）")
    return None


def quit_party(uid, msgs):
    row = db.party_member_active(uid)
    if not row:
        return "当前没有进行中的队伍"
    if row["uid"] == uid:
        return "队长不能中途退出——带队撑到时限结算（未开启前可解散）"
    if row["status"] == "open":
        # 组建中退出：视同该成员被解散——退还精力、周次数不再计入
        db.party_member_set(row["id"], uid, expect="in", status="refunded", refund=1)
        msgs.append("🚪 已退出「" + game.PARTY[row["idx"]][0] + "」——精力与本周次数将退还")
        return None
    if row["status"] != "running":
        return "当前没有进行中的队伍"
    if not db.party_member_set(row["id"], uid, expect="in", status="quit"):
        return "已处理过了"
    msgs.append("🚪 已退出「" + game.PARTY[row["idx"]][0] + "」——中途退出无奖励、不退精力")
    return None


def abandon(uid, msgs):
    """解散组建中的队伍（未开启：全体退还精力与本周次数）"""
    row = db.party_leader_active(uid)
    if not row or row["status"] != "open":
        return "当前没有可解散的队伍"
    _refund_members(row)
    db.party_set_status(row["id"], "abandoned", expect="open")
    msgs.append("已解散「" + game.PARTY[row["idx"]][0] + "」——队员的精力与本周次数已退还")
    return None


def offer_abandon(uid, msgs):
    """放弃今日 offer（无消耗、无惩罚）"""
    row = db.party_offer_of_day(uid, _day_key())
    if not row or row["status"] != "offer":
        return "今天没有可放弃的副本"
    db.party_set_status(row["id"], "abandoned", expect="offer")
    msgs.append("已放弃今日副本——明天 08:00 刷新新的")
    return None


def claim(uid, me_s, pid, msgs):
    m = db.party_member_get(pid, uid)
    if not m or m["claim"] != "pending":
        return "没有待领取的结算"
    rw = json.loads(m["reward"] or "{}")
    if not db.party_member_set(pid, uid, expect="in", claim="claimed"):
        return "已领取过了"
    if rw.get("money"):
        me_s["money"] = me_s.get("money", 0) + int(rw["money"])
    for k, n in (rw.get("mats") or {}).items():
        me_s.setdefault("mats", {})
        me_s["mats"][k] = me_s["mats"].get(k, 0) + int(n)
    name = game.PARTY[db.party_get(pid)["idx"]][0]
    parts = [k + "×" + str(n) for k, n in (rw.get("mats") or {}).items()]
    if rw.get("money"):
        parts.insert(0, game.fmt_money(int(rw["money"])))
    game.add_log(me_s, "🏆 组队副本「" + name + "」结算：" + ("、".join(parts) or "无"), "gold")
    msgs.append("🏆 已领取「" + name + "」结算奖励：" + ("、".join(parts) or "无"))
    return None


# ══════════════ 结算 ══════════════

def _roll_reward(p, ok):
    """一份奖励（全员相同）：成功 = 报酬 + 掉表（首项必得、其余按品阶掉率或标注概率）；
       失败 = 安慰奖（必得材料 ≈1/4 数量，无报酬、不判定概率项）"""
    money = int(p[4]) if ok else 0
    mats = {}
    for i, k in enumerate(p[5].keys()):
        v = p[5][k]
        key = k
        if key.startswith("@"):
            grp = game.PARTY_GROUPS.get(key[1:]) or []
            if not grp:
                continue
            key = random.choice(grp)
        if not ok:
            if len(v) > 2:
                continue                        # 失败：概率项不判定
            n = max(1, int(round(game.roll_qty(v[0], v[1]) * cfg("failAid", 0.25))))
            mats[key] = mats.get(key, 0) + n
            continue
        prob = 1.0 if i == 0 else (v[2] if len(v) > 2 else game.mat_drop_rate(key))
        if i == 0 or random.random() < min(1, prob):
            n = game.roll_qty(v[0], v[1])
            mats[key] = mats.get(key, 0) + n
    return money, mats


def _settle_row(row, ok):
    """结算（幂等）：给全体在队成员写 reward + claim=pending；状态 done / failed"""
    if not db.party_set_status(row["id"], "done" if ok else "failed", expect="running", settled=1):
        return False
    money, mats = _roll_reward(game.PARTY[row["idx"]], ok)
    rw = json.dumps({"ok": bool(ok), "money": money, "mats": mats}, ensure_ascii=False)
    for m in db.party_members(row["id"]):
        if m["status"] == "in" and not m["claim"]:
            db.party_member_set(row["id"], m["uid"], reward=rw, claim="pending")
    return True


def _refund_members(row):
    """未开启即作废：全体成员记 refund=1（待本人下次打开时退还精力）；周次数同步不再计入"""
    for m in db.party_members(row["id"]):
        if m["status"] == "in":
            db.party_member_set(row["id"], m["uid"], status="refunded", refund=1)


# ══════════════ global_sweep：到期结算 ══════════════

def sweep_party(now_ms=None):
    """到期结算（幂等）：offer/open 过期作废（组建过的退还精力）；running 到期按失败结算。
       返回处理条数"""
    now = int(now_ms if now_ms is not None else _now_ms())
    n = 0
    for row in db.party_expired_unstarted(now):
        if db.party_set_status(row["id"], "expired", expect=row["status"]):
            if row["status"] == "open":
                _refund_members(row)
            n += 1
    for row in db.party_running_expired(now):
        if _settle_row(row, ok=False):
            n += 1
    return n


sweep.register(sweep_party)
