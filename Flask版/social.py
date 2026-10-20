# -*- coding: utf-8 -*-
"""v1.64（社交 P1）：好友系统 + 邮件系统（赠送底座）业务逻辑

- 仅存在于 Flask 版：原型保持单机、体验版不含社交层（见 11_社交与协作.md 11.1）
- 数据落库在 db.py（friend_edge / friend_req / block_list / mail）；本模块负责规则与结算
- 退回不直接改对方存档：拒收 / 超时都生成一封「退回邮件」（kind=return），由本人开箱领取——
  避免跨账号写档的并发丢更新（一切存档修改都发生在本人请求的互斥锁内）
- global_sweep 处理器：到期邮件（赠送 7 天未接收 → 退回邮件；普通邮件 30 天过期）
"""
import time
from datetime import datetime, timedelta

import db
import game
import sweep

LOW_TIERS = ("普通", "精良", "稀有")
HIGH_TIERS = ("史诗", "传说")
TIER_GATE_DEFAULT = {"普通": 0, "精良": 0, "稀有": 2, "史诗": 3, "传说": 4}   # 接收方最低等级（1 基）


def cfg(key, default):
    return (game.CFG.get("social") or {}).get(key, default)


def _now_ms():
    return int(time.time() * 1000)


def _day_start_ms(now=None):
    """v1.73：与游戏日同口径（06:00 日界线）——避免 00:00~05:59 重复领取每日额度。"""
    d = now or datetime.now()
    gd = datetime.strptime(game.today_str(d), "%Y-%m-%d").replace(hour=game.DAY_CUTOFF_HOUR)
    return int(gd.timestamp() * 1000)


def _week_start_ms(now=None):
    d = now or datetime.now()
    gd = datetime.strptime(game.today_str(d), "%Y-%m-%d")
    gd -= timedelta(days=gd.weekday())        # 游戏日所在周的周一 06:00
    gd = gd.replace(hour=game.DAY_CUTOFF_HOUR)
    return int(gd.timestamp() * 1000)


def _lv(s):
    return int(s.get("lv_idx", 0)) + 1


def _tier(mat):
    return (game.M.get(mat) or ["", ""])[1]


def _load(uid):
    raw, _ = db.load_user_state(uid)
    return game.migrate_state(raw) if raw else game.new_state()


def _week_avg(s):
    """本周均值：最近 7 个已结算日 + 今日实时分"""
    vals = [h.get("score", 0) for h in (s.get("history") or [])[-7:]]
    vals.append(game.calc_health(s))
    return round(sum(vals) / len(vals), 1) if vals else 0


def _is_high(mat):
    return _tier(mat) in HIGH_TIERS


def _low_gift_used(uid):
    """今日已用的普通 / 精良 / 稀有赠送额度（个·合计）——被拒收 / 超时退回的不占；史诗 / 传说不占。
    v1.66a：社交页计数（展示）与 gift_send（拦截）共用本函数，保证两处口径完全一致"""
    return sum(r["qty"] for r in db.gift_rows_since(uid, _day_start_ms())
               if not _is_high(r["mat"]) and r["status"] not in ("declined", "expired"))


# ══════════════ 概览（社交页一次拉取）══════════════

def _card(u, s, with_health):
    card = {"uid": u["id"], "name": u["name"], "lv": _lv(s), "last_login": u.get("last_login", 0),
            "friend": False, "health": None, "public": bool(u.get("health_public"))}
    if with_health and u.get("health_public"):
        # v1.73（P0-1）：单个玩家的脏档不得拖垮整张社交页——健康分异常只影响这一行
        try:
            card["health"] = {"today": game.calc_health(s), "week": _week_avg(s)}
        except Exception:
            card["health"] = {"today": 0, "week": 0, "error": True}
    return card


def overview(me_uid):
    me = db.get_user(me_uid)
    day0, week0 = _day_start_ms(), _week_start_ms()
    friend_ids = db.friends_of(me_uid)
    # v1.73（P2）：账号列表 + 存档各查一次（原实现每个好友 / 玩家 / 邮件发件人各查一次 → N+1）
    users = db.list_users()
    by_id = {u["id"]: u for u in users}
    need = set(by_id) | set(friend_ids) | {me_uid}
    raw_states = db.load_user_states(need)

    def state_of(uid):
        raw, _ = raw_states.get(uid, (None, False))
        return game.migrate_state(raw) if raw else game.new_state()

    me_s = state_of(me_uid)
    friends = []
    for fid in friend_ids:
        u = by_id.get(fid) or db.get_user(fid)
        if not u or u.get("banned"):
            continue
        c = _card(u, state_of(fid), True)
        c["friend"] = True
        friends.append(c)
    players = []
    for u in users:
        if u["id"] == me_uid or not u.get("name") or u.get("migrated") or u.get("banned"):
            continue
        c = _card(u, state_of(u["id"]), True)
        c["friend"] = u["id"] in friend_ids
        players.append(c)
    # 健康榜（仅公开者）：含自己（自己对自己可见）
    # v1.71b：好友单独并入榜单——好友即使不满足 players 的过滤条件（如迁移标记），
    #          只要公开了健康分也应可见；按 uid 去重，好友优先于公开玩家。
    board = []
    seen = set()

    def _board_add(c):
        if c.get("health") and c["uid"] not in seen:
            seen.add(c["uid"])
            board.append(c)

    try:
        _me_health = {"today": game.calc_health(me_s), "week": _week_avg(me_s)}
    except Exception:
        _me_health = {"today": 0, "week": 0, "error": True}
    me_card = {"uid": me_uid, "name": me.get("name") or "我", "lv": _lv(me_s),
               "health": _me_health}
    _board_add(me_card)
    for c in friends:
        _board_add(c)
    for c in players:
        _board_add(c)
    # 邮件（近 60 条）
    mails = []
    for m in db.mail_list(me_uid):
        frm = ""
        if m.get("from_uid"):
            fu = by_id.get(m["from_uid"])
            frm = (fu or {}).get("name") or "已注销的冒险者"
        mails.append({"id": m["id"], "kind": m["kind"], "from": frm, "from_uid": m["from_uid"],
                      "title": m["title"], "body": m["body"], "mat": m["mat"], "qty": m["qty"],
                      "money": m["money"], "status": m["status"],
                      "created": m["created_at"], "expire": m["expire_at"]})
    # 额度
    low_today = _low_gift_used(me_uid)      # v1.66a：按「个」合计；与 gift_send 拦截同一函数、同一口径
    sent_high, recv_high = gift_high_state(me_uid)   # v1.67：高阶同样按「个」；接收 = 已收 + 待收（与拦截同口径）
    return {
        "me": {
            "uid": me_uid, "friend_code": me.get("friend_code") or "",
            "settings": {"health_public": bool(me.get("health_public")),
                         "gift_perm": me.get("gift_perm") or "friends",
                         "req_perm": me.get("req_perm") or "allow"},
            "quotas": {
                "gift_low_today": low_today, "gift_low_max": cfg("giftLowDaily", 5),
                "gift_high_sent": sent_high, "gift_high_recv": recv_high,
                "gift_high_max": cfg("giftHighWeekly", 2),
                "req_today": db.friend_req_count_since(me_uid, day0),
                "req_max": cfg("friendReqDaily", 10),
            },
            "friend_count": len(friend_ids), "friend_max": cfg("friendMax", 30),
        },
        "friends": friends,
        "players": players,
        "reqs": db.friend_req_list(me_uid),
        "blocked": [{"uid": r["uid"], "name": r["name"] or ""} for r in db.block_list_of(me_uid)],
        "mail": mails,
        "board": board,
    }


def dot(uid):
    """页签红点：待处理好友申请 + 未读 / 待接收邮件"""
    reqs = len(db.friend_req_list(uid)["in"])
    return reqs + db.mail_dot(uid)


# ══════════════ 好友 ══════════════

def friend_add(me_uid, ident, msg, msgs):
    ident = (ident or "").strip()
    if not ident:
        return "请输入好友码或冒险者之名"
    target = None
    norm = "".join(ch for ch in ident.upper() if ch.isalnum())
    if len(norm) == 8:
        target = db.get_user_by_friend_code(norm)
    if not target:
        target = db.get_user_by_name(ident)
    if not target:
        return "没有找到这个好友码或冒险者之名——核对一下再试"
    if target["id"] == me_uid:
        return "不能添加自己为好友"
    if not target["name"]:
        return "该账号还没有冒险者之名"
    if db.is_friend(me_uid, target["id"]):
        msgs.append("你们已经是好友了")
        return None
    if db.is_blocked(me_uid, target["id"]):
        return "对方暂时无法接收好友申请"
    if (target.get("req_perm") or "allow") == "off":
        return "对方关闭了好友申请"
    if db.friend_req_pending(me_uid, target["id"]):
        return "申请已发送过了，等待对方处理"
    if db.friend_req_pending(target["id"], me_uid):
        return "对方已向你发来申请——到「待处理」里同意即可"
    if len(db.friends_of(me_uid)) >= cfg("friendMax", 30):
        return "你的好友位已满（" + str(cfg("friendMax", 30)) + " 位）"
    if db.friend_req_count_since(me_uid, _day_start_ms()) >= cfg("friendReqDaily", 10):
        return "今天发送的好友申请已达上限（" + str(cfg("friendReqDaily", 10)) + " 次）"
    db.friend_req_create(me_uid, target["id"], msg)
    msgs.append("📨 好友申请已发送给「" + target["name"] + "」")
    return None


def friend_op(me_uid, req_id, op, msgs):
    r = db.friend_req_get(req_id)
    if not r or r["status"] != "pending":
        return "该申请不存在或已处理"
    fmax = cfg("friendMax", 30)
    if op == "accept":
        if r["to_uid"] != me_uid:
            return "只能处理发给自己的申请"
        if len(db.friends_of(me_uid)) >= fmax:
            return "你的好友位已满（" + str(fmax) + " 位）"
        if len(db.friends_of(r["from_uid"])) >= fmax:
            return "对方的好友位已满，暂时无法成为好友"
        if not db.friend_req_set(req_id, "accepted"):
            return "该申请已处理过了"
        db.friend_add_pair(me_uid, r["from_uid"])
        fu = db.get_user(r["from_uid"])
        msgs.append("🤝 已和「" + ((fu or {}).get("name") or "对方") + "」成为好友")
        return None
    if op == "reject":
        if r["to_uid"] != me_uid:
            return "只能处理发给自己的申请"
        if not db.friend_req_set(req_id, "rejected"):
            return "该申请已处理过了"
        msgs.append("已拒绝该好友申请")
        return None
    return "未知操作"


def friend_del(me_uid, uid, msgs):
    u = db.get_user(uid)
    if not u:
        return "账号不存在"
    db.friend_remove_pair(me_uid, uid)
    msgs.append("已与「" + (u["name"] or "对方") + "」解除好友关系")
    return None


def friend_block(me_uid, uid, on, msgs):
    if uid == me_uid:
        return "不能拉黑自己"
    u = db.get_user(uid)
    if not u:
        return "账号不存在"
    if on:
        db.block_add(me_uid, uid)
        db.friend_remove_pair(me_uid, uid)
        db.friend_req_cancel_between(me_uid, uid)
        msgs.append("🚫 已拉黑「" + (u["name"] or "对方") + "」（双方好友关系与待处理申请已解除）")
    else:
        db.block_remove(me_uid, uid)
        msgs.append("已解除拉黑")
    return None


def privacy_set(me_uid, d, msgs):
    sets = []
    hp = d.get("health")
    if hp is not None:
        db.set_health_public(me_uid, bool(hp))
        sets.append("健康分公开：" + ("开" if hp else "关"))
    gp = d.get("gift")
    if gp in ("friends", "all", "off"):
        db.set_pref(me_uid, "gift_perm", gp)
        sets.append("赠送权限：" + {"friends": "仅好友", "all": "全部人", "off": "关闭"}[gp])
    rp = d.get("req")
    if rp in ("allow", "off"):
        db.set_pref(me_uid, "req_perm", rp)
        sets.append("好友申请：" + ("允许" if rp == "allow" else "关闭"))
    if sets:
        msgs.append("⚙️ " + " · ".join(sets))
    return None


# ══════════════ 赠送 / 邮件 ══════════════

def gift_high_state(uid, now=None):
    """uid 的本周（史诗+传说）送出 / 接收**数量（个）**（接收 = 已接受 + 待接收排队）
       v1.67：口径由「笔」改「个」（与低阶一致）；展示与拦截共用本函数"""
    week0 = _week_start_ms(now)
    sent = sum(r["qty"] for r in db.gift_rows_since(uid, week0)
               if _is_high(r["mat"]) and r["status"] not in ("declined", "expired"))
    recv = sum(r["qty"] for r in db.gift_received_rows_since(uid, week0) if _is_high(r["mat"]))
    pend = sum(r["qty"] for r in db.gift_pending_for(uid) if _is_high(r["mat"]))
    return sent, recv + pend


def gift_send(me_uid, me_s, to_uid, mat, qty, msgs):
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        return "数量不正确"
    if not game.M.get(mat):
        return "只能赠送材料（道具 / 装备 / 图纸不可流通）"
    qmax = cfg("giftLowQtyMax", 50)
    if qty < 1 or qty > qmax:
        return "单次数量须为 1~" + str(qmax) + " 个"
    to = db.get_user(to_uid)
    if not to or not to["name"]:
        return "对方账号不存在"
    if to_uid == me_uid:
        return "不能给自己赠送"
    if db.is_blocked(me_uid, to_uid):
        return "对方暂不接受你的赠送"
    perm = to.get("gift_perm") or "friends"
    if perm == "off":
        return "对方已关闭赠送"
    if perm == "friends" and not db.is_friend(me_uid, to_uid):
        return "对方只接收好友的赠送——先加个好友吧"
    tier = _tier(mat)
    gate = (game.CFG.get("social") or {}).get("giftUnlockGate", TIER_GATE_DEFAULT)
    to_s = _load(to_uid)
    need = gate.get(tier, 0)
    if _lv(to_s) < need:
        return "对方尚未解锁该材料的获取途径（" + tier + "材料需 Lv" + str(need) + "）——不能赠送"
    if _is_high(mat):
        hmax = cfg("giftHighWeekly", 2)          # v1.67：按「个」计——周送出 ≤2 个、接收 ≤2 个
        sent, _ = gift_high_state(me_uid)
        if sent + qty > hmax:
            if sent >= hmax:
                return "本周史诗 / 传说赠送（送出）已达上限（每周共 " + str(hmax) + " 个）"
            return ("本周史诗 / 传说赠送上限为 " + str(hmax) + " 个（已送 " + str(sent)
                    + " 个，本次 " + str(qty) + " 个）")
        _, recv_queued = gift_high_state(to_uid)
        if recv_queued + qty > hmax:
            return "对方本周可接收的史诗 / 传说已达上限（每周共 " + str(hmax) + " 个）"
    else:
        lmax = cfg("giftLowDaily", 5)           # v1.66a：普通/精良/稀有 = 每日合计数量上限（个）
        used = _low_gift_used(me_uid)
        if qty > lmax:
            return "单次最多 " + str(lmax) + " 个（每日合计上限 " + str(lmax) + " 个）"
        if used + qty > lmax:
            return "今日赠送数量已达上限（每日共 " + str(lmax) + " 个，已送 " + str(used) + " 个）"
    have = (me_s.get("mats") or {}).get(mat, 0)
    if have < qty:
        return "背包里的「" + mat + "」不足（现有 " + str(have) + " 个）"
    # 托管：先从背包扣除，放入对方邮箱（待接收）
    me_s["mats"][mat] = have - qty
    if me_s["mats"][mat] <= 0:
        del me_s["mats"][mat]
    days = cfg("giftExpireDays", 7)
    db.mail_create(to_uid, "gift", from_uid=me_uid,
                   title="来自「" + (me_s.get("name") or "冒险者") + "」的赠送",
                   body=mat + " ×" + str(qty),
                   mat=mat, qty=qty, expire_at=_now_ms() + days * 86400000)
    game.add_log(me_s, "🎁 赠送「" + to["name"] + "」" + mat + "×" + str(qty) + "（待接收，"
                 + str(days) + " 天未接收自动退回）", "gold")
    msgs.append("🎁 已送出 " + mat + "×" + str(qty) + " 给「" + to["name"] + "」——等待对方接收")
    return None


def _return_via_mail(m, why):
    """退回不直接写对方存档——生成一封「退回邮件」（kind=return），由本人开箱领取。
       幂等由调用方状态机保证（每封赠送最多触发一次退回）"""
    if not m.get("from_uid"):
        return
    if why == "expire":
        title = "↩️ 赠送超时退回"
        body = "对方 7 天内未接收——" + m["mat"] + " ×" + str(m["qty"]) + " 已退回，请领取。"
    else:
        _to = (db.get_user(m["uid"]) or {}).get("name") or "对方"
        title = "↩️ 赠送被拒收"
        body = "「" + _to + "」拒收了你的赠送——" + m["mat"] + " ×" + str(m["qty"]) + " 已退回，请领取。"
    db.mail_create(m["from_uid"], "return", title=title, body=body,
                   mat=m["mat"], qty=m["qty"], money=m.get("money", 0), expire_at=0)


def mail_op(me_uid, me_s, mail_id, op, msgs):
    if op == "read_all":                      # v1.67：一键已读不校验单封（原 UI 调用不带 id → 恒返回「邮件不存在」，红点不消）
        db.mail_read_all(me_uid)
        return None
    m = db.mail_get(mail_id)
    if not m or m["uid"] != me_uid:
        return "邮件不存在"
    if op == "read":
        db.mail_set_status(mail_id, "read", expect="unread")
        return None
    if op in ("claim", "decline"):
        if m["kind"] == "system" or not (m.get("mat") or m.get("money")):
            return "该邮件没有需要处理的附件"
        if m["status"] != "pending":
            return "该邮件已处理过了"
        if op == "decline":
            if m["kind"] != "gift":
                return "该邮件无需拒收（直接领取即可）"
            if m["expire_at"] and m["expire_at"] <= _now_ms():
                if db.mail_set_status(mail_id, "expired", expect="pending"):
                    _return_via_mail(m, "expire")
                return "该赠送已超时——材料已退回寄件人"
            if not db.mail_set_status(mail_id, "declined", expect="pending"):
                return "该赠送已处理过了"
            _return_via_mail(m, "decline")
            msgs.append("已拒收「" + m["mat"] + " ×" + str(m["qty"]) + "」——材料已原路退回")
            return None
        # 领取（接受赠送 / 领取退回件 / 未来领取货款）
        if m["kind"] == "gift":
            if m["expire_at"] and m["expire_at"] <= _now_ms():
                if db.mail_set_status(mail_id, "expired", expect="pending"):
                    _return_via_mail(m, "expire")
                return "该赠送已超时——材料已退回寄件人"
            # 复核接收方门槛与额度（发送后接收方等级 / 额度可能变化）
            tier = _tier(m["mat"])
            gate = (game.CFG.get("social") or {}).get("giftUnlockGate", TIER_GATE_DEFAULT)
            if _lv(me_s) < gate.get(tier, 0):
                return "你尚未解锁该材料的获取途径（" + tier + "材料需 Lv" + str(gate.get(tier, 0)) + "）"
            if _is_high(m["mat"]):
                hmax = cfg("giftHighWeekly", 2)  # v1.67：按「个」复核
                recv = sum(r["qty"] for r in db.gift_received_rows_since(me_uid, _week_start_ms())
                           if _is_high(r["mat"]))
                if recv + m["qty"] > hmax:
                    return "你本周接收的史诗 / 传说已达上限（每周共 " + str(hmax) + " 个）——可拒收退回"
        if not db.mail_set_status(mail_id, "claimed", expect="pending"):
            return "该邮件已处理过了"
        _got = []
        if m.get("mat") and m.get("qty"):
            me_s.setdefault("mats", {})
            me_s["mats"][m["mat"]] = me_s["mats"].get(m["mat"], 0) + m["qty"]
            _got.append(m["mat"] + " ×" + str(m["qty"]))
        if m.get("money"):
            me_s["money"] = me_s.get("money", 0) + m["money"]
            _got.append("货款 " + game.fmt_money(m["money"]))
        game.add_log(me_s, "🎁 领取了「" + "、".join(_got) + "」", "gold")   # v1.67：货款邮件不再显示「 ×0」
        msgs.append("🎁 已领取 " + "、".join(_got))
        return None
    return "未知操作"


# ══════════════ global_sweep：邮件到期 ══════════════

def sweep_mail(now_ms=None):
    """到期邮件结算（幂等）：
       - 待接收赠送超时 → 生成退回邮件（status → expired）
       - 未读 / 已读普通邮件超时 → expired（无附件）
       返回处理条数"""
    n = 0
    for m in db.mail_expired(int(now_ms if now_ms is not None else _now_ms())):
        if m["kind"] == "gift" and m["status"] == "pending":
            if db.mail_set_status(m["id"], "expired", expect="pending"):
                _return_via_mail(m, "expire")
                n += 1
        elif m["status"] in ("unread", "read"):
            if db.mail_set_status(m["id"], "expired", expect=m["status"]):
                n += 1
    return n


sweep.register(sweep_mail)
