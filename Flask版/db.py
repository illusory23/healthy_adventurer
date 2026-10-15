# -*- coding: utf-8 -*-
"""SQLite 持久化：账号表（每设备/每人独立存档）+ 事件日志表

v1.37：单存档 → 多账号
  - users 表：一行 = 一个账号；首次访问静默建号（设备令牌 Cookie 自动登录），
    跨设备用 8 位「接入码」绑定切换
  - 旧版单行 player 表（id=1）自动迁入 users（migrated=1，等本机首次访问认领）；
    player 表保留作原始备份，此后不再读写
v1.62（社交 P0）：邀请码注册 + 好友码 + 封禁
  - invite_codes 表：服主在 /admin 生成，远程新设备须凭码注册（本机免码）
  - users 新增 friend_code（好友码，独立于接入码，仅社交用途）与 banned（封禁）
  - 服务器所在电脑（localhost）保持免注册直通；昵称唯一性由 name_taken 校验
"""
import json
import secrets
import sqlite3
import time
import shutil
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "adventurer.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS player (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  name TEXT NOT NULL DEFAULT '',
  exp INTEGER NOT NULL DEFAULT 0,
  rep INTEGER NOT NULL DEFAULT 0,
  money INTEGER NOT NULL DEFAULT 0,
  lv_idx INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL DEFAULT 0,
  data TEXT NOT NULL              -- 完整状态 JSON（背包/历史/日志等）
);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL DEFAULT '',
  token TEXT NOT NULL UNIQUE,            -- 设备令牌（Cookie 自动登录）
  code TEXT NOT NULL UNIQUE,             -- 接入码（8 位，信息页展示 / 跨设备绑定；＝账号钥匙，勿外传）
  friend_code TEXT NOT NULL DEFAULT '',  -- v1.62：好友码（8 位，仅社交用途，独立于接入码，可重置）
  migrated INTEGER NOT NULL DEFAULT 0,   -- 1 = 旧版存档迁移而来（等待本机认领）
  banned INTEGER NOT NULL DEFAULT 0,     -- v1.62：封禁（1 = 拒入，服主工具）
  created_at INTEGER NOT NULL DEFAULT 0,
  last_login INTEGER NOT NULL DEFAULT 0, -- 0 = 从未被登录/认领
  data TEXT NOT NULL DEFAULT '{}'        -- 完整状态 JSON
);
CREATE TABLE IF NOT EXISTS invite_codes (
  code TEXT PRIMARY KEY,                 -- v1.62：邀请码（8 位，与接入码/好友码独立命名空间）
  uses_total INTEGER NOT NULL DEFAULT 5, -- 该码可注册的总次数
  uses_left INTEGER NOT NULL DEFAULT 5,  -- 剩余可用次数
  created_at INTEGER NOT NULL DEFAULT 0,
  expires_at INTEGER NOT NULL DEFAULT 0, -- 0 = 不过期
  revoked INTEGER NOT NULL DEFAULT 0,    -- 1 = 服主吊销
  note TEXT NOT NULL DEFAULT ''          -- 备注（发给谁等）
);
CREATE TABLE IF NOT EXISTS event_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  cls TEXT NOT NULL DEFAULT '',
  user_id INTEGER NOT NULL DEFAULT 0,
  msg TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_log_uid ON event_log(user_id, id);   -- v1.39b（E4）：按账号取最近日志加速
"""

# v1.64（社交 P1）：好友 / 申请 / 拉黑 / 邮件（赠送与货款共同底座）——旧库升级经 _ensure_columns 执行
_SOCIAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS friend_edge (
  a INTEGER NOT NULL, b INTEGER NOT NULL, created_at INTEGER NOT NULL DEFAULT 0,  -- 双向各一行（a→b 与 b→a）
  PRIMARY KEY (a, b)
);
CREATE TABLE IF NOT EXISTS friend_req (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  from_uid INTEGER NOT NULL, to_uid INTEGER NOT NULL,
  msg TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',   -- pending / accepted / rejected
  created_at INTEGER NOT NULL DEFAULT 0, handled_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_friend_req_to ON friend_req(to_uid, status);
CREATE INDEX IF NOT EXISTS idx_friend_req_from ON friend_req(from_uid, status);
CREATE TABLE IF NOT EXISTS block_list (
  a INTEGER NOT NULL, b INTEGER NOT NULL, created_at INTEGER NOT NULL DEFAULT 0,  -- a 拉黑 b
  PRIMARY KEY (a, b)
);
CREATE TABLE IF NOT EXISTS mail (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid INTEGER NOT NULL,                     -- 收件人
  kind TEXT NOT NULL DEFAULT 'system',      -- system / gift / proceeds（P3 货款预留）
  from_uid INTEGER NOT NULL DEFAULT 0,      -- 0 = 系统
  title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
  mat TEXT NOT NULL DEFAULT '', qty INTEGER NOT NULL DEFAULT 0, money INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'unread',    -- unread / read / pending / claimed / declined / expired
  created_at INTEGER NOT NULL DEFAULT 0, expire_at INTEGER NOT NULL DEFAULT 0,  -- 0 = 不过期
  handled_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_mail_uid ON mail(uid, id);
"""

# v1.65（社交 P2）：组队副本——offer（当日名额）→ open（组建中）→ running → done / failed
_PARTY_SCHEMA = """
CREATE TABLE IF NOT EXISTS party (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid INTEGER NOT NULL,                     -- 队长（发起人）
  idx INTEGER NOT NULL DEFAULT 0,           -- PARTY 池下标
  tier TEXT NOT NULL DEFAULT '', diff TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'offer',     -- offer / open / running / done / failed / abandoned / expired
  day INTEGER NOT NULL DEFAULT 0,           -- 副本日（yyyymmdd；每日 08:00 换日，当日有效）
  created_at INTEGER NOT NULL DEFAULT 0, expire_at INTEGER NOT NULL DEFAULT 0,   -- 24h 未开启作废
  started_at INTEGER NOT NULL DEFAULT 0, ends_at INTEGER NOT NULL DEFAULT 0,
  goal INTEGER NOT NULL DEFAULT 0, progress INTEGER NOT NULL DEFAULT 0,
  settled INTEGER NOT NULL DEFAULT 0        -- 0/1：结算幂等标记
);
CREATE INDEX IF NOT EXISTS idx_party_uid ON party(uid, id);
CREATE INDEX IF NOT EXISTS idx_party_st ON party(status, expire_at);
CREATE TABLE IF NOT EXISTS party_member (
  party_id INTEGER NOT NULL, uid INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'in',        -- in / quit / refunded（退款成功换状态，语义：该次不再计入周限）
  joined_at INTEGER NOT NULL DEFAULT 0, week0 INTEGER NOT NULL DEFAULT 0,
  rate REAL NOT NULL DEFAULT 0,             -- 接取时锁定的成功率（0~1 分数）
  actions_left INTEGER NOT NULL DEFAULT 0,
  spent INTEGER NOT NULL DEFAULT 0,         -- 已扣精力（退还基准）
  refund INTEGER NOT NULL DEFAULT 0,        -- 1 = 待退还精力（本人下次打开时在其锁内结算）
  reward TEXT NOT NULL DEFAULT '',          -- 结算结果 JSON {"ok":bool,"money":n,"mats":{...}}
  claim TEXT NOT NULL DEFAULT '',           -- '' / pending / claimed
  PRIMARY KEY (party_id, uid)
);
CREATE INDEX IF NOT EXISTS idx_party_member_uid ON party_member(uid, joined_at);
CREATE TABLE IF NOT EXISTS party_invite (
  party_id INTEGER NOT NULL, uid INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',   -- pending / accepted / declined / expired
  created_at INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (party_id, uid)
);
"""

# v1.66（社交 P3）：材料市场——挂单即托管（成交交付 / 下架过期原样退回）
_MARKET_SCHEMA = """
CREATE TABLE IF NOT EXISTS market (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  seller INTEGER NOT NULL, mat TEXT NOT NULL,
  qty INTEGER NOT NULL DEFAULT 0,           -- 当前剩余数量
  price INTEGER NOT NULL DEFAULT 0,         -- 单价（铜）
  status TEXT NOT NULL DEFAULT 'on',        -- on / sold / off / expired
  created_at INTEGER NOT NULL DEFAULT 0, expire_at INTEGER NOT NULL DEFAULT 0,
  sold INTEGER NOT NULL DEFAULT 0,          -- 已卖出数量（展示用）
  off_reason TEXT NOT NULL DEFAULT ''       -- '' / cancel（卖家下架）/ expire（到期下架）
);
CREATE INDEX IF NOT EXISTS idx_market_st ON market(status, id);
CREATE INDEX IF NOT EXISTS idx_market_seller ON market(seller, id);
CREATE TABLE IF NOT EXISTS market_buys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  buyer INTEGER NOT NULL, listing INTEGER NOT NULL,
  qty INTEGER NOT NULL DEFAULT 0, price INTEGER NOT NULL DEFAULT 0,
  ts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_market_buys ON market_buys(buyer, ts);
"""

_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # 去掉易混的 0/O/1/I/L


def _now_ms():
    return int(time.time() * 1000)


def _new_token():
    return secrets.token_urlsafe(24)


def _new_code():
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))


# v1.39（B5）：建表/补列/迁移只跑一次（按库路径缓存）；WAL + busy_timeout 防并发写锁
_init_done_path = None


def conn():
    """打开数据库连接。初始化（建表/补列/迁移）仅每库首次执行；
       启用 WAL（读写并发不互锁）与 busy_timeout（锁等待 5 秒，替代默认"立即报错"）。"""
    global _init_done_path
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    fresh = not DB_PATH.exists()                       # 文件被删后重建 → 强制重跑初始化
    c = sqlite3.connect(str(DB_PATH), timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=5000")
    if fresh or _init_done_path != str(DB_PATH):
        c.execute("PRAGMA journal_mode=WAL")           # 库级持久设置，一次生效
        c.executescript(_SCHEMA)
        _ensure_columns(c)
        _migrate_legacy(c)
        _init_done_path = str(DB_PATH)
    return c


def _ensure_columns(c):
    """旧库平滑升级：event_log 补 user_id 列（v1.37）；v1.50：去重 + 唯一索引（防重复写入）"""
    cols = {r["name"] for r in c.execute("PRAGMA table_info(event_log)").fetchall()}
    if "user_id" not in cols:
        c.execute("ALTER TABLE event_log ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
        c.commit()
    # v1.50：历史重复行清理（保留最小 id）+ 唯一索引——flush 幂等的最终保险
    try:
        row = c.execute("SELECT name FROM sqlite_master WHERE type='index' "
                        "AND name='idx_event_log_dedup'").fetchone()
        if not row:
            c.execute("DELETE FROM event_log WHERE id NOT IN ("
                      "  SELECT MIN(id) FROM event_log GROUP BY user_id, ts, msg)")
            c.execute("CREATE UNIQUE INDEX idx_event_log_dedup ON event_log(user_id, ts, msg)")
            c.commit()
    except sqlite3.Error:
        pass
    # v1.62：users 补 friend_code / banned 列 + 好友码回填 + 唯一性索引（尽力而为）
    ucols = {r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
    if "friend_code" not in ucols:
        c.execute("ALTER TABLE users ADD COLUMN friend_code TEXT NOT NULL DEFAULT ''")
        c.commit()
    if "banned" not in ucols:
        c.execute("ALTER TABLE users ADD COLUMN banned INTEGER NOT NULL DEFAULT 0")
        c.commit()
    # v1.64：社交偏好列（健康分公开 / 赠送权限 / 申请权限）+ 社交表（好友 / 申请 / 拉黑 / 邮件）
    for col, ddl in (("health_public", "INTEGER NOT NULL DEFAULT 0"),
                     ("gift_perm", "TEXT NOT NULL DEFAULT 'friends'"),
                     ("req_perm", "TEXT NOT NULL DEFAULT 'allow'")):
        if col not in ucols:
            c.execute("ALTER TABLE users ADD COLUMN %s %s" % (col, ddl))
            c.commit()
    c.executescript(_SOCIAL_SCHEMA)
    c.executescript(_PARTY_SCHEMA)
    c.executescript(_MARKET_SCHEMA)
    ensure_friend_codes(c)
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_name_uni "
                  "ON users(name COLLATE NOCASE) WHERE name <> ''")
        c.commit()
    except sqlite3.Error:
        pass            # 旧库已有重名 → 放弃索引（新写入仍由 name_taken 拦截）
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_friend "
                  "ON users(friend_code) WHERE friend_code <> ''")
        c.commit()
    except sqlite3.Error:
        pass


def ensure_friend_codes(c=None):
    """v1.62：为缺失好友码的账号补齐（8 位、库内唯一）。旧库升级自动调用；幂等，
       返回本轮补齐数量。传入连接 c 时复用该连接（初始化流程内调用）。"""
    own = c is None
    if own:
        c = conn()
    try:
        existing = {r["friend_code"] for r in
                    c.execute("SELECT friend_code FROM users WHERE friend_code <> ''").fetchall()}
        ids = [r["id"] for r in c.execute("SELECT id FROM users WHERE friend_code = ''").fetchall()]
        for uid in ids:
            for _ in range(60):
                fc = _new_code()
                if fc in existing:
                    continue
                existing.add(fc)
                c.execute("UPDATE users SET friend_code = ? WHERE id = ?", (fc, uid))
                break
        c.commit()
        return len(ids)
    finally:
        if own:
            c.close()


def _migrate_legacy(c):
    """旧版单行存档 → users 首行（仅一次；player 表保留作备份）"""
    n = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if n:
        return
    row = c.execute("SELECT data FROM player WHERE id = 1").fetchone()
    if not row:
        return
    try:
        name = (json.loads(row["data"]) or {}).get("name", "")
    except Exception:
        name = ""
    cur = c.execute(
        "INSERT INTO users (name, token, code, migrated, created_at, last_login, data) "
        "VALUES (?, ?, ?, 1, ?, 0, ?)",
        (name, _new_token(), _new_code(), _now_ms(), row["data"]))
    c.execute("UPDATE event_log SET user_id = ? WHERE user_id = 0", (cur.lastrowid,))
    c.commit()


def _row_to_user(row):
    if not row:
        return None
    return {k: row[k] for k in ("id", "name", "token", "code", "friend_code",
                                "migrated", "banned", "created_at", "last_login",
                                "health_public", "gift_perm", "req_perm")}


def get_user_by_token(token):
    if not token:
        return None
    with closing(conn()) as c:
        return _row_to_user(c.execute("SELECT * FROM users WHERE token = ?", (token,)).fetchone())


def get_user_by_code(code):
    if not code:
        return None
    with closing(conn()) as c:
        return _row_to_user(c.execute("SELECT * FROM users WHERE code = ?", (code,)).fetchone())


def find_unclaimed_migrated():
    """待认领的旧版迁移账号（仅本机首次访问分配）"""
    with closing(conn()) as c:
        return _row_to_user(c.execute(
            "SELECT * FROM users WHERE migrated = 1 AND last_login = 0 ORDER BY id LIMIT 1").fetchone())


def create_user(name=""):
    """新建账号：name 为空 = 旧式空档（本机免注册直通）；v1.62 远程注册时带昵称建号"""
    name = (name or "").strip()
    with closing(conn()) as c:
        for _ in range(30):
            try:
                cur = c.execute(
                    "INSERT INTO users (name, token, code, friend_code, created_at, last_login, data) "
                    "VALUES (?, ?, ?, ?, ?, 0, '{}')",
                    (name, _new_token(), _new_code(), _new_code(), _now_ms()))
                c.commit()
                return _row_to_user(c.execute("SELECT * FROM users WHERE id = ?",
                                              (cur.lastrowid,)).fetchone())
            except sqlite3.IntegrityError:
                continue
    raise RuntimeError("无法生成唯一接入码")


def claim_user(uid):
    """认领/激活账号（清迁移标记 + 记登录时间）"""
    with closing(conn()) as c:
        c.execute("UPDATE users SET migrated = 0, last_login = ? WHERE id = ?", (_now_ms(), uid))
        c.commit()


def touch_login(uid):
    with closing(conn()) as c:
        c.execute("UPDATE users SET last_login = ? WHERE id = ?", (_now_ms(), uid))
        c.commit()


def delete_user_if_fresh(uid):
    """换绑前清理：仅删「完全没动过」的空档（无名字 / 无经验 / 无钱 / 无历史 / 无打卡记录）"""
    with closing(conn()) as c:
        row = c.execute("SELECT name, data FROM users WHERE id = ?", (uid,)).fetchone()
        if not row or row["name"]:
            return False
        try:
            s = json.loads(row["data"]) or {}
        except Exception:
            return False
        if s.get("exp", 0) or s.get("money", 0) or s.get("history"):
            return False
        if any((s.get("health") or {}).get("done", []) or []):
            return False
        c.execute("DELETE FROM users WHERE id = ?", (uid,))
        c.commit()
        return True


def delete_user(uid):
    """本机账号管理（v1.38q2）：删除账号并清除其事件日志（不可恢复）；
       v1.64：同步清理其社交数据（好友边 / 申请 / 拉黑 / 邮件——含他人发给其的待领取邮件）；
       v1.65：清理其副本数据（作为队长的整队一并消失；作为队员的行一并移除）；
       v1.66：清理其市场挂单（在售的行连同托管材料一并删除）"""
    with closing(conn()) as c:
        c.execute("DELETE FROM event_log WHERE user_id = ?", (uid,))
        c.execute("DELETE FROM friend_edge WHERE a = ? OR b = ?", (uid, uid))
        c.execute("DELETE FROM friend_req WHERE from_uid = ? OR to_uid = ?", (uid, uid))
        c.execute("DELETE FROM block_list WHERE a = ? OR b = ?", (uid, uid))
        c.execute("DELETE FROM mail WHERE uid = ? OR (from_uid = ? AND status = 'pending')", (uid, uid))
        c.execute("DELETE FROM market WHERE seller = ?", (uid,))
        _pids = [r["id"] for r in c.execute("SELECT id FROM party WHERE uid = ?", (uid,)).fetchall()]
        for pid in _pids:
            c.execute("DELETE FROM party WHERE id = ?", (pid,))
            c.execute("DELETE FROM party_member WHERE party_id = ?", (pid,))
            c.execute("DELETE FROM party_invite WHERE party_id = ?", (pid,))
        c.execute("DELETE FROM party_member WHERE uid = ?", (uid,))
        c.execute("DELETE FROM party_invite WHERE uid = ?", (uid,))
        cur = c.execute("DELETE FROM users WHERE id = ?", (uid,))
        c.commit()
        return cur.rowcount > 0


def list_users():
    """账号列表（仅供本机账号管理面板 / 社交概览）——不返回 token"""
    with closing(conn()) as c:
        rows = c.execute("SELECT id, name, code, friend_code, migrated, banned, "
                         "health_public, gift_perm, req_perm, "
                         "created_at, last_login FROM users ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def name_taken(name, exclude_id=0):
    """v1.62：昵称是否已被占用（不区分大小写；空名空档不计入）"""
    name = (name or "").strip()
    if not name:
        return False
    with closing(conn()) as c:
        row = c.execute("SELECT id FROM users WHERE name <> '' AND name = ? COLLATE NOCASE "
                        "AND id <> ? LIMIT 1", (name, exclude_id)).fetchone()
        return bool(row)


def reset_friend_code(uid):
    """v1.62：重置好友码（服主工具），返回新码或 None"""
    with closing(conn()) as c:
        existing = {r["friend_code"] for r in
                    c.execute("SELECT friend_code FROM users WHERE id <> ? AND friend_code <> ''",
                              (uid,)).fetchall()}
        for _ in range(60):
            fc = _new_code()
            if fc in existing:
                continue
            cur = c.execute("UPDATE users SET friend_code = ? WHERE id = ?", (fc, uid))
            c.commit()
            return fc if cur.rowcount else None
        return None


def set_banned(uid, flag=True):
    """v1.62：封禁 / 解封（服主工具）"""
    with closing(conn()) as c:
        cur = c.execute("UPDATE users SET banned = ? WHERE id = ?", (1 if flag else 0, uid))
        c.commit()
        return cur.rowcount > 0


# ══════════════ 邀请码（v1.62 · 注册闸门）══════════════

def create_invite_code(uses=5, hours=72, note=""):
    """生成邀请码：uses 次可用、hours 小时有效（0 = 不过期）。返回码或 None"""
    try:
        uses = max(1, int(uses))
        hours = int(hours)
    except (TypeError, ValueError):
        uses, hours = 5, 72
    now = _now_ms()
    expires = now + hours * 3600 * 1000 if hours else 0
    with closing(conn()) as c:
        for _ in range(60):
            code = _new_code()
            try:
                c.execute("INSERT INTO invite_codes (code, uses_total, uses_left, created_at, "
                          "expires_at, note) VALUES (?, ?, ?, ?, ?, ?)",
                          (code, uses, uses, now, expires, (note or "")[:40]))
                c.commit()
                return code
            except sqlite3.IntegrityError:
                continue
    return None


def list_invite_codes():
    with closing(conn()) as c:
        rows = c.execute("SELECT * FROM invite_codes ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def invite_error(code, now_ms=None):
    """只读校验邀请码：None = 可用；否则返回不可用原因（中文）"""
    now = int(now_ms if now_ms is not None else _now_ms())
    code = (code or "").strip().upper()
    if not code:
        return "请输入邀请码。"
    with closing(conn()) as c:
        row = c.execute("SELECT * FROM invite_codes WHERE code = ?", (code,)).fetchone()
    if not row:
        return "邀请码不存在——请核对服主发来的 8 位码。"
    if row["revoked"]:
        return "该邀请码已被服主吊销。"
    if row["expires_at"] and now > row["expires_at"]:
        return "该邀请码已过期，请向服主索取新的邀请码。"
    if row["uses_left"] <= 0:
        return "该邀请码已用完，请向服主索取新的邀请码。"
    return None


def consume_invite(code, now_ms=None):
    """原子消费一次邀请码（校验+扣减一条 SQL）。返回 True = 扣减成功"""
    now = int(now_ms if now_ms is not None else _now_ms())
    code = (code or "").strip().upper()
    with closing(conn()) as c:
        cur = c.execute("UPDATE invite_codes SET uses_left = uses_left - 1 "
                        "WHERE code = ? AND revoked = 0 AND uses_left > 0 "
                        "AND (expires_at = 0 OR expires_at > ?)", (code, now))
        c.commit()
        return cur.rowcount == 1


def revoke_invite_code(code):
    with closing(conn()) as c:
        cur = c.execute("UPDATE invite_codes SET revoked = 1 WHERE code = ?",
                        ((code or "").strip().upper(),))
        c.commit()
        return cur.rowcount > 0


# ══════════════ 备份列表（v1.62 · 服主工具展示）══════════════

def backup_list(limit=10):
    """最近的日备份（新→旧）：[{name, size, mtime}]"""
    bak_dir = DB_PATH.parent / "backups"
    if not bak_dir.exists():
        return []
    out = []
    for f in sorted(bak_dir.glob("adventurer-*.db"))[-limit:][::-1]:
        try:
            st = f.stat()
            out.append({"name": f.name, "size": st.st_size, "mtime": int(st.st_mtime * 1000)})
        except OSError:
            pass
    return out


def load_user_state(uid):
    """读取指定账号状态，返回 (state, corrupted)：
         - 无记录 → (None, False)
         - 正常   → (dict, False)
         - JSON 损坏 → (None, True)：原文另存 data/corrupt/ 供手动修复（v1.39 A4，不再静默重置）"""
    with closing(conn()) as c:
        row = c.execute("SELECT data FROM users WHERE id = ?", (uid,)).fetchone()
    if not row:
        return None, False
    try:
        return json.loads(row["data"]), False
    except Exception:
        _keep_corrupt(uid, row["data"])
        return None, True


def _keep_corrupt(uid, raw):
    """存档 JSON 损坏：原文另存 data/corrupt/user<id>-<ts>.json（不覆盖、不删除原档）"""
    try:
        d = DB_PATH.parent / "corrupt"
        d.mkdir(parents=True, exist_ok=True)
        fn = "user%d-%s-%d.json" % (uid, time.strftime("%Y%m%d-%H%M%S"), _now_ms() % 1000)
        (d / fn).write_text(raw, encoding="utf-8")
    except Exception:
        pass


def save_user_state(uid, state):
    """写入指定账号状态（name 冗余同步，便于账号管理列表展示）"""
    with closing(conn()) as c:
        c.execute("UPDATE users SET name = ?, data = ? WHERE id = ?",
                  (state.get("name", ""), json.dumps(state, ensure_ascii=False), uid))
        c.commit()


def flush_event_log(state, uid=0):
    """把内存日志中尚未写库的条目写入 event_log（watermark 去重 + 唯一索引，幂等）。
       注意调用顺序：必须先 flush（更新内存 watermark）再 save_user_state（watermark 落库）——
       否则水位不落库，下次请求整批重写。"""
    wm = state.get("log_watermark", 0)
    new = [e for e in state.get("log", []) if e.get("ts", 0) > wm]
    if not new:
        return
    with closing(conn()) as c:
        for e in reversed(new):          # 内存为倒序（新在前），写库按时间正序
            c.execute("INSERT OR IGNORE INTO event_log (ts, cls, user_id, msg) VALUES (?, ?, ?, ?)",
                      (e["ts"], e.get("cls", ""), uid, e["msg"]))
        c.commit()
    state["log_watermark"] = max(e["ts"] for e in new)


def recent_logs(uid, limit=100):
    with closing(conn()) as c:
        rows = c.execute("SELECT ts, cls, msg FROM event_log WHERE user_id = ? "
                         "ORDER BY id DESC LIMIT ?", (uid, limit)).fetchall()
    return [dict(r) for r in rows]


def prune_event_log(keep_per_user=2000):
    """v1.39b（E4）：event_log 增长治理——
       ①每账号仅保留最近 keep_per_user 条（玩家侧只读近 120 条，2000 富余）；
       ②清除孤儿行（user_id 不属于任何现存账号的残留，如早期删除遗留；user_id=0 的历史行保留）。
       返回删除行数。幂等，可安全反复调用。"""
    total = 0
    with closing(conn()) as c:
        uids = [r["user_id"] for r in c.execute("SELECT DISTINCT user_id FROM event_log").fetchall()]
        for uid in uids:
            if not uid:
                continue
            cur = c.execute(
                "DELETE FROM event_log WHERE user_id = ? AND id < ("
                "  SELECT MIN(id) FROM ("
                "    SELECT id FROM event_log WHERE user_id = ? ORDER BY id DESC LIMIT ?"
                "  ))", (uid, uid, keep_per_user))
            total += cur.rowcount
        cur = c.execute("DELETE FROM event_log WHERE user_id != 0 AND user_id NOT IN "
                        "(SELECT id FROM users)")
        total += cur.rowcount
        c.commit()
    return total


def backup_daily():
    """v1.38：每日自动备份——data/backups/adventurer-YYYY-MM-DD.db，滚动保留最近 14 份（v1.39：7→14）。
       用 SQLite 的 VACUUM INTO 做原子快照；不支持时 WAL 检查点后回退文件复制。
       返回 True = 今日备份已就绪（含"今日已存在"）；False = 失败（调用方不记日期，下次重试）。"""
    bak_dir = DB_PATH.parent / "backups"
    bak_dir.mkdir(parents=True, exist_ok=True)
    dst = bak_dir / ("adventurer-" + time.strftime("%Y-%m-%d") + ".db")
    if not DB_PATH.exists():
        return False
    if not dst.exists():
        try:
            with closing(conn()) as c:
                c.execute("VACUUM INTO ?", (str(dst),))
        except Exception:
            try:
                with closing(conn()) as c:             # WAL 下先合并回主文件再复制
                    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            try:
                shutil.copy2(str(DB_PATH), str(dst))
            except Exception:
                return False
    _prune_backups(bak_dir)
    return True


def _prune_backups(bak_dir):
    """滚动保留最近 14 份日备份"""
    olds = sorted(bak_dir.glob("adventurer-*.db"))
    for f in olds[:-14]:
        try:
            f.unlink()
        except Exception:
            pass


# ══════════════ 社交：好友 / 申请 / 拉黑（v1.64 · P1）══════════════

def get_user_by_friend_code(fc):
    fc = (fc or "").strip().upper()
    if not fc:
        return None
    with closing(conn()) as c:
        return _row_to_user(c.execute("SELECT * FROM users WHERE friend_code = ?", (fc,)).fetchone())


def get_user_by_name(name):
    name = (name or "").strip()
    if not name:
        return None
    with closing(conn()) as c:
        return _row_to_user(c.execute("SELECT * FROM users WHERE name = ? COLLATE NOCASE "
                                      "AND name <> '' LIMIT 1", (name,)).fetchone())


def get_user(uid):
    with closing(conn()) as c:
        return _row_to_user(c.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone())


def friends_of(uid):
    """好友 id 列表（friend_edge 双向各一行）"""
    with closing(conn()) as c:
        return [r["b"] for r in c.execute("SELECT b FROM friend_edge WHERE a = ? ORDER BY b",
                                          (uid,)).fetchall()]


def friend_add_pair(a, b):
    """建立双向好友边（幂等）"""
    with closing(conn()) as c:
        now = _now_ms()
        c.execute("INSERT OR IGNORE INTO friend_edge (a, b, created_at) VALUES (?, ?, ?)", (a, b, now))
        c.execute("INSERT OR IGNORE INTO friend_edge (a, b, created_at) VALUES (?, ?, ?)", (b, a, now))
        c.commit()


def friend_remove_pair(a, b):
    with closing(conn()) as c:
        c.execute("DELETE FROM friend_edge WHERE (a = ? AND b = ?) OR (a = ? AND b = ?)", (a, b, b, a))
        c.commit()


def is_friend(a, b):
    with closing(conn()) as c:
        return bool(c.execute("SELECT 1 FROM friend_edge WHERE a = ? AND b = ? LIMIT 1",
                              (a, b)).fetchone())


def friend_req_create(from_uid, to_uid, msg=""):
    with closing(conn()) as c:
        cur = c.execute("INSERT INTO friend_req (from_uid, to_uid, msg, status, created_at) "
                        "VALUES (?, ?, ?, 'pending', ?)", (from_uid, to_uid, (msg or "")[:60], _now_ms()))
        c.commit()
        return cur.lastrowid


def friend_req_pending(from_uid, to_uid):
    """a→b 方向上是否有待处理申请"""
    with closing(conn()) as c:
        return c.execute("SELECT * FROM friend_req WHERE from_uid = ? AND to_uid = ? "
                         "AND status = 'pending' LIMIT 1", (from_uid, to_uid)).fetchone() is not None


def friend_req_list(uid):
    """uid 视角的申请：in = 收到的待处理（含对方名字）、out = 我发出的待处理"""
    with closing(conn()) as c:
        ins = [dict(r) for r in c.execute(
            "SELECT r.id, r.from_uid, r.msg, r.created_at, u.name AS name "
            "FROM friend_req r LEFT JOIN users u ON u.id = r.from_uid "
            "WHERE r.to_uid = ? AND r.status = 'pending' ORDER BY r.id DESC", (uid,)).fetchall()]
        outs = [dict(r) for r in c.execute(
            "SELECT r.id, r.to_uid, r.msg, r.created_at, u.name AS name "
            "FROM friend_req r LEFT JOIN users u ON u.id = r.to_uid "
            "WHERE r.from_uid = ? AND r.status = 'pending' ORDER BY r.id DESC", (uid,)).fetchall()]
        return {"in": ins, "out": outs}


def friend_req_get(req_id):
    with closing(conn()) as c:
        row = c.execute("SELECT * FROM friend_req WHERE id = ?", (req_id,)).fetchone()
        return dict(row) if row else None


def friend_req_set(req_id, status, expect="pending"):
    """条件更新（幂等）：仅当当前状态 == expect 才写入，返回是否更新成功"""
    with closing(conn()) as c:
        cur = c.execute("UPDATE friend_req SET status = ?, handled_at = ? WHERE id = ? AND status = ?",
                        (status, _now_ms(), req_id, expect))
        c.commit()
        return cur.rowcount == 1


def friend_req_count_since(from_uid, since_ms):
    with closing(conn()) as c:
        return c.execute("SELECT COUNT(*) AS n FROM friend_req WHERE from_uid = ? AND created_at >= ?",
                         (from_uid, since_ms)).fetchone()["n"]


def friend_req_cancel_between(a, b):
    """拉黑时清理：取消双方之间全部待处理申请"""
    with closing(conn()) as c:
        cur = c.execute("UPDATE friend_req SET status = 'cancelled', handled_at = ? "
                        "WHERE status = 'pending' AND ((from_uid = ? AND to_uid = ?) "
                        "OR (from_uid = ? AND to_uid = ?))", (_now_ms(), a, b, b, a))
        c.commit()
        return cur.rowcount


def set_health_public(uid, flag):
    with closing(conn()) as c:
        c.execute("UPDATE users SET health_public = ? WHERE id = ?", (1 if flag else 0, uid))
        c.commit()


def set_pref(uid, key, value):
    """更新社交偏好列（gift_perm / req_perm）——key 白名单防注入"""
    if key not in ("gift_perm", "req_perm"):
        return False
    with closing(conn()) as c:
        cur = c.execute("UPDATE users SET %s = ? WHERE id = ?" % key, (value, uid))
        c.commit()
        return cur.rowcount > 0


def block_add(a, b):
    with closing(conn()) as c:
        c.execute("INSERT OR IGNORE INTO block_list (a, b, created_at) VALUES (?, ?, ?)", (a, b, _now_ms()))
        c.commit()


def block_remove(a, b):
    with closing(conn()) as c:
        cur = c.execute("DELETE FROM block_list WHERE a = ? AND b = ?", (a, b))
        c.commit()
        return cur.rowcount > 0


def is_blocked(a, b):
    """a 是否被 b 拉黑（b 的黑名单含 a）"""
    with closing(conn()) as c:
        return bool(c.execute("SELECT 1 FROM block_list WHERE a = ? AND b = ? LIMIT 1",
                              (b, a)).fetchone())


def block_list_of(uid):
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT bl.b AS uid, u.name FROM block_list bl LEFT JOIN users u ON u.id = bl.b "
            "WHERE bl.a = ? ORDER BY bl.b", (uid,)).fetchall()]


# ══════════════ 社交：邮件（v1.64 · P1 赠送底座；P3 货款复用）══════════════

def mail_create(uid, kind, from_uid=0, title="", body="", mat="", qty=0, money=0, expire_at=0):
    with closing(conn()) as c:
        cur = c.execute("INSERT INTO mail (uid, kind, from_uid, title, body, mat, qty, money, "
                        "status, created_at, expire_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (uid, kind, from_uid, title, body, mat, qty, money,
                         "pending" if (mat or money) else "unread", _now_ms(), expire_at))
        c.commit()
        return cur.lastrowid


def mail_list(uid, limit=60):
    with closing(conn()) as c:
        rows = c.execute("SELECT * FROM mail WHERE uid = ? ORDER BY id DESC LIMIT ?",
                         (uid, limit)).fetchall()
        return [dict(r) for r in rows]


def mail_get(mail_id):
    with closing(conn()) as c:
        row = c.execute("SELECT * FROM mail WHERE id = ?", (mail_id,)).fetchone()
        return dict(row) if row else None


def mail_set_status(mail_id, status, expect=None):
    """条件更新（幂等）：expect 给定时仅当旧状态 == expect 才写入；返回是否更新成功"""
    with closing(conn()) as c:
        if expect is None:
            cur = c.execute("UPDATE mail SET status = ?, handled_at = ? WHERE id = ?",
                            (status, _now_ms(), mail_id))
        else:
            cur = c.execute("UPDATE mail SET status = ?, handled_at = ? WHERE id = ? AND status = ?",
                            (status, _now_ms(), mail_id, expect))
        c.commit()
        return cur.rowcount == 1


def mail_read_all(uid):
    """v1.67：一键已读（全表 unread → read；幂等）。修复：原实现只覆盖列表上限 60 封，积压时红点不消"""
    with closing(conn()) as c:
        cur = c.execute("UPDATE mail SET status = 'read', handled_at = ? WHERE uid = ? AND status = 'unread'",
                        (_now_ms(), uid))
        c.commit()
        return cur.rowcount


def mail_dot(uid):
    """待处理计数（页签红点）：未读系统邮件 + 待接收赠送"""
    with closing(conn()) as c:
        n1 = c.execute("SELECT COUNT(*) AS n FROM mail WHERE uid = ? AND status = 'unread'",
                       (uid,)).fetchone()["n"]
        n2 = c.execute("SELECT COUNT(*) AS n FROM mail WHERE uid = ? AND status = 'pending'",
                       (uid,)).fetchone()["n"]
        return n1 + n2


def gift_rows_since(from_uid, since_ms):
    """从 from_uid 发出的赠与邮件行（含 qty；上游按品阶过滤，被拒收 / 超时退回由上游排除——
    v1.66a 起展示与拦截同一口径）"""
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT id, mat, qty, status FROM mail WHERE kind = 'gift' AND from_uid = ? AND created_at >= ?",
            (from_uid, since_ms)).fetchall()]


def gift_received_rows_since(uid, since_ms):
    """本周 uid 已接受的赠与邮件行（按接受时间计；含 qty，上游按品阶过滤并求和）"""
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT id, mat, qty FROM mail WHERE kind = 'gift' AND uid = ? AND status = 'claimed' "
            "AND handled_at >= ?", (uid, since_ms)).fetchall()]


def gift_pending_for(uid):
    """发给 uid 的待接收赠与行（含 qty，上游按品阶过滤并求和）"""
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT id, mat, qty FROM mail WHERE kind = 'gift' AND uid = ? AND status = 'pending'",
            (uid,)).fetchall()]


def mail_pending_kinds_to(uid, kinds):
    """发给 uid 且仍待处理的指定类型邮件数（v1.67：导入存档防复制资产——退回 / 货款在途时禁导入）"""
    kinds = tuple(kinds)
    marks = ",".join("?" for _ in kinds)
    with closing(conn()) as c:
        return c.execute("SELECT COUNT(*) AS n FROM mail WHERE uid = ? AND status = 'pending' "
                         "AND kind IN (" + marks + ")", (uid,) + kinds).fetchone()["n"]


def mail_expired(now_ms):
    """到期且仍待处理（待接收赠送 / 未读未领的普通邮件）——供 global_sweep 结算"""
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM mail WHERE expire_at > 0 AND expire_at <= ? "
            "AND status IN ('pending', 'unread', 'read') ORDER BY id", (now_ms,)).fetchall()]


# ══════════════ 社交：组队副本（v1.65 · P2）══════════════

def party_create(uid, idx, tier, diff, day, expire_at):
    with closing(conn()) as c:
        cur = c.execute("INSERT INTO party (uid, idx, tier, diff, status, day, created_at, expire_at) "
                        "VALUES (?, ?, ?, ?, 'offer', ?, ?, ?)",
                        (uid, idx, tier, diff, day, _now_ms(), expire_at))
        c.commit()
        return cur.lastrowid


def party_get(pid):
    with closing(conn()) as c:
        row = c.execute("SELECT * FROM party WHERE id = ?", (pid,)).fetchone()
        return dict(row) if row else None


def party_leader_active(uid):
    """我作为队长仍未结束的副本行（offer / open / running）"""
    with closing(conn()) as c:
        row = c.execute("SELECT * FROM party WHERE uid = ? AND status IN ('offer','open','running') "
                        "ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
        return dict(row) if row else None


def party_offer_of_day(uid, day):
    """我这一「副本日」的行（每天只刷 1 个——无论后来是 offer/open/running/abandoned）"""
    with closing(conn()) as c:
        row = c.execute("SELECT * FROM party WHERE uid = ? AND day = ? ORDER BY id DESC LIMIT 1",
                        (uid, day)).fetchone()
        return dict(row) if row else None


def party_set_status(pid, status, expect=None, **fields):
    """条件更新（幂等）：expect 给定时仅当旧状态 == expect 才写入；fields 追加列"""
    sets, args = ["status = ?"], [status]
    for k in ("expire_at", "started_at", "ends_at", "goal", "progress", "settled"):
        if k in fields:
            sets.append(k + " = ?")
            args.append(fields[k])
    args.append(pid)
    where = "id = ?" + (" AND status = ?" if expect else "")
    if expect:
        args.append(expect)
    with closing(conn()) as c:
        cur = c.execute("UPDATE party SET " + ", ".join(sets) + " WHERE " + where, args)
        c.commit()
        return cur.rowcount == 1


def party_add_progress(pid, n):
    """原子加格（仅 running 时生效）；返回最新 {progress, goal} 或 None"""
    with closing(conn()) as c:
        cur = c.execute("UPDATE party SET progress = progress + ? WHERE id = ? AND status = 'running'",
                        (n, pid))
        c.commit()
        if cur.rowcount != 1:
            return None
        row = c.execute("SELECT progress, goal FROM party WHERE id = ?", (pid,)).fetchone()
        return dict(row) if row else None


def party_member_upsert(pid, uid, status, week0, rate, actions_left, spent):
    with closing(conn()) as c:
        c.execute("INSERT INTO party_member (party_id, uid, status, joined_at, week0, rate, "
                  "actions_left, spent) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                  "ON CONFLICT(party_id, uid) DO UPDATE SET status = excluded.status",
                  (pid, uid, status, _now_ms(), week0, rate, actions_left, spent))
        c.commit()


def party_member_get(pid, uid):
    with closing(conn()) as c:
        row = c.execute("SELECT * FROM party_member WHERE party_id = ? AND uid = ?", (pid, uid)).fetchone()
        return dict(row) if row else None


def party_member_set(pid, uid, expect=None, **fields):
    cols = [k for k in ("status", "actions_left", "refund", "reward", "claim", "rate") if k in fields]
    if not cols:
        return False
    sets = [k + " = ?" for k in cols]
    args = [fields[k] for k in cols]
    args += [pid, uid]
    where = "party_id = ? AND uid = ?" + (" AND status = ?" if expect else "")
    if expect:
        args.append(expect)
    with closing(conn()) as c:
        cur = c.execute("UPDATE party_member SET " + ", ".join(sets) + " WHERE " + where, args)
        c.commit()
        return cur.rowcount == 1


def party_members(pid):
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT pm.*, u.name FROM party_member pm LEFT JOIN users u ON u.id = pm.uid "
            "WHERE pm.party_id = ? ORDER BY pm.joined_at, pm.uid", (pid,)).fetchall()]


def party_member_active(uid):
    """我作为队员、所在副本仍未结束的行（open / running）"""
    with closing(conn()) as c:
        row = c.execute(
            "SELECT p.*, pm.status AS m_status FROM party_member pm JOIN party p ON p.id = pm.party_id "
            "WHERE pm.uid = ? AND pm.status = 'in' AND p.status IN ('open','running') "
            "ORDER BY p.id DESC LIMIT 1", (uid,)).fetchone()
        return dict(row) if row else None


def party_week_count(uid, week0):
    """本周参与次数（接受即计入；未开启取消 → 行转 refunded 不再计入）"""
    with closing(conn()) as c:
        return c.execute("SELECT COUNT(*) AS n FROM party_member WHERE uid = ? AND week0 = ? "
                         "AND status IN ('in', 'quit')", (uid, week0)).fetchone()["n"]


def party_invite_add(pid, uid):
    with closing(conn()) as c:
        c.execute("INSERT INTO party_invite (party_id, uid, status, created_at) VALUES (?, ?, 'pending', ?) "
                  "ON CONFLICT(party_id, uid) DO UPDATE SET status = 'pending'", (pid, uid, _now_ms()))
        c.commit()


def party_invite_set(pid, uid, status, expect=None):
    with closing(conn()) as c:
        if expect:
            cur = c.execute("UPDATE party_invite SET status = ? WHERE party_id = ? AND uid = ? AND status = ?",
                            (status, pid, uid, expect))
        else:
            cur = c.execute("UPDATE party_invite SET status = ? WHERE party_id = ? AND uid = ?",
                            (status, pid, uid))
        c.commit()
        return cur.rowcount == 1


def party_invite_get(pid, uid):
    with closing(conn()) as c:
        row = c.execute("SELECT * FROM party_invite WHERE party_id = ? AND uid = ?", (pid, uid)).fetchone()
        return dict(row) if row else None


def party_invites_of(uid):
    """发给我的待处理邀请（附副本信息）"""
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT pi.party_id, p.uid AS leader_uid, p.idx, p.tier, p.diff, p.status AS p_status, "
            "u.name AS leader_name FROM party_invite pi JOIN party p ON p.id = pi.party_id "
            "LEFT JOIN users u ON u.id = p.uid "
            "WHERE pi.uid = ? AND pi.status = 'pending' AND p.status = 'open' ORDER BY pi.party_id DESC",
            (uid,)).fetchall()]


def party_invites_sent(pid):
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT pi.uid, pi.status, u.name FROM party_invite pi LEFT JOIN users u ON u.id = pi.uid "
            "WHERE pi.party_id = ? ORDER BY pi.uid", (pid,)).fetchall()]


def party_refunds_pending(uid):
    """待退还精力的成员行（本人下次打开时在其锁内入账并清标记）"""
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT pm.party_id, pm.spent, p.idx FROM party_member pm JOIN party p ON p.id = pm.party_id "
            "WHERE pm.uid = ? AND pm.refund = 1", (uid,)).fetchall()]


def party_claims_pending(uid):
    """待领取的结算结果（本人下次打开时展示领取）"""
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT pm.party_id, pm.reward, p.idx, p.status AS p_status, p.settled "
            "FROM party_member pm JOIN party p ON p.id = pm.party_id "
            "WHERE pm.uid = ? AND pm.claim = 'pending' ORDER BY pm.party_id DESC LIMIT 5", (uid,)).fetchall()]


def party_expired_unstarted(now_ms):
    """未开启即到期（offer / open 且过 expire_at）——供 global_sweep 结算"""
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM party WHERE status IN ('offer','open') AND expire_at > 0 AND expire_at <= ?",
            (now_ms,)).fetchall()]


def party_running_expired(now_ms):
    """进行中且已到时长上限（running 且过 ends_at）——供 global_sweep 按失败结算"""
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM party WHERE status = 'running' AND ends_at > 0 AND ends_at <= ?",
            (now_ms,)).fetchall()]


# ══════════════ 社交：材料市场（v1.66 · P3）══════════════

def market_create(seller, mat, qty, price, expire_at):
    with closing(conn()) as c:
        cur = c.execute("INSERT INTO market (seller, mat, qty, price, status, created_at, expire_at) "
                        "VALUES (?, ?, ?, ?, 'on', ?, ?)",
                        (seller, mat, qty, price, _now_ms(), expire_at))
        c.commit()
        return cur.lastrowid


def market_get(lid):
    with closing(conn()) as c:
        row = c.execute("SELECT * FROM market WHERE id = ?", (lid,)).fetchone()
        return dict(row) if row else None


def market_on(limit=80):
    """在售挂单（含卖家名）"""
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT m.*, u.name AS seller_name FROM market m LEFT JOIN users u ON u.id = m.seller "
            "WHERE m.status = 'on' ORDER BY m.id DESC LIMIT ?", (limit,)).fetchall()]


def market_on_by_others(uid):
    with closing(conn()) as c:
        return c.execute("SELECT COUNT(*) AS n FROM market WHERE status = 'on' AND seller != ?",
                         (uid,)).fetchone()["n"]


def market_mine(seller, limit=20):
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM market WHERE seller = ? ORDER BY id DESC LIMIT ?", (seller, limit)).fetchall()]


def market_set(lid, expect=None, **fields):
    """条件更新（幂等）：qty / sold / status / off_reason"""
    cols = [k for k in ("qty", "sold", "status", "off_reason") if k in fields]
    if not cols:
        return False
    sets = [k + " = ?" for k in cols]
    args = [fields[k] for k in cols]
    args.append(lid)
    where = "id = ?" + (" AND status = ?" if expect else "")
    if expect:
        args.append(expect)
    with closing(conn()) as c:
        cur = c.execute("UPDATE market SET " + ", ".join(sets) + " WHERE " + where, args)
        c.commit()
        return cur.rowcount == 1


def market_take(lid, qty):
    """原子扣减剩余数量（部分购买；仅 on 且余量足够时生效）→ 返回最新剩余或 None"""
    with closing(conn()) as c:
        cur = c.execute("UPDATE market SET qty = qty - ?, sold = sold + ? "
                        "WHERE id = ? AND status = 'on' AND qty >= ?", (qty, qty, lid, qty))
        c.commit()
        if cur.rowcount != 1:
            return None
        row = c.execute("SELECT qty FROM market WHERE id = ?", (lid,)).fetchone()
        left = row["qty"]
        if left == 0:
            c.execute("UPDATE market SET status = 'sold' WHERE id = ? AND status = 'on'", (lid,))
            c.commit()
        return left


def market_take_off(lid, status, reason):
    """v1.67：原子收摊（下架 / 到期）——仅当仍在售时置状态，并返回**置状态瞬间的剩余数量**。
       原实现用进入函数时读到的陈旧 qty 退回，与部分买入并发时会多退 → 复制材料。None = 已被处理过"""
    with closing(conn()) as c:
        row = c.execute("UPDATE market SET status = ?, off_reason = ? WHERE id = ? AND status = 'on' "
                        "RETURNING qty", (status, reason, lid)).fetchone()
        c.commit()
        return row["qty"] if row else None


def market_buy_add(buyer, listing, qty, price):
    with closing(conn()) as c:
        c.execute("INSERT INTO market_buys (buyer, listing, qty, price, ts) VALUES (?, ?, ?, ?, ?)",
                  (buyer, listing, qty, price, _now_ms()))
        c.commit()


def market_buys_since(buyer, since_ms):
    """买入限额统计（个）：since 起 qty 合计"""
    with closing(conn()) as c:
        row = c.execute("SELECT COALESCE(SUM(qty), 0) AS n FROM market_buys WHERE buyer = ? AND ts >= ?",
                        (buyer, since_ms)).fetchone()
        return int(row["n"])


def market_day_listings(seller, since_ms):
    """每日上架次数（含已售出 / 下架 / 过期）"""
    with closing(conn()) as c:
        return c.execute("SELECT COUNT(*) AS n FROM market WHERE seller = ? AND created_at >= ?",
                         (seller, since_ms)).fetchone()["n"]


def market_active_count(seller):
    with closing(conn()) as c:
        return c.execute("SELECT COUNT(*) AS n FROM market WHERE seller = ? AND status = 'on'",
                         (seller,)).fetchone()["n"]


def market_expired(now_ms):
    """到期仍在售的挂单——供 global_sweep 下架（原样退回 = 退回邮件）"""
    with closing(conn()) as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM market WHERE status = 'on' AND expire_at > 0 AND expire_at <= ?",
            (now_ms,)).fetchall()]
