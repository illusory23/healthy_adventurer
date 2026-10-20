# -*- coding: utf-8 -*-
"""全局维护通道（v1.62 · 社交 P0 骨架）

背景：本项目所有时间性机制走「惰性补算」——per-account 的 catch_up 只结算
该账号自己的内容；而社交层引入了一批**跨账号**的到期对象：
  - 市场挂单到期（P3）
  - 邮件过期（P1，赠送超时退回）
  - 组队副本到期结算（P2）
这些对象"谁先上线谁负责结算"，因此需要一个**全局**维护通道：任何账号的
任何请求都会触发一次 sweep，把到期的跨账号对象幂等落地。

设计约定（实装各期时遵守）：
  1. 幂等：每个处理器必须"结算状态已变更的对象时零副作用"（先查状态再动作，
     或单条 UPDATE ... WHERE status=旧态 判断 rowcount）；重复调用不产生重复收益。
  2. 事务：每个处理器的关键写入用一条 UPDATE/INSERT 表达（SQLite 单写者，
     自带原子性）；复杂对象先在内存判定、再单事务落库。
  3. 异常隔离：单个处理器抛异常不影响其它处理器、不影响玩家请求（就地记日志）。
  4. 节流：进程内 60 秒最多跑一轮（15 人规模足够）；测试可 force。

调用：app.py 的口令门通过后每请求调用一次 sweep.run()（内部节流）。
"""
import logging
import time

log = logging.getLogger("sweep")

MIN_INTERVAL_MS = 60 * 1000          # 节流窗口：60 秒
_last_run_ms = 0
_handlers = []                       # 处理器：fn(now_ms) -> 处理条数（int 或 None）
_stats = {"runs": 0, "handled": 0}


def register(fn):
    """注册一个 {fn(now_ms) -> int|None} 处理器（幂等：同函数不重复注册）"""
    if fn not in _handlers:
        _handlers.append(fn)
    return fn


def handlers():
    return list(_handlers)


def run(force=False, now_ms=None):
    """跑一轮全局维护。返回本轮处理条数。
       force=True 跳过节流（测试/运维手动触发）；now_ms 可注入固定时钟（测试）。"""
    global _last_run_ms
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    if not force and (now - _last_run_ms) < MIN_INTERVAL_MS:
        return 0
    _last_run_ms = now
    _stats["runs"] += 1
    n = 0
    for fn in list(_handlers):
        try:
            r = fn(now)
            if isinstance(r, int) and r > 0:
                n += r
        except Exception:
            log.exception("global_sweep 处理器异常：%s", getattr(fn, "__name__", fn))
    _stats["handled"] += n
    return n


def stats():
    return dict(_stats)


def _reset_for_tests():
    """仅供测试：清空处理器与节流/统计状态"""
    global _last_run_ms
    _handlers.clear()
    _last_run_ms = 0
    _stats["runs"] = 0
    _stats["handled"] = 0
