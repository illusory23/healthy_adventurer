# -*- coding: utf-8 -*-
"""《健康的冒险者的一天》· Flask 服务（端口 5899）

运行：python app.py
  - 电脑浏览器：http://localhost:5899
  - 手机（同一 WiFi）：http://电脑IP:5899
"""
import logging
import secrets
import socket
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, jsonify, request, redirect, g
from werkzeug.exceptions import HTTPException

import db
import game

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024        # v1.39（B7）：请求体上限 4MB（防超大 JSON 拖垮）

# ══════════════ 访问口令门（远程访问保护 · v1.26）══════════════
# 手机经樱花内网穿透等公网方式访问时，须先输入访问口令（本机 localhost 免输）。
# 口令保存在同目录 access_key.txt；首运行自动生成，改动后重启服务生效。
KEY_FILE = Path(__file__).parent / "access_key.txt"


def _load_access_key():
    if KEY_FILE.exists():
        k = KEY_FILE.read_text(encoding="utf-8").strip()
        if k:
            return k
    k = secrets.token_urlsafe(9)
    KEY_FILE.write_text(k, encoding="utf-8")
    return k


ACCESS_KEY = _load_access_key()

GATE_HTML = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>访问验证 · 健康的冒险者的一天</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       background:#12121a;color:#e8e8f0;font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
  .box{background:#1b1b26;border:1px solid #2c2c3a;border-radius:14px;padding:30px 26px;width:300px;text-align:center}
  h1{font-size:16px;color:#d9b160;margin:0 0 8px}
  p{font-size:12px;color:#8a8aa0;margin:0 0 18px;line-height:1.7}
  input{width:100%;box-sizing:border-box;padding:11px;border-radius:9px;border:1px solid #2c2c3a;
        background:#12121a;color:#e8e8f0;font-size:15px;text-align:center;letter-spacing:2px}
  button{width:100%;margin-top:14px;padding:11px;border-radius:9px;border:none;background:#d9b160;
         color:#17171f;font-weight:700;font-size:14px;cursor:pointer}
  .err{color:#d97f7f;font-size:12.5px;margin-top:12px}
</style></head>
<body>
<form class="box" method="post" action="/gate">
  <h1>🌙 健康的冒险者的一天</h1>
  <p>请输入访问口令<br>（保存在电脑上 Flask版/access_key.txt）</p>
  <input name="k" type="password" placeholder="访问口令" autofocus autocomplete="current-password">
  <button type="submit">进入</button>
  <!--ERR-->
</form>
</body></html>"""


def _is_local_host():
    """本机直连豁免（v1.39 A1 加固，防 Host 头伪造绕过口令）——三项须同时成立：
       ① TCP 来源是回环地址；② Host 头是本机名；③ 不带 X-Forwarded-For（隧道/反代会带）。
       任一项不满足 → 按远程对待（须口令）。"""
    addr = (request.remote_addr or "").strip()
    if addr not in ("127.0.0.1", "::1"):
        return False
    if request.headers.get("X-Forwarded-For"):
        return False
    h = (request.host or "").lower()
    if h.startswith("["):                          # IPv6 形如 [::1]:5899
        h = h[1:].split("]")[0]
    else:
        h = h.split(":")[0]
    return h in ("localhost", "127.0.0.1", "::1")


def _grant(resp):
    resp.set_cookie("gp_key", ACCESS_KEY, max_age=90 * 86400, httponly=True, samesite="Lax")
    return resp


# ══════════════ 账号（v1.37：设备静默登录 + 接入码换绑）══════════════
# 每台设备首次访问自动建独立账号（令牌写 Cookie，1 年）；跨设备用 8 位接入码绑定切换；
# 旧版单存档由本机（localhost）首次访问自动认领。

def _current_user():
    """解析当前设备账号：令牌 → 已有账号；否则本机认领旧档 / 静默新建"""
    u = db.get_user_by_token(request.cookies.get("gp_uid"))
    if u:
        db.touch_login(u["id"])
        return u
    if _is_local_host():
        u = db.find_unclaimed_migrated()        # 旧版存档 → 本机首次访问认领
        if u:
            db.claim_user(u["id"])
            g.new_token = u["token"]
            return u
    u = db.create_user()
    g.new_token = u["token"]
    return u


@app.after_request
def _persist_device(resp):
    t = getattr(g, "new_token", None)
    if t:
        resp.set_cookie("gp_uid", t, max_age=365 * 86400, httponly=True, samesite="Lax")
    return resp


_last_backup_date = None


_last_prune_date = None


def _maybe_prune():
    """v1.39b（E4）：每日一次 event_log 治理（每账号保留最近 2000 条 + 清孤儿行）。
       与备份同频：跨日首个请求触发；失败不记日期，下次请求重试。"""
    global _last_prune_date
    today = time.strftime("%Y-%m-%d")
    if _last_prune_date == today:
        return
    if not db.DB_PATH.exists():
        _last_prune_date = today
        return
    try:
        n = db.prune_event_log()
        if n:
            app.logger.info("event_log 治理：清理 " + str(n) + " 条过期/孤儿日志")
        _last_prune_date = today
    except Exception:
        app.logger.warning("event_log 治理失败（下次请求重试）")


def _maybe_backup(force=False):
    """v1.38：每日自动备份 adventurer.db（滚动保留 14 份；惰性触发，一天一次）。
       v1.39（A3）：仅成功才记日期（失败下次请求自动重试）；启动时 force=True 先备一份。"""
    global _last_backup_date
    today = time.strftime("%Y-%m-%d")
    if not force and _last_backup_date == today:
        return True
    if not db.DB_PATH.exists():                        # 库尚未建立（全新部署首启/测试）→ 无档可备
        _last_backup_date = today
        return True
    try:
        ok = db.backup_daily()
    except Exception:
        ok = False
    if ok:
        _last_backup_date = today
    else:
        app.logger.warning("每日数据库备份失败（下次请求重试）")
    return bool(ok)


@app.before_request
def _access_gate():
    if request.path in ("/gate", "/favicon.ico"):
        return None
    if not _is_local_host() and request.cookies.get("gp_key") != ACCESS_KEY:
        if request.args.get("k") == ACCESS_KEY:        # 支持 ?k=口令 一次性解锁
            return _grant(redirect(request.path or "/"))
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "gate": True,
                            "error": "访问验证已失效——请刷新页面并输入访问口令"}), 401
        return GATE_HTML
    # 口令门已通过：每日自动备份 + 日志治理 + 解析设备账号（静态资源无需）
    if request.path.startswith("/static/"):
        return None
    _maybe_backup()
    _maybe_prune()
    g.user = _current_user()


@app.post("/gate")
def gate_submit():
    k = (request.form.get("k") or "").strip()
    if k == ACCESS_KEY:
        return _grant(redirect("/"))
    return GATE_HTML.replace("<!--ERR-->", '<div class="err">口令不正确，请重试</div>')


def local_ip():
    try:
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sk.connect(("8.8.8.8", 80))
        ip = sk.getsockname()[0]
        sk.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _dispatch(s, d, msgs):
    """动作分发：返回错误文案（None = 成功）"""
    act = d.get("action", "")

    def i(key, default=0):
        try:
            return int(d.get(key, default))
        except (TypeError, ValueError):
            return default

    if act == "name":
        return game.take_name(s, d.get("name", ""))
    if act == "checkin":
        return game.toggle_task(s, i("idx"), msgs)
    if act == "meal":
        return game.toggle_meal(s, i("idx"), msgs)
    if act == "multi":
        return game.add_multi(s, i("idx"), i("delta", 1), msgs)
    if act == "use_item":
        return game.use_item(s, d.get("name", ""), msgs)
    if act == "gale":
        return game.use_gale(s, i("idx"), msgs)
    if act == "cook":
        return game.cook(s, i("idx"), msgs)
    if act == "buy":
        return game.buy(s, i("idx"), msgs, i("n", 1))
    if act == "buy_vit":
        return game.buy_vit(s, i("idx"), msgs, i("n", 1))
    if act == "buy_con":
        return game.buy_con(s, i("idx"), msgs, i("n", 1), d.get("mat"))
    if act == "buy_plat":                              # v1.50：铂金商店·统一购买（全部铂金币结算）
        return game.buy_plat(s, msgs, i("idx", 0), d.get("mat"))
    if act == "buy_mat":                               # v1.41 H3：交易所买入
        return game.buy_mat(s, d.get("name", ""), msgs)
    if act == "buy_master_gear":                       # v1.41 I6：大师商店·专属装备
        return game.buy_master_gear(s, msgs, i("idx"))
    if act == "buy_master_mat":                        # v1.41 I6：大师商店·指定传说材料
        return game.buy_master_mat(s, msgs, d.get("mat"))
    if act == "buy_master_vit":                        # v1.41 I6：大师商店·活力点
        return game.buy_master_vit(s, msgs)
    if act == "sell":
        return game.sell_mat(s, d.get("name", ""), d.get("cnt"))
    if act == "sell_all":
        return game.sell_all(s, msgs)
    if act == "equip":
        return game.equip_item(s, d.get("name", ""), msgs)
    if act == "unequip":
        return game.unequip(s, d.get("slot", ""), msgs)
    if act == "craft":
        return game.craft(s, d.get("name", ""), msgs)
    if act == "craft_item":                            # v1.46：炼金台合成（任务准备物）
        return game.craft_item(s, d.get("name", ""), msgs)
    if act == "blueprint":
        return game.buy_blueprint(s, d.get("name", ""), msgs)
    if act == "skill":
        return game.up_skill(s, d.get("name", ""), msgs)
    if act == "charm":
        return game.buy_charm(s, msgs)
    if act == "sick_leave":                            # v1.60：医务室·病假（今日 / 补请昨日）
        return game.take_sick_leave(s, d.get("day", "today"), msgs)
    if act == "feed_wolf":
        return game.feed_wolf(s, d.get("name", ""), msgs)
    if act == "evolve_wolf":
        return game.evolve_wolf(s, msgs)
    if act == "feed_pet":                             # v1.35：宠物养成
        return game.feed_pet(s, d.get("name", ""), d.get("food", ""), msgs)
    if act == "evolve_pet":
        return game.evolve_pet(s, d.get("name", ""), msgs)
    if act == "pet_pat":                              # v1.56：抚摸（每日 1 次）
        return game.pet_pat(s, d.get("name", ""), msgs)
    if act == "pet_walk":                             # v1.56：派宠物去散步
        return game.pet_walk_start(s, d.get("name", ""), msgs)
    if act == "pet_nick":                             # v1.56：宠物昵称
        return game.set_pet_nick(s, d.get("name", ""), d.get("nick", ""), msgs)
    if act == "accept":
        return game.accept_quest(s, i("idx"), msgs, d.get("name"), d.get("point"))   # v1.50：池身份校验
    if act == "accept_bonus":
        return game.accept_bonus(s, i("idx", 0), msgs)
    if act == "accept_priv":                       # v1.38o：W 级公会特权委托
        return game.accept_priv(s, msgs)
    if act == "accept_glass":                      # v1.38o：时间沙漏委托
        return game.accept_glass(s, msgs)
    if act == "abandon":
        return game.abandon_quest(s, i("idx"), d.get("name"))
    if act == "explore":
        return game.do_explore(s, i("idx"), msgs)
    if act == "explore_return":
        return game.explore_return(s, msgs)
    if act == "explore_ack":
        s["explore_result"] = None
        return None
    if act == "explore_choice":
        return game.explore_choice(s, bool(i("accept")), msgs)
    if act == "event_ack":
        s["event_result"] = None
        return None
    if act == "take_legend":
        return game.take_legend(s, msgs)
    if act == "results_ack":
        s["results"] = []
        s["levelups"] = []                # v1.38r：升级详情队列（UI 已消费）
        s["pending_rare"] = []
        s["pending_legend"] = None
        return None
    if act == "yesterday_ack":
        s["yesterday_shown"] = True
        return None
    if act == "festival_ack":
        s["pending_festival"] = None      # v1.41d：节日欢迎弹窗已展示
        return None
    if act == "set_carry_pet":                         # v1.38f：携带宠物切换
        return game.set_carry_pet(s, d.get("name") or "", msgs)
    if act == "import_save":                           # v1.38d：存档互通（camel → snake）
        s2 = game.import_save_state(d.get("data"))
        if s2 is None:
            return "导入文件格式不正确（需要存档 JSON）"
        s.clear()
        s.update(s2)
        msgs.append("📂 已导入存档：" + (s2.get("name") or "未命名"))
        return None
    if act == "reset":
        s.clear()
        s.update(game.new_state())
        return None
    return "未知操作：" + str(act)


_HISTORY_SEND = 150          # v1.39（C3）：下发 history 条数上限（全量在库；导出走 export_save）


def _payload(s, msgs, err=None, user=None):
    # v1.35：图鉴·材料"曾获得"懒合并（当前持有的材料一律计入）
    if "seen_mats" not in s:
        s["seen_mats"] = []
    for k in list(s.get("mats", {}).keys()):
        if k not in s["seen_mats"]:
            s["seen_mats"].append(k)
    # v1.38s：道具"曾获得"懒合并（探索详情保密；旧宝箱由探索结算另行记录）
    if "seen_items" not in s:
        s["seen_items"] = []
    for k in list(s.get("items", {}).keys()):
        if k not in s["seen_items"]:
            s["seen_items"].append(k)
    # v1.39（C3）：瘦身——history 仅下发近 _HISTORY_SEND 条（前端消费窗口最长 30 天）；
    # 全量天数与成就计数以派生字段随包走；完整 history 仍在库、可 export_save 全量导出
    hs = s.get("history") or []
    view = dict(s)
    view["history_total"] = len(hs)
    view["hist_stats"] = {
        "sleep": sum(1 for h in hs if h.get("sleep")),
        "early": sum(1 for h in hs if h.get("tasks") and h["tasks"][1]),
        "sport": sum(1 for h in hs if h.get("tasks") and h["tasks"][4]),
        "read":  sum((h.get("multi") or [0, 0])[1] for h in hs),
    }
    if len(hs) > _HISTORY_SEND:
        view["history"] = hs[-_HISTORY_SEND:]
    acc = None
    if user:
        acc = {"code": user.get("code", ""), "created": user.get("created_at", 0)}
    return jsonify({
        "ok": err is None,
        "error": err,
        "msgs": msgs,
        "state": view,
        "account": acc,
    })


@app.route("/")
def index():
    # 前端 = 原型的完整界面（static/game.html），数据经 /api/* 由服务端驱动
    return app.send_static_file("game.html")


def _load(uid, msgs=None):
    """读档（自动迁移补全）。v1.39（A4）：若存档 JSON 损坏 → 原文已另存 data/corrupt/，
       返回新档并向玩家提示（msgs 传入时追加警告；不再静默重置）"""
    raw, corrupted = db.load_user_state(uid)
    s = game.migrate_state(raw) if raw else game.new_state()
    if corrupted and msgs is not None:
        msgs.append("⚠️ 存档数据损坏：原档已另存 data/corrupt/（未删除），当前已重置为新档——"
                    "如需恢复请联系开发者用原档修复")
    return s


# v1.50：per-账号互斥锁——防并发请求（双开/连点）读到同档相互覆盖（丢更新）
_locks = {}
_locks_guard = threading.Lock()


def _lock_for(uid):
    with _locks_guard:
        lk = _locks.get(uid)
        if lk is None:
            lk = threading.Lock()
            _locks[uid] = lk
        return lk


def _norm_code(txt):
    return "".join(ch for ch in str(txt or "").upper() if ch.isalnum())


def _bind_code(d):
    """接入码换绑（v1.37）：本设备切换到目标账号；当前若是没动过的空档则顺手清理"""
    u = g.user
    u2 = db.get_user_by_code(_norm_code(d.get("code")))
    if not u2:
        return _payload(_load(u["id"]), [], "接入码不正确——请核对「冒险者信息 → 账号」里的 8 位码", u)
    if u2["id"] == u["id"]:
        return _payload(_load(u["id"]), ["已经就是本账号，无需绑定"], None, u)
    with _lock_for(u2["id"]):                      # v1.50：并发互斥
        db.delete_user_if_fresh(u["id"])
        db.claim_user(u2["id"])
        g.new_token = u2["token"]
        msgs = []
        s = _load(u2["id"], msgs)
        msgs += game.catch_up(s) + ["🔑 已绑定账号「" + (u2["name"] or "未命名") + "」"]
        db.flush_event_log(s, u2["id"])            # v1.50：先 flush（更新水位）再 save（水位落库）
        db.save_user_state(u2["id"], s)
        return _payload(s, msgs, None, u2)


@app.get("/api/state")
def api_state():
    u = g.user
    with _lock_for(u["id"]):                       # v1.50：并发互斥
        msgs = []
        s = _load(u["id"], msgs)
        msgs += game.catch_up(s)
        db.flush_event_log(s, u["id"])             # v1.50：先 flush（更新水位）再 save（水位落库）
        db.save_user_state(u["id"], s)
        return _payload(s, msgs, None, u)


@app.post("/api/action")
def api_action():
    d = request.get_json(force=True, silent=True) or {}
    act = d.get("action")
    if act == "bind_code":                             # v1.37：接入码换绑
        return _bind_code(d)
    u = g.user
    if act == "export_save":
        # v1.39（C3）：全量存档导出——状态下发已瘦身（history 截近 150 条），导出接口不受影响；
        # 只读不结算不落库（无副作用）；返回 snake 原始档，前端 adaptState 转 camel 后下载
        return jsonify({"ok": True, "error": None, "save": _load(u["id"])})
    msgs = []
    with _lock_for(u["id"]):                       # v1.50：并发互斥
        s = _load(u["id"], msgs)
        msgs += game.catch_up(s)
        err = _dispatch(s, d, msgs)
        db.flush_event_log(s, u["id"])             # v1.50：先 flush（更新水位）再 save（水位落库）
        db.save_user_state(u["id"], s)
        return _payload(s, msgs, err, u)


@app.get("/api/accounts")
def api_accounts():
    """本机账号管理面板数据（仅 localhost 可见）"""
    if not _is_local_host():
        return jsonify({"ok": False, "error": "账号管理仅本机（localhost）可查看"}), 403
    return jsonify({"ok": True, "accounts": db.list_users()})


@app.post("/api/accounts/delete")
def api_accounts_delete():
    """删除账号（仅 localhost）：body {"id": N}——账号与其事件日志一并清除，不可恢复"""
    if not _is_local_host():
        return jsonify({"ok": False, "error": "账号管理仅本机（localhost）可用"}), 403
    d = request.get_json(force=True, silent=True) or {}
    try:
        uid = int(d.get("id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "参数不正确"}), 400
    ok = db.delete_user(uid)
    return jsonify({"ok": ok, "error": None if ok else "账号不存在",
                    "accounts": db.list_users()})


@app.get("/api/logs")
def api_logs():
    return jsonify({"logs": db.recent_logs(g.user["id"], 120)})


@app.errorhandler(Exception)
def _handle_uncaught(e):
    """v1.39（A5）：未捕获异常——/api/ 路径回 JSON（前端弹提示），其余按 HTTP 错误处理；
       非 HTTP 异常写入 logs/server.log（v1.39 B8）"""
    if isinstance(e, HTTPException):
        if request.path.startswith("/api/"):
            msg = "上传内容过大（上限 4MB）" if e.code == 413 else (e.description or e.name)
            return jsonify({"ok": False, "error": msg, "state": None}), e.code
        return e
    app.logger.exception("未捕获异常 %s %s", request.method, request.path)
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "服务器内部错误（已记录到 logs/server.log）",
                        "state": None}), 500
    return "服务器内部错误（已记录到 logs/server.log）", 500


def _setup_logging():
    """v1.39（B8）：服务日志 → logs/server.log（2MB × 5 滚动，utf-8），排障用"""
    try:
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(str(log_dir / "server.log"), maxBytes=2 * 1024 * 1024,
                                backupCount=5, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        app.logger.addHandler(h)
        app.logger.setLevel(logging.INFO)
        logging.getLogger("waitress").setLevel(logging.WARNING)   # 避免每请求一行刷满日志
    except Exception:
        pass


if __name__ == "__main__":
    _setup_logging()
    bak_ok = _maybe_backup(force=True)                 # v1.39（A3）：启动先备一份当日档
    ip = local_ip()
    print("=" * 52)
    print("  《健康的冒险者的一天》服务已启动")
    print("  电脑浏览器：http://localhost:5899")
    print("  手机访问  ：http://" + ip + ":5899  （同一 WiFi）")
    print("  远程访问口令：" + ACCESS_KEY)
    print("  （手机首次访问时输入一次；保存在 access_key.txt，改动后重启生效）")
    print("  账号：每台设备首次访问自动创建独立账号；跨设备用「冒险者信息 → 账号」的接入码找回")
    print("  今日数据库备份：" + ("已就绪（data/backups/，保留最近 14 份）" if bak_ok
                              else "❌ 失败——请检查 data/backups 目录是否可写"))
    print("=" * 52)
    try:
        from waitress import serve                    # v1.39（B3）：生产级 WSGI 引擎（原 Werkzeug 开发服）
        app.logger.info("waitress 启动 0.0.0.0:5899（threads=8）")
        serve(app, host="0.0.0.0", port=5899, threads=8)
    except ImportError:
        print("  （未安装 waitress：pip install waitress 后体验更稳；当前回退开发服务器）")
        app.run(host="0.0.0.0", port=5899, debug=False)
