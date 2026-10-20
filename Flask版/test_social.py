# -*- coding: utf-8 -*-
"""社交测试（v1.62 P0 + v1.64 P1）：python test_social.py
   P0：本机免注册直通 / 邀请码注册（远程）/ 邀请码生命周期 / 昵称唯一（注册+改名）/
       好友码（生成·重置·回填）/ 封禁 / 服主工具（/admin 仅本机）/ global_sweep 骨架
   P1：好友（申请·通过·拒绝·拉黑·上限）/ 赠送（托管·领取·拒收退回·额度·品阶门槛）/
       邮件（已读·广播·私有性）/ 到期 sweep（幂等）/ 隐私（健康分公开）"""
import sys
from contextlib import closing
from pathlib import Path

import app as appmod
import db
import game
import social as socmod
import sweep

PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  ❌ " + msg)


# 独立临时库（v1.62：放在 data/test_run/ 子树——每日备份/损坏存档同样隔离在此，不碰正式 data/）
db.DB_PATH = Path(__file__).parent / "data" / "test_run" / "test_social.db"
if db.DB_PATH.exists():
    db.DB_PATH.unlink()

REMOTE = {"REMOTE_ADDR": "10.0.0.9"}
KEY = appmod.ACCESS_KEY


def remote_client():
    """新远程设备：过口令门（?k=）→ 拿 gp_key cookie，未注册"""
    c = appmod.app.test_client()
    c.get("/register?k=" + KEY, environ_base=REMOTE)
    return c


print("=== 1. 本机免注册直通（旧行为保留）===")
cl = appmod.app.test_client()
j = cl.get("/api/state").get_json()
check(j["ok"] and j["state"]["name"] == "", "本机新设备静默建号（空档）")
check(len(db.list_users()) == 1, "仅 1 个账号")

print("=== 2. 远程新设备 → 注册闸门 ===")
c = remote_client()
r = c.get("/api/state", environ_base=REMOTE)
check(r.status_code == 401 and (r.get_json() or {}).get("register"), "未注册远程设备 API 返回 401/register")
r = c.get("/", environ_base=REMOTE)
check(r.status_code == 302 and "/register" in r.headers.get("Location", ""), "页面重定向到注册页")
r = c.get("/register", environ_base=REMOTE)
check(r.status_code == 200 and "邀请码" in r.get_data(as_text=True), "注册页含邀请码输入框")

print("=== 3. 邀请码生命周期（校验→消耗→耗尽）===")
code = db.create_invite_code(uses=2, hours=72, note="测试")
check(isinstance(code, str) and len(code) == 8, "生成 8 位邀请码")
check(db.invite_error(code) is None, "新码可用")
r = c.post("/register", data={"nick": "甲", "invite": code}, environ_base=REMOTE)
check("至少 2 个字" in r.get_data(as_text=True), "过短昵称被拒")
check(db.invite_error(code) is None, "被拒的注册不消耗邀请码（昵称先于邀请码校验）")
r = c.post("/register", data={"nick": "阿远", "invite": "ZZZZZZZZ"}, environ_base=REMOTE)
check("邀请码不存在" in r.get_data(as_text=True), "错误邀请码被拒")
r = c.post("/register", data={"nick": "阿远", "invite": code}, environ_base=REMOTE)
check(r.status_code == 302, "注册成功跳转 /")
j = c.get("/api/state", environ_base=REMOTE).get_json()
check(bool(j and j["ok"] and j["state"]["name"] == "阿远"), "注册后直接进入游戏，昵称已设定")
row = [v for v in db.list_invite_codes() if v["code"] == code][0]
check(row["uses_left"] == 1, "邀请码剩余 2 → 1")

print("=== 4. 昵称唯一（注册侧 + 改名侧 + 大小写）===")
c2 = remote_client()
r = c2.post("/register", data={"nick": "阿远", "invite": code}, environ_base=REMOTE)
check("已经有人用了" in r.get_data(as_text=True), "重名注册被拒")
row = [v for v in db.list_invite_codes() if v["code"] == code][0]
check(row["uses_left"] == 1, "重名注册不消耗邀请码")
r = c2.post("/register", data={"nick": "阿远2", "invite": code}, environ_base=REMOTE)
check(r.status_code == 302, "第二人注册成功（消耗最后 1 次）")
c3 = remote_client()
r = c3.post("/register", data={"nick": "第三人", "invite": code}, environ_base=REMOTE)
check("已用完" in r.get_data(as_text=True), "用完的邀请码被拒")
j = c.post("/api/action", json={"action": "name", "name": "阿远2"}, environ_base=REMOTE).get_json()
check((not j["ok"]) and "已经有人用了" in (j.get("error") or ""), "改名撞车被拒")
j = c.post("/api/action", json={"action": "name", "name": "x"}, environ_base=REMOTE).get_json()
check((not j["ok"]) and "至少 2 个字" in (j.get("error") or ""), "改名过短被拒")
j = c.post("/api/action", json={"action": "name", "name": "远行客"}, environ_base=REMOTE).get_json()
check(j["ok"] and j["state"]["name"] == "远行客", "正常改名成功")
cl_a = appmod.app.test_client()
r = cl_a.post("/register", data={"nick": "Alice"})
check(r.status_code == 302, "本机直接注册（免邀请码）")
cl_a.set_cookie("gp_key", KEY)      # P1：Alice 走 ract（远程环境）时需带口令门 cookie
cl_b = appmod.app.test_client()
r = cl_b.post("/register", data={"nick": "alice"})
check("已经有人用了" in r.get_data(as_text=True), "大小写不同视为重名")

print("=== 5. 好友码（生成 / 重置 / 回填）===")
users = db.list_users()
fcs = [u["friend_code"] for u in users]
check(all(len(fc or "") == 8 for fc in fcs), "所有账号都有 8 位好友码")
check(len(set(fcs)) == len(fcs), "好友码互不相同")
check(all(fc != u["code"] for fc, u in zip(fcs, users)), "好友码与接入码独立")
old_fc = fcs[0]
new_fc = db.reset_friend_code(users[0]["id"])
check(bool(new_fc) and new_fc != old_fc and len(new_fc) == 8, "重置好友码生效")
with closing(db.conn()) as cc:
    cc.execute("UPDATE users SET friend_code = ''")
    cc.commit()
n = db.ensure_friend_codes()
check(n == len(users), "清空后回填全部好友码（%d 个）" % len(users))
users2 = db.list_users()
check(all(u["friend_code"] for u in users2)
      and len({u["friend_code"] for u in users2}) == len(users2), "回填后仍齐全且互不相同")

print("=== 6. 封禁 ===")
uid = [u for u in db.list_users() if u["name"] == "远行客"][0]["id"]
db.set_banned(uid, True)
r = c.get("/api/state", environ_base=REMOTE)
check(r.status_code == 403 and (r.get_json() or {}).get("banned"), "封禁账号 API 被拒")
r = c.get("/", environ_base=REMOTE)
check(r.status_code == 403, "封禁账号页面被拒")
db.set_banned(uid, False)
r = c.get("/api/state", environ_base=REMOTE)
check(r.status_code == 200, "解封后恢复访问")

print("=== 7. 服主工具（/admin 仅本机 + token）===")
cl2 = appmod.app.test_client()
r = cl2.get("/admin")
check(r.status_code == 403, "本机但无 token → 服主工具被拒（v1.73）")
r = cl2.get("/admin?token=" + appmod.ADMIN_TOKEN)
check(r.status_code == 302, "token 换 cookie → 重定向")
r = cl2.get("/admin")
check(r.status_code == 200 and "邀请码" in r.get_data(as_text=True), "本机 + token 可开服主工具")
r = remote_client().get("/admin?token=" + appmod.ADMIN_TOKEN, environ_base=REMOTE)
check(r.status_code == 403, "远程访问服主工具被拒（即使带 token）")
r = cl2.post("/admin/invite/new", data={"uses": "2", "hours": "24", "note": "服主工具测试"})
check(r.status_code == 302, "服主生成邀请码（表单）")
top = db.list_invite_codes()[0]
check(top["note"] == "服主工具测试" and top["uses_left"] == 2, "邀请码参数生效")
cl2.post("/admin/invite/revoke", data={"code": top["code"]})
check("吊销" in (db.invite_error(top["code"]) or ""), "吊销后不可用")
r = remote_client().post("/admin/invite/new", data={"uses": "1", "hours": "1"}, environ_base=REMOTE)
check(r.status_code == 403, "远程操作服主工具被拒")
u0 = db.list_users()[0]
fc_before = u0["friend_code"]
r = cl2.post("/admin/account/op", data={"id": str(u0["id"]), "op": "friend"})
check(r.status_code == 302 and db.list_users()[0]["friend_code"] != fc_before, "表单重置好友码")
cl2.post("/admin/account/op", data={"id": str(u0["id"]), "op": "ban"})
check(db.list_users()[0]["banned"] == 1, "表单封禁")
cl2.post("/admin/account/op", data={"id": str(u0["id"]), "op": "unban"})
check(db.list_users()[0]["banned"] == 0, "表单解封")

print("=== 8. global_sweep 骨架 ===")
sweep._reset_for_tests()
calls = []
sweep.register(lambda now: calls.append(now) or 3)
check(sweep.run(force=True, now_ms=100000) == 3, "run 返回处理条数")
check(len(calls) == 1 and isinstance(calls[0], int), "处理器收到 now_ms")
check(sweep.run(now_ms=100001) == 0 and len(calls) == 1, "60s 节流内不重复执行")
check(sweep.run(force=True, now_ms=100001) == 3 and len(calls) == 2, "force 跳过节流")


def _boom(now):
    raise RuntimeError("boom")


sweep.register(_boom)
check(sweep.run(force=True, now_ms=100002) == 3 and len(calls) == 3, "异常处理器被隔离，不影响其它")
# 应用层挂接：任何账号的请求都会触发一轮（节流后）
sweep._reset_for_tests()
hits = []
sweep.register(lambda now: hits.append(1) or 0)
cl3 = appmod.app.test_client()
cl3.get("/api/state")
check(len(hits) == 1, "请求触发 global_sweep（首次）")
cl3.get("/api/state")
check(len(hits) == 1, "节流生效：第二次请求不再触发")
sweep._reset_for_tests()
check(len(sweep.handlers()) == 0 and sweep.stats()["runs"] == 0, "测试复位干净")


# ══════════════════════ v1.64（P1）：好友 + 邮件 ══════════════════════

def ract(c, payload):
    return c.post("/api/action", json=payload, environ_base=REMOTE).get_json()


def lact(c, payload):
    return c.post("/api/action", json=payload).get_json()


def uid_of(name):
    return [u for u in db.list_users() if u["name"] == name][0]["id"]


def set_save(uid, fn):
    raw, _ = db.load_user_state(uid)
    s = game.migrate_state(raw) if raw else game.new_state()
    fn(s)
    db.save_user_state(uid, s)
    return s


u_c = uid_of("远行客")       # c（远程）
u_c2 = uid_of("阿远2")       # c2（远程）
u_al = uid_of("Alice")       # Alice（本机注册）
fc_c2 = db.get_user(u_c2)["friend_code"]

print("=== 9. P1：概览 / 好友申请 ===")
j = ract(c, {"action": "social"})
so = j.get("social") or {}
check(j["ok"] and so and len(so["me"]["friend_code"]) == 8, "社交概览：含本人好友码")
check("social_dot" in j, "响应携带社交红点计数")
check(all(p["name"] != "远行客" for p in so["players"]), "本服玩家列表不含自己")
check(any(p["name"] == "阿远2" for p in so["players"]), "本服玩家列表含其他已命名账号")
j = lact(cl, {"action": "social"})
check((not j["ok"]) and "冒险者之名" in (j.get("error") or ""), "空档（未命名）不能用社交功能")
j = ract(c, {"action": "friend_add", "ident": "阿远2", "msg": "你好"})
check(j["ok"], "按名字发送好友申请")
j = ract(c2, {"action": "social"})
check(any(r.get("name") == "远行客" for r in j["social"]["reqs"]["in"]), "对方待处理列表出现申请")
j = ract(c, {"action": "friend_add", "ident": "阿远2", "msg": "再来"})
check(not j["ok"] and "等待对方处理" in j["error"], "重复申请被拒")
j = ract(c, {"action": "friend_add", "ident": "远行客"})
check(not j["ok"] and "自己" in j["error"], "不能添加自己")
j = ract(c, {"action": "friend_add", "ident": "查无此人"})
check(not j["ok"] and "没有找到" in j["error"], "查无此人被拒")
req_id = ract(c2, {"action": "social"})["social"]["reqs"]["in"][0]["id"]
j = ract(c2, {"action": "friend_op", "id": req_id, "op": "accept"})
check(j["ok"], "同意好友申请")
j = ract(c, {"action": "social"})
check(any(f["name"] == "阿远2" for f in j["social"]["friends"]), "双方成为好友（我方列表）")
j = ract(cl_a, {"action": "friend_add", "ident": fc_c2, "msg": "代码加的"})
check(j["ok"], "按好友码发送申请")
req_id2 = ract(c2, {"action": "social"})["social"]["reqs"]["in"][0]["id"]
j = ract(c2, {"action": "friend_op", "id": req_id2, "op": "reject"})
check(j["ok"], "拒绝好友申请")
j = ract(cl_a, {"action": "social"})
check(not any(r.get("name") == "阿远2" for r in j["social"]["reqs"]["out"]), "被拒后申请从发出列表消失")

print("=== 10. P1：拉黑 / 删除好友 / 申请日限 ===")
j = ract(cl_a, {"action": "friend_add", "ident": "阿远2"})
check(j["ok"], "再次发送申请（待拉黑测试）")
j = ract(c2, {"action": "friend_block", "uid": u_al, "on": 1})
check(j["ok"], "拉黑成功")
j = ract(c2, {"action": "social"})
check(any(b["name"] == "Alice" for b in j["social"]["blocked"]), "黑名单列表可见")
j = ract(cl_a, {"action": "social"})
check(not any(r.get("name") == "阿远2" for r in j["social"]["reqs"]["out"]), "拉黑后双方待处理申请被取消")
j = ract(cl_a, {"action": "friend_add", "ident": "阿远2"})
check(not j["ok"] and "无法接收" in j["error"], "被拉黑方无法再申请")
j = ract(c2, {"action": "friend_block", "uid": u_al, "on": 0})
check(j["ok"], "解除拉黑")
j = ract(cl_a, {"action": "friend_add", "ident": "阿远2"})
check(j["ok"], "解除后可重新申请")
req_id3 = ract(c2, {"action": "social"})["social"]["reqs"]["in"][0]["id"]
ract(c2, {"action": "friend_op", "id": req_id3, "op": "accept"})
j = ract(c2, {"action": "friend_del", "uid": u_al})
check(j["ok"], "删除好友")
j = ract(c2, {"action": "social"})
check(not any(f["name"] == "Alice" for f in j["social"]["friends"]), "删除后列表移除")
with closing(db.conn()) as cc:                      # 构造日限：补 9 条今天已发申请（补向 c2，避免 c→Alice 被「已发过」先拦）
    for k in range(9):
        cc.execute("INSERT INTO friend_req (from_uid, to_uid, msg, status, created_at) "
                   "VALUES (?, ?, '_t', 'pending', ?)", (u_c, u_c2, db._now_ms()))
    cc.commit()
j = ract(c, {"action": "friend_add", "ident": "Alice"})
check(not j["ok"] and "上限" in j["error"], "好友申请日限生效（10/10）")
with closing(db.conn()) as cc:
    cc.execute("DELETE FROM friend_req WHERE msg = '_t'")
    cc.commit()

print("=== 11. P1：赠送（托管 / 领取 / 拒收退回 / 数量与权限）===")
set_save(u_c, lambda s: s["mats"].update({"止血草": 20}))
j = ract(c, {"action": "gift_send", "to": u_c2, "mat": "止血草", "qty": 3})
check(j["ok"] and j["social"]["me"]["quotas"]["gift_low_today"] == 3, "赠送成功且计入今日额度（3/5 个）")
j = ract(c, {"action": "social"})
s_c = db.load_user_state(u_c)[0]
check(s_c["mats"].get("止血草") == 17, "托管：发送方先扣除（20 → 17）")
j = ract(c2, {"action": "social"})
pend = [m for m in j["social"]["mail"] if m["status"] == "pending"]
check(len(pend) == 1 and pend[0]["mat"] == "止血草" and pend[0]["qty"] == 3, "邮件箱出现待接收赠送")
j = ract(c2, {"action": "mail_op", "id": pend[0]["id"], "op": "claim"})
check(j["ok"], "领取赠送")
check(db.load_user_state(u_c2)[0]["mats"].get("止血草") == 3, "领取后入包（×3）")
j = ract(c2, {"action": "mail_op", "id": pend[0]["id"], "op": "claim"})
check(not j["ok"], "重复领取被拒（状态机幂等）")
j = ract(c, {"action": "gift_send", "to": u_c2, "mat": "止血草", "qty": 51})
check(not j["ok"] and "1~50" in j["error"], "单次超 50 被拒")
j = ract(c, {"action": "gift_send", "to": u_c2, "mat": "止血草", "qty": 6})
check(not j["ok"] and "单次最多" in j["error"], "单次超每日上限（6 > 5 个）被拒")
j = ract(c, {"action": "gift_send", "to": u_c2, "mat": "止血草", "qty": 3})
check(not j["ok"] and "已达上限" in j["error"], "累计额度拦截（已送 3 + 3 > 5）")
j = ract(c, {"action": "gift_send", "to": u_c2, "mat": "止血草", "qty": 0})
check(not j["ok"], "数量 0 被拒")
j = ract(c, {"action": "gift_send", "to": u_c2, "mat": "专注药剂", "qty": 1})
check(not j["ok"] and "只能赠送材料" in j["error"], "规则道具不可赠送")
set_save(u_al, lambda s: s["mats"].update({"止血草": 5}))
j = ract(cl_a, {"action": "gift_send", "to": u_c2, "mat": "止血草", "qty": 5})
check(not j["ok"] and "好友" in j["error"], "非好友赠送被拒（默认仅好友）")
j = ract(c2, {"action": "privacy_set", "gift": "all"})
check(j["ok"], "接收方改为「全部人可赠送」")
j = ract(cl_a, {"action": "gift_send", "to": u_c2, "mat": "止血草", "qty": 5})
check(j["ok"], "改为 all 后非好友可赠送")
mid = [m for m in ract(c2, {"action": "social"})["social"]["mail"] if m["status"] == "pending"][0]["id"]
j = ract(c2, {"action": "mail_op", "id": mid, "op": "decline"})
check(j["ok"], "拒收赠送")
j = ract(cl_a, {"action": "social"})
ret = [m for m in j["social"]["mail"] if m["kind"] == "return" and m["status"] == "pending"]
check(len(ret) == 1 and ret[0]["mat"] == "止血草" and ret[0]["qty"] == 5, "拒收后退回邮件回到发送方")
check(j["social"]["me"]["quotas"]["gift_low_today"] == 0, "被拒收的赠送不计额度（归还）")
j = ract(cl_a, {"action": "mail_op", "id": ret[0]["id"], "op": "claim"})
check(j["ok"] and db.load_user_state(u_al)[0]["mats"].get("止血草") == 5, "领取退回件恢复材料")
ract(c2, {"action": "privacy_set", "gift": "off"})
j = ract(c, {"action": "gift_send", "to": u_c2, "mat": "止血草", "qty": 1})
check(not j["ok"] and "关闭" in j["error"], "对方关闭赠送后被拒")
ract(c2, {"action": "privacy_set", "gift": "friends"})

print("=== 12. P1：品阶门槛 + 史诗/传说周限（双侧）===")
set_save(u_c, lambda s: s["mats"].update({"暗影草": 5, "龙心": 1}))
j = ract(c, {"action": "gift_send", "to": u_c2, "mat": "暗影草", "qty": 1})
check(not j["ok"] and "尚未解锁" in j["error"], "接收方等级不足（史诗需 Lv3）被拒")
ract(cl_a, {"action": "privacy_set", "gift": "all"})           # Alice 放开赠送（否则先被「仅好友」拦，测不到品阶门槛）
j = ract(c, {"action": "gift_send", "to": u_al, "mat": "龙心", "qty": 1})
check(not j["ok"] and "尚未解锁" in j["error"], "传说材料需 Lv4 才能接收")
def _to_lv3(s):
    s["lv_idx"] = 2


set_save(u_c2, _to_lv3)                                       # 提升到 Lv3
j = ract(c, {"action": "gift_send", "to": u_c2, "mat": "暗影草", "qty": 1})
check(j["ok"] and j["social"]["me"]["quotas"]["gift_high_sent"] == 1, "史诗赠送成功（送出 1/2）")
j = ract(c, {"action": "gift_send", "to": u_c2, "mat": "暗影草", "qty": 1})
check(j["ok"] and j["social"]["me"]["quotas"]["gift_high_sent"] == 2, "第二次送出（2/2）")
j = ract(c, {"action": "gift_send", "to": u_c2, "mat": "暗影草", "qty": 1})
check(not j["ok"] and "上限" in j["error"], "第三次送出被周限拦截")
j = ract(c, {"action": "gift_send", "to": u_c2, "mat": "止血草", "qty": 2})
check(j["ok"] and j["social"]["me"]["quotas"]["gift_low_today"] == 5,
      "史诗/传说不挤占普通日额度：低品阶补送 2 个（3 + 2 = 5/5）")
j = ract(c, {"action": "gift_send", "to": u_c2, "mat": "止血草", "qty": 1})
check(not j["ok"] and "已达上限" in j["error"], "普通日额度用满后第 6 个被拒")
set_save(u_al, lambda s: s["mats"].update({"暗影草": 3}))
ract(cl_a, {"action": "friend_add", "ident": "阿远2"})
rid = ract(c2, {"action": "social"})["social"]["reqs"]["in"][0]["id"]
ract(c2, {"action": "friend_op", "id": rid, "op": "accept"})
j = ract(cl_a, {"action": "gift_send", "to": u_c2, "mat": "暗影草", "qty": 1})
check(not j["ok"] and "可接收" in j["error"], "接收方周额度（待接收已排队 2 封）被前置拦截")
his = [m for m in ract(c2, {"action": "social"})["social"]["mail"] if m["status"] == "pending" and m["mat"] == "暗影草"]
j = ract(c2, {"action": "mail_op", "id": his[0]["id"], "op": "claim"})
check(j["ok"] and j["social"]["me"]["quotas"]["gift_high_recv"] == 2,
      "接收史诗（1 已收 + 1 待接收 = 显示 2/2；v1.67 按个且待接收计入）")
j = ract(c2, {"action": "mail_op", "id": his[1]["id"], "op": "claim"})
check(j["ok"] and j["social"]["me"]["quotas"]["gift_high_recv"] == 2, "接收第二件（2/2）")
mid3 = db.mail_create(u_c2, "gift", from_uid=u_c, title="直插测试", mat="暗影草", qty=1, expire_at=0)
j = ract(c2, {"action": "mail_op", "id": mid3, "op": "claim"})
check(not j["ok"] and "上限" in j["error"], "接收侧周限在领取时兜底")
j = ract(c2, {"action": "mail_op", "id": mid3, "op": "decline"})
check(j["ok"], "超限的赠送可拒收退回")
j = ract(c, {"action": "social"})
_ret2 = [m for m in j["social"]["mail"] if m["kind"] == "return" and m["mat"] == "暗影草"]
check(db.load_user_state(u_c)[0]["mats"].get("暗影草") == 3 and len(_ret2) == 1,
      "退回件生成（送出 2 扣包剩 3、被拒 1 封排队待领）")

print("=== 13. P1：邮件已读 / 私有性 / 隐私 / 广播 ===")
mid4 = db.mail_create(u_c, "system", title="测试系统信", body="hello", expire_at=0)
j = ract(c, {"action": "social"})
check(j["social"]["mail"][0]["status"] == "unread", "系统邮件初始未读")
n_dot = j["social_dot"]
j = ract(c, {"action": "mail_op", "id": mid4, "op": "read"})
check(j["ok"], "标记已读")
check(ract(c, {"action": "social"})["social"]["mail"][0]["status"] == "read", "已读状态落库")
j = ract(c2, {"action": "mail_op", "id": mid4, "op": "claim"})
check(not j["ok"] and "不存在" in j["error"], "不能操作他人邮件")
_m_r1 = db.mail_create(u_c, "system", title="批量已读 1", body="a", expire_at=0)   # v1.67：多封实测（原邮件已先被标记已读，属空转）
_m_r2 = db.mail_create(u_c, "system", title="批量已读 2", body="b", expire_at=0)
check(db.mail_get(_m_r1)["status"] == "unread" and db.mail_get(_m_r2)["status"] == "unread", "read_all 前置：两封未读")
ract(c, {"action": "mail_op", "op": "read_all"})
check(all(m["status"] != "unread" for m in ract(c, {"action": "social"})["social"]["mail"])
      and db.mail_get(_m_r1)["status"] == "read" and db.mail_get(_m_r2)["status"] == "read",
      "read_all 全部标记已读（多封实测）")
j = ract(c, {"action": "social"})
check(all(not b["health"] for b in j["social"]["board"] if b["uid"] != u_c), "默认健康分不公开（榜上仅自己）")
check(all(b.get("public") is False for b in j["social"]["players"] if b["uid"] != u_c),
      "v1.71b：未公开者卡片带 public=False（前端显示「健康分未公开」）")
_boards = j["social"]["board"]
check(len({b["uid"] for b in _boards}) == len(_boards), "v1.71b：健康榜按 uid 去重（自己 + 好友 + 公开玩家合并）")
j = ract(c2, {"action": "privacy_set", "health": True})
check(j["ok"] and j["social"]["me"]["settings"]["health_public"] is True, "开启健康分公开")
j = ract(c, {"action": "social"})
b2 = [b for b in j["social"]["board"] if b["uid"] == u_c2]
check(bool(b2) and isinstance(b2[0]["health"]["today"], int) and "week" in b2[0]["health"],
      "公开后出现在他人健康榜（今日 + 本周均值）")
check(bool(b2) and b2[0].get("public") is True, "v1.71b：公开好友卡片带 public=True")
check(n_dot >= 1, "未读 / 待领取邮件计入红点")
cl2 = appmod.app.test_client()
cl2.get("/admin?token=" + appmod.ADMIN_TOKEN)      # v1.73：token → cookie
r = cl2.post("/admin/broadcast", data={"title": "全服公告", "body": "今晚八点副本"})
check(r.status_code == 302, "服主发广播")
found = [m for m in ract(c, {"action": "social"})["social"]["mail"] if m["kind"] == "system" and "全服公告" in m["title"]]
check(len(found) == 1, "广播送达账号邮箱")
r = remote_client().post("/admin/broadcast", data={"title": "x"}, environ_base=REMOTE)
check(r.status_code == 403, "远程不能发广播")

print("=== 14. P1：到期 sweep（超时退回 + 幂等）===")
past = db._now_ms() - 1000
mid5 = db.mail_create(u_c2, "gift", from_uid=u_c, title="超时测试", mat="兽肉", qty=3, expire_at=past)
set_save(u_c, lambda s: s["mats"].update({"兽肉": 0}))
n1 = socmod.sweep_mail()
check(n1 >= 1, "到期 sweep 处理 ≥1 封")
check(db.mail_get(mid5)["status"] == "expired", "超时赠送标记 expired")
rets = [m for m in db.mail_list(u_c) if m["kind"] == "return" and m["mat"] == "兽肉"]
check(len(rets) == 1 and rets[0]["status"] == "pending" and rets[0]["qty"] == 3, "生成退回邮件（兽肉×3）")
n2 = socmod.sweep_mail()
check(n2 == 0, "sweep 幂等（二次运行 0 处理）")
j = ract(c, {"action": "mail_op", "id": rets[0]["id"], "op": "claim"})
check(j["ok"] and db.load_user_state(u_c)[0]["mats"].get("兽肉") == 3, "领取超时退回件")


# ══════════════════════ v1.65（P2）：组队副本 ══════════════════════

import party as pty

def mk_party_user(nick, lv=2, energy=300, score=85):
    cc = appmod.app.test_client()
    r = cc.post("/register", data={"nick": nick})
    assert r.status_code == 302, nick
    cc.set_cookie("gp_key", KEY)
    u = uid_of(nick)
    set_save(u, lambda s: (s.update({"lv_idx": lv - 1, "energy": energy}),
                           s.update({"history": [{"date": "2026-10-07", "score": score, "sleep": True}]})))
    return cc, u

def force_party(pid, idx):
    """把抽样结果改成指定池条目（测试确定性；金额/精力与池一致）"""
    with closing(db.conn()) as cc:
        p = game.PARTY[idx]
        cc.execute("UPDATE party SET idx = ?, tier = ?, diff = ? WHERE id = ?", (idx, p[1], p[2], pid))
        cc.commit()

# ══════════════════════ v1.65（P2）：组队副本 ══════════════════════

import json as _json
import party as pty


def mk_party_user(nick, lv=2, energy=300, score=85):
    cc = appmod.app.test_client()
    r = cc.post("/register", data={"nick": nick})
    assert r.status_code == 302, nick
    cc.get("/api/state")                    # 先触发一次跨天恢复（08:00 满精力），避免后续断言被恢复覆盖
    u = uid_of(nick)
    set_save(u, lambda s: s.update({"lv_idx": lv - 1, "energy": energy,
                                    "history": [{"date": "2026-10-07", "score": score, "sleep": True}]}))
    return cc, u


def force_party(pid, idx):
    """把抽样结果固定为指定池条目（测试确定性；精力/报酬随池一致）"""
    with closing(db.conn()) as cc:
        p = game.PARTY[idx]
        cc.execute("UPDATE party SET idx = ?, tier = ?, diff = ? WHERE id = ?", (idx, p[1], p[2], pid))
        cc.commit()


def give_offer(uid, idx=0, day_off=1):
    """直接造一条「某副本日」的 offer 行（测试用——绕开每日 1 个的限定）"""
    from datetime import datetime, timedelta
    day = int((datetime.strptime(str(pty._day_key()), "%Y%m%d") + timedelta(days=day_off)).strftime("%Y%m%d"))
    return db.party_create(uid, idx, game.PARTY[idx][1], game.PARTY[idx][2], day, pty._day_end_ms(day))


print("=== 15. P2：概览 / 抽取资格 ===")
cA, uA = mk_party_user("队长甲", lv=2, energy=70, score=85)
cB, uB = mk_party_user("队员乙", lv=2, energy=70, score=85)
cC, uC = mk_party_user("队员丙", lv=3, energy=70, score=85)
cE, uE = mk_party_user("候补戊", lv=2, energy=70, score=40)
cL, uL = mk_party_user("见习丁", lv=1, energy=70, score=85)
j = lact(cA, {"action": "party"})
P = j["party"]
check(j["ok"] and "party_dot" in j, "副本概览随响应下发（含页签红点）")
check(P["me"]["unlock"] and P["me"]["can_tiers"] == ["精良"], "Lv2 仅可参与精良（昨日 85 分）")
check(P["offer"] and P["offer"]["status"] == "offer" and P["offer"]["tier"] == "精良", "当日 offer 已抽（精良）")
check(len(P["offer"]["txt"]) == 5 and P["offer"]["money"] > 0, "offer 携带报酬与 5 则文案")
j2 = lact(cA, {"action": "party"})
check(j2["party"]["offer"]["id"] == P["offer"]["id"], "同日重复拉取不重复抽（每日仅 1 个）")
j = lact(cL, {"action": "party"})
check((not j["party"]["me"]["unlock"]) and j["party"]["offer"] is None, "Lv1 不抽 offer（未解锁）")
j = lact(cC, {"action": "party"})
check(set(j["party"]["me"]["can_tiers"]) == {"精良", "稀有"}, "Lv3 可参与精良 + 稀有")

print("=== 16. P2：组建 / 邀请 / 门槛 / 周限 ===")
pid0 = P["offer"]["id"]
force_party(pid0, 0)                                   # 固定为「冬狼谷·清剿」（精力 32 / 报酬 1800）
j = lact(cA, {"action": "party_create"})
check(j["ok"], "组建成功")
check(db.load_user_state(uA)[0]["energy"] == 70 - 32, "组建扣发起人精力（32）")
check(db.party_get(pid0)["status"] == "open", "offer → open")
j = lact(cA, {"action": "party_create"})
check(not j["ok"], "重复组建被拒（当日仅 1 个）")
j = lact(cA, {"action": "party_invite", "to": uB})
check(j["ok"], "邀请成功（小圈子：非同好友也可邀）")
j = lact(cA, {"action": "party_invite", "to": uA})
check(not j["ok"] and "自己" in j["error"], "不能邀请自己")
lact(cC, {"action": "friend_block", "uid": uA, "on": 1})
j = lact(cA, {"action": "party_invite", "to": uC})
check(not j["ok"] and "邀请" in j["error"], "被拉黑者不能被邀请")
lact(cC, {"action": "friend_block", "uid": uA, "on": 0})
j = lact(cB, {"action": "party"})
_inv = [v for v in j["party"]["invites"] if v["id"] == pid0]
check(len(_inv) == 1 and _inv[0]["leader_name"] == "队长甲" and _inv[0]["gate_ok"], "受邀者可见邀请且门槛通过")
j = lact(cB, {"action": "party_accept", "id": pid0})
check(j["ok"] and db.load_user_state(uB)[0]["energy"] == 70 - 32, "接受 = 扣精力入队")
j = lact(cB, {"action": "party_accept", "id": pid0})
check(not j["ok"], "重复接受被拒（幂等）")
# 门槛：等级 / 昨日分 / 精力
lact(cA, {"action": "party_invite", "to": uL})
j = lact(cL, {"action": "party_accept", "id": pid0})
check(not j["ok"] and "等级不足" in j["error"], "等级门槛拦截（Lv1 进 Lv2 本）")
lact(cA, {"action": "party_invite", "to": uE})
j = lact(cE, {"action": "party_accept", "id": pid0})
check(not j["ok"] and "健康分不足" in j["error"], "昨日健康分门槛拦截（40 < 60）")
set_save(uC, lambda s: s.update({"energy": 5}))
lact(cA, {"action": "party_invite", "to": uC})
j = lact(cC, {"action": "party_accept", "id": pid0})
check(not j["ok"] and "精力不足" in j["error"], "精力不足拦截")
set_save(uC, lambda s: s.update({"energy": 70}))
lact(cA, {"action": "party_invite", "to": uC})
# 周限：直插 3 条本周参与行后拦截
wk0 = pty._week_start_ms()
with closing(db.conn()) as cc:
    for _i in range(3):
        cc.execute("INSERT INTO party_member (party_id, uid, status, joined_at, week0, rate, actions_left, spent) "
                   "VALUES (?, ?, 'in', ?, ?, 0.5, 0, 0)", (90000 + _i, uC, db._now_ms(), wk0))
    cc.commit()
j = lact(cC, {"action": "party_accept", "id": pid0})
check(not j["ok"] and "上限" in j["error"], "周参与上限（3/3）拦截")
with closing(db.conn()) as cc:
    cc.execute("DELETE FROM party_member WHERE party_id >= 90000 AND uid = ?", (uC,))
    cc.commit()

print("=== 17. P2：开启 / 行动 / 通关结算 ===")
j = lact(cA, {"action": "party_start"})
check(not j["ok"], "不足 3 人不能开启")
j = lact(cC, {"action": "party_accept", "id": pid0})
check(j["ok"] and db.load_user_state(uC)[0]["energy"] == 70 - 32, "丙入队（3 人齐）")
j = lact(cA, {"action": "party_start"})
check(j["ok"], "满 3 人开启")
row = db.party_get(pid0)
check(row["status"] == "running" and row["goal"] == 6, "running；目标 6 格（3 人 × 3 次 × 0.6）")
check(abs(row["ends_at"] - row["started_at"] - 8 * 3600000) < 5000, "时长 = 精良 8 小时")
_rand0 = game.rand
game.rand = lambda n: 1                                 # 桩：全部大成功（+2 格）
for i, cu in enumerate((cA, cB, cC)):
    j = lact(cu, {"action": "party_act"})
    check(j["ok"] and any("大成功" in m for m in j["msgs"]), "第 %d 掷：大成功 +2 格" % (i + 1))
row = db.party_get(pid0)
check(row["status"] == "done" and row["progress"] == 6, "达标立即通关（done）")
game.rand = _rand0
j = lact(cA, {"action": "party_act"})
check(not j["ok"], "通关后不能再掷")
for cu, nm in ((cA, "甲"), (cB, "乙"), (cC, "丙")):
    j = lact(cu, {"action": "party"})
    _cl = [x for x in j["party"]["claims"] if x["pid"] == pid0]
    check(len(_cl) == 1 and _cl[0]["ok"], "%s 有通关结算待领取" % nm)
_mB = db.load_user_state(uB)[0]["mats"].get("兽肉", 0)
j = lact(cB, {"action": "party_claim", "id": pid0})
_sB = db.load_user_state(uB)[0]
check(j["ok"] and _sB["money"] == 1800 and _sB["mats"].get("兽肉", 0) > _mB,
      "乙领取入包：报酬 1800 铜 + 兽肉（冬狼谷掉表）")
j = lact(cB, {"action": "party_claim", "id": pid0})
check(not j["ok"], "重复领取被拒（幂等）")
lact(cC, {"action": "party_claim", "id": pid0})
j = lact(cA, {"action": "party"})
check(len([x for x in j["party"]["claims"] if x["pid"] == pid0]) == 1, "甲未领 → 结算保留待领（离线补领）")
lact(cA, {"action": "party_claim", "id": pid0})

print("=== 18. P2：失败安慰奖 / 中途退出 / 到期结算 ===")
pid1 = give_offer(uB, 0, 1)                             # 乙：造一条次日 offer 行（模拟另一场）
db.party_set_status(pid1, "open", expect="offer")
db.party_member_upsert(pid1, uB, "in", wk0, 0.5, 3, 32)
db.party_member_upsert(pid1, uA, "in", wk0, 0.5, 3, 32)
db.party_member_upsert(pid1, uC, "in", wk0, 0.5, 3, 32)
err = pty.start(uB, [])
check(err is None and db.party_get(pid1)["status"] == "running", "服务层开启第二队（跑通 start）")
j = lact(cC, {"action": "party_quit"})
check(j["ok"] and any("无奖励" in m for m in j["msgs"]), "中途退出：无奖励、不退精力")
with closing(db.conn()) as cc:
    cc.execute("UPDATE party SET ends_at = ? WHERE id = ?", (db._now_ms() - 1000, pid1))
    cc.commit()
n = pty.sweep_party()
check(n >= 1 and db.party_get(pid1)["status"] == "failed", "到期按失败结算（sweep）")
check(pty.sweep_party() == 0, "sweep 幂等（二次 0 处理）")
mB = db.party_member_get(pid1, uB)
rB = _json.loads(mB["reward"])
check(mB["claim"] == "pending" and rB["ok"] is False and rB["money"] == 0, "失败 → 安慰奖待领取（无报酬）")
check("兽肉" in rB["mats"] and "野兔皮" in rB["mats"] and "狼牙" not in rB["mats"]
      and all(1 <= n <= 2 for n in rB["mats"].values()),
      "安慰奖 = 必得材料 ≈1/4（兽肉/野兔皮 1~2；概率项 狼牙 不发）")
mC = db.party_member_get(pid1, uC)
check(mC["status"] == "quit" and not mC["reward"], "中途退出者不参与结算")
_mA = db.load_user_state(uA)[0]["mats"].get("兽肉", 0)
j = lact(cA, {"action": "party_claim", "id": pid1})
check(j["ok"] and db.load_user_state(uA)[0]["mats"].get("兽肉", 0) > _mA, "甲领取安慰奖（兽肉入包）")

print("=== 19. P2：未开启作废（退还精力 + 周次数）===")
pid2 = give_offer(uA, 0, 2)
db.party_set_status(pid2, "open", expect="offer")
db.party_member_upsert(pid2, uA, "in", wk0, 0.5, 3, 32)
set_save(uA, lambda s: s.update({"energy": s["energy"] - 32}))
_e0 = db.load_user_state(uA)[0]["energy"]
_w0 = db.party_week_count(uA, wk0)
with closing(db.conn()) as cc:
    cc.execute("UPDATE party SET expire_at = ? WHERE id = ?", (db._now_ms() - 1000, pid2))
    cc.commit()
n = pty.sweep_party()
check(n >= 1 and db.party_get(pid2)["status"] == "expired", "未开启到期 → expired（含 open 行）")
check(db.party_week_count(uA, wk0) == _w0 - 1, "本周次数即时退还（refunded 不再计入）")
j = lact(cA, {"action": "party"})
check(any("退还精力 32" in m for m in j["msgs"]), "本人下次打开：退还精力入账并提示")
check(db.load_user_state(uA)[0]["energy"] == _e0 + 32, "精力 +32 入账")
check(db.party_member_get(pid2, uA)["refund"] == 0, "退还标记已清（幂等）")
j2 = lact(cA, {"action": "party"})
check(not any("退还" in m for m in j2["msgs"]), "退还只发生一次")
j = lact(cB, {"action": "party"})
check(j["party"]["offer"] and j["party"]["offer"]["status"] == "offer", "乙抽到今日 offer（待用）")
j = lact(cB, {"action": "party_offer_abandon"})
check(j["ok"], "放弃 offer（无消耗、无惩罚）")
j = lact(cB, {"action": "party"})
check(j["party"]["offer"] is not None and j["party"]["offer"]["status"] == "abandoned",
      "放弃后当日不再补发（卡片显示已放弃）")


# ══════════════════════ v1.66（P3）：材料市场 ══════════════════════

import market as mkt


def mk_mkt_user(nick, lv=3, rep=None, money=200000):
    if rep is None:
        rep = game.CFG["guildReq"][3]
    cc = appmod.app.test_client()
    r = cc.post("/register", data={"nick": nick})
    assert r.status_code == 302, nick
    cc.get("/api/state")
    u = uid_of(nick)
    set_save(u, lambda s: s.update({"lv_idx": lv - 1, "rep": rep, "money": money,
                                    "mats": {"止血草": 40, "暗影草": 5}}))
    return cc, u


print("=== 20. P3：解锁 / 上架（托管 · 区间 · 限额）===")
_C_REP = game.CFG["guildReq"][3]
cM, uM = mk_mkt_user("摊主")               # Lv3 + 公会 D（v1.75：C → D）
cK, uK = mk_mkt_user("顾客")               # 同上，钱多
cF, uF = mk_mkt_user("路人", lv=3, rep=0)  # 公会 F
cG, uG = mk_mkt_user("学徒", lv=2, rep=_C_REP)  # Lv2
cE4, uE4 = mk_mkt_user("大师兄", lv=4, rep=_C_REP)   # Lv4：史诗门槛
j = lact(cF, {"action": "market"})
check(not j["market"]["unlock"], "公会未到 D 不解锁")
j = lact(cG, {"action": "market"})
check(not j["market"]["unlock"], "Lv2 不解锁")
j = lact(cM, {"action": "market"})
MK = j["market"]
check(MK["unlock"] and "market_dot" in j, "Lv3 + 公会 D 解锁（含市场红点字段）")
check(MK["limits"]["maxListings"] == 3 and MK["limits"]["buyDaily"] == 5
      and MK["limits"]["buyWeekly"] == 20 and MK["limits"]["listingDays"] == 3, "限额参数随概览下发")
_lo, _hi = mkt._price_bounds("止血草")
_base = game.M["止血草"][2]
check(_lo == int(_base * 3 * 0.9) and _hi == int(_base * 3 * 3),
      "价格区间 = 商店价（基准 %d×3=%d）的 90%%~300%%" % (_base, _base * 3))
_P = _hi
j = lact(cM, {"action": "market_list", "mat": "龙心", "qty": 1, "price": 300000})
check(not j["ok"] and "不可上架" in j["error"], "传说不可上架")
j = lact(cM, {"action": "market_list", "mat": "专注药剂", "qty": 1, "price": 100})
check(not j["ok"] and "不可上架" in j["error"], "道具不可上架")
j = lact(cM, {"action": "market_list", "mat": "暗影草", "qty": 1, "price": 120000})
check(not j["ok"] and "Lv4" in j["error"], "史诗上架需 Lv4（卖方）")
j = lact(cM, {"action": "market_list", "mat": "止血草", "qty": 20, "price": _lo - 1})
check(not j["ok"] and "单价" in j["error"], "低于区间下限被拒")
j = lact(cM, {"action": "market_list", "mat": "止血草", "qty": 20, "price": _hi + 1})
check(not j["ok"] and "单价" in j["error"], "高于区间上限被拒")
j = lact(cM, {"action": "market_list", "mat": "止血草", "qty": 20, "price": _P})
check(j["ok"] and j["market"]["mine"][0]["status"] == "on", "上架成功（托管在售）")
check(db.load_user_state(uM)[0]["mats"].get("止血草") == 20, "托管：上架先从背包扣除（40 → 20）")
check(j["market"]["me"]["list_today"] == 1 and j["market"]["me"]["list_active"] == 1, "额度计数（今日 1/3）")
lact(cM, {"action": "market_list", "mat": "止血草", "qty": 5, "price": _P})
lact(cM, {"action": "market_list", "mat": "止血草", "qty": 5, "price": _P})
j = lact(cM, {"action": "market_list", "mat": "止血草", "qty": 5, "price": _P})
check(not j["ok"] and "挂单" in j["error"], "同时挂单上限（3/3）拦截")
j = lact(cM, {"action": "market"})
lid5 = [r for r in j["market"]["mine"] if r["status"] == "on" and r["qty"] == 5][0]["id"]
j = lact(cM, {"action": "market_cancel", "id": lid5})
check(j["ok"], "下架一单")
check(db.load_user_state(uM)[0]["mats"].get("止血草") == 15, "下架原样退回（10 → 15）")
j = lact(cM, {"action": "market_list", "mat": "止血草", "qty": 5, "price": _P})
check(not j["ok"] and "上架次数" in j["error"], "每日上架 ≤3 次（含已下架）")

print("=== 21. P3：买入 / 限额 / 货款 / 到期 ===")
listings = lact(cK, {"action": "market"})["market"]["on"]
check(len(listings) == 2 and all(not r["mine"] for r in listings), "在售列表（他人 2 单）")
lid1 = [r for r in listings if r["qty"] == 20][0]["id"]
j = lact(cM, {"action": "market_buy", "id": lid1, "qty": 1})
check(not j["ok"] and "自己" in j["error"], "禁止购买自己的挂单")
_mK = db.load_user_state(uK)[0]["money"]
j = lact(cK, {"action": "market_buy", "id": lid1, "qty": 3})
check(j["ok"], "部分购买（3/20）")
sK = db.load_user_state(uK)[0]
check(sK["money"] == _mK - _P * 3 and sK["mats"].get("止血草") == 43, "买家扣款 %d 铜、入包 ×3" % (_P * 3))
check(db.market_get(lid1)["qty"] == 17, "挂单剩余 17")
proceeds = [m for m in db.mail_list(uM) if m["kind"] == "proceeds"]
check(len(proceeds) == 1 and proceeds[0]["money"] == _P * 3, "货款进卖家邮件（%d 铜）" % (_P * 3))
_mM = db.load_user_state(uM)[0]["money"]
j = lact(cM, {"action": "mail_op", "id": proceeds[0]["id"], "op": "claim"})
check(j["ok"] and db.load_user_state(uM)[0]["money"] == _mM + _P * 3, "卖家领取货款入账")
# 周限 20：新买家 + 周初流水 20 个（当天恰为周一时，日限会先于周限触发）
cW, uW = mk_mkt_user("周限客")
with closing(db.conn()) as cc:
    cc.execute("INSERT INTO market_buys (buyer, listing, qty, price, ts) VALUES (?, 0, 20, 0, ?)",
               (uW, mkt._week_start_ms() + 1000))
    cc.commit()
j = lact(cW, {"action": "market_buy", "id": lid1, "qty": 1})
_txt = "今日" if mkt._week_start_ms() == mkt._day_start_ms() else "本周"
check(not j["ok"] and _txt in j["error"], "买入周限 20 个拦截")
with closing(db.conn()) as cc:
    cc.execute("DELETE FROM market_buys WHERE buyer = ? AND listing = 0", (uW,))
    cc.commit()
# 日限 5：uK 已买 3 → 再买 2 成功、第 6 个被拒
j = lact(cK, {"action": "market_buy", "id": lid1, "qty": 2})
check(j["ok"], "再买 2 个（今日 5/5）")
j = lact(cK, {"action": "market_buy", "id": lid1, "qty": 1})
check(not j["ok"] and "限额" in j["error"], "今日买入限额 5 个拦截")
# 史诗门槛：新增 Lv4 卖家挂史诗（摊主当日 3 次额度已用完）→ Lv3 顾客被拒、Lv4 大师兄可买
cE, uE = mk_mkt_user("史诗摊主", lv=4)
j = lact(cE, {"action": "market_list", "mat": "暗影草", "qty": 2, "price": 120000})
check(j["ok"], "Lv4 上架史诗")
eid = [r for r in j["market"]["on"] if r["mat"] == "暗影草"][0]["id"]
j = lact(cK, {"action": "market_buy", "id": eid, "qty": 1})
check(not j["ok"] and "Lv4" in j["error"], "史诗买入需 Lv4（买方）")
_e4 = db.load_user_state(uE4)[0]["mats"].get("暗影草", 0)
j = lact(cE4, {"action": "market_buy", "id": eid, "qty": 1})
check(j["ok"] and db.load_user_state(uE4)[0]["mats"].get("暗影草") == _e4 + 1, "Lv4 可买史诗（入包）")
# 到期退回
with closing(db.conn()) as cc:
    cc.execute("UPDATE market SET expire_at = ? WHERE id = ?", (db._now_ms() - 1000, lid1))
    cc.commit()
n = mkt.sweep_market()
check(n >= 1 and db.market_get(lid1)["status"] == "expired", "到期挂单自动下架（sweep）")
check(mkt.sweep_market() == 0, "sweep 幂等")
ret = [m for m in db.mail_list(uM) if m["kind"] == "return" and m["mat"] == "止血草"]
check(len(ret) == 1 and ret[0]["qty"] == 15, "剩余 15 个 → 退回邮件")
_before = db.load_user_state(uM)[0]["mats"].get("止血草", 0)
j = lact(cM, {"action": "mail_op", "id": ret[0]["id"], "op": "claim"})
check(j["ok"] and db.load_user_state(uM)[0]["mats"].get("止血草", 0) == _before + 15, "领取退回件恢复材料")
j = lact(cF, {"action": "market_list", "mat": "止血草", "qty": 1, "price": _P})
check(not j["ok"], "未解锁不能上架（服务端权威）")
j = lact(cK, {"action": "market"})
check(j["market"]["me"]["buy_today"] == 5 and j["market"]["me"]["buy_week"] == 5, "买入额度统计准确")
# v1.67 B4：部分买入后下架 → 原子收摊只退剩余（防竞态多退）
_lid_b4 = db.market_create(uM, "止血草", 5, 120, db._now_ms() + 86400000)
check(db.market_take(_lid_b4, 2) == 3, "B4：market_take 部分买入后剩 3")
check(db.market_take_off(_lid_b4, "off", "cancel") == 3, "B4：收摊只退剩余 3（非原始 5）")
check(db.market_take_off(_lid_b4, "off", "cancel") is None, "B4：重复收摊返回 None（幂等防线）")

print()
print("=" * 56)
if FAIL:
    print("❌ 失败 %d 项 / 共 %d 项（test_social）" % (FAIL, PASS + FAIL))
    sys.exit(1)
print("✅ 全部 %d 项通过（test_social）" % PASS)
