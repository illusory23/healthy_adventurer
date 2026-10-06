# -*- coding: utf-8 -*-
"""SQLite 持久化：账号表（每设备/每人独立存档）+ 事件日志表

v1.37：单存档 → 多账号
  - users 表：一行 = 一个账号；首次访问静默建号（设备令牌 Cookie 自动登录），
    跨设备用 8 位「接入码」绑定切换
  - 旧版单行 player 表（id=1）自动迁入 users（migrated=1，等本机首次访问认领）；
    player 表保留作原始备份，此后不再读写
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
  code TEXT NOT NULL UNIQUE,             -- 接入码（8 位，信息页展示 / 跨设备绑定）
  migrated INTEGER NOT NULL DEFAULT 0,   -- 1 = 旧版存档迁移而来（等待本机认领）
  created_at INTEGER NOT NULL DEFAULT 0,
  last_login INTEGER NOT NULL DEFAULT 0, -- 0 = 从未被登录/认领
  data TEXT NOT NULL DEFAULT '{}'        -- 完整状态 JSON
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
    return {k: row[k] for k in ("id", "name", "token", "code", "migrated", "created_at", "last_login")}


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


def create_user():
    """静默新建账号（空档）"""
    with closing(conn()) as c:
        for _ in range(30):
            try:
                cur = c.execute(
                    "INSERT INTO users (name, token, code, created_at, last_login, data) "
                    "VALUES ('', ?, ?, ?, 0, '{}')",
                    (_new_token(), _new_code(), _now_ms()))
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
    """本机账号管理（v1.38q2）：删除账号并清除其事件日志（不可恢复）"""
    with closing(conn()) as c:
        c.execute("DELETE FROM event_log WHERE user_id = ?", (uid,))
        cur = c.execute("DELETE FROM users WHERE id = ?", (uid,))
        c.commit()
        return cur.rowcount > 0


def list_users():
    """账号列表（仅供本机账号管理面板）——不返回 token"""
    with closing(conn()) as c:
        rows = c.execute("SELECT id, name, code, migrated, created_at, last_login "
                         "FROM users ORDER BY id").fetchall()
        return [dict(r) for r in rows]


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
