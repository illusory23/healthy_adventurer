# -*- coding: utf-8 -*-
"""生成中国传统节日（农历）公历日期表：2025~2040
   用法：python _生成农历节日.py  （在 数据表/ 目录，依赖 lunardate）
   输出：打印两份可直接粘贴的数据（Python dict / JS 对象）——同步到 game.py 与两个 HTML。
   节日范围（v1.41e 用户确认·核心 10 个）：除夕 / 春节（含除夕~初六假期区间）/ 元宵 / 清明 / 端午 / 七夕 / 中秋 / 重阳 / 腊八 / 小年"""
from datetime import date, timedelta
import lunardate

START_Y, END_Y = 2025, 2040          # 覆盖的公历年份（含）

events = {}                          # "YYYY-MM-DD" -> 节日名


def put(d, name):
    events[d.isoformat()] = name


def lunar(ly, lm, ld):
    return lunardate.LunarDate(ly, lm, ld).to_solar_date()


def qingming(y):                     # 清明：21 世纪通用公式 [Y×0.2422+4.81] − [Y/4]
    yy = y % 100
    return date(y, 4, int(yy * 0.2422 + 4.81) - yy // 4)


# 逐农历年计算节日（覆盖公历 2025-01 所需的 2024 年腊月节日 → 从 2024 农历年起算）
for ly in range(2023, END_Y + 1):
    put(lunar(ly, 1, 1), "春节")
    put(lunar(ly, 1, 15), "元宵节")
    put(lunar(ly, 5, 5), "端午节")
    put(lunar(ly, 7, 7), "七夕节")
    put(lunar(ly, 8, 15), "中秋节")
    put(lunar(ly, 9, 9), "重阳节")
    put(lunar(ly, 12, 8), "腊八节")
    put(lunar(ly, 12, 23), "小年")
    chuxi = None                     # 除夕：腊月最后一天（廿九或三十）
    for dd in (30, 29):
        try:
            chuxi = lunar(ly, 12, dd)
            break
        except Exception:
            continue
    assert chuxi, "除夕计算失败：" + str(ly)
    put(chuxi, "除夕")

for y in range(START_Y, END_Y + 1):   # 清明（公历节气）
    put(qingming(y), "清明节")

# 春节假期区间：除夕 ~ 初六（除夕已单独登记"除夕"，初一起 6 天登记"春节"）
springs = [d for d, n in events.items() if n == "春节"]
for s in springs:
    d0 = date.fromisoformat(s)
    for k in range(0, 6):            # 初一 ~ 初六
        d = d0 + timedelta(days=k)
        if d.isoformat() not in events:
            put(d, "春节")

# 过滤 + 按公历年分组、年内排序
sel = {d: n for d, n in events.items() if START_Y <= int(d[:4]) <= END_Y and d[:4] <= str(END_Y)}
rows = {}
for d in sorted(sel):
    rows.setdefault(d[:4], []).append(d[5:] + " " + sel[d])

meta = {
    "除夕":   ("🎆 除夕",   "阖家团圆", "爆竹声里辞旧岁——今晚守岁可以，别熬太狠。"),
    "春节":   ("🧧 春节",   "新年大吉", "新春快乐！新的一年，好好吃饭、好好睡觉，冒险才有劲。"),
    "元宵节": ("🏮 元宵节", "节日快乐", "汤圆甜又圆——赏灯可以，23:30 前记得回家睡。"),
    "清明节": ("🌿 清明节", "清明安康", "清明时节——踏青之余，也照顾好自己。"),
    "端午节": ("🐉 端午节", "端午安康", "粽叶飘香——粽子好吃，肠胃和作息更要紧。"),
    "七夕节": ("💫 七夕节", "节日快乐", "今夜星河灿烂——有人相伴很好，独善其身也很好。"),
    "中秋节": ("🌕 中秋节", "节日快乐", "月圆人团圆——掰块月饼，今晚早点睡。"),
    "重阳节": ("🍁 重阳节", "重阳安康", "登高望远，敬老思亲——秋深处，添衣保暖。"),
    "腊八节": ("🥣 腊八节", "节日快乐", "一碗腊八粥，暖到心里——年味开始了。"),
    "小年":   ("🧹 小年",   "节日快乐", "掸尘扫房，辞旧迎新——小年到，过年不远了。"),
}

print("# ═══ Python（粘到 game.py 的 FESTIVALS 之后）═══")
print("CN_FEST_META = {")
for k, v in meta.items():
    print('    "%s": ("%s", "%s", "%s"),' % (k, v[0], v[1], v[2]))
print("}")
print("CN_LUNAR_FEST = {   # 公历年 → 年内农历节日（MM-DD 名称，| 分隔；2025~2040 表）")
for y in sorted(rows):
    print('    "%s": "%s",' % (y, "|".join(rows[y])))
print("}")
print()
print("// ═══ JS（粘到两个 HTML 的 FESTIVALS 之后）═══")
print("const CN_FEST_META = {")
for k, v in meta.items():
    print('  "%s": ["%s", "%s", "%s"],' % (k, v[0], v[1], v[2]))
print("};")
print("const CN_LUNAR_FEST = {   // 公历年 → 年内农历节日（MM-DD 名称，| 分隔；2025~2040 表）")
for y in sorted(rows):
    print('  "%s": "%s",' % (y, "|".join(rows[y])))
print("};")
print()
print("// 抽查：", "2025 春节", rows["2025"][0][:30], "…| 2026 春节 02-17 in 表:",
      "02-17 春节" in rows["2026"] or any("02-17 春节" == x for x in rows["2026"]))
for y in ("2025", "2026"):
    print(y, "：", "  ".join(x for x in rows[y] if "春节" in x or "除夕" in x))
print("共", sum(len(v) for v in rows.values()), "天节日 /", len(rows), "年")
