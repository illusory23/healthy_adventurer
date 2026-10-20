# -*- coding: utf-8 -*-
"""存档工具 —— 查看 / 修改 Flask 版账号存档（v1.69）

两种用法：

  【交互式菜单·推荐】python 存档工具.py            → 分类菜单，逐步选：账号 → 类别 → 操作 → 填参数
      自动判模式：服务在跑 → 在线（走本机 /admin/dev，改完即时生效，游戏里能看到动画）；
                  没跑     → 离线（直接读写数据库，改完启动服务生效）。
      在线 / 离线都能用的功能：刷新委托栏、立刻完成委托（可指定掷骰值：1=大成功 / 96=大失败 /
      任意 1~100 / 随机）、改钱 / 等级 / 经验 / 声望 / 精力、加材料道具装备、宠物、称号成就、
      探索、复位各类队列、RAW JSON 直改…… 共 40 项（另有整档替换 / 自动备份回滚）。
  【命令行】python 存档工具.py <子命令> …          → 原来的一行命令用法（下表，行为不变）。

⚠️ 离线改档前请先停服（双击「停止服务.bat」）；改完用「run.bat / 重启服务.bat」启动。
   两种方式都在每次写入前，自动把该账号的「修改前整档」备份到 data/backups/manual-*.json。

命令行用法（在 Flask版 目录下运行）：

  python 存档工具.py 列表
  python 存档工具.py 查看 <昵称或id> [--全量]
  python 存档工具.py 导出 <昵称或id> [保存路径]
  python 存档工具.py 设置 <昵称或id> money=1000000 lv_idx=3 exp=8000
  python 存档工具.py 加材料 <昵称或id> 暗影草=5 龙鳞=2        # 数量可为负（负 = 扣除）
  python 存档工具.py 加道具 <昵称或id> 专注药剂=3
  python 存档工具.py 加装备 <昵称或id> 黑铁重剑 [武器/护甲/饰品/护符]   # 可选：直接穿上
  python 存档工具.py 加宠物 <昵称或id> 月光狐 [携带]
  python 存档工具.py 替换 <昵称或id> 编辑好的整档.json          # 兼容游戏「导出快照」的驼峰格式

金额单位 = 铜：1 银 = 100 铜 ｜ 1 金 = 10000 铜 ｜ 1 铂金币 = 1000000 铜。
更多改法（健康历史 / 称号 / 图鉴 / 社交表等）见根目录《存档修改教程.md》。
"""
import json
import os
import socket
import sys
import time
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import db
import devops
import game

# 测试用：GP_DB=xxx.db 可指向临时库（正常使用不需要设置）
_override = os.environ.get("GP_DB")
if _override:
    db.DB_PATH = Path(_override)

# 可设置键 → (最小值, 最大值或 None)   —— 其余键请照《存档修改教程.md》写脚本改
SET_KEYS = {
    "money": (0, None), "lv_idx": (0, 4), "exp": (0, None), "rep": (0, None),
    "con": (0, None), "vit": (0, None), "energy": (0, None), "explore": (0, None),
    "perm_energy": (0, 50), "train_energy": (0, 200), "incense": (0, 5),
    "charm": (0, 5), "echo": (0, 3), "heat_n": (0, None),
    "done_below5": (0, None), "total_quests": (0, None),
}
SET_KEYS_TXT = ("money(金币·铜) / lv_idx(等级下标 0~4) / exp(累计经验) / rep(声望) / con(贡献) / "
                "vit(活力点) / energy(精力) / explore(探索点) / perm_energy / train_energy / "
                "incense(薰香·0~5) / charm(护符·0~5) / echo(回响·0~3) / heat_n / done_below5 / total_quests")

# 装备槽位：装备表部位 → equipped 键；SLOT_ALIAS = 用户输入的槽位词 → equipped 键
SLOT_BY_GEAR = {"武器": "weapon", "护甲": "armor", "饰品": "accessory", "成就饰品槽": "charmSlot"}
SLOT_ALIAS = {"武器": "weapon", "护甲": "armor", "饰品": "accessory",
              "护符": "charmSlot", "成就饰品": "charmSlot", "成就饰品槽": "charmSlot"}


def die(msg):
    print("✖ " + msg)
    sys.exit(1)


def check_server():
    """服务器（:5899）运行中时禁止改档——运行中改会被下一个请求整档回写覆盖"""
    try:
        with socket.create_connection(("127.0.0.1", 5899), timeout=0.6):
            if "--强制" not in sys.argv:
                die("检测到服务器正在运行（端口 5899）——请先双击「停止服务.bat」再改档。\n"
                    "  （确实要继续、不推荐时，可在命令末尾加 --强制）")
    except OSError:
        pass


def find_user(ident):
    rows = db.list_users()
    if str(ident).isdigit():
        for r in rows:
            if r["id"] == int(ident):
                return r
    low = str(ident).casefold()
    for r in rows:
        if (r["name"] or "").casefold() == low:
            return r
    die("找不到账号「%s」——先运行「python 存档工具.py 列表」看看有哪些账号。" % ident)


def load(uid):
    raw, bad = db.load_user_state(uid)
    if bad:
        die("该账号的存档 JSON 已损坏（原文已另存 data/corrupt/）——请先人工修复，本工具不覆盖损坏档。")
    s = game.migrate_state(raw) if raw else game.new_state()
    # v1.69：记下「改动前」快照——save() 拿它做备份（原来备份的是改完的档，等于把这次改动也存进去了，
    #        真改坏了拿它恢复 = 恢复成坏的那份，白备份）
    _PRE[uid] = json.loads(json.dumps(s))
    return s


_PRE = {}          # uid → 改动前整档快照（load 记录、save 消费，一次性）


def backup(uid, s):
    """写入前自动备份（改坏了可以拿它整档恢复）"""
    d = Path(db.DB_PATH).parent / "backups"
    d.mkdir(parents=True, exist_ok=True)
    fn = d / ("manual-user%d-%s-%03d.json" % (uid, time.strftime("%Y%m%d-%H%M%S"), int(time.time() * 1000) % 1000))
    fn.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    return fn


def save(uid, s, act):
    fn = backup(uid, _PRE.pop(uid, None) or s)     # v1.69：优先备份「改动前」快照（见 load）
    db.save_user_state(uid, s)
    print("✔ %s 已写入（账号 id=%d）。" % (act, uid))
    print("  修改前的备份：%s" % fn)
    print("  改完请启动服务（run.bat / 重启服务.bat），进游戏核对。")


def fmt_kv(pair):
    k, _, v = str(pair).partition("=")
    if not k or not v:
        die("参数「%s」格式不对——应写成 键=值（如 money=1000000）。" % pair)
    try:
        return k.strip(), int(v)
    except ValueError:
        die("参数「%s」的值不是整数。" % pair)


# ══════════════ 各命令 ══════════════

def cmd_list():
    rows = db.list_users()
    if not rows:
        print("（还没有任何账号）")
        return
    print("%-4s %-12s %-10s %-10s %s" % ("id", "昵称", "接入码", "好友码", "状态"))
    for r in rows:
        st = "已封禁" if r["banned"] else ("待认领" if r["migrated"] else "正常")
        print("%-4d %-12s %-10s %-10s %s" % (r["id"], r["name"] or "（未命名）",
                                             r["code"] or "—", r["friend_code"] or "—", st))


def cmd_show(ident, full):
    u = find_user(ident)
    s = load(u["id"])
    if full:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return
    h = s["health"]
    hist = s.get("history") or []
    pets = "、".join(s.get("pets") or []) or "—"
    print("账号 id=%d ｜ 昵称：%s ｜ 接入码：%s ｜ 好友码：%s %s"
          % (u["id"], u["name"] or "（未命名）", u["code"] or "—", u["friend_code"] or "—",
             "（已封禁）" if u["banned"] else ""))
    print("等级：Lv%d（lv_idx=%d）｜ 累计经验：%d ｜ 金币：%s（%d 铜）"
          % (s["lv_idx"] + 1, s["lv_idx"], s["exp"], game.fmt_money(s["money"]), s["money"]))
    print("声望：%d ｜ 贡献：%d ｜ 活力点：%d ｜ 精力：%d/%d ｜ 探索点：%d"
          % (s["rep"], s["con"], s["vit"], s["energy"], game.energy_max_now(s), s["explore"]))
    print("材料：%d 种 ｜ 道具：%d 种 ｜ 装备：%d 件 ｜ 图纸：%d 张 ｜ 技能：%s"
          % (len(s.get("mats") or {}), len(s.get("items") or {}), len(s.get("gear") or []),
             len(s.get("blueprints") or {}),
             " ".join("%s%d" % (k, v) for k, v in (s.get("skills") or {}).items())))
    print("宠物：%s ｜ 携带：%s" % (pets, s.get("carry_pet") or "—"))
    print("健康：已记录 %d 天 ｜ 昨日 %s 分 ｜ 今日打卡 %d/7 ｜ 称号 %d ｜ 成就 %d"
          % (len(hist), (hist[-1].get("score", "?") if hist else "—"),
             sum(1 for x in h.get("done") or [] if x), len(s.get("titles") or []), len(s.get("achv") or [])))
    print("（加 --全量 可打印整档 JSON；常用数值用「设置」命令改。）")


def cmd_export(ident, path=None):
    u = find_user(ident)
    s = load(u["id"])
    if not path:
        path = str(Path.cwd() / ("存档导出-%s-%s.json" % (u["name"] or u["id"], time.strftime("%Y%m%d-%H%M%S"))))
    Path(path).write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    print("✔ 已导出到：%s" % path)
    print("  （这是“服务端原始格式”；游戏内「导出快照」下载的是驼峰格式——两者都可被「替换」命令读取。）")


def cmd_set(ident, pairs):
    u = find_user(ident)
    s = load(u["id"])
    for p in pairs:
        k, v = fmt_kv(p)
        if k not in SET_KEYS:
            die("不支持直接设置「%s」。可用键：%s\n  （其它键请照《存档修改教程.md》写脚本改。）" % (k, SET_KEYS_TXT))
        lo, hi = SET_KEYS[k]
        if v < lo or (hi is not None and v > hi):
            die("「%s」= %d 超出合理范围（%s）。" % (k, v, ("%d ~ %d" % (lo, hi)) if hi is not None else "≥ %d" % lo))
        s[k] = v
        print("  · %s → %d" % (k, v))
    save(u["id"], s, "设置")


def cmd_add_dict(ident, pairs, which):
    table = {"材料": game.M, "道具": game.ITEM_DESC}[which]
    u = find_user(ident)
    s = load(u["id"])
    bag = s.setdefault("mats" if which == "材料" else "items", {})
    for p in pairs:
        name, qty = fmt_kv(p)
        if name not in table:
            die("「%s」不在%s表里，名字要写准确（材料见 数据表/材料总表.csv）。" % (name, which))
        bag[name] = bag.get(name, 0) + qty
        if bag[name] <= 0:
            del bag[name]
            print("  · %s 扣光（已移除）" % name)
        else:
            print("  · %s %s%d（现有 %d）" % (name, "+" if qty >= 0 else "", qty, bag[name]))
    save(u["id"], s, "加" + which)


def cmd_gear(ident, name, slot=None):
    g = game.gear_def(name)
    if not g:
        die("「%s」不在装备表里（名称见 数据表/装备总表.csv）。" % name)
    if slot and slot not in SLOT_ALIAS:
        die("槽位只能是：武器 / 护甲 / 饰品 / 护符。")
    u = find_user(ident)
    s = load(u["id"])
    if name in (s.get("gear") or []):
        print("  · 已拥有「%s」（装备同名唯一，不重复添加）" % name)
    else:
        s.setdefault("gear", []).append(name)
        print("  · 获得「%s」（%s）" % (name, g[2]))
    if slot:
        key = SLOT_ALIAS[slot]
        if SLOT_BY_GEAR.get(g[2]) != key:
            die("「%s」是「%s」类装备，不能装到「%s」位上。" % (name, g[2], slot))
        s.setdefault("equipped", {})[key] = name
        print("  · 已切换到该槽位（%s）" % key)
    save(u["id"], s, "加装备")


def cmd_pet(ident, name, carry=False):
    if name != "小狼" and name not in game.PET_LINES:
        die("「%s」不在宠物表里。可养：小狼 / %s" % (name, " / ".join(game.PET_LINES.keys())))
    u = find_user(ident)
    s = load(u["id"])
    if name not in (s.get("pets") or []):
        s.setdefault("pets", []).append(name)
        print("  · 获得「%s」" % name)
    else:
        print("  · 已拥有「%s」" % name)
    if name == "小狼":
        if not s.get("wolf"):
            s["wolf"] = {"stage": 1, "growth": 0, "mutate": 0, "fedDate": "", "fedCount": 0}
            print("  · 小狼成长数据已初始化（一阶）")
    else:
        pd = s.setdefault("pet_data", {})
        if name not in pd:
            pd[name] = {"stage": 1, "growth": 0, "mutate": 0, "fedDate": "", "fedCount": 0}
            print("  · 成长数据已初始化（一阶）")
    if carry:
        s["carry_pet"] = name
        print("  · 已设为当前携带伙伴")
    save(u["id"], s, "加宠物")


def cmd_replace(ident, path):
    u = find_user(ident)
    old = load(u["id"])
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception as e:
        die("读取 / 解析 JSON 失败：%s" % e)
    s2 = game.import_save_state(obj)     # 兼容 驼峰（游戏导出快照）与 蛇形（本工具导出）两种格式；自动补全缺失字段
    if s2 is None:
        die("这个文件不是有效的存档 JSON。")
    if not s2.get("name"):
        s2["name"] = old.get("name", "")
    save(u["id"], s2, "整档替换")
    print("  提示：替换会以文件内容为准（含名字）；开始进行中的队列会被清空，属正常。")


def usage():
    print(__doc__)


# ══════════════ 交互式改档菜单（v1.69） ══════════════
# 无参数运行 = 进菜单；带参数 = 命令行用法（老行为不变）。
# 改档逻辑全在 devops.py：在线（服务在跑 → 本机 /admin/dev）与离线（直接读写库）共用同一套操作函数。
HOST, PORT = "127.0.0.1", 5899
_BAR = "─" * 64


def _server_up():
    try:
        with socket.create_connection((HOST, PORT), timeout=0.6):
            return True
    except OSError:
        return False


def _admin_token():
    try:
        return (Path(__file__).resolve().parent / "admin_token.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _api(op, uid, args):
    """在线：调本机 /admin/dev（服务端在自己的锁内结算 + 写档 + 自动备份）"""
    body = json.dumps({"uid": uid, "op": op, "args": args}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request("http://%s:%d/admin/dev" % (HOST, PORT), data=body,
                                 headers={"Content-Type": "application/json; charset=utf-8",
                                          "X-Admin-Token": _admin_token()})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _ask(prompt, default=""):
    t = input(prompt).strip()
    return t if t else default


def _read_text(p):
    try:
        return Path(p).read_text(encoding="utf-8-sig")
    except Exception as e:
        print("  ✘ 读文件失败：%s" % e)
        return None


def _brief(uid):
    """一行现状摘要（直接读库，只读不改；服务在跑时读也安全）"""
    raw, bad = db.load_user_state(uid)
    if bad:
        return "（存档损坏，见 data/corrupt/）"
    if not raw:
        return "（空档）"
    s = game.migrate_state(raw)
    return "Lv%d ｜ 金币 %s ｜ 声望 %d ｜ 委托栏 %d 条" % (
        s.get("lv_idx", 0) + 1, game.fmt_money(s.get("money", 0)),
        s.get("rep", 0), len(s.get("pool") or []))


def _pick_user():
    rows = db.list_users()
    if not rows:
        print("（还没有任何账号——先在游戏里注册 / 创建角色）")
        return None
    print()
    print("  %-3s %-4s %-14s %-10s %s" % ("序", "id", "昵称", "接入码", "状态"))
    for i, r in enumerate(rows, 1):
        st = "已封禁" if r["banned"] else ("待认领" if r["migrated"] else "正常")
        print("  %-3d %-4d %-14s %-10s %s"
              % (i, r["id"], r["name"] or "（未命名）", r["code"] or "—", st))
    while True:
        t = _ask("\n选账号（序号 / id / 昵称；q 退出）：")
        if t.lower() == "q":
            return None
        if t.isdigit():
            n = int(t)
            for i, r in enumerate(rows, 1):
                if i == n or r["id"] == n:
                    return r
        low = t.casefold()
        for r in rows:
            if (r["name"] or "").casefold() == low:
                return r
        print("  没找到——输入上面的序号或 id。")


def _do_op(uid, opname, args, online):
    """执行一次改档（失败只提示、不中断菜单）"""
    if online:
        try:
            r = _api(opname, uid, args)
        except Exception as e:
            print("  ✘ 在线调用失败：%s" % e)
            print("    （服务可能刚被关掉——回主菜单按 [m] 切离线模式）")
            return
        if r.get("ok"):
            print("  ✔ " + str(r.get("msg") or "完成"))
        else:
            print("  ✘ " + str(r.get("error")))
        for m in (r.get("msgs") or []):
            print("    · " + str(m))
        if r.get("backup"):
            print("    备份：data/backups/" + str(r["backup"]))
        return
    if _server_up():                       # 兜底：进菜单后又把服务打开了
        print("  ⚠ 服务正在运行——离线写档会被它覆盖，已中止。")
        print("    回主菜单按 [m] 切在线模式，或先停服（停止服务.bat）。")
        return
    s = load(uid)
    try:
        msg = devops.run_op(s, opname, **args)
    except devops.OpError as e:
        print("  ✘ %s（未写入）" % e)
        return
    save(uid, s, "改档·" + opname)
    print("  ✔ " + str(msg))


def _rollback(uid, online):
    d = Path(db.DB_PATH).parent / "backups"
    files = sorted(d.glob("manual-user%d-*.json" % uid), reverse=True)[:12] if d.is_dir() else []
    if not files:
        print("  没有该账号的自动备份（每次写入前会自动存一份，改过一次就有了）。")
        return
    print("  最近的自动备份（新 → 旧）：")
    for i, f in enumerate(files, 1):
        print("   [%2d] %s" % (i, f.name))
    t = _ask("  选序号回滚（回车取消）：")
    if not t.isdigit() or not (1 <= int(t) <= len(files)):
        return
    txt = _read_text(files[int(t) - 1])
    if txt is None:
        return
    print("  说明：回滚 = 拿这份备份整档覆盖当前档；当前档也会先自动备份一份，随时能再滚回来。")
    if _ask("  确认回滚？(y/N)：").lower() not in ("y", "yes", "是"):
        print("  已取消。")
        return
    _do_op(uid, "raw_replace", {"json": txt}, online)


def _menu_account(uid, online):
    while True:
        print()
        print(_BAR)
        print(" 账号：查看 / 导出 / 整档替换 / 备份回滚（账号 #%d）" % uid)
        print(_BAR)
        print("  [1] 数值摘要          [2] 全量 JSON（打印整档）")
        print("  [3] 导出到文件        [4] 整档替换（用 JSON 文件覆盖）")
        print("  [5] 回滚到某次自动备份（manual-user%d-*.json）" % uid)
        print("  [0] 返回")
        t = _ask("选择：").lower()
        if t in ("", "0", "q"):
            return
        if t == "1":
            cmd_show(str(uid), False)
        elif t == "2":
            cmd_show(str(uid), True)
        elif t == "3":
            cmd_export(str(uid), _ask("  保存到（回车 = 自动命名）：") or None)
        elif t == "4":
            p = _ask("  JSON 文件路径（回车取消）：")
            if p:
                txt = _read_text(p)
                if txt is not None:
                    _do_op(uid, "raw_replace", {"json": txt}, online)
        elif t == "5":
            _rollback(uid, online)
        else:
            print("  没有这个选项。")


def _menu_group(uid, gname, items, online):
    while True:
        print()
        print(_BAR)
        print(" %s（共 %d 项）" % (gname, len(items)))
        print(_BAR)
        for i, (_, meta) in enumerate(items, 1):
            print("  [%2d] %s" % (i, meta["label"]))
        print("  [ 0] 返回")
        t = _ask("选操作：")
        if t in ("", "0", "q"):
            return
        if not t.isdigit() or not (1 <= int(t) <= len(items)):
            print("  输入 1 ~ %d 的数字。" % len(items))
            continue
        opname, meta = items[int(t) - 1]
        if opname == "set":                # 数值类：先把字段清单摆出来（免得逐个试）
            print("  可用字段（可设范围见括号）：")
            for k, (lo, hi, desc) in devops.SET_KEYS.items():
                print("    %-14s %s%s" % (k, desc, "" if hi is None else "，最大 %s" % hi))
        args = {}
        for key, hint, dflt in meta["args"]:
            lab = "  " + hint + ("（回车 = %s）" % dflt if dflt != "" else "（可留空）")
            args[key] = _ask(lab + "：", dflt)
        _do_op(uid, opname, args, online)


def cmd_menu():
    online = _server_up()
    pinned = False                          # 用户手动按过 [m] → 不再自动跟随服务状态
    print("=" * 64)
    print(" 存档工具 · 交互模式（v1.69）")
    print("=" * 64)
    print(" 一行命令的老用法照旧，例如：python 存档工具.py 设置 昵称 money=1000000")
    groups = devops.op_list()
    gnames = sorted(groups)
    uid, uname = None, ""
    while True:
        if uid is None:
            u = _pick_user()
            if u is None:
                return
            uid, uname = u["id"], (u["name"] or "（未命名）")
        print()
        print(_BAR)
        print(" 账号 #%d「%s」 ｜ %s" % (uid, uname, _brief(uid)))
        print(" 模式：%s" % ("在线（服务在跑 → 改完即时生效，游戏里能看到）" if online
                            else "离线（服务未启动 → 改完启动游戏生效）"))
        print(_BAR)
        for i, gn in enumerate(gnames, 1):
            print("  [%d] %s（%d 项）" % (i, gn, len(groups[gn])))
        print("  [a] 账号：查看 / 导出 / 整档替换 / 回滚备份")
        print("  [s] 换账号     [m] 切换 在线·离线     [q] 退出")
        t = _ask("选择：").lower()
        if t in ("q", "quit", "exit"):
            return
        if t == "a":
            _menu_account(uid, online)
        elif t == "s":
            uid = None
        elif t == "m":
            online, pinned = (not online), True
            print("  → 已切到%s模式。" % ("在线" if online else "离线"))
        elif t.isdigit() and 1 <= int(t) <= len(gnames):
            _menu_group(uid, gnames[int(t) - 1], groups[gnames[int(t) - 1]], online)
        else:
            print("  没有这个选项。")
        if not pinned:                      # 自动跟随：服务刚启动 / 刚关闭时提醒并切换
            now = _server_up()
            if now != online:
                online = now
                print("  （检测到服务%s → 已自动切到%s模式）"
                      % ("已启动" if now else "已关闭", "在线" if now else "离线"))


def main():
    args = [a for a in sys.argv[1:] if a != "--强制"]
    if not args:
        try:
            cmd_menu()
        except (KeyboardInterrupt, EOFError):
            print("\n已退出。")
        return
    act, rest = args[0], args[1:]
    if act == "列表" and not rest:
        cmd_list()
        return
    if act in ("设置", "加材料", "加道具", "加装备", "加宠物", "替换"):
        check_server()          # 只有写入类命令要求先停服；查看 / 导出 是只读的、随时可用
    if act == "查看" and rest:
        full = "--全量" in rest
        rest = [a for a in rest if a != "--全量"]
        cmd_show(rest[0], full)
    elif act == "导出" and rest:
        cmd_export(rest[0], rest[1] if len(rest) > 1 else None)
    elif act == "设置" and len(rest) >= 2:
        cmd_set(rest[0], rest[1:])
    elif act == "加材料" and len(rest) >= 2:
        cmd_add_dict(rest[0], rest[1:], "材料")
    elif act == "加道具" and len(rest) >= 2:
        cmd_add_dict(rest[0], rest[1:], "道具")
    elif act == "加装备" and len(rest) >= 2:
        cmd_gear(rest[0], rest[1], rest[2] if len(rest) > 2 else None)
    elif act == "加宠物" and len(rest) >= 2:
        cmd_pet(rest[0], rest[1], carry=("携带" in rest[2:]))
    elif act == "替换" and len(rest) >= 2:
        cmd_replace(rest[0], rest[1])
    else:
        usage()


if __name__ == "__main__":
    main()
