# -*- coding: utf-8 -*-
"""一键跑全部测试套件（项目根运行：python run_all_tests.py，或双击 跑全部测试.bat）
   依次执行：原型冒烟 / 原型创造模式 / Flask 核心逻辑 / Flask API / game.html 桥接 / 双端对拍
   退出码：0 = 全过；1 = 有失败（供批处理/CI 判断）"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")

SUITES = [
    ("Flask 前端 · 冒烟逻辑",  ROOT / "创造模式测试原型", ["node", "_smoke_run.js"]),
    ("Flask 前端 · 创造模式",  ROOT / "创造模式测试原型", ["node", "_smoke_creator.js"]),
    ("Flask · 核心逻辑",     ROOT / "Flask版",          [PY, "test_game.py"]),
    ("Flask · API 端到端",   ROOT / "Flask版",          [PY, "test_api.py"]),
    ("Flask · game.html 桥接", ROOT / "Flask版",        ["node", "_verify_game_html.js"]),
    ("双端 · 公式对拍",      ROOT / "Flask版",          [PY, "_parity_check.py"]),
]

failed = []
for i, (name, cwd, cmd) in enumerate(SUITES, 1):
    print()
    print("=" * 60)
    print("[%d/%d] %s" % (i, len(SUITES), name))
    print("=" * 60)
    try:
        rc = subprocess.run(cmd, cwd=str(cwd), env=ENV).returncode
    except FileNotFoundError as e:
        print("无法执行 %s：%s" % (cmd[0], e))
        rc = 1
    if rc != 0:
        failed.append(name)

print()
print("=" * 60)
if failed:
    print("[FAIL] 失败套件：" + "、".join(failed))
    sys.exit(1)
print("[OK] 全部 %d 套测试通过" % len(SUITES))
