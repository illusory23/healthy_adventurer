# -*- coding: utf-8 -*-
"""并发压测（v1.62 · P0 验收）：python _loadtest.py [--users 15] [--rounds 10] [--port 5901]

   做法：把最小运行集（app/game/db/sweep + data/static_data.json）拷到临时目录 →
   子进程起 waitress（临时库，与正式 data/ 完全隔离，端口默认 5901 避开 5899） →
   HTTP 注册 N 个账号 → N 线程并发 GET /api/state × rounds 轮。
   输出：请求数 / 失败数 / P50 / P95 / 最大耗时；并扫描服务端日志中的
   "database is locked" 与 Traceback。

   15 人规模验收线：无失败请求、无锁报错、P95 < 5 秒。
"""
import argparse
import http.client
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _wait_port(port, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            s.close()
            return True
        except OSError:
            time.sleep(0.2)
    return False


def main():
    ap = argparse.ArgumentParser(description="15 人规模并发压测（P0 验收）")
    ap.add_argument("--users", type=int, default=15)
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--port", type=int, default=5901)
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="had_loadtest_"))
    for f in ["app.py", "game.py", "db.py", "sweep.py"]:
        shutil.copy2(HERE / f, tmp / f)
    (tmp / "data").mkdir(exist_ok=True)
    sd = HERE / "data" / "static_data.json"
    if sd.exists():
        shutil.copy2(sd, tmp / "data" / "static_data.json")
    print("临时运行目录：" + str(tmp))

    child_code = (
        "import sys, os\n"
        "sys.path.insert(0, os.getcwd())\n"
        "import app\n"
        "try:\n"
        "    from waitress import serve\n"
        "    serve(app.app, host='127.0.0.1', port=%d, threads=8)\n"
        "except ImportError:\n"
        "    app.app.run(host='127.0.0.1', port=%d, threaded=True)\n" % (args.port, args.port)
    )
    log_path = tmp / "loadtest_child.log"
    logf = open(log_path, "wb")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen([sys.executable, "-c", child_code], cwd=str(tmp),
                            stdout=logf, stderr=subprocess.STDOUT, env=env)
    passed = False
    try:
        if not _wait_port(args.port):
            print("❌ 服务未能启动（端口 %d）——见 %s" % (args.port, log_path))
            return 1
        print("服务已起：127.0.0.1:%d（waitress threads=8，临时库）" % args.port)

        tokens = []
        for i in range(args.users):
            conn = http.client.HTTPConnection("127.0.0.1", args.port, timeout=10)
            body = urllib.parse.urlencode({"nick": "压测%02d" % i})
            conn.request("POST", "/register", body=body,
                         headers={"Content-Type": "application/x-www-form-urlencoded"})
            r = conn.getresponse()
            r.read()
            sc = r.getheader("Set-Cookie") or ""
            m = re.search(r"gp_uid=([^;]+)", sc)
            if r.status == 302 and m:
                tokens.append(m.group(1))
            conn.close()
        print("账号注册：%d / %d" % (len(tokens), args.users))

        results = []
        lock = threading.Lock()

        def worker(tk):
            conn2 = http.client.HTTPConnection("127.0.0.1", args.port, timeout=15)
            hdr = {"Cookie": "gp_uid=" + tk}
            for _ in range(args.rounds):
                t0 = time.time()
                ok = False
                try:
                    conn2.request("GET", "/api/state", headers=hdr)
                    rr = conn2.getresponse()
                    rr.read()
                    ok = (rr.status == 200)
                except Exception:
                    ok = False
                dt = (time.time() - t0) * 1000
                with lock:
                    results.append((ok, dt))
            conn2.close()

        ths = [threading.Thread(target=worker, args=(t,)) for t in tokens]
        t_start = time.time()
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        wall = time.time() - t_start

        total = len(results)
        fails = sum(1 for ok, _ in results if not ok)
        dts = sorted(dt for _, dt in results)
        p50 = dts[len(dts) // 2] if dts else 0
        p95 = dts[min(len(dts) - 1, int(len(dts) * 0.95))] if dts else 0
        mx = dts[-1] if dts else 0
        print("结果：请求 %d · 失败 %d · 墙钟 %.1fs · P50 %.0fms · P95 %.0fms · 最大 %.0fms"
              % (total, fails, wall, p50, p95, mx))

        time.sleep(0.5)
        logf.flush()
        logtxt = log_path.read_bytes().decode("utf-8", "replace")
        locked = "database is locked" in logtxt
        trace = "Traceback" in logtxt
        print("服务端日志：locked=%s traceback=%s（%s）" % (locked, trace, log_path))

        passed = (len(tokens) == args.users and not fails and not locked
                  and not trace and p95 < 5000)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        logf.close()

    if passed:
        print("✅ 通过：无失败 / 无锁 / P95 < 5s")
        shutil.rmtree(tmp, ignore_errors=True)
        return 0
    print("❌ 未通过——现场保留在：" + str(tmp))
    return 1


if __name__ == "__main__":
    sys.exit(main())
