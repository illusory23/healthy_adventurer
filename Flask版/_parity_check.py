# -*- coding: utf-8 -*-
"""C1 双端公式对拍（JS 原型 ↔ Python 服务端）
   步骤：① node 跑 创造模式测试原型/_parity_dump.js 生成 _parity_out.json；
         ② 用 game.py 同源函数对同输入逐条比对（容差 1e-9）。
   运行：python _parity_check.py（需 node；控制台建议 PYTHONIOENCODING=utf-8）"""
import json
import subprocess
import sys
from pathlib import Path

import game

PASS = 0
FAIL = 0


def _val_eq(a, b):
    """v1.55：数值感知的深比较——JS 的 0 与 Python 的 0.0 序列化不同但等值"""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_val_eq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_val_eq(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return a == b


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  ❌ " + msg)


PROTO = Path(__file__).parent.parent / "创造模式测试原型"

print("=== 1. 生成原型侧结果（node _parity_dump.js） ===")
r = subprocess.run(["node", "_parity_dump.js"], cwd=str(PROTO),
                   capture_output=True, text=True, encoding="utf-8")
if r.returncode != 0:
    print(r.stdout or "")
    print(r.stderr or "")
    sys.exit("node dump 失败——请确认已安装 node")
out = json.loads((PROTO / "_parity_out.json").read_text(encoding="utf-8"))
print("  " + (r.stdout or "").strip())

print("=== 2. 常量表对拍 ===")
check(out["expNeed"] == game.CFG["expNeed"], "expNeed 经验门槛表")
check(out["sucBase"] == game.CFG["sucBase"], "sucBase 基础成功率表")
check(out["matDrop"] == game.CFG["matDrop"], "matDrop 材料掉率表")
check(out["drawCount"] == game.CFG["drawCount"], "drawCount 池抽取数表")

print("=== 3. successRate ↔ success_rate（委托等级 × 当前等级 × 难度） ===")
s = game.new_state()
bad3 = []
for item in out["successRate"]:
    s["lv_idx"] = item["lv"]
    q = [item["name"], "采集", 0, 1, item["diff"], 100, 10, [], {}]
    got = game.success_rate(s, q)
    if abs(got - item["out"]) > 1e-9:
        bad3.append("%s@Lv%d(委托Lv%d) 双端 %.6f/%.6f"
                    % (item["diff"], item["lv"], item["qi"] + 1, item["out"], got))
check(not bad3, "成功率全部一致（" + str(len(out["successRate"])) + " 组）"
      + ("；不一致 " + str(len(bad3)) + " 组: " + "; ".join(bad3[:5]) if bad3 else ""))

print("=== 4. matDropRate ↔ mat_drop_rate（全部材料） ===")
bad4 = []
for item in out["matDropRate"]:
    got = game.mat_drop_rate(item["name"])
    if abs(got - item["out"]) > 1e-9:
        bad4.append(item["name"])
check(not bad4, "材料掉率一致（" + str(len(out["matDropRate"])) + " 种）"
      + ("；不一致: " + ", ".join(bad4[:6]) if bad4 else ""))

print("=== 5. matQtyRange ↔ mat_qty_range ===")
bad5 = []
for item in out["matQtyRange"]:
    if list(game.mat_qty_range(item["v"])) != list(item["out"]):
        bad5.append(str(item["v"]))
check(not bad5, "数量区间归一一致（" + str(len(out["matQtyRange"])) + " 组）"
      + ("；不一致: " + ", ".join(bad5) if bad5 else ""))

print("=== 6. 硬编码表双端一致（v1.48e：防洪移漂移） ===")
_T = out["tables"]


def _diff(name, a, b):
    sa, sb = set(map(str, a)), set(map(str, b))
    only_p, only_s = sa - sb, sb - sa
    check(not only_p and not only_s,
          name + "（原型 " + str(len(a)) + " / 服务端 " + str(len(b)) + "）"
          + ("；仅原型: " + str(sorted(only_p)) if only_p else "")
          + ("；仅服务端: " + str(sorted(only_s)) if only_s else ""))


_diff("ACHV 成就", _T["achv"], [a[0] for a in game.ACHV])
_diff("FESTIVALS 单日节日", _T["festivals"], list(game.FESTIVALS.keys()))
_diff("FEST_EFF 节日效果", _T["festEff"], list(game.FEST_EFF.keys()))
_diff("FESTIVAL_RANGES 假期区间", _T["festRanges"], [x[2] for x in game.FESTIVAL_RANGES])
_diff("PET_LINES 可养成宠物", _T["petLines"], list(game.PET_LINES.keys()))
_diff("WOLF_STAGES 狼链", _T["wolfStages"], [x["name"] if x else None for x in game.WOLF_STAGES])
_diff("CFG.recipes 料理", _T["recipes"], [r["n"] for r in game.CFG["recipes"]])
check(_T["subCats"] == game.SUB_CATS, "SUB_CATS 副材品类表逐项一致")
_cfgP, _cfgS = out["cfgFull"], game.CFG
_diffk = [k for k in set(_cfgP) | set(_cfgS)
          if json.dumps(_cfgP.get(k), ensure_ascii=False, sort_keys=True)
          != json.dumps(_cfgS.get(k), ensure_ascii=False, sort_keys=True)]
check(not _diffk, "CFG 全量一致（" + str(len(_cfgP)) + " 键）" + ("；差异键: " + str(_diffk) if _diffk else ""))

print("=== 7. GEAR 装备表双端一致（v1.49） ===")
_pg, _ps = out["gear"], [list(x) for x in game.GEAR]
_badg = [i for i in range(max(len(_pg), len(_ps))) if i >= len(_pg) or i >= len(_ps) or _pg[i] != _ps[i]]
check(not _badg, "GEAR 全量一致（" + str(len(_pg)) + " 件）"
      + ("；差异下标: " + str(_badg[:6]) if _badg else ""))

print("=== 8. 全量数据表 · 前端 ↔ 服务端（v1.51：27 表防漂移；v1.55：+PET_LINES 含品阶/数值 = 28 表） ===")
_tf = out["tablesFull"]
_bad8 = []
for k in sorted(_tf):
    srv = getattr(game, k, None)
    if _val_eq(_tf[k], srv):
        continue
    if k == "C" and isinstance(srv, dict) and isinstance(_tf[k], dict):
        ok = True                       # C 表：仅顺序历史差异（渲染副作用），按名字集合 + 逐条内容比
        for lv in srv:
            sm = {q[0]: q for q in srv.get(lv, [])}
            pm = {q[0]: q for q in _tf[k].get(lv, [])}
            if set(sm) != set(pm) or any(not _val_eq(sm[n], pm[n]) for n in sm):
                ok = False
                break
        if ok:
            continue
    _bad8.append(k)
check(not _bad8, "全量数据表一致（" + str(len(_tf)) + " 表）" + ("；差异: " + str(_bad8) if _bad8 else ""))

print("=== 9. 全量数据表 · 原型 ↔ 前端（v1.51：创造模式与 Flask 前端同步） ===")
_r2 = subprocess.run(["node", "_dump_proto.js"], cwd=str(PROTO),
                     capture_output=True, text=True, encoding="utf-8")
if _r2.returncode != 0:
    print(_r2.stdout or "")
    print(_r2.stderr or "")
    sys.exit("node _dump_proto.js 失败——请确认已安装 node")
_proto = json.loads((PROTO / "_proto_out.json").read_text(encoding="utf-8"))
_bad9 = [k for k in sorted(_tf)
         if not _val_eq(_proto["tablesFull"].get(k), _tf[k])]
check(not _bad9, "原型数据表一致（" + str(len(_tf)) + " 表）" + ("；差异: " + str(_bad9) if _bad9 else ""))
check(_proto.get("gear") == out.get("gear"),
      "原型 GEAR 一致（" + str(len(_proto.get("gear") or [])) + " 件）")

print()
print("=" * 40)
print("  对拍：通过 " + str(PASS) + " 项 | 失败 " + str(FAIL) + " 项 " + ("✅ 全部一致" if FAIL == 0 else "❌"))
sys.exit(1 if FAIL else 0)
