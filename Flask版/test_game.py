# -*- coding: utf-8 -*-
"""Flask 版核心逻辑测试：python test_game.py
   覆盖：状态 / 补算 / 打卡 / 接取 / 结算 / 掉落 / 区间奖励 / 周月结算 / 成就 / 商店 / 打造 / 探索"""
import sys
from datetime import datetime, timedelta

import game
from game import (new_state, catch_up, settle, success_rate, calc_health,
                  day_settle, weekly_settle, monthly_settle, check_achievements,
                  roll_qty, mat_qty_range)

PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  ❌ " + msg)


# v1.41c：测试隔离节日——成功率 / 报酬 / 窗口等基线断言均在「无节日」假设下编写；
# 假期区间（国庆 10-01~10-07）与单日节日会引入 +20% 报酬 / +10% 成功率 / 窗口延长，
# 故全局清空区间并移除今天的单日键（节日机制由 C9 与「节日窗口扩展」专节显式构造验证）。
_REAL_FEST_RANGES = list(game.FESTIVAL_RANGES)
game.FESTIVAL_RANGES.clear()
game.FESTIVALS.pop(game.today_str()[5:], None)

# v1.50：禁用稀有事件的随机触发——settle / 探索收尾会按 rare_chance 掷 5% 发额外奖励，
# 而基线断言（报酬 / 材料 / 金钱）均在「无稀有事件」假设下编写，随机触发会造成偶发失败。
# 稀有事件效果由「buff_next / rare_next_*」专节直接构造验证，不依赖随机掷骰。
game.rare_chance = lambda s: 0.0


print("=== 1. 初始状态与补算 ===")
s = new_state()
check(s["lv_idx"] == 0 and s["money"] == 0, "新档初始值")
msgs = catch_up(s)
check(s["pool"] is not None, "补算后生成刷新池")
check(game.CFG["drawCount"] == [1, 3, 5, 6, 8], "各级抽取数量 1-3-5-6-8")
print("  刷新池：" + s["pool"]["point"] + " · " + str(len(s["pool"]["list"])) + " 个委托")

print("=== 2. 命名与打卡 ===")
game.take_name(s, "测试者")
check(s["name"] == "测试者", "命名")
game.toggle_task(s, 0, msgs, now=datetime(2026, 10, 3, 22, 0))   # 早睡 20（入睡窗口 21:00~23:30 内）
game.toggle_task(s, 1, msgs, now=datetime(2026, 10, 3, 7, 0))    # 早起 15（起床窗口 06:00~08:00 内）
game.toggle_task(s, 4, msgs, now=datetime(2026, 10, 3, 12, 0))     # 运动 10（无窗口；v1.50：显式白天时刻避开午夜锁）
game.add_multi(s, 1, 1, msgs, now=datetime(2026, 10, 3, 12, 0))    # 阅读 6
check(s["health"]["score"] == 51, "健康分 20+15+10+6=51，实际 " + str(s["health"]["score"]))

print("=== 3. 接取与精力 ===")
s["energy"] = 200
s["pool"]["bornTs"] = game.now_ms()      # 模拟刚刷新
game.accept_quest(s, 0, msgs)
check(len(s["active"]) == 1, "接取成功")
check(s["pool"]["taken"], "本批已标记接取")
print("  接取：" + s["active"][0]["name"] + "，成功率 " + str(round(s["active"][0]["rate"] * 100)) + "%")

print("=== 4. 结算与掉落 ===")
q0 = game.C["Lv1"][0]     # 采集草药 {"止血草":[3,5]}
mat0 = s["mats"].get("止血草", 0)
res = settle(s, {"q": q0, "rate": 1.0, "qlv": 1, "meal": None}, msgs)
gain = s["mats"].get("止血草", 0) - mat0
check(res["title"] in ("成功", "大成功！"), "结算成功")
check(3 <= gain <= 5, "止血草掉落 " + str(gain) + " 应在 [3,5]")
print("  结算：" + res["title"] + " roll " + str(res["roll"]) + " → " + " ".join(res["got"]))

print("=== 5. 数量区间递减权重 ===")
cnt = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
for _ in range(8000):
    cnt[roll_qty(1, 5)] += 1
check(cnt[1] > cnt[2] > cnt[3] > cnt[4] > cnt[5], "递减分布 " + str(cnt))
print("  [1,5] 8000 次：" + " / ".join(str(k) + "→" + str(v) for k, v in cnt.items()))

print("=== 6. 日结算与区间奖励 ===")
s["health"] = {"date": "2026-10-01", "done": [1] * 7, "multi": [4, 2], "score": 0}
s["daily"] = game._blank_daily("2026-10-01")
s["history"] = []
msgs2 = []
day_settle(s, msgs2)
check(s["buff_next"]["pay"] == 0.15 and s["buff_next"]["energy"] == 10, "满分日 → 次日 buff")
check(s["buff_next"]["date"] == "2026-10-02", "buff 生效日")
check(s["heat_n"] == 1, "安眠室累计 +1")
print("  区间奖励：" + str(s["buff_next"]))
# 低分日
s["health"] = {"date": "2026-10-02", "done": [0] * 7, "multi": [0, 0], "score": 0}
s["daily"] = game._blank_daily("2026-10-02")
day_settle(s, msgs2)
check(s["buff_next"].get("energyPct") == -0.10, "0 分（虚弱档）→ 精力上限 −10%（v1.40）")
# v1.32：40–59「普通」档 → 无额外奖励（对齐 02 文档 2.2）——50 分 = 早睡20+起床15+午休5+喝水10
s["health"] = {"date": "2026-10-03", "done": [1, 1, 1, 1, 0, 0, 0], "multi": [0, 0], "score": 50}
s["daily"] = game._blank_daily("2026-10-03")
day_settle(s, msgs2)
check(s["buff_next"]["energy"] == 0 and s["buff_next"]["pay"] == 0, "50 分（普通档）→ 无额外奖励、无惩罚")
# v1.59b：60–74「良好」档（第三档）→ 结算 声望+2/贡献+1/活力点+1；次日区间奖励 报酬+5%/贡献+1/活力点+1
s["health"] = {"date": "2026-10-04", "done": [1, 1, 1, 1, 1, 0, 0], "multi": [0, 0], "score": 65}
s["daily"] = game._blank_daily("2026-10-04")
_c65, _v65 = s["con"], s["vit"]
day_settle(s, msgs2)
check(s["con"] - _c65 == 1 and s["vit"] - _v65 == 1, "65 分（良好档）→ 结算 贡献+1 / 活力点+1（v1.59b）")
check(s["buff_next"]["pay"] == 0.05 and s["buff_next"]["con"] == 1 and s["buff_next"].get("vit") == 1,
      "65 分（良好档）→ 次日区间奖励 报酬+5% / 贡献+1 / 活力点+1（v1.59b）")

print("=== 7. 周结算（全黄金周） ===")
s["week_settled"] = ""
s["history"] = []
for i in range(7):
    d = (datetime(2026, 9, 28) + timedelta(days=i)).strftime("%Y-%m-%d")
    s["history"].append({"date": d, "score": 95, "sleep": True, "done": 2, "gold": 0,
                         "tasks": [1] * 7, "multi": [4, 2]})
m0, v0, c0, e0 = s["money"], s["vit"], s["con"], s["explore"]
weekly_settle(s, "2026-10-04", [])
again = weekly_settle(s, "2026-10-04", [])
check(s["money"] - m0 == 19000 and s["vit"] - v0 == 40, "周结算奖励（幂等：" + str(again is None) + "）")
print("  周结算：铜+" + str(s["money"] - m0) + " 活力+" + str(s["vit"] - v0) + " 贡献+" + str(s["con"] - c0) + " 探索+" + str(s["explore"] - e0))

print("=== 8. 月结算（全黄金月） ===")
s["month_settled"] = ""
s["history"] = []
for i in range(30):
    d = (datetime(2026, 9, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
    s["history"].append({"date": d, "score": 92, "sleep": True, "done": 3, "gold": 0,
                         "tasks": [1] * 7, "multi": [4, 3]})
monthly_settle(s, "2026-09-30", [])
check(s["perm_energy"] == 20, "永久精力累积 +20（v1.40：原「取历史最高」首金 50 后归零）")
check("月光狐" in s["pets"], "阅读黄金 → 宠物月光狐")
check(s["tim_titles"].get("安眠守护者") and s["tim_titles"].get("公会中坚") and s["tim_titles"].get("作息守护者"), "三个当月称号")

print("=== 9. 成就 ===")
s["achv"] = []
s["total_quests"] = 100
check_achievements(s, [])
check("百炼成钢" in s["achv"] and "百炼徽记" in s["gear"], "百炼成钢 → 百炼徽记")
s["legend_done"].append("屠龙传说")
check_achievements(s, [])
check("屠龙者" in s["achv"], "屠龙者成就")

print("=== 10. 豁免 ===")
s["equipped"]["accessory"] = "安神吊坠"
s["exempt"] = {"sleep": "", "early": ""}
s["health"] = {"date": "2026-10-05", "done": [0, 0, 1, 1, 1, 1, 1], "multi": [0, 0], "score": 0}
s["daily"] = game._blank_daily("2026-10-05")
s["buff_next"] = None
s["week_settled"] = "2026-10-04"
s["month_settled"] = "2026-10"
day_settle(s, [])
check(s["health"]["done"][0] == 0 and s["exempt"]["sleep"] != "2026-10", "安神吊坠不再提供早睡豁免（v1.40 删除残留）")

print("=== 11. 熬夜惩罚 ===")
s["equipped"] = {"weapon": None, "armor": None, "accessory": None, "charmSlot": None}
s["lv_idx"] = 3
s["health"] = {"date": game.today_str(), "done": [0] * 7, "multi": [0, 0], "score": 50}
q1 = ["精英测试", "精英", "08:00-23:30", 60, "普通", 100, 1, 8, {}]
s["history"] = [{"date": "y", "score": 90, "sleep": False, "done": 0}]
r0 = success_rate(s, q1)
s["history"][0]["sleep"] = True
r1 = success_rate(s, q1)
check(abs((r1 - r0) - 0.15) < 1e-9, "熬夜惩罚差额 15pp（" + str(round((r1 - r0) * 100)) + "pp）")

print("=== 12. 商店 / 打造 / 探索 ===")
s["money"] = 100000000
s["con"] = 100000
s["vit"] = 100000
s["rep"] = 999999
game.buy(s, 1, [])
check(len(s["mats"]) > 0, "材料包购买")
# v1.38k/m/o：批量购买 / 兑换 + 商店限购（渠道独立计数）；v1.61d：清醒符咒/安眠护符移出铜币商店 → 用材料包/疾风符咒验证
m0, mat0 = s["money"], sum(s["mats"].values())
bad = game.buy(s, 0, [], 4)
check(bad is not None and s["money"] == m0, "超日限购被拒（普通材料包 ×4 > 日限 3）")
game.buy(s, 0, [], 3)
check(s["money"] == m0 - 18000 and sum(s["mats"].values()) == mat0 + 15, "限购内批量购买 ×3（-1.8 万，+15 材料）")
bad = game.buy(s, 0, [], 1)
check(bad is not None, "达日限购后再买被拒")
# v1.38o：疾风符咒日限 1（v1.61d：贡献商店首项；清醒/安眠已移至铂金商店）
s["con"] = 1000
wind0 = s["items"].get("疾风符咒", 0)
game.buy_con(s, 0, [], 1)
check(s["items"].get("疾风符咒", 0) == wind0 + 1 and s["con"] == 600, "贡献商店：疾风符咒 ×1（-400 贡献）")
c1 = s["con"]; s["con"] = 10
bad = game.buy_con(s, 0, [], 1)
check(bad is not None and s["con"] == 10, "已购满日限后再兑换被拒")
s["con"] = c1
# v1.38o：史诗材料 周限 2；v1.41 H2：材料改真自选（传 mat；索引按名查找防插项错位）
_i_ep = next(i for i, x in enumerate(game.CON_SHOP) if x.get("matSel") and x["matSel"][0] == "史诗")
_i_rare = next(i for i, x in enumerate(game.CON_SHOP) if x.get("matSel") and x["matSel"][0] == "稀有")
_ep_mat = next(k for k, v in game.M.items() if v[1] == "史诗")
_rare_mat = next(k for k, v in game.M.items() if v[1] == "稀有")
ep0 = sum(v for k, v in s["mats"].items() if game.M.get(k, [None, None])[1] == "史诗")
s["con"] = 2000
game.buy_con(s, _i_ep, [], 1, _ep_mat)
check(sum(v for k, v in s["mats"].items() if game.M.get(k, [None, None])[1] == "史诗") == ep0 + 1
      and s["con"] == 1700, "贡献兑换史诗材料 ×1（-300 贡献）")
game.buy_con(s, _i_ep, [], 1, _ep_mat)
check(sum(v for k, v in s["mats"].items() if game.M.get(k, [None, None])[1] == "史诗") == ep0 + 2
      and s["con"] == 1400, "史诗材料 ×2（周限 2 内）")
bad = game.buy_con(s, _i_ep, [], 1, _ep_mat)
check(bad is not None and s["con"] == 1400, "史诗材料周限购拦截（每周 2）")
# v1.38o：稀有材料 周限 3
rare0 = sum(v for k, v in s["mats"].items() if game.M.get(k, [None, None])[1] == "稀有")
s["con"] = 2000
game.buy_con(s, _i_rare, [], 3, _rare_mat)
check(sum(v for k, v in s["mats"].items() if game.M.get(k, [None, None])[1] == "稀有") == rare0 + 6
      and s["con"] == 1640, "稀有材料 ×3（每次 2 个 → +6，-360 贡献）")
bad = game.buy_con(s, _i_rare, [], 1, _rare_mat)
check(bad is not None and s["con"] == 1640, "稀有材料周限购拦截（每周 3）")
s["con"] = c1
e0 = s["explore"]
game.buy_vit(s, 2, [], 3)                        # v1.61d：探索点 +5 新索引 2（清醒/安眠移出后移位）
check(s["explore"] == e0 + 15 and s["vit"] == 100000 - 75, "批量活力点兑换（探索点 +15）")
m2 = s["money"]; s["money"] = 100000
bad = game.buy(s, 0, [], 9999)
check(bad is not None and s["money"] == 100000, "批量超量（钱不够）被拒且不扣款")
s["money"] = m2
# v1.38o：穿戴精力上限装备——当前与上限同步 +差值；卸下收敛至新上限
s["equipped"] = {"weapon": None, "armor": None, "accessory": None, "charmSlot": None}
s["gear"] = ["龙鳞重铠"]
s["energy"] = 60
m_e = game.energy_max_now(s)
game.equip_item(s, "龙鳞重铠", [])
check(s["energy"] == 95 and game.energy_max_now(s) == m_e + 35, "穿戴上限装备：当前与上限同步 +35（60→95）")
game.unequip(s, "armor", [])
check(game.energy_max_now(s) == m_e and s["energy"] == min(95, m_e), "卸下上限装备：当前精力收敛至新上限")
# v1.38o：熬夜减免不溢出（未熬夜不受益；减免封顶于惩罚本身）
_h_bak = s["history"]
_q0 = ["N测试", "采集", "全天", 60, "简单", 100, 1, 8, {}]
s["history"] = [{"date": "d", "score": 80, "sleep": True, "done": 0, "tasks": [1]*7, "multi": [0, 0]}]
s["rare_next_rate"] = 0
s["equipped"] = {"weapon": None, "armor": None, "accessory": None, "charmSlot": None}
_r_base = game.success_rate(s, _q0)
s["equipped"]["charmSlot"] = "安眠坠"
check(game.success_rate(s, _q0) == _r_base, "未熬夜：夜免装备不产生正加成（修前 +30%）")
s["history"][0]["sleep"] = False
check(abs((game.success_rate(s, _q0) - _r_base) + 0.05) < 1e-9,
      "熬夜 + 安眠坠(−10%)：惩罚减免至 −5%（v1.40 由 −30% 削弱，原完全免疫）")
s["equipped"] = {"weapon": None, "armor": "龙鳞重铠", "accessory": None, "charmSlot": None}
_r_ld_night = game.success_rate(s, _q0)
s["history"][0]["sleep"] = True
_r_ld_idle = game.success_rate(s, _q0)
check(abs((_r_ld_night - _r_ld_idle) + 0.15) < 1e-9, "熬夜 + 龙鳞重铠（词条已改精英续航）：惩罚 −15%，无夜免")
s["history"] = _h_bak
# v1.38p：公会额外委托 6 选 1（独立槽位：不占接取次数与同时进行上限）
s["bonus_quests"] = [["额外A", "采集", "全天", 60, "简单", 100, 1, 8, {}],
                     ["额外B", "采集", "全天", 60, "简单", 100, 1, 8, {}]]
s["energy"] = 100
_a_n0, _a_acc0 = len(s["active"]), s["accepted"]
bad = game.accept_bonus(s, 1, [])
check(bad is None and s["bonus_quests"] is None and len(s["active"]) == _a_n0 + 1
      and s["active"][-1]["name"] == "额外B" and s["accepted"] == _a_acc0,
      "公会额外委托 6 选 1：选第 2 个接取、整批清空、不占接取次数")
s["active"] = s["active"][:_a_n0]
# v1.38o：酒馆传闻当日补齐（幂等——修复"每次刷新页面就变"）
s["rumor"] = None
game.catch_up(s)
_r_idx = s["rumor"]["idx"] if s.get("rumor") else None
game.catch_up(s)
check(s.get("rumor") and s["rumor"]["date"] == game.today_str() and s["rumor"]["idx"] == _r_idx,
      "酒馆传闻：当日缺失时 catch_up 幂等补齐")
game.buy_vit(s, 4, [])                           # v1.61d：薰香 Ⅰ 新索引 4
check(s["incense"] == 1, "安眠薰香 I")
bad = game.buy_vit(s, 8, [])                     # 薰香 Ⅴ 新索引 8（跳级拦截）
check(s["incense"] == 1 and bad, "薰香跳级拦截")
game.up_skill(s, "体能", [])
check(s["skills"]["体能"] == 1, "技能升级")
check(game.skill_cap(s) == 25, "P 级技能上限 25")
game.buy_charm(s, [])
check(s["charm"] == 1, "冥念护符 I")
# 打造（v1.38c：副材料需与主材料同系品类——铜剑=矿石系，配松木）
s["blueprints"] = {"铜剑": True}
s["mats"]["铜矿石"] = 99
s["mats"]["松木"] = 99
game.craft(s, "铜剑", [])
check("铜剑" in s["gear"], "打造铜剑")
# 探索（时间窗放行：独立验证探索逻辑本身；v1.25 现实时间制）
s["explore"] = 100
s["explore_used"] = 0
s["lv_idx"] = 4
s["history"] = [{"date": "y", "score": 100, "sleep": True, "done": 0, "tasks": [1] * 7, "multi": [0, 0]}]
game.in_region_time = lambda t: True
# v1.60：自由探索解锁 = Lv2 + 完成 12 次 Lv2 委托
s["done_quests"] = {}
bad = game.do_explore(s, 0, [])
check(bad is not None and "12" in bad, "自由探索：未完成 12 次 Lv2 委托被拦")
_lv2names = [q[0] for q in game.C.get("Lv2", [])]
for _qn in _lv2names[:11]:
    s["done_quests"][_qn] = s["done_quests"].get(_qn, 0) + 1
bad = game.do_explore(s, 0, [])
check(bad is not None and "11/12" in bad, "自由探索：11 次仍被拦（进度提示）")
s["done_quests"][_lv2names[11]] = 1
err = game.do_explore(s, 0, [])
check(err is None and s.get("explore_active") and s["explore_active"]["n"] == "晨光森林", "探索发起（进行中）")
check(s["explore"] == 97 and s["explore_used"] == 1, "发起时扣点（-3）与次数")
check(s["explore_active"]["h"] == 2 and s["explore_active"]["finishTs"] > game.now_ms(), "区域耗时 2 小时（未到点）")
err = game.do_explore(s, 1, [])
check(err is not None and "进行中" in err, "进行中重复探索被拒")
mat0 = dict(s["mats"]); mon0 = s["money"]
err = game.explore_return(s, [])
check(err is None and s.get("explore_active") is None, "中途返回（放弃）")
check(dict(s["mats"]) == mat0 and s["money"] == mon0, "返回无任何掉落")
err = game.do_explore(s, 0, [])
check(err is None, "重新发起")
s["explore_active"]["finishTs"] = game.now_ms() - 1000
game.explore_finish_check(s, [])
check(s.get("explore_active") is None, "到点结算后清空进行中")
check(s["explore_result"] is not None and s["explore_result"]["region"] == "晨光森林", "探索结果结构（到点结算）")

print("=== 13. 稀有事件「下一次委托」加成 ===")
s2 = new_state()
s2["lv_idx"] = 2                     # Lv3 困难：成功率远离 cap，能验证 +5%
s2["health"] = {"date": game.today_str(), "done": [0] * 7, "multi": [0, 0], "score": 0}
q9 = ["稀有加成测试", "采集", "全天", 60, "困难", 100, 1, 8, {}]
s2["rare_next_rate"] = 0.05
rB = success_rate(s2, q9)
s2["rare_next_rate"] = 0
rA = success_rate(s2, q9)
check(abs((rB - rA) - 0.05) < 1e-9, "稀有 +5% 成功率差额 " + str(round((rB - rA) * 100)) + "pp")
s2["rare_next_rate"] = 0.05
s2["rare_next_pay"] = 0.25
m0 = s2["money"]
settle(s2, {"q": q9, "rate": 1.0, "qlv": 1, "meal": None}, [])
d9 = s2["money"] - m0
check(d9 in (125, 150), "稀有 +25% 报酬：" + str(d9))
check(s2["rare_next_pay"] == 0 and s2["rare_next_rate"] == 0, "用后清零")

print("=== 14. 补算引擎（跨 3 天） ===")
s = new_state()
s["name"] = "补算测试"
s["last_day"] = (datetime.strptime(game.today_str(), "%Y-%m-%d") - timedelta(days=3)).strftime("%Y-%m-%d")   # 以游戏日（早 6 点日界）为基准，凌晨运行也稳定
s["health"] = {"date": s["last_day"], "done": [1, 1, 1, 1, 1, 1, 1], "multi": [4, 2], "score": 0}
done_msgs = catch_up(s)
check(len(s["history"]) >= 3, "跨 3 天至少生成 3 条历史，实际 " + str(len(s["history"])))
check(s["last_day"] == game.today_str(), "last_day 对齐到今天")
check(s["buff_next"] is not None, "补算产生区间奖励")
print("  补算消息 " + str(len(done_msgs)) + " 条；历史 " + str(len(s["history"])) + " 天")

print("=== 15. 探索事件（完整交互版） ===")
s = new_state()
s["daily"] = game._blank_daily(game.today_str())
s["money"] = 100
s["pending_event"] = {"name": "迷路商人", "title": "x", "text": "x",
                      "options": [{"label": "买", "accept": 1, "pri": 1}, {"label": "不买", "accept": 0}]}
game.explore_choice(s, True, [])
check(s["items"].get("清醒符咒") == 1 and s["money"] == 90, "迷路商人购买：10 铜换清醒符咒")
check(s["event_result"] is not None and s["pending_event"] is None, "事件结果写入 + 待选清空")
s["pending_event"] = {"name": "受伤小狼", "title": "x", "text": "x",
                      "options": [{"label": "救", "accept": 1}, {"label": "离开", "accept": 0}]}
game.explore_choice(s, False, [])
check(not s.get("wolf_done") and s["pending_event"] is None, "受伤小狼·离开分支")
s["pending_event"] = {"name": "受伤小狼", "title": "x", "text": "x",
                      "options": [{"label": "救", "accept": 1}, {"label": "离开", "accept": 0}]}
game.explore_choice(s, True, [])
check(s.get("wolf_done") and s.get("pending_pet") and s["event_result"], "受伤小狼·救治分支（3 天后入伙）")
# 事件判定结构（20% 触发，500 次内必现）
s2 = new_state()
s2["daily"] = game._blank_daily(game.today_str())
seen = None
for _ in range(500):
    e = game.roll_explore_event(s2, {"n": "晨光森林"})
    if e:
        seen = e
        break
check(seen is not None and "text" in seen and "options" in seen, "探索事件结构（触发 20%）")
print("  首个事件：" + (seen["name"] if seen else "未触发"))
# 盗贼伏击消耗 10 精力
s3 = new_state()
s3["daily"] = game._blank_daily(game.today_str())
s3["energy"] = 60
hit = False
for _ in range(1000):
    e = game.roll_explore_event(s3, {"n": "晨光森林"})
    if e and e["name"] == "盗贼伏击":
        hit = True
        break
check(hit and s3["energy"] <= 50, "盗贼伏击：消耗 10 精力（现 " + str(s3["energy"]) + "）")
# v1.61c：盗贼伏击抢夺上限 1 铂金币（控制随机：0.1 触发事件 → 0.9 跳过宠物奇遇 → 0.1 抽中盗贼；rand=100 强制「被抢」分支）
s4 = new_state()
s4["daily"] = game._blank_daily(game.today_str())
s4["money"] = 20000000                     # 200 铂金币；10% = 200 万 → 应封顶 100 万
_seq = [0.1, 0.9, 0.1]
_orig_random = game.random.random
_orig_rand = game.rand
game.random.random = lambda: _seq.pop(0) if _seq else 0.1
game.rand = lambda n: 100
try:
    e4 = game.roll_explore_event(s4, {"n": "晨光森林"})
finally:
    game.random.random = _orig_random
    game.rand = _orig_rand
check(e4 and e4["name"] == "盗贼伏击" and s4["money"] == 19000000,
      "盗贼伏击：抢夺上限 1 铂金币（200 铂金 → 实损 1 铂金，现余 " + str(s4["money"]) + "）")

print("=== 16. 搜索新动作（sell_all / abandon name / pending_rare） ===")
s = new_state()
s["lv_idx"] = 1
s["mats"] = {"止血草": 3, "蘑菇": 2}
m0 = s["money"]
game.sell_all(s, [])
check(s["mats"] == {} and s["money"] > m0, "一键卖出全部材料")
check(game.sell_all(s, []) is not None, "空背包卖出拦截")
s = new_state()
s["active"] = [{"name": "A", "q": [], "rate": 1, "acceptTs": 0, "finishTs": 0, "qlv": 1},
               {"name": "B", "q": [], "rate": 1, "acceptTs": 0, "finishTs": 0, "qlv": 1}]
game.abandon_quest(s, 0, "B")          # idx 与 name 不符 → 按 name 找到 B
check(len(s["active"]) == 1 and s["active"][0]["name"] == "A", "放弃委托按名字校验")
s = new_state()
check(s["results"] == [] and s["pending_rare"] == [] and s["explore_result"] is None
      and s["pending_event"] is None and s["event_result"] is None, "新字段就绪（rare/探索）")

print("=== 17. 宠物·小狼成长链（v1.22） ===")
s = new_state()
check(s["wolf"] is None, "初始无小狼")
s["pets"].append("小狼")
game.migrate_state(s)
check(s["wolf"]["stage"] == 1 and s["wolf"]["mutate"] == 0, "旧档迁移：有小狼 → 一阶")
s["mats"] = {"止血草": 10, "野兔皮": 5, "兽肉": 10, "龙血": 5, "龙心": 3, "暗影草": 2}
bad = game.feed_wolf(s, "野兔皮", [])
check(bad is not None and s["wolf"]["growth"] == 0, "非可喂材料被拒（兽材）")
game.feed_wolf(s, "兽肉", [])
check(s["wolf"]["growth"] == 1 and s["mats"]["兽肉"] == 9, "喂食兽肉 +1 成长值")
game.feed_wolf(s, "止血草", [])
check(s["wolf"]["growth"] == 2, "草药可喂：止血草 +1")
game.feed_wolf(s, "兽肉", [])
check(s["wolf"]["growth"] == 3, "每日 3 次内正常累积")
bad = game.feed_wolf(s, "兽肉", [])
check(bad is not None and s["wolf"]["growth"] == 3, "第 4 次被拒（每日 3 次上限）")
s["wolf"]["fedDate"] = ""
s["wolf"]["fedCount"] = 0
g0, mu0 = s["wolf"]["growth"], s["wolf"]["mutate"]
game.feed_wolf(s, "龙血", [])
check(s["wolf"]["growth"] == g0 + 8 and s["wolf"]["mutate"] == mu0 + 5, "龙血：+8 成长 / +5 变异值")
s["wolf"]["fedDate"] = ""
s["wolf"]["fedCount"] = 0
game.feed_wolf(s, "暗影草", [])
check(s["wolf"]["mutate"] == mu0 + 10, "暗影草（草药）：+5 变异值")
s["wolf"]["fedDate"] = ""
s["wolf"]["fedCount"] = 0
game.feed_wolf(s, "龙心", [])
check(s["wolf"]["mutate"] == mu0 + 22, "龙心：额外 +12 变异值")
s["carry_pet"] = "小狼"   # v1.56c：宠物加成改为携带生效（本节断言依赖）
s["wolf"] = {"stage": 1, "growth": 59, "mutate": 22, "fedDate": "", "fedCount": 0}
game.feed_wolf(s, "兽肉", [])
check(s["wolf"]["stage"] == 2 and s["wolf"]["growth"] == 0 and s["wolf"]["mutate"] == 22, "60 → 成年狼（变异值保留）")
s["wolf"] = {"stage": 2, "growth": 199, "mutate": 22, "fedDate": "", "fedCount": 0}
game.feed_wolf(s, "兽肉", [])
check(s["wolf"]["stage"] == 3, "200 → 巨狼")
check(abs(game.wolf_mat_bonus(s) - 0.05) < 1e-9 and abs(game.wolf_rate_bonus(s) - 0.01) < 1e-9, "巨狼加成 5% / 1%")
s["wolf"] = {"stage": 3, "growth": 300, "mutate": 22, "fedDate": "", "fedCount": 0}
game.feed_wolf(s, "兽肉", [])
check(s["wolf"]["growth"] == 300 and s["wolf"]["mutate"] == 22, "成长满：普通食材不再加成（可继续喂）")
s["wolf"]["fedDate"] = ""
s["wolf"]["fedCount"] = 0
game.feed_wolf(s, "龙心", [])
check(s["wolf"]["mutate"] == 34, "成长满：龙心仍 +12 变异值")
bad = game.evolve_wolf(s, [])
check(bad is not None and "变异值" in bad, "变异值不足被拒")
s["wolf"]["mutate"] = 300
err = game.evolve_wolf(s, [])
check(err is None and s["wolf"]["stage"] == 4, "变异值满 → 变异成功（远古魔狼）")
check(abs(game.wolf_mat_bonus(s) - 0.08) < 1e-9 and abs(game.wolf_rate_bonus(s) - 0.03) < 1e-9, "魔狼加成 8% / 3%")
q = ["狼测试", "采集", "全天", 60, "普通", 100, 1, 8, {}]
s["lv_idx"] = 2
s["health"] = {"date": game.today_str(), "done": [0] * 7, "multi": [0, 0], "score": 0}
s["wolf"] = {"stage": 3, "growth": 0, "mutate": 0, "fedDate": "", "fedCount": 0}
r1 = success_rate(s, q)
s["wolf"] = None
r0 = success_rate(s, q)
check(abs((r1 - r0) - 0.01) < 1e-9, "巨狼成功率独立 +1pp")
s["wolf"] = {"stage": 4, "growth": 0, "mutate": 0, "fedDate": "", "fedCount": 0}
base = game.mat_drop_rate("龙心")
cnt = 0
for _ in range(20000):
    if game.random.random() < min(1, base + game.wolf_mat_bonus(s)):
        cnt += 1
check(cnt > (base + 0.05) * 20000, "材料掉落独立加点生效（命中 " + str(cnt) + "）")

print("=== 18. 传奇事件「预览」（v1.24；v1.41 用户指定保留） ===")
s = new_state()
_orig_rand = game.random.random
game.random.random = lambda: 0.01
msgs18 = []
game.roll_legend(s, msgs18)
check(s["legend_active"] is not None and s["legend_preview"] is True, "未解锁 2% 预览触发")
check(any("预览" in m for m in msgs18), "预览消息入队")
check(s["pending_legend"] and s["pending_legend"]["preview"] is True
      and s["pending_legend"]["name"] == s["legend_active"][0], "预览弹窗待展示（pending_legend）")
err = game.take_legend(s, [])
check(err is not None and "无法接取" in err, "预览无法接取（服务端拦截）")
check(s["legend_active"] is not None, "预览事件保留（未被消费）")
s["legend_day"] = ""
game.random.random = lambda: 0.99
game.roll_legend(s, [])
check(s["legend_active"] is None and s["legend_preview"] is False, "跨天清除预览")
check(s["pending_legend"] is None, "跨天同时清除预览弹窗")
game.random.random = _orig_rand

print("=== 19. 6 点日界（v1.27） ===")
# 1) today_str 边界：00:00~05:59 算前一天，06:00 起算当天
check(game.today_str(datetime(2026, 10, 3, 0, 0)) == "2026-10-02", "0:00 算前一天")
check(game.today_str(datetime(2026, 10, 3, 5, 59)) == "2026-10-02", "5:59 仍算前一天")
check(game.today_str(datetime(2026, 10, 3, 6, 0)) == "2026-10-03", "6:00 起算当天")
check(game.today_str(datetime(2026, 10, 3, 23, 59)) == "2026-10-03", "23:59 仍是当天")
# 2) 熬夜时段（凌晨 2 点）打开：不跨天、无结算
s = new_state()
s["name"] = "日界测试"
s["last_day"] = "2026-10-02"
s["health"] = {"date": "2026-10-02", "done": [0] * 7, "multi": [0, 0], "score": 0}
s["daily"] = game._blank_daily("2026-10-02")
m19 = catch_up(s, now=datetime(2026, 10, 3, 2, 0))
check(s["last_day"] == "2026-10-02", "凌晨 2 点打开：不跨天（last_day 仍为前一天）")
check(not any("新的一天" in m for m in m19), "凌晨 2 点打开：无跨天结算消息")
# 3) 早上 7 点打开：跨天结算 + 新的一天
s["health"]["done"] = [1] * 7
m19b = catch_up(s, now=datetime(2026, 10, 3, 7, 0))
check(s["last_day"] == "2026-10-03", "早上 7 点打开：完成跨天（last_day 为当天）")
check(any("新的一天" in m for m in m19b), "早上 7 点打开：产生跨天结算消息")
# 4) 委托跨 0 点完成（23:50 接 → 0:20 完成）：熬夜时段仍属同一天 → 当日完成立即结算
s = new_state()
s["name"] = "跨零点委托"
s["last_day"] = "2026-10-02"
s["health"] = {"date": "2026-10-02", "done": [0] * 7, "multi": [0, 0], "score": 0}
s["daily"] = game._blank_daily("2026-10-02")
q19 = ["日界委托", "采集", "全天", 60, "简单", 100, 5, 10, {}]
s["active"] = [{"q": q19, "rate": 1.0, "qlv": 1, "meal": None,
                "acceptTs": int(datetime(2026, 10, 2, 23, 50).timestamp() * 1000),
                "finishTs": int(datetime(2026, 10, 3, 0, 20).timestamp() * 1000),
                "name": "日界委托"}]
catch_up(s, now=datetime(2026, 10, 3, 1, 0))
check(len(s["active"]) == 0, "23:50 接 → 0:20 完成（熬夜时段）：按当日完成立即结算")
# 5) 反向：23:50 接 → 次日 7:00 完成 → 跨游戏日，挂「明早打卡时结算」
s2 = new_state()
s2["name"] = "跨日委托"
s2["last_day"] = "2026-10-03"
s2["health"] = {"date": "2026-10-03", "done": [0] * 7, "multi": [0, 0], "score": 0}
s2["daily"] = game._blank_daily("2026-10-03")
q19b = ["跨日委托", "采集", "全天", 60, "简单", 100, 5, 10, {}]
s2["active"] = [{"q": q19b, "rate": 1.0, "qlv": 1, "meal": None,
                 "acceptTs": int(datetime(2026, 10, 2, 23, 50).timestamp() * 1000),
                 "finishTs": int(datetime(2026, 10, 3, 7, 0).timestamp() * 1000),
                 "name": "跨日委托"}]
catch_up(s2, now=datetime(2026, 10, 3, 8, 0))
check(len(s2["active"]) == 1 and s2["active"][0].get("pending"),
      "23:50 接 → 次日 7:00 完成：跨游戏日挂 pending（等待打卡结算）")

print("=== 20. 打卡时间窗 + 三餐拆分（v1.28） ===")
# 1) 时间窗：窗口外新打卡被拒、窗口内成功、窗口外取消被拒（v1.32 防误触）
s = new_state()
r20 = game.toggle_task(s, 1, [], now=datetime(2026, 10, 3, 14, 0))     # 下午点起床 → 拒绝
check(r20 is not None and s["health"]["done"][1] == 0, "起床打卡窗口外被拒（下午 14:00）")
game.toggle_task(s, 1, [], now=datetime(2026, 10, 3, 7, 0))            # 窗口内 → 成功
check(s["health"]["done"][1] == 1, "起床打卡窗口内成功（07:00）")
r21 = game.toggle_task(s, 1, [], now=datetime(2026, 10, 3, 14, 0))     # 窗口外取消 → 拒绝（v1.32 防误触）
check(r21 is not None and s["health"]["done"][1] == 1, "窗口外不可取消（防误触，v1.32）")
# 入睡窗口边界（v1.38r：21:00~23:30）：23:30 内可打、23:31 拒绝、20:59 未开窗
s2 = new_state()
game.toggle_task(s2, 0, [], now=datetime(2026, 10, 3, 23, 30))
check(s2["health"]["done"][0] == 1, "入睡打卡 23:30（窗口末尾）可打")
s3 = new_state()
r3 = game.toggle_task(s3, 0, [], now=datetime(2026, 10, 3, 23, 31))
check(r3 is not None and s3["health"]["done"][0] == 0, "入睡打卡 23:31（超窗）被拒")
s3b = new_state()
r3b = game.toggle_task(s3b, 0, [], now=datetime(2026, 10, 3, 20, 59))
check(r3b is not None and s3b["health"]["done"][0] == 0, "入睡打卡 20:59（窗口未开）被拒")
# 2) 三餐拆分：三项全点才得 15 分（全有全无）
s4 = new_state()
base4 = game.calc_health(s4)
game.toggle_meal(s4, 0, [], now=datetime(2026, 10, 3, 8, 0))     # 早餐
game.toggle_meal(s4, 1, [], now=datetime(2026, 10, 3, 12, 0))    # 午餐
sc_m2 = game.calc_health(s4)
check(s4["health"]["meals"] == [1, 1, 0] and s4["health"]["done"][5] == 0 and sc_m2 == base4,
      "三餐饮 2/3：不得分（全有全无）")
game.toggle_meal(s4, 2, [], now=datetime(2026, 10, 3, 18, 0))    # 晚餐
check(s4["health"]["meals"] == [1, 1, 1] and s4["health"]["done"][5] == 1
      and game.calc_health(s4) == base4 + 15, "三餐全点：+15 分")
game.toggle_meal(s4, 1, [], now=datetime(2026, 10, 3, 12, 30))   # 窗口内取消午餐 → 允许（v1.32）
check(s4["health"]["meals"] == [1, 0, 1] and s4["health"]["done"][5] == 0
      and game.calc_health(s4) == base4, "窗口内取消一餐：允许，回落 0 分")
r6 = game.toggle_meal(s4, 0, [], now=datetime(2026, 10, 3, 20, 0))   # 窗口外取消早餐 → 拒绝（防误触）
check(r6 is not None and s4["health"]["meals"] == [1, 0, 1], "窗口外不可取消（防误触，v1.32）")
# 三餐窗口校验
s5 = new_state()
r5 = game.toggle_meal(s5, 0, [], now=datetime(2026, 10, 3, 15, 0))   # 下午 3 点点早餐 → 拒绝
check(r5 is not None and s5["health"]["meals"][0] == 0, "早餐打卡窗口外被拒（15:00）")
# 3) 跨天熬夜提示
s6 = new_state()
s6["name"] = "熬夜提示"
s6["last_day"] = "2026-10-02"
s6["health"] = {"date": "2026-10-02", "done": [0, 1, 1, 1, 1, 1, 1], "multi": [0, 0], "score": 0, "meals": [1, 1, 1]}
s6["daily"] = game._blank_daily("2026-10-02")
m6 = catch_up(s6, now=datetime(2026, 10, 3, 9, 0))
check(any("−15%" in m and "23:30" in m for m in m6), "跨天未早睡 → 提示「成功率 −15%」")
s7 = new_state()
s7["last_day"] = "2026-10-02"
s7["health"] = {"date": "2026-10-02", "done": [1, 1, 1, 1, 1, 1, 1], "multi": [0, 0], "score": 0, "meals": [1, 1, 1]}
s7["daily"] = game._blank_daily("2026-10-02")
m7 = catch_up(s7, now=datetime(2026, 10, 3, 9, 0))
check(not any("−15%" in m for m in m7), "早睡达成 → 无熬夜提示")
# 4) 旧档迁移：done[5] 已勾选 → meals 视为全点
s8 = {"health": {"date": "2026-10-02", "done": [1, 1, 1, 1, 1, 1, 1], "multi": [0, 0], "score": 100}}
game.migrate_state(s8)
check(s8["health"]["meals"] == [1, 1, 1], "旧档迁移：三餐已勾选 → meals 全点")

print("=== 21. v1.29 委托池扩充与新增道具 ===")
# 1) 委托数量（扩充目标 16/24/30/20/16）
qcount = {lv: len(game.C[lv]) for lv in ["Lv1", "Lv2", "Lv3", "Lv4", "Lv5"]}
check(qcount == {"Lv1": 16, "Lv2": 25, "Lv3": 32, "Lv4": 34, "Lv5": 50},
      "委托池 16/25/32/34/50（v1.32 补 8 简单档 + v1.41 I1 加 10 链委托 + I4 加 6 新机制委托 + v1.42 加 6 龙种委托 + v1.45 加 6 恶魔/种族委托 + v1.45b 加 3 链委托 + v1.57 种族链 12），实际 " + str(qcount))
# 2) 全部委托：9 字段、有专属描写、掉落材料在材料表、主材料格式合法
fmt_bad = [q[0] for lv in game.C for q in game.C[lv]
           if len(q) != 9 or q[0] not in game.QUEST_STORY or any(m not in game.M for m in q[8])]
check(not fmt_bad, "全部委托字段/描写/材料引用正确" + ("，异常：" + str(fmt_bad[:3]) if fmt_bad else ""))
gear_bad = [g[0] for g in game.GEAR
            if g[5] != "—" and g[5].split("×")[0] not in game.M]
check(not gear_bad, "全部装备主材料在材料表" + ("，异常：" + str(gear_bad[:3]) if gear_bad else ""))
# 3) 新增装备 / 材料 / 料理在表
new_gear = ["枭羽猎弓", "秘银戒指", "符文长剑", "蛇怪皮甲", "守誓者护符", "虚空结晶坠", "星界护铠"]
g_bad = [n for n in new_gear if not any(g[0] == n for g in game.GEAR)]
check(not g_bad, "7 件新装备在装备表" + str(g_bad))
new_mats = ["枭羽", "秘银矿", "符文石", "蛇怪之眼", "虚空结晶", "星界尘"]
m_bad = [n for n in new_mats if n not in game.M]
check(not m_bad, "6 种新材料在材料表" + str(m_bad))
new_recipes = ["蜜炙鹿排", "月光花茶", "蛇怪眼汤"]
r_bad = [n for n in new_recipes if not any(r["n"] == n for r in game.CFG["recipes"])]
check(not r_bad, "3 道新料理在配方表" + str(r_bad))
# 4) 探索区掉落：新规则道具入池（每项独立判定，概率无需合计 100）
check(any(n == "幸运币" and p == 4 for n, p in [x for x in game.REGIONS if x["n"] == "腐化森林"][0]["d"]),
      "腐化森林掉落含幸运币（独立概率 4%）")
check(any(n == "时之怀表" and p == 3 for n, p in [x for x in game.REGIONS if x["n"] == "虚空裂痕"][0]["d"]),
      "虚空裂痕掉落含时之怀表（独立概率 3%）")
# 5) 时之怀表：接取窗口重置
s9 = new_state()
s9["items"]["时之怀表"] = 1
s9["pool"] = {"point": "08:00", "list": [list(game.C["Lv1"][0])], "taken": False,
              "bornTs": game.now_ms() - game.POOL_WINDOW_MS - 1000, "expiredLogged": True}
check(game.pool_expired(s9), "构造：接取窗口已过期")
game.use_item(s9, "时之怀表", [])
check(not game.pool_expired(s9) and s9["items"].get("时之怀表") is None,
      "时之怀表：窗口重置为 1 小时、道具消耗")
s9["pool"]["taken"] = True
s9["items"]["时之怀表"] = 1
r9 = game.use_item(s9, "时之怀表", [])
check(r9 is not None and s9["items"].get("时之怀表") == 1, "时之怀表：本批已接取 → 拒绝")
# 6) 幸运币：下次委托 +5%（与稀有事件同级），不叠加、取最大
s10 = new_state()
s10["items"]["幸运币"] = 1
game.use_item(s10, "幸运币", [])
check(abs(s10.get("rare_next_rate", 0) - 0.05) < 1e-9, "幸运币：rare_next_rate = 0.05")
s10["items"]["幸运币"] = 1
game.use_item(s10, "幸运币", [])
check(abs(s10.get("rare_next_rate", 0) - 0.05) < 1e-9, "幸运币：重复使用不叠加（保持 0.05）")
s10["rare_next_rate"] = 0.06
s10["items"]["幸运币"] = 1
game.use_item(s10, "幸运币", [])
check(abs(s10["rare_next_rate"] - 0.06) < 1e-9, "幸运币：已有更高加成 → 保持 0.06")
# 7) 幸运币加成进入成功率公式（Lv3 普通 48% → 53%）
s11 = new_state()
s11["lv_idx"] = 2
q3 = [q for q in game.C["Lv3"] if q[4] == "普通"][0]
rate_n = game.success_rate(s11, q3)
s11["rare_next_rate"] = 0.05
rate_y = game.success_rate(s11, q3)
check(abs((rate_y - rate_n) - 0.05) < 0.005,
      "幸运币 +5pp 作用于成功率（" + str(round(rate_n * 100, 1)) + "% → " + str(round(rate_y * 100, 1)) + "%）")

print("=== 22. v1.30 混合委托池 + 按委托等级参数 + 等级差修正 ===")
# 1) 混合池构成：Lv_n 玩家池 = Lv1~Lv_n
for li, want in [(0, {0}), (2, {0, 1, 2}), (4, {0, 1, 2, 3, 4})]:
    s = new_state(); s["lv_idx"] = li
    lvs = {game.QUEST_LV[q[0]] for q in game.mix_pool(s)}
    check(lvs == want, "Lv" + str(li + 1) + " 玩家混合池含 Lv" + str(sorted(x + 1 for x in want)))
s = new_state(); s["lv_idx"] = 4
# v1.41 I1：全新存档未满足链前置 → 157 总池 - 31 条链节点 = 126（v1.57：链前置 18 → 31）
check(len(game.mix_pool(s)) == 126, "Lv5 玩家混合池（新档，链前置过滤后）= 126 个委托")
# v1.41 I1：完成前置后链节点进入池（迷雾灯塔·引航 → 残焰）
s2 = new_state(); s2["lv_idx"] = 4; s2["done_quests"] = {"迷雾灯塔·引航": 1}
check(len(game.mix_pool(s2)) == 127, "完成链前置后混合池 +1（127）")
_mixnames = [q[0] for q in game.mix_pool(s2)]
check("迷雾灯塔·残焰" in _mixnames and "迷雾灯塔·引航" in _mixnames,
      "完成前置 → 链下一节点进入抽取池")
# v1.41 I1：QUEST_REQ 引用完整性（键值都必须是真实委托名且键确有前置）
_allnames = {q[0] for lv in game.C for q in game.C[lv]}
_req_bad = [k2 for k2, v2 in game.QUEST_REQ.items() if k2 not in _allnames or v2 not in _allnames]
check(not _req_bad, "QUEST_REQ 引用完整性（31 条链节点，键值均为真实委托）" + ("，异常：" + str(_req_bad) if _req_bad else ""))
check(len(game.QUEST_REQ) == 31, "QUEST_REQ 共 31 条链前置，实际 " + str(len(game.QUEST_REQ)))
# 2) draw_pool 从混合池抽取（多次采样覆盖全部等级）
s = new_state(); s["lv_idx"] = 4
got = set()
for _ in range(120):
    for q in game.draw_pool(s, game.latest_point()):
        got.add(game.QUEST_LV[q[0]])
check(got == {0, 1, 2, 3, 4}, "Lv5 玩家抽取覆盖全部 5 个等级")
# 3) 成功率参数按委托等级
def rate_of(lv_idx, lv, diff):
    q = [x for x in game.C["Lv" + str(lv)] if x[4] == diff][0]
    s = new_state(); s["lv_idx"] = lv_idx
    s["history"] = [{"sleep": True}]
    return game.success_rate(s, q)
check(abs(rate_of(4, 1, "简单") - 1.0) < 1e-9, "Lv5 做 Lv1 委托 = 100%（按委托等级 Floor 100%）")
check(abs(rate_of(4, 1, "困难") - 1.0) < 1e-9, "Lv5 做 Lv1 困难委托 = 100%（Floor 强制）")
check(abs(rate_of(4, 2, "简单") - 0.95) < 1e-9, "Lv5 做 Lv2 简单 = 60+10+36（等级差）= 106% → 封顶 95%")
# 4) 等级差修正：+12%/级，上限 +36%（v1.32）
check(abs(rate_of(3, 3, "普通") - 0.60) < 1e-9, "Lv4 做 Lv3 普通 = 48+12 = 60%")
check(abs(rate_of(4, 3, "普通") - 0.72) < 1e-9, "Lv5 做 Lv3 普通 = 48+24 = 72%")
check(abs(rate_of(4, 4, "普通") - 0.52) < 1e-9, "Lv5 做 Lv4 普通 = 40+12 = 52%")
check(abs(rate_of(3, 4, "普通") - 0.40) < 1e-9, "Lv4 做 Lv4 普通 = 40%（同级无等级差）")
check(abs(rate_of(4, 5, "普通") - 0.32) < 1e-9, "Lv5 做 Lv5 普通 = 32%（同级无等级差）")
check(abs(rate_of(4, 5, "噩梦") - 0.12) < 1e-9, "Lv5 做 Lv5 噩梦 = 32-20 = 12%")
check(abs(rate_of(4, 2, "普通") - 0.95) < 1e-9, "Lv5 做 Lv2 普通 = 60+36 = 96% → 封顶 95%")
check(abs(rate_of(4, 2, "困难") - 0.86) < 1e-9, "Lv5 做 Lv2 困难 = 60-10+36 = 86%")
check(abs(rate_of(3, 2, "普通") - 0.84) < 1e-9, "Lv4 做 Lv2 普通 = 60+24（2 级差）= 84%")
# 5) v1.32：eCap 提升 + Lv4/Lv5 简单档委托
check(game.CFG["eCap"] == [0.10, 0.10, 0.08, 0.08, 0.06], "eCap 提升：Lv4=8pp、Lv5=6pp")
check(sum(1 for x in game.C["Lv4"] if x[4] == "简单") == 4
      and sum(1 for x in game.C["Lv5"] if x[4] == "简单") == 4, "Lv4/Lv5 各含 4 个简单档委托")

print("=== 23. v1.32 内容大扩充（材料/装备/料理/道具）+ 噩梦词条修复 ===")
# 1) 数量总览
check(len(game.M) == 125, "材料 125 种（v1.57 → 119；v1.58 六域遗珍 +6）")
check(len(game.GEAR) == 131, "装备 131 件（v1.58 → 128；v1.59 弱出口补全 +3）")
check(len(game.CFG["recipes"]) == 25, "料理 25 道（v1.50 → 21；v1.58 六域遗珍 +4）")
check(len(game.ITEM_DESC) == 15, "道具 15 种（7→11，+4；v1.46 +4 准备物）")
# 2) 新装备主材料均在材料表
new_gear = ["云杉木法杖", "白桦木长矛", "棉纹软甲", "黄玉吊坠", "黑檀木骨杖", "黑曜石重锤", "大理石壁垒",
            "紫藤花冠", "秘银合金巨剑", "凤凰木长弓", "魔狼鬃甲", "月长石护符", "星陨岩战锤", "云纹锦衣", "星辉花冠", "时砂指环"]
check(all(game.gear_def(n) for n in new_gear), "16 件新装备全部在册")
check(all(game.gear_def(n)[5].split("×")[0] in game.M for n in new_gear), "新装备主材料均在材料表")
# 3) 料理 / 委托掉落 / 探索掉落合法性
check(all(k in game.M for r in game.CFG["recipes"] for k in game.recipe_ing(r)), "全部料理材料（主材+辅材）在材料表")
check(all(m in game.M for lv in ("Lv4", "Lv5") for x in game.C[lv] for m in x[8]), "新委托掉落材料均在材料表")
ok_items = set(game.M) | set(game.ITEM_DESC) | {"旧宝箱"}
check(all(it in ok_items for rg in game.REGIONS for it, _ in rg["d"] if it), "探索掉落全部合法")
# 4) 噩梦难度成功率词条（v1.29 起为死词条，v1.32 修复）
sv = new_state(); sv["lv_idx"] = 4; sv["history"] = [{"sleep": True}]
q_nm = [x for x in game.C["Lv5"] if x[4] == "噩梦"][0]
r0 = game.success_rate(sv, q_nm)
sv["equipped"]["weapon"] = "龙牙巨剑"
r1 = game.success_rate(sv, q_nm)
check(abs((r1 - r0) - 0.10) < 1e-9,
      "龙牙巨剑：主属性 +5pp 与 噩梦词条 +5pp 均生效（" + str(round(r0 * 100)) + "% → " + str(round(r1 * 100)) + "%）")
# 5) 四个新道具
s23 = new_state(); m23 = []
s23["items"]["专注药剂"] = 1; game.use_item(s23, "专注药剂", m23)
check(s23.get("rare_next_rate") == 0.03, "专注药剂 → 下一次成功率 +3%")
s23["items"]["谈判卷轴"] = 1; game.use_item(s23, "谈判卷轴", m23)
check(s23.get("rare_next_pay") == 0.15, "谈判卷轴 → 下一次报酬 +15%")
s23["items"]["旅行干粮"] = 1; s23["energy"] = 0; game.use_item(s23, "旅行干粮", m23)
check(s23["energy"] == 30, "旅行干粮 → 精力 +30（v1.38m 上调）")
s23["items"]["神秘地图"] = 1; e0 = s23["explore"]; game.use_item(s23, "神秘地图", m23)
check(s23["explore"] == e0 + 2, "神秘地图 → 探索点 +2（v1.38m 下调）")

print("=== 24. v1.34 健康分口径：昨日日结算分 ===")
q24 = ["讨伐独眼巨人", "精英", "08:00-23:30", 180, "困难", 50000, 60, 62, {"巨人骨": [1, 3]}]
s24 = new_state(); s24["lv_idx"] = 3
s24["health"]["score"] = 50
s24["history"] = [{"date": "昨日", "score": 90, "sleep": True, "done": 0}]
check(abs(game.success_rate(s24, q24) - (0.40 - 0.10 + 90 * 0.002)) < 1e-9,
      "success_rate 按昨日分 90（+18pp），忽略当日分 50")
s24["health"]["score"] = 100
check(abs(game.success_rate(s24, q24) - (0.40 - 0.10 + 90 * 0.002)) < 1e-9, "当日评分变化不影响成功率")
s25 = new_state(); s25["lv_idx"] = 3; s25["health"]["score"] = 100
check(abs(game.success_rate(s25, q24) - (0.40 - 0.10)) < 1e-9, "新号第一天无历史 → 健康加成 0")
s26 = new_state()
s26["health"]["score"] = 100
s26["history"] = [{"date": "y", "score": 80, "sleep": True}]
check(abs(game.legend_rate(s26, "普通") - (0.05 + 80 * 0.005)) < 1e-9, "legend_rate 按昨日分 80（+40pp）")

print("=== 25. v1.35 图鉴记录与新成就 ===")
s27 = new_state()
check("seen_mats" in s27 and "forged" in s27 and "cooked" in s27, "图鉴字段默认存在（seen_mats/forged/cooked）")

# craft → forged 记录
g0 = [g for g in game.GEAR if g[1] == "普通" and g[5] != "—"][0]
mm0 = game.craft_main_mat(g0[0])
sub_cnt0 = game.sub_mat_count(g0[1], g0[2])
cats0 = game.sub_cats_for(mm0["mat"])          # v1.38c：副材料需同系品类
pool0 = [k for k, v in game.M.items() if v[1] == "普通" and v[0] in cats0 and k != mm0["mat"]]
s27["mats"] = {mm0["mat"]: mm0["cnt"]}
for k in pool0[:3]:
    s27["mats"][k] = sub_cnt0
s27["money"] = 10**9
s27["blueprints"][g0[0]] = True
err0 = game.craft(s27, g0[0], [])
check(err0 is None and g0[0] in s27["forged"], "craft 后写入图鉴 forged 记录")

# cook → cooked 记录
r0 = game.CFG["recipes"][0]
s28 = new_state()
for k, n in game.recipe_ing(r0).items():
    s28["mats"][k] = n
err1 = game.cook(s28, 0, [])
check(err1 is None and r0["n"] in s28["cooked"], "cook 后写入图鉴 cooked 记录")

# 新成就判定（v1.35：5→10）
s29 = new_state()
s29["history"] = [{"date": "d", "score": 80, "sleep": True,
                   "tasks": [1, 0, 0, 0, 0, 0, 0], "multi": [0, 0]} for _ in range(60)]
check(game._achv_cond(s29, "夜之安眠"), "夜之安眠：累计 60 天早睡达成")
check(not game._achv_cond(s29, "晨间行者"), "晨间行者：未满足条件时不达成")
s29["history"] = [{"date": "d", "score": 80, "sleep": False,
                   "tasks": [0, 1, 0, 0, 1, 0, 0], "multi": [0, 2]} for _ in range(60)]
check(game._achv_cond(s29, "晨间行者"), "晨间行者：累计 60 天早起达成")
check(game._achv_cond(s29, "身强体健"), "身强体健：累计 60 天运动达成")
check(game._achv_cond(s29, "博览群书"), "博览群书：累计 120 次阅读达成")
s29["total_quests"] = 300
check(game._achv_cond(s29, "百战之躯"), "百战之躯：累计 300 次委托达成")
msgs29 = []
game.check_achievements(s29, msgs29)
check(all(n in s29["achv"] for n in ("晨间行者", "身强体健", "博览群书", "百战之躯"))
      and "百战护符" in s29["gear"], "新成就达成 → 发放对应成就饰品")

print("=== 26. v1.35 / v1.55 宠物系统（多宠 / 偏好 / 进化变异 / 阅读驱动 / 品阶） ===")
s30 = new_state()
check("pet_data" in s30, "宠物成长字段默认存在（pet_data）")
game.grant_pet(s30, "月光狐")
game.grant_pet(s30, "星界幼龙")
check("月光狐" in s30["pets"] and s30["pet_data"]["月光狐"]["stage"] == 1, "grant_pet 加入宠物并初始化成长数据")
b0 = game.pet_bonus(s30)
check(abs(b0["rate"]) < 1e-9 and abs(b0["mat"]) < 1e-9,
      "pet_bonus（v1.56c）：未携带 → 全 0（星界幼龙 / 月光狐均不计入）")
s30["carry_pet"] = "月光狐"
b0c = game.pet_bonus(s30)
check(abs(b0c["pay"] - 0.01) < 1e-9 and abs(b0c["rate"]) < 1e-9,
      "pet_bonus（携带月光狐）：一阶报酬+1%，星界幼龙不计入")
# v1.55b：品阶体系（普通 < 精良 < 稀有 < 史诗 < 传说）
check(game.PET_LINES["史莱姆"].get("rank") == "普通" and game.PET_LINES["绒球兽"].get("rank") == "精良"
      and game.PET_LINES["捣蛋鬼"].get("rank") == "稀有" and game.PET_LINES["月光狐"].get("rank") == "史诗"
      and all(game.PET_LINES[n].get("rank") == "传说" for n in ("星界幼龙", "龙神幼崽", "幼龙群", "深渊之眼")),
      "宠物品阶标签（普通 / 精良 / 稀有 / 史诗 / 传说）")
def _pv(n):   # 终局折算（百分点）：mat 1%=1、rate 1%=1.2、pay 1%=1、exp 1%=0.8；sp 项兼容保留（v1.56b 起宠物无探索点加成，恒 0）
    m = game.PET_LINES[n]["mut"]
    return (m.get("mat", 0) + m.get("rate", 0) * 1.2 + m.get("pay", 0) + m.get("exp", 0) * 0.8) * 100 + m.get("sp", 0) * 3.5
check(_pv("史莱姆") < _pv("绒球兽") < _pv("捣蛋鬼") < _pv("月光狐")
      < min(_pv(n) for n in ("星界幼龙", "龙神幼崽", "幼龙群", "深渊之眼")),
      "品阶梯度：终局加成折算值严格递增（史莱姆 < 绒球兽 < 捣蛋鬼 < 月光狐 < 传说 4 伙伴）")
pv = game.pet_feed_value("月光狐", "月光草")
check(pv["v"] == 0 and pv["mv"] == 8, "v1.55：月光狐（阅读驱动）喂月光草 成长+0 / 变异+8")
# v1.55c：品阶营养（未列出材料按品阶给成长；口味与品阶取较高者）
check(game.pet_feed_value("捣蛋鬼", "龙心")["v"] == 15, "品阶营养：未列出传说材料 +15 成长（对齐小狼）")
check(game.pet_feed_value("捣蛋鬼", "月光草")["v"] == 4, "品阶营养：未列出材料按品阶给成长（月光草·稀有 +4）")
check(game.pet_feed_value("深渊之眼", "暗影草")["v"] == 10, "品阶营养：口味与品阶取较高者（暗影草 口味 10 > 史诗基数 8）")
check(game.pet_feed_value("绒球兽", "蘑菇")["v"] == 5 and game.pet_feed_value("史莱姆", "山珍")["v"] == 4,
      "品阶营养：口味值高于基数时保留口味（蘑菇 +5）；高品阶材料通用托底（山珍 +4）")
# v1.56e：本命材料（非食材 / 草药的主题材料——只有本宠能吃）
check(game.pet_feed_value("星界幼龙", "星核")["v"] == 17 and game.pet_feed_value("星界幼龙", "星尘")["v"] == 8,
      "v1.56e：星界幼龙本命材料（星核 +17 / 星尘 +8）")
check(game.pet_feed_value("深渊之眼", "混沌碎片")["v"] == 10 and game.pet_feed_value("深渊之眼", "暗影龙鳞")["v"] == 17,
      "v1.56e：深渊之眼本命材料（混沌碎片 +10 / 暗影龙鳞 +17）")
check(game.pet_feed_value("史莱姆", "星核").get("refuse") and game.pet_feed_value("星界幼龙", "混沌碎片").get("refuse")
      and not game.pet_feed_value("史莱姆", "净化石").get("refuse"),
      "v1.56e：本命材料只有本宠能吃（史莱姆拒星核 / 星界幼龙拒混沌碎片；史莱姆吃自己的净化石）")
check(game.pet_feed_value("绒球兽", "兽肉").get("refuse"), "偏好：绒球兽拒食兽肉（素食）")
check(game.pet_feed_value("捣蛋鬼", "暗影草")["mv"] == 12, "偏好：捣蛋鬼喂暗影草 变异+12（本命材料）")
s30["mats"]["月光草"] = 20
err = game.feed_pet(s30, "月光狐", "月光草", [])
check(err is not None and "二阶起" in err and s30["mats"]["月光草"] == 20,
      "v1.55：阅读驱动一阶喂高级材料被拦（不扣材料）")
pd30 = s30["pet_data"]["月光狐"]
check(game.pet_read_need("月光狐", 1) == 45 and game.pet_read_need("月光狐", 2) == 60
      and game.pet_read_need("月光狐", 3) is None, "阅读驱动：升阶门槛 45 / 60 / —")
# v1.55：阅读驱动进化（阅读次数达标自动升阶）
s30["history"] = [{"date": "x", "multi": [0, 44]}]
game.sync_read_pets(s30, [])
check(pd30["stage"] == 1, "阅读 44 次：不进化")
s30["history"] = [{"date": "x", "multi": [0, 45]}]
game.sync_read_pets(s30, [])
check(pd30["stage"] == 2, "阅读 45 次 → 月影狐")
s30["history"] = [{"date": "x", "multi": [0, 60]}]
game.sync_read_pets(s30, [])
check(pd30["stage"] == 3, "阅读 60 次 → 幻月九尾")
game.sync_read_pets(s30, [])
check(pd30["stage"] == 3, "满阶后幂等（不重复升阶）")
# 二阶起喂高级材料积累变异
pd30["stage"] = 2
err = game.feed_pet(s30, "月光狐", "月光草", [])
check(err is None and pd30["mutate"] == 8 and s30["mats"]["月光草"] == 19, "二阶喂月光草 → 变异+8")
pd30["stage"] = 3
pd30["mutate"] = 260
err = game.evolve_pet(s30, "月光狐", [])
check(err is None and pd30["stage"] == 4, "evolve_pet：变异成功（阅读驱动不看成长值）")
b1 = game.pet_bonus(s30)
check("sp" not in b1 and abs(b1["rate"] - 0.02) < 1e-9 and abs(b1["mat"] - 0.06) < 1e-9,
      "变异后 pet_bonus（携带星月狐仙）：材料+6%、成功率+2%；v1.58 sp 通道移除（星界幼龙不计入）")
s30["carry_pet"] = "星界幼龙"
b2 = game.pet_bonus(s30)
check(abs(b2["rate"] - 0.01) < 1e-9 and abs(b2["mat"]) < 1e-9,
      "pet_bonus：切换携带 → 只算新携带宠物（星界幼龙 成功率+1%）")
s30["carry_pet"] = "月光狐"

print("=== 27. v1.38 批3：连击保险 / 节日·纪念日 / 图鉴称号 ===")
_T = datetime.strptime(game.today_str(), "%Y-%m-%d")
_Y = (_T - timedelta(days=1)).strftime("%Y-%m-%d")


def _mk_hist(first_ago, n, sleep=True):
    out = []
    for i in range(n):
        out.append({"date": (_T - timedelta(days=first_ago + i)).strftime("%Y-%m-%d"),
                    "score": 80, "sleep": sleep, "done": 3, "gold": 10,
                    "tasks": [1, 1, 1, 1, 1, 1, 1], "multi": [0, 0]})
    return list(reversed(out))          # 正序（老在前）


def _state_yesterday(hist):
    s2 = new_state()
    s2["history"] = hist
    s2["health"] = {"date": _Y, "done": [0] * 7, "multi": [0, 0], "score": 0, "meals": [0, 0, 0]}
    s2["last_day"] = _Y
    return s2


# A2 连击保险
s31 = _state_yesterday(_mk_hist(2, 7))
m31 = catch_up(s31)
check(any("连击保险" in m for m in m31), "连击保险：早睡 7 天断 1 天 → 触发")
check(s31["shield_days"] == [_Y], "连击保险：被保护日 = 昨天")
check(game._sleep_streak(s31) == 8, "连击保险：连击保留为 8（7+被保护日）")
check(game._try_combo_shield(s31, [], 9) is False, "连击保险：同月不二次触发")
s32 = _state_yesterday(_mk_hist(2, 5))
m32 = catch_up(s32)
check(not any("连击保险" in m for m in m32) and s32["shield_days"] == [], "连击保险：连击不足 7 天不触发")
s33 = new_state()
catch_up(s33)
check(s33["shield_days"] == [], "连击保险：新号零历史不触发")
o31 = {"history": [], "health": {}}
game.migrate_state(o31)
check(o31["shield_month"] == "" and o31["shield_days"] == [], "连击保险：旧档迁移自动补字段")

# C9 节日（mmdd 临时覆盖 + 还原，跑测试当天是真实节日也不受影响）
_mmdd = game.today_str()[5:]
_saved_fest = game.FESTIVALS.get(_mmdd)
game.FESTIVALS[_mmdd] = {"name": "🧪 测试节", "greet": "节日快乐", "text": "测试文案",
                         "eff": {"desc": "测试效果：报酬 +20%、成功率 +10%", "pay": 0.2, "rate": 0.1}}
s34 = new_state()
m34 = catch_up(s34)
check(s34["pending_festival"] and "测试节" in s34["pending_festival"]["name"]
      and s34["festival_shown"] == game.today_str(), "节日：当天首次打开 → 欢迎弹窗入队（v1.41d）")
s34["pending_festival"] = None          # 模拟前端 festival_ack 已展示
m35 = catch_up(s34)
check(s34["pending_festival"] is None, "节日：同日重开不重复入队（ack 后不再生成）")

# 节日报酬 +10%（stub 掷骰固定 6：成功且非暴击/大失败）
_real_rand = game.rand
game.rand = lambda n: 6
q0 = game.C["Lv1"][0]
s36 = new_state()
_p0 = s36["money"]
game.settle(s36, {"q": q0, "rate": 1.0, "acceptTs": game.now_ms(), "finishTs": game.now_ms()}, [])
gold_fest = s36["money"] - _p0
_saved2 = game.FESTIVALS[_mmdd]
del game.FESTIVALS[_mmdd]              # 临时关掉节日，验证基线
s37 = new_state()
_p1 = s37["money"]
game.settle(s37, {"q": q0, "rate": 1.0, "acceptTs": game.now_ms(), "finishTs": game.now_ms()}, [])
gold_plain = s37["money"] - _p1
game.FESTIVALS[_mmdd] = _saved2        # 还原节日
game.rand = _real_rand
check(gold_plain == q0[5], "节日：无节日时报酬为原值（" + str(gold_plain) + "）")
check(gold_fest == int(round(q0[5] * 1.2)), "节日：当天报酬 +20%（" + str(gold_plain) + " → " + str(gold_fest) + "）")
if _saved_fest is None:
    del game.FESTIVALS[_mmdd]
else:
    game.FESTIVALS[_mmdd] = _saved_fest

# ── v1.41c：假期区间 + 节日窗口扩展（临时恢复真实区间验证，测完还原隔离态）──
game.FESTIVAL_RANGES.extend(_REAL_FEST_RANGES)
check(game.festival_of("2026-10-01") is not None and game.festival_of("2026-10-05") is not None
      and game.festival_of("2026-10-07") is not None, "假期区间：10-01 / 10-05 / 10-07 均判定为节日")
check(game.festival_of("2026-10-08") is None and game.festival_of("2026-09-30") is None,
      "区间外（10-08 / 09-30）非节日")
check(game.festival_of("2026-01-01")["name"].find("元旦") >= 0, "单日节日：元旦仍生效")
_w0 = game.task_window_of(0, datetime(2026, 10, 5, 22, 0))
_w1 = game.task_window_of(1, datetime(2026, 10, 5, 7, 0))
check(_w0 == (21 * 60, 23 * 60 + 30 + 60), "节日：入睡窗口尾部 +1 小时（延至 00:30）")
check(_w1 == (6 * 60, 8 * 60 + 60), "节日：起床窗口尾部 +1 小时（延至 09:00）")
check(game.meal_window_of(1, datetime(2026, 10, 5, 12, 0)) == (11 * 60 - 30, 14 * 60 + 30),
      "节日：三餐窗口前后各 +30 分钟")
check(game._in_win(_w0, datetime(2026, 10, 2, 0, 15)), "节日：入睡窗口跨日（次日 00:15 仍可打卡）")
check(not game._in_win(_w0, datetime(2026, 10, 2, 1, 0)), "节日：入睡窗口次日 01:00 已关")
check(game._win_str(_w0) == "21:00-00:30", "跨日窗口显示次日时刻（21:00-00:30）")
check(game.task_window_of(0, datetime(2026, 9, 20, 22, 0)) == (21 * 60, 23 * 60 + 30),
      "非节日：入睡窗口还原 21:00~23:30")
_saved_is = game.is_festival
game.is_festival = lambda d=None: True          # 打桩：pool_window_ms 内部按 is_festival 判定
check(game.pool_window_ms() == game.POOL_WINDOW_MS + game.FEST_POOL_BONUS_MS, "节日：接取窗口 +1 小时")
game.is_festival = _saved_is
# v1.41e：农历节日表（2025~2040）
check(game.festival_of("2026-02-17") and "春节" in game.festival_of("2026-02-17")["name"], "农历：2026 春节（02-17）判定")
check(game.festival_of("2026-02-16") and "除夕" in game.festival_of("2026-02-16")["name"], "农历：除夕（02-16）判定")
check(game.festival_of("2026-02-22") is not None and game.festival_of("2026-02-23") is None,
      "春节区间：初六（02-22）生效 / 初七（02-23）结束")
check(game.festival_of("2026-09-25")["name"].find("中秋") >= 0 and game.festival_of("2026-06-19")["name"].find("端午") >= 0
      and game.festival_of("2026-10-18")["name"].find("重阳") >= 0, "农历：中秋 / 端午 / 重阳判定")
check(game.festival_of("2025-01-29")["name"].find("春节") >= 0, "农历：2025 春节（01-29）判定")
check(game.festival_of("2026-02-01") is None, "农历表外日期非节日（2026-02-01）")
check(game.festival_of("2026-02-17")["greet"] == "新年大吉" and game.festival_of("2026-06-19")["greet"] == "端午安康",
      "农历：节日问候语（春节「新年大吉」/ 端午「端午安康」）")
# v1.41f：节日专属效果表（每节日不同；v1.41f2 平衡调整）
check(game.today_fest_eff("2026-10-01").get("pay") == 0.2 and game.today_fest_eff("2026-10-01").get("rate") == 0.1,
      "节日效果：国庆 = 报酬 +20% / 成功率 +10%")
check(game.today_fest_eff("2026-04-05").get("rate_types", {}).get("采集") == 0.10,
      "节日效果：清明 = 采集类成功率 +10%（v1.41f2 由 +15% 下调）")
check(game.today_fest_eff("2026-01-26").get("cook_mul") == 2.0, "节日效果：腊八 = 料理效果翻倍")
check(game.today_fest_eff("2026-06-19").get("cook_mul") == 1.5 and not game.today_fest_eff("2026-06-19").get("no_sleep_penalty"),
      "节日效果：端午 = 料理 +50%（v1.41f2 由免熬夜改粽香，免熬夜移交除夕）")
check(game.today_fest_eff("2026-01-01").get("vit_per_task") == 1,
      "节日效果：元旦 = 打卡每项 +1 活力（v1.41f2 由 +3 下调）")
check(game.today_fest_eff("2026-02-16").get("no_sleep_penalty") is True and game.today_fest_eff("2026-02-16").get("login_vit") == 20,
      "节日效果：除夕 = 守岁免熬夜惩罚 + 压岁钱（v1.41f2 移交）")
check(game.today_fest_eff("2026-02-17").get("rate") == 0.10,
      "节日效果：春节成功率 +10%（v1.41f2 由 +15% 下调）")
check(game.today_fest_eff("2026-10-18").get("explore_gain") == 1.0 and game.today_fest_eff("2026-03-03").get("explore_gain") == 0.5,
      "节日效果：重阳探索点翻倍 / 元宵 +50%")
check(game.today_fest_eff("2026-10-05").get("pay") == 0.2, "节日效果：国庆假期区间沿用国庆效果（10-05）")
game.FESTIVAL_RANGES.clear()                    # 还原隔离状态（后续测试继续无节日基线）

# C9 纪念日
s38 = new_state()
s38["created"] = (_T - timedelta(days=30)).strftime("%Y-%m-%d")
_v0 = s38["vit"]
m38 = catch_up(s38)
check(any("纪念日" in m for m in m38) and s38["vit"] == _v0 + 20 + 1 and s38["anniv_last"] == 30
      and s38["sign"]["streak"] == 1,
      "纪念日：第 30 天发放活力点 +20（另 +1 为 v1.50 每日签到）")
m39 = catch_up(s38)
check(not any("纪念日" in m for m in m39), "纪念日：同日不重复发放")

# D11 图鉴称号
s40 = new_state()
s40["seen_mats"] = list(game.M.keys())
s40["forged"] = [g[0] for g in game.GEAR]
s40["cooked"] = [r["n"] for r in game.CFG["recipes"]]
s40["done_quests"] = {q[0]: 1 for lv in game.C.values() for q in lv}
check_achievements(s40, [])
check("博物学家" in s40["titles"] and "军械大师" in s40["titles"]
      and "宫廷主厨" in s40["titles"] and "传说冒险者" in s40["titles"], "图鉴称号：四类集齐全部授予")
s41 = new_state()
s41["seen_mats"] = list(game.M.keys())[:-1]        # 材料少一个
s41["forged"] = [g[0] for g in game.GEAR]
check_achievements(s41, [])
check("博物学家" not in s41["titles"] and "军械大师" in s41["titles"], "图鉴称号：未集齐不授予，已集齐正常授予")
s42 = new_state()
check_achievements(s42, [])
check(s42["titles"] == [], "图鉴称号：空档不误授")

# 节日：成功率独立 +10%
s44 = new_state()
_sr0 = game.success_rate(s44, q0)
game.FESTIVALS[_mmdd] = {"name": "🧪 测试节", "greet": "节日快乐", "text": "测试文案",
                         "eff": {"desc": "测试效果", "pay": 0.2, "rate": 0.1}}
_sr1 = game.success_rate(s44, q0)
if _saved_fest is None:
    del game.FESTIVALS[_mmdd]
else:
    game.FESTIVALS[_mmdd] = _saved_fest
check(abs(min(1.0, _sr0 + 0.10) - _sr1) < 1e-9, "节日：成功率独立 +10%（" + str(round(_sr0, 3)) + " → " + str(round(_sr1, 3)) + "）")

# 副材料品类联动（v1.38c）
s45 = new_state()
s45["mats"] = {"蘑菇": 99}                     # 蘑菇=食材/普通：品阶符合但品类不符
check(game.pick_sub_mats(s45, "普通", "松木", 2) is None, "副材料：食材（蘑菇）不可用于打造猎弓")
s45["mats"]["白桦木"] = 99                     # 木材系副材料
check(game.pick_sub_mats(s45, "普通", "松木", 2) == {"白桦木": 2}, "副材料：同系品类（木材）正常选中")
s46 = new_state()
s46["mats"] = {"松木": 5, "白桦木": 2, "蘑菇": 99}
s46["money"] = 10 ** 9
_err46 = game.craft(s46, "猎弓", [])
check(_err46 is None and "猎弓" in s46["gear"] and s46["mats"].get("蘑菇") == 99,
      "副材料：猎弓配方只消耗木材系（蘑菇未被消耗）")
# 低品阶优先消耗
_lm = [k for k, v in game.M.items() if v[0] == "木材" and v[1] == "精良"]
s47 = new_state()
s47["mats"] = {"白桦木": 9}
if _lm:
    s47["mats"][_lm[0]] = 9
_subs47 = game.pick_sub_mats(s47, "精良", "松木", 3)
check(_subs47 == {"白桦木": 3}, "副材料：低品阶优先消耗（不动精良品阶材料）")

print("=== 28. v1.38d 存档互通（import_save_state） ===")
raw28 = {"name": "导入测试", "lvIdx": 3, "money": 12345, "seenMats": ["松木"],
         "shieldMonth": "2026-10", "account": {"code": "X"}, "legendPool": {"x": 1},
         "log": [{"t": "01-01 00:00", "m": "x", "c": ""}],
         "history": [{"date": "2026-10-01", "score": 80, "sleep": True}]}
si = game.import_save_state(raw28)
check(si is not None and si["name"] == "导入测试" and si["lv_idx"] == 3 and si["money"] == 12345,
      "import_save_state：camel→snake 基础字段")
check(si["seen_mats"] == ["松木"] and si["shield_month"] == "2026-10", "import_save_state：下划线字段映射")
check("account" not in si and "legend_pool" not in si, "import_save_state：前端专属字段剔除")
check(si["log"] == [], "import_save_state：日志清空（两端格式不同）")
check(si["history"][0]["score"] == 80, "import_save_state：嵌套历史原样保留")
check(game.import_save_state("bad") is None and game.import_save_state([1]) is None,
      "import_save_state：非法输入拒绝")
check(si["health"] is not None and si["pool_point"] == "" and si["shield_days"] == [],
      "import_save_state：缺失字段自动补齐（migrate）")

print("=== 29. v1.38f 携带宠物（陪同委托成长；v1.55 阅读驱动分流） ===")
s29 = new_state()
s29["pets"] = ["星界幼龙", "月光狐"]
s29["pet_data"] = {"星界幼龙": {"stage": 1, "growth": 0, "mutate": 0, "fedDate": "", "fedCount": 0},
                   "月光狐": {"stage": 1, "growth": 0, "mutate": 0, "fedDate": "", "fedCount": 0}}
check(game.pet_quest_gain(s29, q0, True, 1) == "", "携带宠物：未携带无成长")
_msgs29 = []
check(game.set_carry_pet(s29, "星界幼龙", _msgs29) is None and s29["carry_pet"] == "星界幼龙",
      "set_carry_pet：设置成功")
check(game.set_carry_pet(s29, "不存在宠", _msgs29) == "❌ 还没有这只宠物。",
      "set_carry_pet：未拥有宠物拒绝")
check(game.set_carry_pet(s29, "小狼", _msgs29) == "❌ 还没有小狼。",
      "set_carry_pet：没有小狼时拒绝")
_n1 = game.pet_quest_gain(s29, q0, True, 1)
check(_n1.endswith("成长 +1") and s29["pet_data"]["星界幼龙"]["growth"] == 1, "petQuestGain：Lv1 成功 +1")
_exp3 = 1 + 1 + (1 if q0[4] in ("困难", "噩梦") else 0)
_g1 = s29["pet_data"]["星界幼龙"]["growth"]
game.pet_quest_gain(s29, q0, True, 3)
check(s29["pet_data"]["星界幼龙"]["growth"] == _g1 + _exp3,
      "petQuestGain：Lv3 成功 +" + str(_exp3) + "（难度 " + str(q0[4]) + "）")
_g2 = s29["pet_data"]["星界幼龙"]["growth"]
game.pet_quest_gain(s29, q0, False, 3)
check(s29["pet_data"]["星界幼龙"]["growth"] == _g2 + 1, "petQuestGain：失败保底 +1")
s29["pet_data"]["星界幼龙"]["stage"] = 4
_g3 = s29["pet_data"]["星界幼龙"]["growth"]
check(game.pet_quest_gain(s29, q0, True, 5) == "" and s29["pet_data"]["星界幼龙"]["growth"] == _g3,
      "petQuestGain：满阶不再成长")
s29["pet_data"]["星界幼龙"]["stage"] = 1
# v1.55：阅读驱动宠物不吃委托成长（只提示）
game.set_carry_pet(s29, "星界幼龙", _msgs29)
game.set_carry_pet(s29, "月光狐", _msgs29)
_r = game.pet_quest_gain(s29, q0, True, 3)
check("阅读" in _r and s29["pet_data"]["月光狐"]["growth"] == 0,
      "v1.55：月光狐（阅读驱动）委托只提示、不涨成长")
game.set_carry_pet(s29, "月光狐", _msgs29)
check(s29["carry_pet"] == "", "set_carry_pet：同名再设 = 看家")
s29["wolf"] = {"stage": 2, "growth": 10, "mutate": 0, "fedDate": "", "fedCount": 0}
s29["pets"].append("小狼")
game.set_carry_pet(s29, "小狼", _msgs29)
check(s29["carry_pet"] == "小狼", "set_carry_pet：切换小狼")
game.pet_quest_gain(s29, q0, True, 1)
check(s29["wolf"]["growth"] == 11, "petQuestGain：小狼成长 +1")
_old_rand = game.rand
game.rand = lambda n: 1                      # 必成功（roll=1）
_res29 = game.settle(s29, {"q": q0, "rate": 0.99, "meal": None, "qlv": 5}, [])
game.rand = _old_rand
check(isinstance(_res29, dict) and "成长 +" in _res29.get("pet", ""), "settle：结算结果附带宠物成长提示")

print("=== 30. v1.38r 批次（入睡窗 21:00~23:30 / 接取窗口 / 升级详情队列；v1.41f3 末次刷新 21:00） ===")
# 1) 刷新点：08/12/18/21（v1.41f3：末次 22:00 → 21:00）
check(game.CFG["refreshHours"] == [8, 12, 18, 21], "刷新点 [8,12,18,21]（v1.41f3 末次 22:00 → 21:00）")
# 2) 接取窗口：常规 1 小时（30 分钟 → 1 小时）；最后一次刷新点 2.5 小时至 23:30
check(game.POOL_WINDOW_MS == 60 * 60 * 1000, "接取窗口 = 1 小时（30 分钟 → 1 小时）")
check(game.LAST_POOL_WINDOW_MS == 150 * 60 * 1000, "最后班窗口 = 2.5 小时（21:00 → 23:30）")
s30 = new_state()
s30["pool"] = {"point": "08:00", "list": [list(game.C["Lv1"][0])], "taken": False,
               "bornTs": game.now_ms() - 59 * 60 * 1000, "expiredLogged": False}
check(not game.pool_expired(s30), "常规班刷新后 59 分钟：窗口内")
s30["pool"]["bornTs"] = game.now_ms() - 61 * 60 * 1000
check(game.pool_expired(s30), "常规班刷新后 61 分钟：已过期")
s30b = new_state()
s30b["pool"] = {"point": "2026-10-05@21", "list": [list(game.C["Lv1"][0])], "taken": False,
                "bornTs": game.now_ms() - 140 * 60 * 1000, "expiredLogged": False}
check(not game.pool_expired(s30b), "最后班（@21）140 分钟：窗口内（2.5 小时）")
s30b["pool"]["bornTs"] = game.now_ms() - 151 * 60 * 1000
check(game.pool_expired(s30b), "最后班（@21）151 分钟：已过期")
# 3) 入睡窗口常量
check(game.TASK_WINDOWS[0] == (21 * 60, 23 * 60 + 30), "TASK_WINDOWS[0] = 21:00~23:30")
# 4) 升级详情队列（levelups，前端弹窗数据源）
s31 = new_state()
s31["exp"] = 60
s31["energy"] = 10                            # v1.38s2：压低后验证升级补满
game.check_level_up(s31)
check(s31["lv_idx"] == 1 and s31.get("levelups") == [1], "升级写入 levelups（Lv2）")
check(s31["energy"] == game.energy_max_now(s31), "升级补满当前精力（= 新上限，v1.38s2）")
game.check_level_up(s31)
check(s31.get("levelups") == [1], "未升级不重复入队")
s31["exp"] = 500
game.check_level_up(s31)
check(s31["lv_idx"] == 2 and s31.get("levelups") == [1, 2], "连升追加 levelups（Lv3）")

print("=== 31. v1.38s 批次（探索详情保密 seen_items） ===")
# 1) new_state 含 seen_items（探索详情"曾获得"记录）
check(new_state().get("seen_items") == [], "new_state 含 seen_items（空列表）")
# 2) 探索开出旧宝箱 → 写入 seen_items（mock 随机序列：只命中旧宝箱）
_i_mine = next(i for i, r in enumerate(game.REGIONS) if r["n"] == "废弃矿道")   # v1.41：区域表已扩展，索引按名查找
s32 = new_state()
s32["lv_idx"] = 4
s32["explore_active"] = {"idx": _i_mine, "n": "废弃矿道", "c": 5, "h": 6,
                         "startTs": 0, "finishTs": 0}      # 到点 → 立即结算
_seq = [0.99] * 7 + [0.01, 0.05, 0.5]
_old_rr = game.random.random
game.random.random = lambda: _seq.pop(0) if _seq else 0.99
try:
    _msgs32 = []
    game.explore_finish_check(s32, _msgs32)
finally:
    game.random.random = _old_rr
check(s32["explore_active"] is None, "探索到点结算（explore_active 清空）")
check("旧宝箱" in s32.get("seen_items", []), "开出旧宝箱 → 写入 seen_items（详情随之解锁）")
check("紫水晶" not in s32.get("seen_items", []) and s32["mats"].get("紫水晶", 0) == 0,
      "未命中材料不入 seen_items / 背包")
# 3) migrate_state 给旧档补字段
s33 = new_state()
del s33["seen_items"]
game.migrate_state(s33)
check(s33.get("seen_items") == [], "migrate_state：旧档补 seen_items")
# 4) 旧宝箱 10% 装备奖励（随机普通~精良 ×1，尚未拥有才给；全拥有则空箱）
s34 = new_state()
s34["lv_idx"] = 4
s34["explore_active"] = {"idx": _i_mine, "n": "废弃矿道", "c": 5, "h": 6, "startTs": 0, "finishTs": 0}
_seq2 = [0.99] * 7 + [0.01, 0.95]
game.random.random = lambda: _seq2.pop(0) if _seq2 else 0.99
try:
    game.explore_finish_check(s34, [])
finally:
    game.random.random = _old_rr
check(len(s34["gear"]) == 1 and s34["gear"][0] in [g[0] for g in game.GEAR],
      "旧宝箱 10% 开出装备 → 入装备背包（" + (s34["gear"][0] if s34["gear"] else "无") + "）")
s34["gear"] = [g[0] for g in game.GEAR if g[1] in ("普通", "精良")]
_gn = len(s34["gear"])
s34["explore_active"] = {"idx": _i_mine, "n": "废弃矿道", "c": 5, "h": 6, "startTs": 0, "finishTs": 0}
_seq3 = [0.99] * 7 + [0.01, 0.95]
game.random.random = lambda: _seq3.pop(0) if _seq3 else 0.99
try:
    game.explore_finish_check(s34, [])
finally:
    game.random.random = _old_rr
check(len(s34["gear"]) == _gn, "普通~精良全拥有 → 旧宝箱不重复发放（空箱）")

print("=== 32. v1.38s5 批次（委托奖励平衡修正） ===")
_jz = [q for q in game.C["Lv5"] if q[0] == "禁咒书夺回"][0]
check(list(_jz[8].keys())[0] == "暗影草" and _jz[8]["暗影草"] == [2, 4],
      "禁咒书夺回：史诗暗影草为主材料（必得）")
_lw = [q for q in game.C["Lv5"] if q[0] == "猎杀远古巨狼"][0]
check(list(_lw[8].keys())[0] == "魔狼鬃毛", "猎杀远古巨狼：新增史诗主材料（魔狼鬃毛）")
_lc = [q for q in game.C["Lv5"] if q[0] == "龙巢外围巡查"][0]
check(list(_lc[8].keys())[0] == "龙息草", "龙巢外围巡查：主材料降为稀有（龙息草）")
_sm = [q for q in game.C["Lv4"] if q[0] == "讨伐石魔像"][0]
check(list(_sm[8].keys())[0] == "陨铁", "讨伐石魔像：主材料升为史诗（陨铁）")
_jl = [q for q in game.C["Lv3"] if q[0] == "巨龙巢穴侦察"][0]
check(list(_jl[8].keys())[0] == "龙骨" and _jl[8]["龙骨"] == [1, 1], "巨龙巢穴侦察：史诗降为单份（龙骨×1）")
_gl = [q for q in game.C["Lv4"] if q[0] == "古龙遗骸采集"][0]
check(_gl[8]["龙角"] == [1, 3], "古龙遗骸采集：龙角概率量 1~5 → 1~3")

print("=== 33. v1.39 B1：超 7 天未上线的跳过对齐 ===")
s39 = new_state()
_now39 = datetime(2026, 10, 4, 10, 0)
s39["last_day"] = "2026-09-04"
s39["created"] = "2026-08-01"
s39["health"] = game._blank_health("2026-09-04")
s39["daily"] = game._blank_daily("2026-09-04")
m39 = catch_up(s39, _now39)
_t39 = game.today_str(_now39)
check(s39["last_day"] == _t39, "跳过 30 天 → last_day 对齐今日")
check(s39["health"]["date"] == _t39 and s39["daily"]["date"] == _t39,
      "health/daily 重建为今日（打卡不会写进旧日期）")
check(any("未逐日结算" in m for m in m39), "给出跳过提示")
m39b = catch_up(s39, _now39)
check(not any("未逐日结算" in m for m in m39b), "再次补算幂等（不重复跳过）")

# 跳过区间跨月末 → 该月结算必须补跑（有打卡数据 → 奖励到账）
s40 = new_state()
_now40 = datetime(2026, 11, 5, 10, 0)
s40["last_day"] = "2026-10-20"
s40["created"] = "2026-01-01"
s40["health"] = game._blank_health("2026-10-20")
s40["daily"] = game._blank_daily("2026-10-20")
s40["history"] = [{"date": "2026-10-%02d" % (i + 1), "score": 95, "sleep": True, "done": 3,
                   "tasks": [1] * 7, "multi": [5, 5]} for i in range(25)]
_m40 = s40["money"]
m40 = catch_up(s40, _now40)
check(s40["month_settled"] == "2026-10", "跳过区间跨月末 → 10 月结算补跑（结算键已记）")
check(s40["money"] > _m40 and any("月结算" in m for m in m40), "月结算奖励到账（不因跳过而丢）")

print("=== 34. v1.39 B6：队列封顶（cap 50） ===")
s41 = new_state()
for i in range(60):
    game._push_capped(s41, "results", {"i": i})
check(len(s41["results"]) == 50 and s41["results"][0]["i"] == 10 and s41["results"][-1]["i"] == 59,
      "results 封顶 50（保留最近）")
for i in range(60):
    game._push_capped(s41, "pending_rare", i)
check(len(s41["pending_rare"]) == 50, "pending_rare 封顶 50")
for i in range(55):
    game._push_capped(s41, "levelups", i)
check(len(s41["levelups"]) == 50, "levelups 封顶 50")
s41b = new_state()
s41b["exp"] = 40000
game.check_level_up(s41b)
check(s41b["lv_idx"] == 4 and s41b["levelups"] == [1, 2, 3, 4], "check_level_up 正常入队（封顶不影响）")

print("=== 35. v1.40：硬伤修复与健康闭环调整 ===")
# ① 冥念护符 V：完成 ≥1 次传奇事件后解锁（原 need:99 永不可解锁）
_s42 = new_state()
check(game.charm_unlocked(_s42, 4) is False, "护符 V：未完成传奇 → 未解锁")
_s42["legend_done"] = ["屠龙传说"]
check(game.charm_unlocked(_s42, 4) is True, "护符 V：完成 ≥1 次传奇 → 解锁")
# ② 传奇奖励入装备/图纸（原全部误入藏品）
_s43 = new_state()
game.grant_legend_reward(_s43, ["世界树种子", "采集+精英", 3, "困难", 0, 0, "", "世界树护符", {}])
check("世界树护符" in _s43["gear"] and "世界树护符" not in _s43["trophies"],
      "传奇装备奖励入装备背包（世界树护符/时间沙漏原永远拿不到）")
game.grant_legend_reward(_s43, ["陨星核心", "采集+精英", 2, "困难", 0, 0, "", "陨星武器图纸", {}])
check(_s43["blueprints"].get("陨星武器") is True, "传奇图纸奖励入图纸库（陨星武器图纸）")
game.grant_legend_reward(_s43, ["公会大师试炼", "精英", 30, "困难", 0, 0, "", "公会大师徽章", {}])
check("公会大师徽章" in _s43["trophies"], "非装备奖励仍入藏品（公会大师徽章）")
# ③ W/H/P 公会称号
_s44 = new_state()
_s44["rep"] = 20000
game.check_guild_titles(_s44, [])
check(all(_t in _s44["titles"] for _t in ("世界行者", "英雄", "至尊")), "W/H/P 称号授予（世界行者/英雄/至尊）")
# ④ 连击保险计入门槛统计（v1.40：保险真正保住连击）
_s45 = new_state()
_s45["history"] = [{"date": "x%02d" % i, "score": 80, "sleep": (i >= 4), "done": 1,
                    "tasks": [1] * 7, "multi": [0, 0]} for i in range(30)]
check(game.sleep_streak(_s45, 30) is False, "连击保险前：30 天缺 4 天 → 不达标（容错 3）")
_s45["shield_days"] = ["x00"]
check(game.sleep_streak(_s45, 30) is True, "连击保险日计入：缺 4 天中 1 天被保险 → 达标")
# ⑤ P 级传奇每周 2 次
_s46 = new_state()
_s46["rep"] = 20000
_s46["legend_name"] = "测试传奇"
_LEG = ["测试传奇", "精英", 3, "困难", 0, 0, "", "", {}]
_s46["legend_active"] = list(_LEG)
_r1 = game.take_legend(_s46, [])
_s46["active"] = [a for a in _s46["active"] if not a.get("legend")]   # v1.51：模拟完成（同时最多 1 个检查否则会拦截）
_s46["legend_active"] = list(_LEG)
_r2 = game.take_legend(_s46, [])
_s46["active"] = [a for a in _s46["active"] if not a.get("legend")]
_s46["legend_active"] = list(_LEG)
_r3 = game.take_legend(_s46, [])
check(_r1 is None and _r2 is None and _s46.get("legend_week_n") == 2,
      "P 级传奇：本周可接 2 次（原每周 1 次）")
check(_r3 is not None and "2 次" in (_r3 or ""), "P 级传奇：第 3 次被拒")
# ⑥ 区间奖励补发（生效日未上线 → 贡献/活力点补到账）
_s47 = new_state()
_s47["health"] = {"date": "2026-10-03", "done": [0] * 7, "multi": [0, 0], "score": 0}
_s47["daily"] = game._blank_daily("2026-10-03")
_s47["buff_next"] = {"date": "2026-10-03", "pay": 0.15, "energy": 0, "con": 6, "vit": 5,
                     "claimed": False, "score": 95}
_c47, _v47 = _s47["con"], _s47["vit"]
_m47 = []
game.day_settle(_s47, _m47)
check("补发" in "".join(_m47) and _s47["con"] == _c47 + 6 and _s47["vit"] > _v47,
      "区间奖励补发：生效日未上线 → 贡献/活力点到账（v1.40）")
# ⑦ 虚弱 = 上限 −10%
_s48 = new_state()
_s48["lv_idx"] = 4
_s48["buff_next"] = {"date": game.today_str(), "pay": 0, "energy": 0, "con": 0, "vit": 0,
                     "claimed": False, "score": 0, "energyPct": -0.10}
check(game.energy_max_now(_s48) == 450, "虚弱：Lv5 精力上限 500 → 450（−10%）")

print("=== 36. v1.41 I3：月度世界事件 ===")
# 1) v1.48f：Lv1（新号）即生成——无 Lv2 门槛
_s50 = new_state(); _s50["lv_idx"] = 0; _s50["month_event"] = None
game.month_event_tick(_s50, [])
check(bool(_s50["month_event"]), "v1.48f：Lv1 生成月度事件（新号解锁）")
check(game.month_event_now(_s50) is not None, "v1.48f：Lv1 month_event_now 返回事件")
# 2) Lv2 生成 + 月份映射
_s50["lv_idx"] = 1
game.month_event_tick(_s50, [])
_mk = game.today_str()[:7]
check(bool(_s50["month_event"]) and _s50["month_event"]["key"] == _mk and _s50["month_event"]["cnt"] == 0,
      "Lv2 生成当月事件（" + _mk + "）")
_ev = game.MONTH_EVENTS[int(_mk[5:7]) - 1]
check(len(game.MONTH_EVENTS) == 12, "12 条事件池")
# 3) 幂等
_s50["month_event"]["cnt"] = 2
game.month_event_tick(_s50, [])
check(_s50["month_event"]["cnt"] == 2, "同月重复 tick 不重置")
# 4) 类型不匹配不计数
_ot = "explore" if _ev["t"] == "quest" else "quest"
game.month_event_add(_s50, [], _ot)
check(_s50["month_event"]["cnt"] == 2, "类型不匹配不计数")
# 5) 达成发奖（monkeypatch 过期判定，测试对当前日期鲁棒）
_orig_exp = game.month_event_expired
game.month_event_expired = lambda: False
_s50["money"] = 0; _s50["mats"] = {}; _s50["tim_titles"] = {}
_s50["month_event"]["cnt"] = _ev["need"] - 1
game.month_event_add(_s50, [], _ev["t"])
check(_s50["month_event"]["done"] is True, "达成置 done")
check(_s50["money"] == int(round(_ev["gold"] * game.lv_gold_mul(_s50))),
      "金币奖励×lv_gold_mul（" + str(_s50["money"]) + "）")
check(_s50["mats"].get(list(_ev["mats"].keys())[0], 0) > 0, "材料奖励入包")
check(_s50["tim_titles"].get(_ev["title"], 0) > game.now_ms(), "当月称号入档（至下月 1 日）")
# 6) 达成后不重复发奖
_m6 = _s50["money"]
game.month_event_add(_s50, [], _ev["t"])
check(_s50["money"] == _m6, "达成后不重复发奖")
# 7) 换月自动轮换
_s50["month_event"] = {"key": "1999-01", "cnt": 9, "done": True}
game.month_event_tick(_s50, [])
check(_s50["month_event"]["key"] == _mk and _s50["month_event"]["cnt"] == 0 and not _s50["month_event"]["done"],
      "换月自动轮换重置")
game.month_event_expired = _orig_exp

print("=== 37. v1.41 I4：追踪类 / 资源指定类 ===")
# 1) 追踪类 3 条、耗时 4320；fmt_dur
_tr = [q for lv in game.C for q in game.C[lv] if q[1] == "追踪"]
check(len(_tr) == 4, "追踪类委托 4 条（v1.42 加黑龙追踪；实际 " + str(len(_tr)) + "）")
check(all(q[3] == 4320 for q in _tr), "追踪类耗时=4320 分钟（3 天）")
check(game.fmt_dur(4320) == "3 天" and game.fmt_dur(240) == "4 小时" and game.fmt_dur(90) == "1.5 小时",
      "fmt_dur 多日显示（3 天/4 小时/1.5 小时）")
# 2) QUEST_TURNIN 引用完整
_alln = {q[0] for lv in game.C for q in game.C[lv]}
_tb = [k for k, v in game.QUEST_TURNIN.items() if k not in _alln or v not in game.M]
check(len(game.QUEST_TURNIN) == 3 and not _tb, "QUEST_TURNIN 3 条、引用完整" + ("：" + str(_tb) if _tb else ""))
# 3) 结算：持有材料 → 翻倍（固定 rand=50：必成功、非暴击；龙血订单无掉落干扰）
_s51 = new_state(); _s51["lv_idx"] = 4
_q3 = [q for q in game.C["Lv5"] if q[0] == "龙血商人的订单"][0]
_orig_rand = game.rand
game.rand = lambda n: 50
_msgs9 = []
game.settle(_s51, {"q": _q3, "qlv": 5, "rate": 2, "acceptTs": game.now_ms(),
                   "finishTs": game.now_ms(), "name": _q3[0], "meal": None}, _msgs9)
_base_g = _s51["money"]
_s51["money"] = 0; _s51["mats"]["龙血"] = 2
_s51["rare_next_pay"] = 0; _s51["rare_next_rate"] = 0; _s51["buff_next"] = None   # 第一次结算尾部可能 roll 出稀有事件加成
game.settle(_s51, {"q": _q3, "qlv": 5, "rate": 2, "acceptTs": game.now_ms(),
                   "finishTs": game.now_ms(), "name": _q3[0], "meal": None}, _msgs9)
check(_base_g > 0 and _s51["money"] == _base_g * 2,
      "上交型：持有材料 → 报酬翻倍（" + str(_base_g) + " → " + str(_s51["money"]) + "）")
check(_s51["mats"].get("龙血", 0) == 1, "上交型：扣 1 个材料（2 → 1）")
game.rand = _orig_rand

print("=== 38. v1.41 I5：收集分层 + 隐藏成就 ===")
# 1) 表结构
check(len(game.ACHV) == 20, "成就表 20 条（11 常规含大师 + 9 隐藏）")
_hid = [n for n, g in game.ACHV if g is None]
check(len(_hid) == 9 and all(n in game.ACHV_TITLE for n in _hid), "隐藏成就 9 条且均有称号映射")
# 2) 隐藏成就达成 → 称号（囤积家 = 持有 50 种材料）
_s52 = new_state()
_s52["mats"] = {k: 1 for k in list(game.M.keys())[:50]}
game.check_achievements(_s52, [])
check("囤积家" in _s52["achv"], "隐藏成就「囤积家」达成（50 种材料）")
check("满仓" in _s52["titles"], "隐藏成就奖励称号「满仓」入档")
check(None not in _s52["gear"], "title 型成就不污染装备背包")
# 3) 图鉴分层：材料 50% / 80%
_s53 = new_state(); _s53["mats"] = {}
_s53["seen_mats"] = list(game.M.keys())[: (len(game.M) + 1) // 2]
game.check_achievements(_s53, [])
check("博物学家·银" in _s53["titles"], "材料收集 50% → 「博物学家·银」")
_s53["seen_mats"] = list(game.M.keys())[: -(-len(game.M) * 8 // 10)]
game.check_achievements(_s53, [])
check("博物学家·金" in _s53["titles"], "材料收集 80% → 「博物学家·金」")

print("=== 39. v1.41 I6：大师层 ===")
# 1) 表结构
_mg = [g for g in game.GEAR if g[0] in ("大师之证", "宗师手套", "终焉披风", "大师徽章")]
check(len(_mg) == 4, "大师层装备 4 件（3 传说 + 1 成就饰品）")
check(any(n == "大师" and g == "大师徽章" for n, g in game.ACHV), "成就「大师」→ 大师徽章")
check(len(game.MASTER_SHOP["gear"]) == 3 and game.MASTER_SHOP["vitC"] == 20
      and game.MASTER_SHOP["gear"][0]["platC"] == 18,
      "MASTER_SHOP：3 装备 / 活力 20 铂金 / 首价 18 铂金")
# 2) 解锁判定：3 传奇未解锁；4 传奇达成
_s60 = new_state(); _s60["legend_done"] = ["屠龙传说", "星界远征", "魔神封印"]
check(not game.master_unlocked(_s60), "3 个传奇 → 大师未解锁")
_s60["legend_done"] = ["屠龙传说", "星界远征", "魔神封印", "时间回廊"]
game.check_achievements(_s60, [])
check("大师" in _s60["achv"] and "大师徽章" in _s60["gear"], "4 个传奇 → 成就「大师」达成、徽章入包")
check(game.master_unlocked(_s60), "≥4 个传奇 → 大师商店解锁")
# 3) 徽章活力词条
_s60["equipped"]["charmSlot"] = "大师徽章"
check(abs(game.gear_effects(_s60)["vit"] - 0.10) < 1e-9, "大师徽章「活力点获取+10%」解析生效")
check(abs(game.charm_vit(_s60) - 0.10) < 1e-9, "charm_vit 并入大师徽章（基础上限 0）")
_s60["equipped"]["charmSlot"] = None
# 4) 购买专属装备（一次性）
_s60["money"] = 20 * 1000000; _s60["mats"]["星核"] = 5
_msgs10 = []
check(game.buy_master_gear(_s60, _msgs10, 0) is None, "购买「大师之证」成功")
check("大师之证" in _s60["gear"], "大师之证入包")
check(_s60["money"] == 2 * 1000000 and _s60["mats"]["星核"] == 2,
      "扣费 18 铂金币 + 星核×3（余 2 铂金 / 星核 2）")
check(game.buy_master_gear(_s60, _msgs10, 0) is not None, "已拥有 → 重复购买被拒")
# 5) 材料不足被拒
_s60["mats"]["世界树心"] = 0
check(game.buy_master_gear(_s60, _msgs10, 1) is not None, "材料不足 → 购买被拒")
check("宗师手套" not in _s60["gear"], "宗师手套未入包")
# 6) 活力点兑换：20 铂金币 → +500
_s60["money"] = 20 * 1000000; _v0 = _s60["vit"]
check(game.buy_master_vit(_s60, _msgs10) is None and _s60["vit"] == _v0 + 500
      and _s60["money"] == 0,
      "大师的馈赠：-20 铂金币 → 活力点 +500")
# 7) 未解锁被拒
_s61 = new_state(); _s61["money"] = 100 * 1000000
check(game.buy_master_gear(_s61, [], 1) is not None, "未解锁大师 → 购买被拒")
check(game.buy_master_vit(_s61, []) is not None, "未解锁大师 → 活力兑换被拒")

print("=== 40. v1.41 厨房分阶段开放 ===")
def _ctier(r):
    t = "普通"
    for k in (r.get("main") or {}):          # v1.50：品级以主材为准
        q = game.M[k][1] if k in game.M else "普通"
        if game.QUALITY_ORDER.index(q) > game.QUALITY_ORDER.index(t):
            t = q
    return t
_hi_i = next((j for j, r in enumerate(game.CFG["recipes"])
              if game.QUALITY_ORDER.index(_ctier(r)) > 0), None)
check(_hi_i is not None, "存在高于普通的料理（门槛有用例）")
if _hi_i is not None:
    _r_hi = game.CFG["recipes"][_hi_i]
    _sK = new_state()                                  # lv_idx = 0（Lv1）
    for k, n in game.recipe_ing(_r_hi).items():
        _sK["mats"][k] = n
    check(game.cook(_sK, _hi_i, []) is not None and _r_hi["n"] not in _sK.get("cooked", []),
          "Lv1：烹饪精良以上料理被拒（不入 cooked）")
    _sK["lv_idx"] = 4
    check(game.cook(_sK, _hi_i, []) is None and _r_hi["n"] in _sK["cooked"],
          "Lv5：同料理烹饪成功")
_lo_i = next(j for j, r in enumerate(game.CFG["recipes"]) if _ctier(r) == "普通")
_sL = new_state()
for k, n in game.recipe_ing(game.CFG["recipes"][_lo_i]).items():
    _sL["mats"][k] = n
check(game.cook(_sL, _lo_i, []) is None and game.CFG["recipes"][_lo_i]["n"] in _sL["cooked"],
      "Lv1：普通料理正常烹饪")

print("=== 41. v1.41 传奇独立槽位 + 耗时压缩 ===")
_days41 = [x[2] for x in game.LEGEND]
check(min(_days41) >= 3 and max(_days41) <= 14,
      "耗时压缩到 3~14 天（" + "/".join(str(x) for x in _days41) + "）")
check(game.active_normal_count({"active": [{"a": 1}, {"legend": ["x"]}]}) == 1,
      "active_normal_count 排除传奇项")
_s70 = new_state()
_s70["legend_active"] = list(game.LEGEND[0])
_s70["legend_name"] = "测试传奇"
_s70["active"] = [{"q": ["x", "采集", "全天", 60, "简单", 0, 0, 0, {}],
                   "rate": 1, "name": "占位委托"}]           # sim_cap=1（Lv1）→ 普通位已满
check(game.take_legend(_s70, []) is None, "普通位已满 → 传奇仍可接（独立槽）")
check(len(_s70["active"]) == 2 and any(a.get("legend") for a in _s70["active"]),
      "传奇已入 active（与普通委托并行）")

print("=== 42. v1.41 称号收集加成 ===")
_s80 = new_state()
_s80["titles"] = []
check(game.title_own_bonus(_s80) == 0, "0 个称号 → +0%")
_s80["titles"] = ["A", "B", "C"]
check(abs(game.title_own_bonus(_s80) - 0.03) < 1e-9, "3 个称号 → +3%")
_s80["titles"] = list("ABCDEFGHIJ")
check(abs(game.title_own_bonus(_s80) - 0.10) < 1e-9, "10 个称号 → +10%")
_s80["titles"] = list("ABCDEFGHIJKLMN")
check(abs(game.title_own_bonus(_s80) - 0.10) < 1e-9, "超过 10 个 → 封顶 +10%（14 个称号）")

print("=== 43. v1.41f5/f6：料理平衡（探索点限次与品阶梯度 / cap 改恢复 / 深渊消耗 / 巨龙盛宴） ===")
# 深渊消耗上调（探索点经济：最高的两个区域）
_dy = {r["n"]: r["c"] for r in game.REGIONS}
check(_dy.get("深渊裂隙") == 10 and _dy.get("深渊核心") == 12,
      "深渊裂隙 10 / 深渊核心 12 探索点消耗（v1.61c：深渊深处改名）")
check(all(not r.get("cap") for r in game.CFG["recipes"]), "cap 类料理清零（全改恢复类）")
_sp_recipes = [(j, r) for j, r in enumerate(game.CFG["recipes"]) if r.get("sp")]
check(len(_sp_recipes) == 5 and all(r["sp"] <= 5 for _j, r in _sp_recipes),
      "探索点料理 5 道、单次 ≤5 点")
# v1.41f6：sp 品阶梯度（普通无 / 精良1 / 稀有2 / 史诗3 / 传说4·5）
_tier_sp = {}
for _j, r in _sp_recipes:
    _tier_sp.setdefault(_ctier(r), []).append(r["sp"])
check(_tier_sp.get("精良") == [1] and _tier_sp.get("稀有") == [2] and _tier_sp.get("史诗") == [3]
      and sorted(_tier_sp.get("传说", [])) == [5, 5] and "普通" not in _tier_sp,
      "sp 品阶梯度：精良1 / 稀有2 / 史诗3 / 传说5（v1.50：星尘蜜露 4→5）")
# v1.50：巨龙盛宴平衡（主辅材 10 种、报酬 18%/率 6%、sp5——最强料理）
_feast = next(r for r in game.CFG["recipes"] if r["n"] == "巨龙盛宴")
_long = next(r for r in game.CFG["recipes"] if r["n"] == "龙血羹")
check(_feast["bonus"] == 0.18 and _feast["rate"] == 0.06 and _feast["sp"] == 5
      and len(game.recipe_ing(_feast)) == 10,
      "巨龙盛宴：报酬18%/率6%/sp5、10 种材料（主材+辅材，v1.50）")
check(_feast["bonus"] > _long["bonus"] and _feast["rate"] >= _long["rate"],
      "盛宴仍全面强于龙血羹（最强定位保留）")
# 限次：金盏花茶 sp1 ×2 + 第 3 次被拒（材料不扣）
_s90 = new_state()
_s90["lv_idx"] = 4
_j1, _r1 = next((j, r) for j, r in _sp_recipes if r["n"] == "金盏花茶")
_j2, _r2 = next((j, r) for j, r in _sp_recipes if r["n"] == "月光花茶")
_j3, _r3 = next((j, r) for j, r in _sp_recipes if r["n"] == "星尘蜜露")
for k, n in game.recipe_ing(_r1).items():
    _s90["mats"][k] = n * 3
for k, n in game.recipe_ing(_r2).items():
    _s90["mats"][k] = n * 3
for k, n in game.recipe_ing(_r3).items():
    _s90["mats"][k] = max(_s90["mats"].get(k, 0), n * 3)
_s90["explore"] = 0
check(game.cook(_s90, _j1, []) is None and _s90["explore"] == 1, "金盏花茶 +1 探索点")
check(game.cook(_s90, _j1, []) is None and _s90["explore"] == 2, "金盏花茶 ×2 = +2")
_gold_n = _s90["mats"].get("金盏花", 0)
check(game.cook(_s90, _j1, []) is not None and _s90["explore"] == 2
      and _s90["mats"].get("金盏花", 0) == _gold_n, "每日第 3 次被拒（材料不扣）")
# 累计封顶 +5：换一天，星尘蜜露 4 + 月光花茶 2 → 截断为 5
_s90["meal_sp"] = {"date": "", "cnt": 0, "got": 0}
_s90["explore"] = 0
check(game.cook(_s90, _j3, []) is None and _s90["explore"] == 5, "星尘蜜露 +5 探索点（v1.50：4→5）")
check(game.cook(_s90, _j2, []) is not None and _s90["explore"] == 5, "星尘蜜露 5 点即达当日累计上限（月光花茶被拒，v1.50）")

print("=== 44. v1.42：龙种体系 + 九头蛇材料改造 + 巨龙盛宴 enPct ===")
check(len(game.M) == 125, "材料 125 种（含 v1.45 新增 / v1.58 六域遗珍）")
_feast44 = next(r for r in game.CFG["recipes"] if r["n"] == "巨龙盛宴")
check(len(game.recipe_ing(_feast44)) == 10 and game.recipe_ing(_feast44)["世界树汁液"] == 1
      and game.recipe_ing(_feast44)["龙心"] == 2,
      "v1.44：巨龙盛宴大杂烩 10 种材料（龙系加重 + 世界树/星界/凤凰/蜜）")
_hy44 = next(q for q in game.C["Lv5"] if q[0] == "讨伐九头蛇")
check(len(_hy44[8]) == 5 and "九头蛇鳞片" in _hy44[8] and "再生蛇髓" in _hy44[8],
      "v1.44：讨伐九头蛇 5 种素材")
_all_names42 = {q[0] for lv in game.C for q in game.C[lv]}
check({"狩猎火龙", "驱赶绿龙", "与白龙探讨魔法", "金龙宝藏的谈判", "平息蓝龙之怒", "追踪黑龙的阴翳"} <= _all_names42,
      "6 个龙种委托在委托池")
_hy = next(q for q in game.C["Lv5"] if q[0] == "讨伐九头蛇")
check("龙鳞" not in _hy[8] and "龙心" not in _hy[8] and "龙牙" not in _hy[8] and "九头蛇心脏" in _hy[8],
      "讨伐九头蛇改用九头蛇素材（不再掉龙材料）")
# 巨龙盛宴：enPct 0.5（按精力上限 50% 恢复）——材料大块龙肉新增
_s99 = new_state()
_s99["lv_idx"] = 4
_feast_i = next(j for j, r in enumerate(game.CFG["recipes"]) if r["n"] == "巨龙盛宴")
_feast_r = game.CFG["recipes"][_feast_i]
check("大块龙肉" in game.recipe_ing(_feast_r) and "en" not in _feast_r and _feast_r.get("enPct") == 0.5,
      "盛宴配方：+大块龙肉×3、en→enPct 0.5")
for k, n in game.recipe_ing(_feast_r).items():
    _s99["mats"][k] = n
_s99["energy"] = 0
game.cook(_s99, _feast_i, [])
check(_s99["energy"] == int(game.energy_max_now(_s99) * 0.5 + 0.5),
      "盛宴恢复 50% 精力上限（" + str(_s99["energy"]) + "/" + str(game.energy_max_now(_s99)) + "）")

print("=== 45. v1.45：地狱/恶魔/魔鬼 + 中立种族 ===")
check(len(game.M) == 125, "材料 125 种（v1.45 +7 / v1.58 +6）")
_all_names45 = {q[0] for lv in game.C for q in game.C[lv]}
check({"猎杀深渊恶魔", "魔鬼的谈判", "血战遗迹考察", "镇压恶魔裂隙", "迷路的仙灵", "净化亡灵谷"} <= _all_names45,
      "6 个新委托在池（恶魔/魔鬼/仙灵/亡灵）")
check(game.M["灵魂币"][1] == "传说" and any(x[0] == "魔鬼的小契约" for x in game.RARE),
      "灵魂币（传说）+ 恶魔系稀有事件")

print("=== 46. v1.45b：委托链「血战与地狱」/「仙灵与亡者」 ===")
_all_names46 = {q[0] for lv in game.C for q in game.C[lv]}
check({"地狱钟声", "仙灵的谢礼", "魂灯引渡"} <= _all_names46, "3 个新链委托在池")
check(game.QUEST_REQ.get("地狱钟声") == "魔鬼的谈判" and game.QUEST_REQ.get("魂灯引渡") == "净化亡灵谷"
      and game.QUEST_REQ.get("净化亡灵谷") == "仙灵的谢礼" and game.QUEST_REQ.get("血战遗迹考察") == "镇压恶魔裂隙",
      "新链前置关系正确（血战与地狱 / 仙灵与亡者）")
_s46 = new_state(); _s46["lv_idx"] = 4; _s46["done_quests"] = {"镇压恶魔裂隙": 1}
_names46 = [q[0] for q in game.mix_pool(_s46)]
check("血战遗迹考察" in _names46 and "猎杀深渊恶魔" not in _names46 and "地狱钟声" not in _names46,
      "链 A 逐环推进：第 2 环解锁、第 3/5 环仍锁")
_s46b = new_state(); _s46b["lv_idx"] = 4
_s46b["done_quests"] = {"镇压恶魔裂隙": 1, "血战遗迹考察": 1, "猎杀深渊恶魔": 1, "魔鬼的谈判": 1}
_names46b = [q[0] for q in game.mix_pool(_s46b)]
check("地狱钟声" in _names46b, "链 A 终环「地狱钟声」在完成全部前序后可达")

print("=== 47. v1.46：任务门槛（委托准备物） ===")
check(len(game.QUEST_ITEM) == 21 and len(game.CRAFT) == 4, "QUEST_ITEM 21 条门槛（v1.57 +5）/ CRAFT 4 条配方")
check(all(v in game.CRAFT for v in game.QUEST_ITEM.values()), "门槛引用完整性（准备物均有配方）")
check(all(k in game.M for r in game.CRAFT.values() for k in r["ing"]), "配方材料全部在材料表")
# 炼金台合成
_s47 = new_state(); _s47["mats"] = {"止血草": 4, "蜂蜜": 2}
_m47 = []
game.craft_item(_s47, "解毒剂", _m47)
check(_s47["items"].get("解毒剂") == 1 and "止血草" not in _s47["mats"] and "蜂蜜" not in _s47["mats"],
      "炼金台：合成解毒剂（扣材 + 得货）")
_err47 = game.craft_item(_s47, "解毒剂", [])
check(_err47 and "材料不足" in _err47 and _s47["items"].get("解毒剂") == 1, "材料不足时合成被拒")
check(game.craft_item(_s47, "不存在", []) is not None, "无配方被拒")
# 接取门槛（服务端权威）
_hyd47 = next(q for q in game.C["Lv5"] if q[0] == "讨伐九头蛇")
_pk47 = game.pool_point_key(*game.latest_point(datetime.now()))   # 防 catch_up 视为过期而重刷
_s47b = new_state(); _s47b["lv_idx"] = 4; _s47b["energy"] = 9999
_s47b["pool"] = {"point": _pk47, "list": [list(_hyd47)], "taken": False, "bornTs": game.now_ms()}
_s47b["pool_point"] = _pk47
_err47b = game.accept_quest(_s47b, 0, [])
check(_err47b and "准备物" in _err47b and not _s47b["pool"]["taken"] and len(_s47b["active"]) == 0,
      "缺准备物 → 服务端拒绝接取（未接取/未消耗）")
# v1.53：需求量随委托等级（Lv5「讨伐九头蛇」需 ×3）——不足 3 仍拒绝
_s47b["items"] = {"解毒剂": 2}
_err47b2 = game.accept_quest(_s47b, 0, [])
check(_err47b2 and "×3" in _err47b2 and _s47b["items"].get("解毒剂") == 2 and not _s47b["pool"]["taken"],
      "Lv5 需求 ×3：只有 2 个仍被拒（未消耗）")
_s47b["items"] = {"解毒剂": 3}
game.accept_quest(_s47b, 0, [])
check(_s47b["pool"]["taken"] and len(_s47b["active"]) == 1 and "解毒剂" not in _s47b["items"],
      "持有准备物 → 接取成功并消耗 ×3（Lv5，服务端）")
check(game.quest_item_need(game.C["Lv3"][0]) == 1, "quest_item_need：Lv3 → 1（分级口径 v1.53）")
_need47 = [(lvk, game.quest_item_need(q)) for lvk in game.C for q in game.C[lvk] if q[0] in game.QUEST_ITEM]
check(all((lvk == "Lv5" and n == 3) or (lvk == "Lv4" and n == 2) or (lvk == "Lv3" and n == 1) for lvk, n in _need47),
      "准备物需求分级：Lv3→1 / Lv4→2 / Lv5→3（全 16 条）")
# 无门槛委托不受影响
_s47c = new_state(); _s47c["lv_idx"] = 4; _s47c["energy"] = 9999
_s47c["pool"] = {"point": _pk47, "list": [list(game.C["Lv5"][0])], "taken": False, "bornTs": game.now_ms()}
_s47c["pool_point"] = _pk47
game.accept_quest(_s47c, 0, [])
check(_s47c["pool"]["taken"] and len(_s47c["active"]) == 1, "无门槛委托照常接取")
# 商店上架
check(any(x.get("item") == "解毒剂" and x["c"] == 30000 for x in game.SHOP)
      and any(x.get("item") == "圣水" and x["c"] == 48000 for x in game.SHOP), "商店上架 4 种准备物（解毒剂 30000 / 圣水 48000，v1.53 提价）")
check(all(game.CRAFT[n]["buy"] == next(x["c"] for x in game.SHOP if x.get("item") == n) for n in game.CRAFT),
      "炼金台「商店价」与 SHOP 一致（v1.53 同步）")

print("=== 48. v1.48b：材料多品类定位（功能保留 · 注入式测试） ===")
check(game.mat_cats("止血草") == ["草药"], "mat_cats：无附加品类时仅主品类")
_multi48 = [k for k in game.M if len(game.M[k]) > 3]
check(_multi48 == ["世界树皮"], "M 表多品类条目 = 世界树皮（v1.48c，实际 " + str(_multi48) + "）")
# 注入：临时给「龙血」挂草药副系（特殊+草药），验证功能链路；结束还原
_bak48 = list(game.M["龙血"])
game.M["龙血"] = ["特殊", "史诗", 80000, ["草药"]]
check(set(game.mat_cats("龙血")) == {"特殊", "草药"}, "mat_cats：主品类 + 附加品类（注入）")
_sc48 = game.sub_cats_for("龙血")
check("草药" in _sc48 and "特殊" in _sc48 and "矿石" in _sc48, "副材品类合并（龙血 → 特殊系 ∪ 草药系，注入）")
# pick_sub_mats：注入蜂蜜（食材+草药）可作草药系副材、不入矿石系
_s48 = new_state(); _s48["mats"] = {"蜂蜜": 5}
_bakH48 = list(game.M["蜂蜜"])
game.M["蜂蜜"] = ["食材", "普通", 600, ["草药"]]
_r48 = game.pick_sub_mats(_s48, "普通", "止血草", 2)
check(_r48 and _r48.get("蜂蜜") == 2, "pick_sub_mats：附加草药系材料（注入蜂蜜）作副材入选")
check(game.pick_sub_mats(_s48, "普通", "陨铁", 2) is None, "不命中矿石系副材（注入蜂蜜 食材+草药）")
game.M["龙血"] = _bak48
game.M["蜂蜜"] = _bakH48
check(game.mat_cats("蜂蜜") == ["食材"] and game.mat_cats("龙血") == ["特殊"], "还原后：仅主品类")

print("=== 49. v1.48c：材料品类修正（竖瞳 / 龙瞳结晶 / 世界树皮） ===")
check(game.M["巨龙竖瞳"][0] == "兽材" and game.M["巨龙竖瞳"][1] == "传说", "巨龙竖瞳：宝石 → 兽材")
check(game.M.get("龙瞳结晶") and game.M["龙瞳结晶"][0] == "宝石" and game.M["龙瞳结晶"][2] > game.M["巨龙竖瞳"][2],
      "龙瞳结晶：宝石·传说（价值高于竖瞳）")
check(game.mat_cats("世界树皮") == ["特殊", "织物", "草药"], "世界树皮：特殊 + 织物 + 草药")
_sc49 = game.sub_cats_for("世界树皮")
check("草药" in _sc49 and "兽材" in _sc49 and "宝石" in _sc49, "世界树皮副材集合 = 特殊系 ∪ 织物系 ∪ 草药系")
_gd49 = None
for _lv49, _lst49 in game.C.items():
    for _q49 in _lst49:
        if _q49 and _q49[0] == "古龙遗骸采集":
            _gd49 = _q49
check(_gd49 and _gd49[8].get("龙瞳结晶") == [1, 2], "古龙遗骸采集掉落龙瞳结晶 [1,2]")

print("=== 50. v1.48d：失败结算规则（30% 报酬 + 30% 经验，至少 1、无掉落） ===")
_real_rand50 = game.rand
game.rand = lambda n: 100              # 固定 100 → 必失败（rate 0.5）
_q50 = game.C["Lv1"][0]
s50 = new_state()
_p50 = s50["money"]; _e50 = s50["exp"]; _mats50 = set((s50["mats"] or {}).keys())
game.settle(s50, {"q": _q50, "rate": 0.5, "acceptTs": game.now_ms(), "finishTs": game.now_ms()}, [])
game.rand = _real_rand50
_dg50 = s50["money"] - _p50
_de50 = s50["exp"] - _e50
check(_dg50 == max(1, int(round(_q50[5] * 0.3))), "失败报酬 = 30%（至少 1，实际 " + str(_dg50) + "）")
check(_de50 == max(1, int(round(_q50[6] * 0.3))), "失败经验 = 30%（至少 1，实际 " + str(_de50) + "）")
check(set((s50["mats"] or {}).keys()) == _mats50, "失败无掉落")

print("=== 51. v1.48e：月度世界事件整月有效（截止当月最后一天 23:30） ===")
check(game.month_event_expired() == False, "expired 恒 False（整月有效）")
s51 = new_state(); s51["lv_idx"] = 2
game.month_event_tick(s51, [])
check(s51["month_event"] and s51["month_event"]["key"] == game.today_str()[:7], "Lv2+ 生成当月事件（雾月）")
_cur51 = game.month_event_now(s51)
check(_cur51 and _cur51["expired"] == False, "当前事件 expired=False")
game.month_event_add(s51, [], _cur51["ev"]["t"])
check(s51["month_event"]["cnt"] == 1, "当月任意日期均可累积进度（7 日后也可）")

print("=== 52. v1.49：主题套装补齐（25 件） ===")
_new49 = ["金龙鳞铠","魔力结晶杖","雷霆龙牙枪","暗影龙鳞袍","龙瞳宝珠","龙角战弓","剧毒龙牙匕","绿龙护心镜",
          "九头蛇鳞铠","再生蛇髓护符","九头蛇之心","九头蛇胆囊杖","剧毒蛇齿链","恶魔角盔","混沌之刃","硫磺结晶甲",
          "魔鬼纹章","冥河护符","幽魂灯杖","仙灵披风","王者之冠","符文岩巨锤","远古符文法杖","流沙战袍","世界树长弓"]
check(len(game.GEAR) == 131, "装备 131 件（v1.49 +25；v1.52 +8；v1.57 +3；v1.58 +7；v1.59 +3）")
_miss49 = [n for n in _new49 if not game.gear_def(n)]
check(not _miss49, "v1.49：25 件全部入表" + ("；缺 " + str(_miss49) if _miss49 else ""))
_bad49 = []
for n in _new49:
    mm = game.craft_main_mat(n)
    if not mm or not mm.get("mat") or not mm.get("cnt"):
        _bad49.append(n)
check(not _bad49, "v1.49：主材料可解析（打造链可用）" + ("；异常 " + str(_bad49) if _bad49 else ""))
# 词条解析：组合词条正则修复——终焉披风自 v1.41 起「精英类成功率」键被整段吞掉的 bug（v1.52 阶梯对齐 3%→4%）
_s49 = new_state(); _s49["equipped"] = {"armor": "终焉披风"}
check(game.gear_effects(_s49)["rate"].get("精英") == 0.04,
      "v1.49 修复：终焉披风「精英类成功率+4%」键正确（原被整段吞键；v1.52 阶梯对齐）")
_s49["equipped"] = {"weapon": "混沌之刃"}
_ef49 = game.gear_effects(_s49)
check(_ef49["rate"].get("短时") == 0.03 and _ef49["nightmare"] == 0.03,
      "v1.49：组合词条分类键不跨「；」（混沌之刃 短时+3% / 噩梦+3%；v1.52 阶梯对齐）")
_s49["equipped"] = {"weapon": "远古符文法杖"}
_ef49b = game.gear_effects(_s49)
check(_ef49b["rate"].get("精英") == 0.03 and _ef49b["exp"] == 0.12,
      "v1.49：组合词条（远古符文法杖 精英+3% / 经验+12%；v1.52 阶梯对齐）")
check(len(game.sub_cats_for("金龙鳞")) > 0 and len(game.sub_cats_for("时间沙")) > 0,
      "v1.49：新材料副材品类系有效")

print("=== 53. v1.50：服务端修复批次（签到 / 午夜锁 / 声望 / 商店重构） ===")
# ① 传奇声望按面额（对齐原型 legendRep 与 03 文档）
check(game.legend_rep(None, ["屠龙传说", "精英", 5, "噩梦", "1铂金币", 500, "", "", {}]) == 700
      and game.legend_rep(None, ["时间回廊", "探索+精英", 3, "噩梦", "1.5铂金币", 700, "", "", {}]) == 750
      and game.legend_rep(None, ["X", "精英", 5, "困难", "50金币", 500, "", "", {}]) == 450
      and game.legend_rep(None, ["Y", "精英", 5, "噩梦", "10铂金币", 900, "", "", {}]) == 1600,
      "传奇声望按面额：1铂金噩梦 700 / 1.5铂金 750 / 50金困难 450 / 10铂金噩梦 1600")
# ② 传奇率熬夜惩罚 N（与普通委托同口径）
_s53 = new_state()
_s53["history"] = [{"date": "d", "score": 80, "sleep": False, "tasks": [0]*7, "multi": [0, 0]}]
_r_no = game.legend_rate(_s53, "噩梦")
_s53["history"] = [{"date": "d", "score": 80, "sleep": True, "tasks": [0]*7, "multi": [0, 0]}]
_r_ok = game.legend_rate(_s53, "噩梦")
check(abs((_r_ok - _r_no) - 0.15) < 1e-9, "传奇率：熬夜惩罚 −15%（v1.50 补齐）")
# ③ 每日签到（幂等 / 连续 / 里程碑）
_s53 = new_state(); _m53 = []
game.sign_tick(_s53, _m53)
check(_m53 and _s53["sign"]["streak"] == 1 and _s53["sign"]["total"] == 1 and _s53["vit"] == 1,
      "签到：首次 +1 活力 / 连续 1 / 累计 1")
_m53b = []; game.sign_tick(_s53, _m53b)
check(not _m53b, "签到：同日重入幂等")
_y53 = (game.parse_date(game.today_str()) - timedelta(days=1)).strftime("%Y-%m-%d")
_s54 = new_state(); _s54["sign"] = {"last": _y53, "streak": 6, "total": 10}
_m54 = []; game.sign_tick(_s54, _m54)
check(_s54["sign"]["streak"] == 7 and _s54["sign"]["total"] == 11 and _s54["vit"] == 4
      and "里程碑" in _m54[0], "签到：连续第 7 天里程碑 +3（共 +4）")
_s54["sign"] = {"last": _y53, "streak": 29, "total": 40}
game.sign_tick(_s54, [])
check(_s54["sign"]["streak"] == 30 and _s54["vit"] == 4 + 11, "签到：连续第 30 天里程碑 +10（共 +11）")
# ④ 00:00 后补打卡锁定（无窗口项；有窗口项行为不变）
_am = game.datetime(2026, 6, 15, 0, 30)
_s55 = new_state()
_r55a = game.toggle_task(_s55, 2, [], now=_am)
_r55b = game.toggle_task(_s55, 3, [], now=_am)
check(_r55a and "00:00" in _r55a and _r55b and _s55["health"]["done"][2] == 0,
      "凌晨 00:30：无窗口项被锁定（午休 / 喝水）")
check(isinstance(game.add_multi(_s55, 1, 1, [], now=_am), str), "凌晨：多次任务被锁定")
check("不在打卡时段" in (game.toggle_task(_s55, 0, [], now=_am) or ""),
      "凌晨：入睡项仍按窗口文案拒绝（非节日行为不变）")
check(game.toggle_task(_s55, 2, [], now=game.datetime(2026, 6, 15, 12, 0)) is None
      and _s55["health"]["done"][2] == 1, "白天 12:00：无窗口项正常打卡")
# ⑤ 活力药水补 meals（v1.53：桩掉午夜锁——原用例在 00:00–05:59 运行会误报失败）
_old_min56 = game._min_of_day
game._min_of_day = lambda now=None: 12 * 60
_s56 = new_state(); _s56["items"] = {"活力药水": 1}
check(game.use_item(_s56, "活力药水", []) is None and _s56["health"]["meals"] == [1, 1, 1]
      and _s56["health"]["score"] == 100, "活力药水：三餐一并补齐（v1.50 修复）")
game._min_of_day = _old_min56
# ⑥ 「大师」不因重复条目虚高（去重兜底）
_s57 = new_state()
_L57 = game.LEGEND[0]                     # v1.51：原按「无条件事件」筛选——现 12 事件均有专属条件，直接取首个
_s57["legend_done"] = [_L57[0]] * 4
check(not game._achv_cond(_s57, "大师"), "「大师」按不同事件数判定（旧档重复不虚高）")
_s57["legend_done"] = [x[0] for x in game.LEGEND[:4]]
check(game._achv_cond(_s57, "大师"), "「大师」：4 个不同传奇达成")
# ⑦ 探索按区域名结算（旧档 idx 错位不再串区）
_s58 = new_state()
_s58["explore_active"] = {"idx": 0, "n": game.REGIONS[3]["n"], "c": 2, "h": 0,
                          "startTs": 0, "finishTs": 0}
game.explore_finish_check(_s58, [])
check(_s58["explore_result"] and _s58["explore_result"]["region"] == game.REGIONS[3]["n"],
      "探索：按区域名结算（idx 错位不再串区）")
# ⑧ 接取池身份校验
_s59 = new_state()
game.catch_up(_s59)
_p59 = _s59.get("pool")
if _p59 and _p59["list"]:
    _nm59 = _p59["list"][0][0]
    _e59a = game.accept_quest(_s59, 0, [], name="不存在的委托", point=_p59["point"])
    _e59b = game.accept_quest(_s59, -1, [], name=_nm59, point=_p59["point"])
    _e59c = game.accept_quest(_s59, 0, [], name=_nm59, point="1999-01-01@08")
    check(_e59a and "刷新" in _e59a and _e59b is not None and _e59c is not None,
          "接取：名字不符 / 负索引 / 池刷新点不符 → 全部拒绝")
# ⑨ 薰香递增 + 铂金商店重构
check(game.INCENSE_BONUS == [0, 4, 9, 16, 26, 40]
      and any(x.get("incense") == 5 and "+14" in x["d"] for x in game.VIT_SHOP),
      "薰香 Ⅰ~Ⅴ 递增 +4/+5/+7/+10/+14（满级累计 +40）")
_s60 = new_state(); _s60["incense"] = 5
check(game.energy_base(_s60) == game.CFG["energyMax"][0] + 40, "薰香 V：精力上限累计 +40")
_epic59 = [k for k, v in game.M.items() if v[1] == "史诗"]
check(len(game.PLAT_SHOP) == 7 and all("platC" in it for it in game.PLAT_SHOP)
      and len(game.PLAT_SHOP[1]["sel"]) == len(_epic59)
      and all(k in game.PLAT_SHOP[1]["sel"] for k in _epic59),
      "铂金商店：7 项全铂金币结算（v1.61d +清醒/安眠）；史诗自选包 = 全部 " + str(len(_epic59)) + " 种")
_s61 = new_state(); _s61["lv_idx"] = 4; _s61["rep"] = 999999; _s61["money"] = 10 ** 9
check(game.buy_plat(_s61, [], 1, "龙血") is None and _s61["mats"].get("龙血") == 3
      and _s61["money"] == 10 ** 9 - 1000000, "铂金商店：史诗自选 ×3（-1 铂金币）")
check(game.buy_plat(_s61, [], 1, "蘑菇") is not None, "铂金商店：素材品阶不符被拒")
check(game.buy_plat(_s61, [], 3) is None and _s61["items"].get("疾风符咒") == 1, "铂金商店：疾风符咒 ×1")
check(game.buy_plat(_s61, [], 5) is None and _s61["items"].get("清醒符咒") == 1,
      "铂金商店：清醒符咒 ×1（v1.61d 由铜币商店移入）")
check(game.buy_plat(_s61, [], 6) is None and _s61["items"].get("安眠护符") == 1,
      "铂金商店：安眠护符 ×1（v1.61d 移入）")
# v1.61d：铂金商店解锁门槛 = 当前持有 ≥1 铂金币（不再看公会 S 级）
_s62 = new_state(); _s62["rep"] = 999999; _s62["money"] = 999999
check(game.buy_plat(_s62, [], 3) is not None, "铂金商店：持有 <1 铂金币被拒（门槛改持有量）")
_s62["money"] = 1000000
check(game.buy_plat(_s62, [], 3) is None, "铂金商店：恰 1 铂金币放行")
# v1.61d：规则道具不可出售（交易所只收材料）
_m0b = _s62["money"]; _s62["items"]["清醒符咒"] = 1
bad = game.sell_mat(_s62, "清醒符咒", 1)
check(bad is not None and _s62["money"] == _m0b and _s62["items"].get("清醒符咒") == 1,
      "规则道具不可出售（交易所仅材料）")
# ⑩ 导入档 schema 校验
_bad10 = game.import_save_state({"lvIdx": "x", "gear": "oops", "mats": 3, "money": -5})
check(_bad10 is not None and _bad10["lv_idx"] == 0 and isinstance(_bad10["gear"], list)
      and _bad10["money"] == 0 and _bad10["health"].get("vitOnce") == [0] * 10,
      "导入档 schema 校验：类型不符回退默认（防脏档）")
# ⑪ 元旦打卡每项仅首次发放（取消再点不重复）
_orig_fe = game.today_fest_eff
game.today_fest_eff = lambda d=None: {"vit_per_task": 3}
try:
    _s62 = new_state()
    game.toggle_task(_s62, 2, [], now=game.datetime(2026, 6, 15, 12, 0))
    _v62a = _s62["vit"]
    game.toggle_task(_s62, 2, [], now=game.datetime(2026, 6, 15, 12, 1))
    game.toggle_task(_s62, 2, [], now=game.datetime(2026, 6, 15, 12, 2))
    check(_v62a == 3 and _s62["vit"] == 3, "元旦打卡：每项仅首次发放（取消再点不重复）")
finally:
    game.today_fest_eff = _orig_fe
# ⑫ 老档迁移：缺字段自动补齐 + 月度事件自动补生成（v1.50c）
_s63 = new_state()
for _k in ("month_event", "sign", "legend_done", "seen_items"):
    _s63.pop(_k, None)
_s63["health"].pop("vitOnce", None)
_m63 = game.migrate_state(_s63)
check(_m63.get("month_event") is None and isinstance(_m63.get("sign"), dict)
      and _m63["health"].get("vitOnce") == [0] * 10 and isinstance(_m63.get("seen_items"), list),
      "老档迁移补全字段（month_event / sign / seen_items / vitOnce）")
game.catch_up(_m63)
check(game.month_event_now(_m63) is not None, "老档迁移后 catch_up 自动生成本月世界事件")

print("=== 54. v1.51：A4 声望 / 贡献按委托等级 + 传奇贡献 150 ===")
_old_r54 = game.rand
game.rand = lambda n: 50                  # 固定 roll=50：成功且无大成功（避免 crit 声望 +5 干扰）
try:
    # ① Lv5 玩家完成 Lv1 委托 → 声望 5 / 贡献 1（旧口径为 18 / 5）
    _s54 = new_state(); _s54["lv_idx"] = 4
    _r0, _c0 = _s54["rep"], _s54["con"]
    _q1_54 = game.C["Lv1"][0]
    settle(_s54, {"q": _q1_54, "rate": 1.0, "qlv": 5, "meal": None}, [])
    check(_s54["rep"] - _r0 == game.quest_rep(None, _q1_54, 1) and _s54["con"] - _c0 == 1,
          "A4：Lv5 玩家完成 Lv1 委托 → 声望 5 / 贡献 1（按委托等级）")
    # ② Lv5 玩家完成 Lv5 委托 → 声望 / 贡献按 Lv5 表
    _s54b = new_state(); _s54b["lv_idx"] = 4
    _r1, _c1 = _s54b["rep"], _s54b["con"]
    _q5_54 = game.C["Lv5"][0]
    settle(_s54b, {"q": _q5_54, "rate": 1.0, "qlv": 5, "meal": None}, [])
    check(_s54b["rep"] - _r1 == game.quest_rep(None, _q5_54, 5) and _s54b["con"] - _c1 == 5,
          "A4：Lv5 委托 → 声望 " + str(game.quest_rep(None, _q5_54, 5)) + " / 贡献 5")
finally:
    game.rand = _old_r54
# ③ 传奇贡献常量（结算分支同用；前端 LEGEND_CON 对齐）
check(game.LEGEND_CON == 150, "A4：传奇事件贡献 +150（LEGEND_CON）")

print("=== 55. v1.51：A3 传奇同时限 1 + 专属传说装备条件 ===")
# ① 4 事件带 gear 条件且装备名有效
_g55 = {L[0]: (L[8] or {}).get("gear") for L in game.LEGEND}
_gnames = {g[0] for g in game.GEAR}
check(_g55.get("星界远征") == "星界护铠" and _g55.get("世界树种子") == "世界树之枝"
      and _g55.get("龙神契约") == "龙瞳宝珠" and _g55.get("万龙之宴") == "金龙鳞铠"
      and all(v in _gnames for v in _g55.values() if v),
      "A3：4 事件专属条件（传说装备）+ 装备名有效")
# ② eligible：无装备 → 不合格；有装备 → 合格
_L55 = [L for L in game.LEGEND if L[0] == "星界远征"][0]
_s55 = new_state()
check(not game.legend_eligible(_s55, _L55), "A3：未拥有星界护铠 → 星界远征不符合条件")
_s55["gear"].append("星界护铠")
check(game.legend_eligible(_s55, _L55), "A3：拥有星界护铠 → 符合条件")
# ③ 同时最多 1 个：进行中传奇未完成时接取被拒
_s55b = new_state()
_s55b["legend_active"] = [L for L in game.LEGEND if L[0] == "公会大师试炼"][0]
_s55b["active"].append({"q": ["X"], "legend": _s55b["legend_active"]})
_r55 = game.take_legend(_s55b, [])
check("同时最多 1 个" in _r55, "A3：已有传奇进行中 → 接取被拒（同时最多 1 个）")

print("=== 56. v1.52：B1 难度报酬 / B2 铂金商店 / B4+B6 词条阶梯 / B7 材料出口 / C3 API 瘦身 ===")
# ① B1：6 条难度报酬修正
_c56 = {q[0]: q[5] for lv in game.C.values() for q in lv}
check(_c56.get("讨伐哥布林") == 16000 and _c56.get("星图师的需求") == 66000
      and _c56.get("探索古代矿坑") == 70000 and _c56.get("深渊裂隙调查") == 70000
      and _c56.get("讨伐独眼巨人") == 75000 and _c56.get("龙血商人的订单") == 260000,
      "B1：6 条难度报酬修正（困难 ≥ 同档普通下限）")
# ② B2：铂金商店传说自选 7 → 13
_sel56 = game.PLAT_SHOP[0]["sel"]
check(len(_sel56) == 13 and all(k in _sel56 for k in ["世界树枝条", "时之沙漏", "星辉花", "星尘蜜", "星陨岩", "云纹锦"]),
      "B2：铂金商店传说自选 13 种（+6 无稳定购买渠道传说主材）")
# ③ B4+B6：全量词条阶梯校验（同效果跨品阶严格递增，0 违规）
import re as _re56
_qo56 = ["精良", "稀有", "史诗", "传说"]
_pat56 = _re56.compile(r'^(.*?)(成功率|精力消耗|委托报酬|报酬|经验|贡献|探索点|材料获取|事件概率)\s*([+-]\d+)%?(/天)?$')
_mat56 = {}
for _g in game.GEAR:
    if _g[4] == "—":
        continue
    for _part in _g[4].split("；"):
        _m = _pat56.match(_part.strip())
        if not _m:
            continue
        _key = (_m.group(1), _m.group(2) + ("/天" if _m.group(4) else ""))
        _mat56.setdefault(_key, {}).setdefault(_g[1], []).append(abs(int(_m.group(3))))
_viol56 = []
for _key, _byq in _mat56.items():
    _qs = [_q for _q in _qo56 if _q in _byq]
    for _i in range(len(_qs) - 1):
        if min(_byq[_qs[_i + 1]]) <= max(_byq[_qs[_i]]):
            _viol56.append((_key, _qs[_i], _qs[_i + 1]))
check(not _viol56, "B4+B6：词条阶梯严格递增（0 违规）" + ("；违规 " + str(_viol56) if _viol56 else ""))
# ④ B7：8 件无出口材料专属装备（主材可解析）
_new8 = ["鹿皮斗篷", "天鹅绒礼服", "白银短剑", "铁木长弓", "蛛丝软甲", "黑铁重剑", "血玛瑙坠", "狮鹫羽弓"]
_bad756 = [n for n in _new8 if not any(g[0] == n for g in game.GEAR)]
check(not _bad756, "B7：8 件新装备入表" + ("；缺失 " + str(_bad756) if _bad756 else ""))
check(all(any(g[0] == n and g[5] != "—" for g in game.GEAR) for n in _new8),
      "B7：8 件全部可打造（有主材）")
# ⑤ 区域掉落补黑曜石/大理石（唯一断档来源修复）
_wk56 = [r for r in game.REGIONS if r["n"] == "废弃矿道"][0]
_d56 = [x[0] for x in _wk56["d"]]
check("黑曜石" in _d56 and "大理石" in _d56, "B7：废弃矿道补黑曜石/大理石掉落（黑曜石原无任何来源）")
# ⑥ C3：derived 已从 API 移除
check(not hasattr(game, "derived"), "C3：derived 已删除（/api/state 停传 55KB 派生数据）")

print("=== 57. v1.58：六域遗珍（新材料 / 装备 / 料理）+ 「探索点/天」词条移除 ===")
# ① 6 种新材料（史诗）入表 + 全部挂在新地点掉落表
_new58 = {"冥河灯油": "特殊", "地狱火种": "宝石", "泰坦石核": "矿石",
          "沼心莲实": "食材", "深海遗珠": "宝石", "冰晶果": "食材"}
check(all(k in game.M and game.M[k][0] == c and game.M[k][1] == "史诗" for k, c in _new58.items()),
      "6 种新材料（史诗）入表且品类正确")
_unl58 = [r for r in game.REGIONS if r.get("unlock")]
_hit58 = [k for k in _new58 if any(k in [e[0] for e in r["d"]] for r in _unl58)]
check(len(_hit58) == 6, "6 种新材料全部挂在链解锁地点掉落表（命中 " + str(len(_hit58)) + "）")
# ② 7 件新装备入表 + 效果解析（词条阶梯由第 56 节全量校验覆盖）
_newg58 = ["引魂长明灯", "狱火护腕", "泰坦石核锤", "遗珠坠", "世界树心护符", "龙炎护手", "观星者指环"]
_miss58 = [n for n in _newg58 if not game.gear_def(n)]
check(not _miss58, "7 件六域遗珍装备入表" + ("；缺 " + str(_miss58) if _miss58 else ""))
_s58 = new_state()
_s58["equipped"] = {"weapon": None, "armor": None, "accessory": "世界树心护符", "charmSlot": None}
check(abs(game.gear_effects(_s58)["healthUp"] - 0.12) < 1e-9, "世界树心护符：健康加成上限+12%")
_s58["equipped"]["accessory"] = "观星者指环"
check(abs(game.gear_effects(_s58)["rare"] - 0.01) < 1e-9, "观星者指环：稀有事件概率+1%")
_s58["equipped"] = {"weapon": None, "armor": "龙炎护手", "accessory": None, "charmSlot": None}
check(abs(game.gear_effects(_s58)["enCut"].get("短时", 0) - 0.12) < 1e-9, "龙炎护手：短时类精力消耗-12%")
_s58["equipped"] = {"weapon": None, "armor": "狱火护腕", "accessory": None, "charmSlot": None}
check(abs(game.gear_effects(_s58)["enCut"].get("精英", 0) - 0.08) < 1e-9, "狱火护腕：精英类精力消耗-8%")
_s58["equipped"] = {"weapon": None, "armor": None, "accessory": "遗珠坠", "charmSlot": None}
check(abs(game.gear_effects(_s58)["enCut"].get("探索", 0) - 0.08) < 1e-9, "遗珠坠：探索类精力消耗-8%")
# ③ 「探索点/天」词条整体移除（装备 / 宠物 / 引擎通道）
check("sp" not in game.gear_effects(new_state()) and all("/天" not in (g[4] or "") for g in game.GEAR),
      "「探索点/天」词条整体移除（gear_effects 无 sp 通道 / 全装备词条无「/天」）")
_s58b = new_state(); _s58b["carry_pet"] = "月光狐"
check("sp" not in game.pet_bonus(_s58b), "pet_bonus 无 sp 项（v1.58 通道移除）")
# ④ 替换词条（银戒指 / 藏书家之冕）
_s58["equipped"] = {"weapon": None, "armor": None, "accessory": "银戒指", "charmSlot": None}
check(abs(game.gear_effects(_s58)["enCut"].get("探索", 0) - 0.03) < 1e-9, "银戒指：探索类精力消耗-3%（原探索点+1/天）")
_s58["equipped"] = {"weapon": None, "armor": None, "accessory": None, "charmSlot": "藏书家之冕"}
check(abs(game.gear_effects(_s58)["exp"] - 0.10) < 1e-9, "藏书家之冕：委托经验+10%（原探索点+1/天）")
# ⑤ 4 道新料理入表 + 盛宴仍最强
_cook58 = ["沼心莲实羹", "冰晶果酪", "遗珠海味羹", "六域拼盘"]
check(all(any(r["n"] == n for r in game.CFG["recipes"]) for n in _cook58), "4 道六域遗珍料理入表")
_feast58 = next(r for r in game.CFG["recipes"] if r["n"] == "巨龙盛宴")
_plate58 = next(r for r in game.CFG["recipes"] if r["n"] == "六域拼盘")
check(_feast58["bonus"] > _plate58["bonus"] and _feast58["rate"] >= _plate58["rate"],
      "六域拼盘（传说）仍弱于巨龙盛宴（最强定位保留）")

print("=== 58. v1.59：传奇报酬上调 / Lv4 简单档梯度 / 弱出口装备补全 ===")
# ① 5 个传奇事件报酬/经验上调（早期与长周期档不再被新内容反超；同档差距保留）
_lg59 = {L[0]: L for L in game.LEGEND}
check(_lg59["屠龙传说"][4] == "2铂金币" and _lg59["屠龙传说"][5] == 800, "屠龙传说：1铂金/500 → 2铂金/800")
check(_lg59["星界远征"][4] == "3铂金币" and _lg59["星界远征"][5] == 1050, "星界远征：2铂金/800 → 3铂金/1050")
check(_lg59["公会大师试炼"][4] == "2铂金币" and _lg59["公会大师试炼"][5] == 1000, "公会大师试炼：50金/600 → 2铂金/1000")
check(_lg59["龙神契约"][4] == "7铂金币" and _lg59["龙神契约"][5] == 2000, "龙神契约：5铂金/1500 → 7铂金/2000")
check(_lg59["万龙之宴"][4] == "9铂金币" and _lg59["万龙之宴"][5] == 2300, "万龙之宴：8铂金/2000 → 9铂金/2300")
check(_lg59["创世碎片"][4] == "10铂金币" and _lg59["虚空王座"][4] == "6铂金币",
      "终局档（创世碎片 / 虚空王座）维持面额——差异化保留")
# ② LEGEND_GOLD 全键覆盖（v1.59 补「9铂金币」——此前缺键会静默回落 1 铂金）
check(all(L[4] in game.LEGEND_GOLD for L in game.LEGEND), "传奇报酬面额全部可解析（LEGEND_GOLD 无缺键）")
check(game.LEGEND_GOLD["9铂金币"] == 9000000, "LEGEND_GOLD 补「9铂金币」= 9000000")
check(game.legend_rep(None, _lg59["屠龙传说"]) == 800, "屠龙传说声望随面额升至 800（400 + 2×100 + 200）")
# ③ Lv4 简单档梯度（上限 < 普通档下限；对齐 Lv5 档距）
_c4 = {q[0]: q for lv in game.C.values() for q in lv}
_lv4_simple = {q[0]: q for q in game.C["Lv4"] if q[4] == "简单"}
_lv4_normal = [q[5] for q in game.C["Lv4"] if q[4] == "普通"]
check(len(_lv4_simple) == 4 and max(q[5] for q in _lv4_simple.values()) < min(_lv4_normal),
      "Lv4 简单档 4 件、报酬上限（" + str(max(q[5] for q in _lv4_simple.values())) + "）< 普通下限（" + str(min(_lv4_normal)) + "）")
check(_c4["商队护卫见习"][5] == 55000 and _c4["王都巡夜"][5] == 58000
      and _c4["药圃除虫"][5] == 52000 and _c4["猎场驱兽"][5] == 60000,
      "Lv4 简单档四件报酬下调到位（5.5 / 5.8 / 5.2 / 6 万，经验同步 56/58/54/60）")
check(_c4["药圃除虫"][6] == 54 and _c4["猎场驱兽"][6] == 60, "Lv4 简单档经验同步下调")
# ④ 弱出口材料补全（花岗岩 / 铅矿石 / 古董钱币 → 装备主材）
_newg59 = {"花岗岩重锤": "花岗岩×2", "铅矿护符": "铅矿石×1", "古币坠饰": "古董钱币×3"}
check(all(game.gear_def(k) is not None and game.gear_def(k)[5] == v for k, v in _newg59.items()),
      "3 件弱出口装备入表且主材数量符规范（普通 2 / 普通饰品 1 / 稀有饰品 3）")
_mains59 = {g[5].split("×")[0] for g in game.GEAR if g[5] != "—"}
check({"花岗岩", "铅矿石", "古董钱币"} <= _mains59, "花岗岩 / 铅矿石 / 古董钱币 取得装备主材出口（弱出口清零）")

print("=== 59. v1.60/v1.61：大师试炼 250 / 疗养圣所（无门槛·每月3天·59 锁定·打卡封存） / 深处 C-A-S / 护符 C-B / 重掷券 B / 虚空裂痕 Lv4 ===")


def _base59(rep=0, lv=4):
    x = new_state()
    x["lv_idx"] = lv
    x["rep"] = rep
    return x


# ① 大师试炼：完成 250 次 Lv1–4 委托（v1.60：40 → 250）
_gm59 = next(L for L in game.LEGEND if L[0] == "公会大师试炼")
_s59a = _base59(rep=2200)
_s59a["done_below5"] = 249
check(game.legend_eligible(_s59a, _gm59) is False, "大师试炼：249 次未达标被拦")
_s59a["done_below5"] = 250
check(game.legend_eligible(_s59a, _gm59) is True, "大师试炼：250 次达标放行")

# ② 疗养圣所（病假，v1.61：无门槛 / 每月 3 天 / 评分锁定 59 + 打卡封存；v1.60 原「医务室」·公会 C·每月 2 天）
_s59b = _base59(rep=0)                         # 0 声望（F 级）——无门槛，直接可用
check(game.take_sick_leave(_s59b, "today", []) is None and _s59b["sick_days"] == [game.today_str()],
      "疗养圣所：0 声望即可请今日病假（写入 sick_days）")
check(game.calc_health(_s59b) == 59, "疗养圣所：病假日评分锁定 59")
bad = game.toggle_task(_s59b, 1, [])
check(bad is not None and "封存" in bad, "疗养圣所：病假日打卡被封存（toggle_task 拒绝）")
bad = game.toggle_meal(_s59b, 0, [])
check(bad is not None and "封存" in bad, "疗养圣所：病假日三餐被封存（toggle_meal 拒绝）")
bad = game.add_multi(_s59b, 0, 1, [])
check(bad is not None and "封存" in bad, "疗养圣所：病假日多次任务被封存（add_multi 拒绝）")
_s59u = _base59(rep=0)
_s59u["sick_days"] = [game.today_str()]
_s59u["items"] = {"活力药水": 1}
bad = game.use_item(_s59u, "活力药水", [])
check(bad is not None and "封存" in bad, "疗养圣所：病假日打卡类道具被封存（活力药水拒绝）")
bad = game.take_sick_leave(_s59b, "today", [])
check(bad is not None, "疗养圣所：同日重复请假被拒")
_ym59 = _s59b["health"]["date"][:7]
_s59c = _base59(rep=0)
_s59c["sick_days"] = [_ym59 + "-01", _ym59 + "-02", _ym59 + "-03"]
bad = game.take_sick_leave(_s59c, "today", [])
check(bad is not None and "用完" in bad, "疗养圣所：每月 3 天上限（第 4 次被拒）")
_y59 = (game.parse_date(game.today_str()) - timedelta(days=1)).strftime("%Y-%m-%d")
_s59d = _base59(rep=0)
_s59d["history"] = [{"date": _y59, "sleep": False, "done": 0, "tasks": [], "multi": [0, 0], "score": 30}]
check(game.take_sick_leave(_s59d, "yesterday", []) is None and _s59d["sick_days"] == [_y59]
      and _s59d["history"][-1]["score"] == 59,
      "疗养圣所：昨日断档 → 补请成功且昨日评分改写为 59")
_s59d2 = _base59(rep=0)
_s59d2["history"] = [{"date": _y59, "sleep": True, "done": 0, "tasks": [], "multi": [0, 0], "score": 80}]
bad = game.take_sick_leave(_s59d2, "yesterday", [])
check(bad is not None, "疗养圣所：昨日已早睡 → 补请被拒")
# 病假覆盖 = 连击保护（_sleep_streak 与 sleep_streak 同口径）
_s59e = _base59()
_s59e["history"] = [
    {"date": "d1", "sleep": True, "done": 0, "tasks": [], "multi": [0, 0]},
    {"date": "d2", "sleep": False, "done": 0, "tasks": [], "multi": [0, 0]},
    {"date": "d3", "sleep": True, "done": 0, "tasks": [], "multi": [0, 0]},
]
check(game._sleep_streak(_s59e) == 1, "病假前：断档日终止连击")
_s59e["sick_days"] = ["d2"]
check(game._sleep_streak(_s59e) == 3, "病假覆盖断档日 → 连击保留（3 天）")
_hist59 = [{"date": "d%02d" % i, "sleep": (i not in (5, 12, 19, 26)), "done": 0, "tasks": [], "multi": [0, 0]}
           for i in range(1, 31)]
_s59f = _base59()
_s59f["history"] = list(_hist59)
check(game.sleep_streak(_s59f, 30) is False, "30 天 4 次断档未覆盖 → 不达标（< 27）")
_s59f["sick_days"] = ["d05", "d12", "d19"]
_s59f["history"] = list(_hist59)
check(game.sleep_streak(_s59f, 30) is True, "病假覆盖 3 次断档 → 达标（≥ 27，保护日计入）")

# ③ 深处双门槛 C/A/S 共绑 + 虚空裂痕 Lv4
_reg59 = {r["n"]: r for r in game.REGIONS}
check(_reg59["晨光森林·深处"].get("lv") == 3 and _reg59["晨光森林·深处"].get("g") == 3, "晨光深处 = Lv3 + 公会 C")
check(_reg59["午间溪谷·深处"].get("g") == 3 and _reg59["黄昏山丘·深处"].get("g") == 3, "午间/黄昏深处 = 公会 C")
check(_reg59["星夜洞窟·深处"].get("lv") == 4 and _reg59["星夜洞窟·深处"].get("g") == 5, "星夜深处 = Lv4 + 公会 A")
check(_reg59["废弃矿道·深处"].get("g") == 5, "废弃矿道深处 = 公会 A")
check(_reg59["腐化森林·深处"].get("lv") == 5 and _reg59["腐化森林·深处"].get("g") == 6, "腐化深处 = Lv5 + 公会 S")
check(_reg59["虚空裂痕·深处"].get("lv") == 5 and _reg59["虚空裂痕·深处"].get("g") == 6, "虚空深处 = Lv5 + 公会 S")
check(_reg59["虚空裂痕"].get("lv") == 4, "虚空裂痕地表 Lv3 → Lv4")
_s59g = _base59(rep=400, lv=2)                 # Lv3 + D
check(game.region_gate(_s59g, _reg59["晨光森林·深处"]) is not None, "晨光深处：Lv3+公会D 被公会线拦（v1.60 起需 C）")
_s59g["rep"] = 850
check(game.region_gate(_s59g, _reg59["晨光森林·深处"]) is None, "晨光深处：Lv3+公会C 放行")
_s59g2 = _base59(rep=2200, lv=3)               # Lv4 + A
check(game.region_gate(_s59g2, _reg59["星夜洞窟·深处"]) is None, "星夜深处：Lv4+公会A 放行")
_s59g2["lv_idx"] = 2
check(game.region_gate(_s59g2, _reg59["星夜洞窟·深处"]) is not None, "星夜深处：Lv3 被等级线拦")

# ④ 护符 I/II 判定对齐文案（C/B）
_s59h = _base59(rep=400)
check(game.charm_unlocked(_s59h, 0) is False, "护符 I：公会 D 未解锁（v1.60 起需 C）")
_s59h["rep"] = 850
check(game.charm_unlocked(_s59h, 0) is True, "护符 I：公会 C 解锁")
_s59h["charm"] = 1
check(game.charm_unlocked(_s59h, 1) is False, "护符 II：公会 C 未解锁（需 B）")
_s59h["rep"] = 1200
check(game.charm_unlocked(_s59h, 1) is True, "护符 II：公会 B 解锁")

# ⑤ 精英委托重掷券：解锁档位 C → B（对齐文案/文档）
_rr59 = next(it for it in game.CON_SHOP if "重掷券" in it["n"])
check(_rr59.get("g") == 4, "精英委托重掷券：解锁公会 B 级（g=4）")

print()
print("=" * 40)
print("  通过 " + str(PASS) + " 项 | 失败 " + str(FAIL) + " 项 " + ("✅ 全部通过" if FAIL == 0 else "❌"))
sys.exit(1 if FAIL else 0)
