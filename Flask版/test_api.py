# -*- coding: utf-8 -*-
"""端到端 API 测试（Flask test_client）：python test_api.py
   覆盖：命名 → 刷新池 → 接取 → 完成 → 结算 → 结果队列 → 打卡 → 商店 → 探索"""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import app as appmod
import db
import game

PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  ❌ " + msg)


# 使用独立的临时库
db.DB_PATH = Path(__file__).parent / "data" / "test_api.db"
if db.DB_PATH.exists():
    db.DB_PATH.unlink()

c = appmod.app.test_client()


def post(d):
    return c.post("/api/action", json=d).get_json()


def get_state():
    return c.get("/api/state").get_json()


print("=== 1. 初始状态 ===")
j = get_state()
check(j["state"]["name"] == "", "新档无名字 → 前端弹开场")
check(j["state"]["pool"] is not None, "补算生成刷新池")
check(isinstance(j["state"].get("seen_items"), list), "state 含 seen_items（v1.38s 探索详情保密）")

# v1.37：多账号——本 client 第一个请求已自动建出账号，取它作为测试主账号
UID = db.list_users()[0]["id"]
def _load(): return db.load_user_state(UID)[0]
def _save(s): db.save_user_state(UID, s)

print("=== 2. 命名 ===")
j = post({"action": "name", "name": "端到端测试"})
check(j["ok"] and j["state"]["name"] == "端到端测试", "命名成功")

print("=== 2b. v1.38s：seen_items 懒合并（探索详情保密） ===")
s = _load()
s["items"]["安眠护符"] = 1
_save(s)
j = get_state()
check("安眠护符" in j["state"].get("seen_items", []), "当前持有道具自动计入 seen_items")

print("=== 3. 模拟刷新窗口 → 接取 ===")
s = _load()
s["pool"]["bornTs"] = game.now_ms()          # 模拟刚刷新（1 小时窗口内）
s["energy"] = 200
s["lv_idx"] = 1                              # Lv2，避免 Lv1 必成功削弱测试意义
_save(s)
j = post({"action": "accept", "idx": 0})
check(j["ok"], "接取成功：" + str(j.get("error")))
check(len(j["state"]["active"]) == 1, "进行中 1 个")
name0 = j["state"]["active"][0]["name"]

print("=== 4. 完成委托 → 结算 → 结果队列 ===")
s = _load()
s["active"][0]["finishTs"] = game.now_ms() - 1000
s["active"][0]["acceptTs"] = game.now_ms() - 2000
_save(s)
j = get_state()                               # 触发 catch_up → settle
check(len(j["state"]["results"]) >= 1, "结算结果入队")
res = j["state"]["results"][0]
check(res["name"] == name0, "结果对应委托「" + name0 + "」")
check(1 <= res["roll"] <= 100 and "title" in res, "结果含掷骰与判定")
check(len(j["state"]["active"]) == 0, "进行中已清空")
print("  结算：" + res["title"] + " roll=" + str(res["roll"]) + " need=" + str(res["need"]) + " gold=" + str(res["gold"]))

print("=== 5. 结果确认（清空队列） ===")
j = post({"action": "results_ack"})
check(len(j["state"]["results"]) == 0, "results_ack 清空队列")

print("=== 6. 打卡 ===")
_sleep_win = game.in_task_window(0)                    # 入睡窗口 21:00~23:30（白天/凌晨运行测试时为窗口外）
j = post({"action": "checkin", "idx": 0})
if _sleep_win:
    check(j["state"]["health"]["score"] == 20, "早睡 +20")
else:
    check(j["state"]["health"]["score"] == 0,
          "窗口外入睡打卡被拒（当前 " + time.strftime("%H:%M") + "；+20 行为由 test_game 段 20 固定时钟覆盖）")
_mid_lock = game._min_of_day() < game.DAY_CUTOFF_HOUR * 60   # v1.53：00:00–05:59 无窗口项被午夜锁（夜间运行测试时的已知分支）
j = post({"action": "checkin", "idx": 4})
# 午夜锁生效时运动打卡被拒 → 分数保持入睡结果不变
_exp6 = (20 if _sleep_win else 0) if _mid_lock else (30 if _sleep_win else 10)
check(j["state"]["health"]["score"] == _exp6,
      "运动 +10（合计 " + str(_exp6) + ("；凌晨午夜锁生效" if _mid_lock else "") + "）")

print("=== 7. 商店与道具 ===")
s = _load()
s["money"] = 2000000
s["shop_daily"] = {"date": game.today_str(), "cnt": {}}     # v1.38m：清限购计数（防上次运行残留）
s["shop_weekly"] = {"week": game.week_key(), "cnt": {}}
_save(s)
j = post({"action": "buy", "idx": 2})
check(j["ok"] and len(j["state"]["mats"]) > 0, "材料包购买")
j = post({"action": "buy", "idx": 0, "n": 2})            # v1.38o：超日限购被拒（清醒符咒 日限 1）
check(not j["ok"] and "限购" in j.get("error", ""), "超日限购被拒（n=2 > 1）")
j = post({"action": "buy", "idx": 0, "n": 1})
check(j["ok"] and j["state"]["items"].get("清醒符咒") == 1, "限购内购买 ×1（n 参数）")
j = post({"action": "buy_vit", "idx": 5})     # 贡献 +10（需先有活力点）
s = _load()
s["vit"] = 500
_save(s)
j = post({"action": "buy_vit", "idx": 5})
check(j["state"]["con"] >= 10, "活力点兑换贡献")

print("=== 8. 探索（v1.25 现实时间制） ===")
s = _load()
s["lv_idx"] = 3
s["explore"] = 50
s["explore_used"] = 0
s["history"] = [{"date": "y", "score": 100, "sleep": True, "done": 0, "tasks": [1] * 7, "multi": [0, 0]}]
s["done_quests"] = {}                          # v1.60：先验证 Lv2+12 次门槛
_save(s)
game.in_region_time = lambda t: True          # 时间窗放行（独立验证探索流程本身）
j = post({"action": "explore", "idx": 0})
check(not j["ok"] and "12" in j.get("error", ""), "自由探索：未完成 12 次 Lv2 委托被拦（API）")
s = _load()
for _q in game.C.get("Lv2", [])[:12]:
    s["done_quests"][_q[0]] = 1
_save(s)
j = post({"action": "explore", "idx": 0})
check(j["ok"] and j["state"]["explore_active"]["n"] == "晨光森林", "探索发起（进行中）：" + str(j.get("error")))
check(j["state"]["explore_used"] == 1 and j["state"]["explore"] == 47, "发起扣点 -3、次数 +1")
j = post({"action": "explore", "idx": 1})
check(not j["ok"] and "进行中" in j.get("error", ""), "进行中重复探索被拒")
j = post({"action": "explore_return"})
check(j["ok"] and j["state"]["explore_active"] is None, "中途返回（无任何掉落）")
j = post({"action": "explore", "idx": 0})     # 重新发起 → 快进到点
check(j["ok"], "重新发起：" + str(j.get("error")))
s = _load()
s["explore_active"]["finishTs"] = game.now_ms() - 1000
_save(s)
j = get_state()                                # catch_up → explore_finish_check 自动结算
check(j["state"]["explore_active"] is None, "到点后进行中清空")
check(j["state"]["explore_result"] is not None, "探索结果待展示（到点结算）")
j = post({"action": "explore_ack"})
check(j["state"]["explore_result"] is None, "探索结果确认清空")

print("=== 8.5 首页与新增动作 ===")
r = appmod.app.test_client().get("/")
check(r.status_code == 200 and "冒险者委托".encode("utf-8") in r.data, "首页 = 原型完整界面")
s = _load()
s["mats"] = {"止血草": 2}
_save(s)
j = post({"action": "sell_all"})
check(j["ok"] and j["state"]["mats"] == {}, "一键卖出（sell_all）")
j = post({"action": "event_ack"})
check(j["ok"] and j["state"]["event_result"] is None, "event_ack 清空")

print("=== 8.6 宠物喂食（v1.22） ===")
s = _load()
s["wolf"] = {"stage": 1, "growth": 0, "mutate": 0, "fedDate": "", "fedCount": 0}
s["mats"] = {"兽肉": 3, "野兔皮": 1, "龙心": 1}
_save(s)
j = post({"action": "feed_wolf", "name": "野兔皮"})
check(not j["ok"], "非可喂材料被拒")
j = post({"action": "feed_wolf", "name": "兽肉"})
check(j["ok"] and j["state"]["wolf"]["growth"] == 1, "喂食兽肉 +1 成长值")
post({"action": "feed_wolf", "name": "兽肉"})
post({"action": "feed_wolf", "name": "兽肉"})
j = post({"action": "feed_wolf", "name": "兽肉"})
check(not j["ok"], "第 4 次喂食被拒（每日 3 次上限）")
j = post({"action": "evolve_wolf"})
check(not j["ok"], "非巨狼变异被拒：" + str(j.get("error")))

print("=== 8.7 传奇事件预览（v1.24） ===")
s = _load()
s["legend_active"] = ["测试传奇", "世界级", 3, "噩梦", 1000000, 500, "龙心", "称号「测试」", {}]
s["legend_preview"] = True
_save(s)
j = post({"action": "take_legend"})
check(not j["ok"] and "无法接取" in j.get("error", ""), "API：预览事件接取被拒")
s = _load()
check(s["legend_active"] is not None, "预览事件未被消费")
s["pending_legend"] = {"title": "传奇事件", "name": "测试传奇", "preview": True}
_save(s)
j = post({"action": "results_ack"})
check(j["state"]["pending_legend"] is None, "results_ack 清空 pending_legend")

print("=== 10. 远程访问口令门（v1.26） ===")
c2 = appmod.app.test_client()
r = c2.get("/api/state")                        # 默认 Host=localhost → 豁免
check(r.status_code == 200 and r.get_json().get("state") is not None, "localhost 直连免口令")
r = c2.get("/api/state", base_url="http://game.natfrp.com")
check(r.status_code == 401 and (r.get_json() or {}).get("gate") is True, "隧道访问未授权 → 401 gate")
r = c2.get("/", base_url="http://game.natfrp.com")
check(r.status_code == 200 and "访问口令".encode("utf-8") in r.data, "未授权首页 → 口令输入页")
r = c2.post("/gate", data={"k": "wrong"}, base_url="http://game.natfrp.com")
check("口令不正确".encode("utf-8") in r.data, "错误口令被拒")
r = c2.post("/gate", data={"k": appmod.ACCESS_KEY}, base_url="http://game.natfrp.com")
check(r.status_code == 302 and "gp_key" in r.headers.get("Set-Cookie", ""), "正确口令 → 重定向 + Cookie")
r = c2.get("/api/state", base_url="http://game.natfrp.com")
check(r.status_code == 200 and r.get_json().get("state") is not None, "带 Cookie 隧道访问放行")

print("=== 10b. v1.39 A1：Host 头伪造加固 ===")
c6 = appmod.app.test_client()                       # 干净设备（无口令 Cookie）
r = c6.get("/api/state", base_url="http://localhost",
           environ_base={"REMOTE_ADDR": "203.0.113.5"})          # 外网来源 + 伪造本机 Host
check(r.status_code == 401 and (r.get_json() or {}).get("gate") is True,
      "外网 remote_addr + 本机 Host 伪造 → 仍要求口令")
r = c6.get("/api/state", headers={"X-Forwarded-For": "1.2.3.4"})  # 回环来源但带 XFF（隧道/反代特征）
check(r.status_code == 401 and (r.get_json() or {}).get("gate") is True,
      "带 X-Forwarded-For → 不视为本机直连")
c7 = appmod.app.test_client()                                        # 在 localhost 域过口令门拿 Cookie
c7.post("/gate", data={"k": appmod.ACCESS_KEY})
r = c7.get("/api/accounts", base_url="http://localhost",             # 伪造本机 Host + 远程来源
           environ_base={"REMOTE_ADDR": "203.0.113.5"})
check(r.status_code == 403, "账号管理：远程来源伪造本机 Host → 仍被拒 403（A1 加固）")

print("=== 9. 未知动作与错误处理 ===")
j = post({"action": "no_such_action"})
check(not j["ok"] and "未知操作" in j["error"], "未知动作返回错误")
j = post({"action": "accept", "idx": 0})       # 窗口外/已接取
check(not j["ok"], "非法接取被拒：" + str(j["error"]))

print("=== 11. 多账号：设备隔离 / 接入码绑定（v1.37） ===")
j_m = get_state()
check(j_m.get("account") and len(j_m["account"]["code"]) == 8, "主账号有 8 位接入码")
c3 = appmod.app.test_client()                   # 模拟「另一台设备」
j3 = c3.get("/api/state").get_json()
check(j3["state"]["name"] == "", "新设备 → 独立全新账号（空档）")
check(j3["account"] and len(j3["account"]["code"]) == 8, "新设备账号有独立接入码")
check(j3["account"]["code"] != j_m["account"]["code"], "两台设备接入码不同（账号隔离）")
j3b = c3.post("/api/action", json={"action": "bind_code", "code": "ZZZZZZZZ"}).get_json()
check(not j3b["ok"], "错误接入码被拒")
j3c = c3.post("/api/action", json={"action": "bind_code", "code": j_m["account"]["code"]}).get_json()
check(j3c["ok"] and j3c["account"]["code"] == j_m["account"]["code"], "接入码绑定成功 → 切到目标账号")
check(j3c["state"]["name"] == "端到端测试", "绑定后取回目标账号存档")
j3d = c3.get("/api/state").get_json()
check(j3d["state"]["name"] == "端到端测试", "换绑后设备持续使用目标账号（Cookie 已切换）")
r = c3.get("/api/accounts")
check(r.status_code == 200 and r.get_json()["ok"], "本机可查看账号列表（管理面板）")
c4 = appmod.app.test_client()
c4.post("/gate", data={"k": appmod.ACCESS_KEY}, base_url="http://game.natfrp.com")   # 先过口令门
r = c4.get("/api/accounts", base_url="http://game.natfrp.com")
check(r.status_code == 403, "非本机（已过口令门）→ 账号管理被拒 403")

print("=== 12. v1.38d 存档导入互通（camel → snake） ===")
j12 = post({"action": "import_save", "data": {
    "name": "导入存档", "money": 777777, "lvIdx": 2,
    "seenMats": ["松木"], "shieldMonth": "2026-10"}})
check(j12["ok"] and j12["state"]["name"] == "导入存档" and j12["state"]["money"] == 777777,
      "导入 camel 存档 → 生效")
check(j12["state"]["lv_idx"] == 2 and j12["state"]["seen_mats"] == ["松木"]
      and j12["state"]["shield_month"] == "2026-10", "字段映射（lvIdx/seenMats/shieldMonth → snake）")
j12b = get_state()
check(j12b["state"]["name"] == "导入存档" and j12b["state"]["money"] == 777777, "导入后持久化")
j12c = post({"action": "import_save", "data": "bad"})
check(not j12c["ok"], "非对象导入被拒")

print("=== 13. v1.38f 携带宠物（set_carry_pet） ===")
j13 = post({"action": "set_carry_pet", "name": "月光狐"})
check(not j13["ok"] and "还没有" in j13["error"], "未拥有宠物 → 拒绝")
j13b = post({"action": "set_carry_pet", "name": "小狼"})
check(not j13b["ok"], "未拥有小狼 → 拒绝")
j13c = post({"action": "set_carry_pet", "name": ""})
check(j13c["ok"] and j13c["state"]["carry_pet"] == "", "空名 = 卸下（安全）")
j13d = post({"action": "import_save", "data": {
    "name": "携带测试", "money": 1000, "pets": ["月光狐"], "carryPet": "月光狐",
    "petData": {"月光狐": {"stage": 1, "growth": 0, "mutate": 0, "fedDate": "", "fedCount": 0}}}})
check(j13d["ok"] and j13d["state"]["carry_pet"] == "月光狐", "导入 carryPet → carry_pet（互通）")
j13e = post({"action": "set_carry_pet", "name": "月光狐"})
check(j13e["ok"] and j13e["state"]["carry_pet"] == "", "同名再设 = 卸下")
j13f = post({"action": "set_carry_pet", "name": "月光狐"})
check(j13f["ok"] and j13f["state"]["carry_pet"] == "月光狐", "重新携带成功")

print("=== 14. v1.38q2 账号删除（仅本机） ===")
c5 = appmod.app.test_client()                       # 第三台设备（自动建空号）
j14 = c5.get("/api/state").get_json()
r14 = c5.get("/api/accounts").get_json()
tgt = [a for a in r14["accounts"] if a["code"] == j14["account"]["code"]][0]
check(tgt["name"] == "", "待删除目标 = 空号（未命名）")
r14a = c4.post("/api/accounts/delete", json={"id": tgt["id"]},
               base_url="http://game.natfrp.com",
               headers={"Cookie": "gp_key=" + appmod.ACCESS_KEY})
check(r14a.status_code == 403, "非本机（已过口令门）→ 删除被拒 403")
r14b = c5.post("/api/accounts/delete", json={"id": 999999}).get_json()
check(not r14b["ok"], "不存在的 id → 拒绝")
r14c = c5.post("/api/accounts/delete", json={"id": tgt["id"]}).get_json()
check(r14c["ok"], "本机删除账号成功")
check(all(a["code"] != tgt["code"] for a in r14c["accounts"]), "删除后列表已移除该账号")
j14b = c5.get("/api/state").get_json()
check(j14b["account"]["code"] != tgt["code"] and j14b["state"]["name"] == "",
      "被删设备再次访问 → 自动新建空号")
check(db.load_user_state(tgt["id"])[0] is None, "被删账号数据已清除（不可恢复）")

print("=== 15. v1.39 C3：状态瘦身与全量导出 ===")
s = _load()
_base = datetime(2025, 1, 1)
s["history"] = [{"date": (_base + timedelta(days=i)).strftime("%Y-%m-%d"), "score": 70,
                 "sleep": i % 2 == 0, "done": 1,
                 "tasks": [1 if i % 2 == 0 else 0, 1, 0, 0, 0, 0, 0],
                 "multi": [0, 3]} for i in range(200)]
_save(s)
j = get_state()
check(len(j["state"]["history"]) == 150, "history 下发截断至近 150 条")
check(j["state"]["history_total"] == 200, "history_total = 全量 200 天")
check(j["state"]["hist_stats"]["sleep"] == 100, "hist_stats.sleep 全量计数（100）")
check(j["state"]["hist_stats"]["early"] == 200 and j["state"]["hist_stats"]["read"] == 600,
      "hist_stats.early/read 全量计数（200 / 600）")
j = c.post("/api/action", json={"action": "export_save"}).get_json()
check(j["ok"] and len(j["save"]["history"]) == 200, "export_save 全量导出（200 条，不受截断影响）")
check("lv_idx" in j["save"], "export_save 返回 snake 原始档（前端 adaptState 转 camel）")

print("=== 16. v1.39 A4：损坏存档处理 ===")
s = _load()
s["name"] = "损坏前"
_save(s)
_cc = db.conn()
_cc.execute("UPDATE users SET data = ? WHERE id = ?", ("{corrupt", UID))
_cc.commit()
_cc.close()
j = get_state()
check(j["state"]["name"] == "", "损档 → 重置为新档（可继续游戏）")
check(any("损坏" in m for m in j.get("msgs", [])), "向玩家提示存档损坏")
_corrupts = sorted((db.DB_PATH.parent / "corrupt").glob("user%d-*.json" % UID))
check(len(_corrupts) >= 1, "原档原文另存 data/corrupt/（可手动修复）")

print("=== 17. v1.39b E4：event_log 治理 ===")
_cc = db.conn()
_idx = _cc.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_event_log_uid'").fetchone()
check(_idx is not None, "event_log(user_id,id) 索引已建立")
for i in range(2100):                                # 塞 2100 条 + 既有 → prune 应保留最近 2000
    _cc.execute("INSERT INTO event_log (ts, cls, user_id, msg) VALUES (?, ?, ?, ?)",
                (1700000000000 + i, "", UID, "seed-%d" % i))
_cc.execute("INSERT INTO event_log (ts, cls, user_id, msg) VALUES (?, ?, ?, ?)",
            (1, "", 99999, "orphan-row"))            # 孤儿行（无对应账号）
_cc.commit()
_cc.close()
_removed = db.prune_event_log()
_n_after = len(db.recent_logs(UID, 100000))
_cc = db.conn()
_orphan = _cc.execute("SELECT COUNT(*) AS n FROM event_log WHERE user_id = 99999").fetchone()["n"]
_cc.close()
check(_removed >= 100 and _n_after == 2000,
      "每账号保留最近 2000 条（清理 " + str(_removed) + " 条，存留 " + str(_n_after) + "）")
check(_orphan == 0, "孤儿日志行已清理")
check(db.prune_event_log() == 0, "再次治理为幂等（已达标不再删）")
_latest = db.recent_logs(UID, 1)[0]["msg"]
check(_latest == "seed-2099", "保留的确实是最新日志（最近一条 = seed-2099）")

print("=== 18. v1.41 修复：昨日结算 ack（防打卡 / 同步重弹） ===")
s = _load()
s["yesterday"] = {"date": "2025-06-01", "score": 88, "rep": 8, "con": 3, "vit": 2,
                  "tasks": [{"n": "23:30 前入睡", "p": 20, "ok": True}], "multiTasks": [],
                  "doneCount": 1, "quests": [], "exp": 5, "gold": 10, "rep2": 0, "con2": 0,
                  "mats": {}, "events": [], "exploreNext": 8}
s["yesterday_shown"] = False
_save(s)
j = get_state()
check(bool(j["state"]["yesterday"]) and j["state"]["yesterday_shown"] is False,
      "跨天后下发昨日快照（yesterday_shown=False）")
j = post({"action": "yesterday_ack"})
check(j["ok"] and j["state"]["yesterday_shown"] is True, "yesterday_ack 落库为 True")
j = get_state()
check(j["state"]["yesterday_shown"] is True, "再次同步仍为 True（前端不再重弹）")

print("=== 19. v1.41d 节日欢迎弹窗（pending_festival + ack） ===")
s = _load()
s["pending_festival"] = {"name": "🎉 测试节", "text": "测试文案", "date": "2025-06-02"}
_save(s)
j = get_state()
check(j["state"]["pending_festival"] and j["state"]["pending_festival"]["name"] == "🎉 测试节",
      "节日欢迎弹窗随状态下发")
j = post({"action": "festival_ack"})
check(j["ok"] and j["state"]["pending_festival"] is None, "festival_ack 清空（不再重弹）")

print()
print("=" * 40)
print("  API 测试：通过 " + str(PASS) + " 项 | 失败 " + str(FAIL) + " 项 " + ("✅ 全部通过" if FAIL == 0 else "❌"))
db.DB_PATH.unlink(missing_ok=True)
sys.exit(1 if FAIL else 0)
