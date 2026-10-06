# -*- coding: utf-8 -*-
"""v1.51：原型同步工具——把「Flask 前端原型层」同步到「创造模式原型」主块。

用法：python _sync_proto.py            （dry-run：写 _sync_out.html 供检查）
      python _sync_proto.py --apply    （实际替换 健康的冒险者的一天.html，先自动备份 .bak_sync）

原理：前端 game.html 的 <script> 内容 = 原型层 + Flask 桥接层 + boot。
     原型主块 = 前端原型层 + 8 处「原型专属」补丁：
       A. 3d 骰子路径（本地 ./3d骰子/ vs 服务端 /static/dice3d/）
       B. 轻提示 toast 本地实现（前端由桥接层统一提供）
       C. 重置存档：连同附属记录一并清除（原型本地版）
       D. 导出/导入按钮文案（原型 2 按钮 vs 前端 3 按钮）
       E. 数据保存说明（localStorage vs SQLite）
       F. 无「账号」卡（设备登录 / 接入码为 Flask 专属）
       G. 尾部启动段（load(); nameInput 监听; setInterval 提醒 —— 前端移入了 boot）
       H. 创造模式面板勾子（creator tab → renderCreator）
"""
import io
import shutil
import sys

ROOT = '..'
FRONT = ROOT + '/Flask版/static/game.html'
PROTO = '健康的冒险者的一天.html'
OUT = '_sync_out.html'


def mainblock(t):
    i0 = t.find('<script>')
    i1 = t.find('</script>', i0)
    return i0, i1, t[i0 + 8:i1]


def sub_once(lines, old, new, label):
    text = '\n'.join(lines)
    assert text.count(old) == 1, '%s：期望唯一匹配，实际 %d 处' % (label, text.count(old))
    return text.replace(old, new, 1).split('\n')


def main():
    ft = io.open(FRONT, encoding='utf-8').read()
    pt = io.open(PROTO, encoding='utf-8').read()
    fi0, fi1, fcode = mainblock(ft)
    pi0, pi1, pcode = mainblock(pt)

    bi = fcode.find('(async function boot(){')
    assert bi > 0, '前端结构变化：未找到 boot 段'
    fproto = fcode[:bi]
    L = fproto.split('\n')

    # 原型侧素材：toast 实现 / 重置块 / 按钮段 / 说明段 / 尾部启动段 / creator 钩子
    pl = pcode.split('\n')

    ti = next(i for i, l in enumerate(pl) if '/* ── 轻提示（v1.28' in l)
    proto_toast = '\n'.join(pl[ti:ti + 15])          # 注释行起 15 行 = toast 本地实现整段
    ri = next(i for i, l in enumerate(pl) if 'try{' in l and 'localStorage.removeItem(KEY)' in pl[i + 1])
    re_ = next(j for j in range(ri, len(pl)) if 'catch(e){}' in pl[j])
    proto_reset = '\n'.join(pl[ri:re_ + 1])
    proto_tail = '\n'.join(pl[next(i for i, l in enumerate(pl) if l == 'try {'):])
    creator_hook = next(l for l in pl if 'renderCreator();   // v1.38d' in l)

    # ── 补丁 A：3d 骰子路径
    L = sub_once(L, "await import('/static/dice3d/dice-bridge.js')",
                 "await import('./3d骰子/dice-bridge.js')", 'A 3d 路径')
    # ── 补丁 B：toast 本地实现
    L = sub_once(L, '/* ── 轻提示：由下方桥接层统一定义（服务端消息 + 本地提醒共用） ── */',
                 proto_toast, 'B toast')
    # ── 补丁 C：重置存档（连同附属记录）
    L = sub_once(L, "    localStorage.removeItem(KEY);\n    load();",
                 proto_reset + "\n    load();", 'C 重置')
    # ── 补丁 D：导出/导入按钮
    L = sub_once(L, '      <button class="btn sm" onclick="exportSave()">导出快照</button>\n'
                    '      <button class="btn sm" onclick="importSaveFile()">导入存档</button>\n'
                    '      <button class="btn sm" onclick="importSave()">数据说明</button>',
                 '      <button class="btn sm" onclick="exportSave()">导出</button>\n'
                 '      <button class="btn sm" onclick="importSave()">导入</button>', 'D 按钮')
    # ── 补丁 E：数据说明
    L = sub_once(L, '      数据保存在电脑的 SQLite 数据库（Flask版/data/adventurer.db）；<b>每台设备有独立账号与存档</b>，\n'
                    '      换设备用下方「账号」卡里的接入码找回。<br>\n'
                    '      备份：复制该 .db 文件即可；「导出快照 / 导入存档」的 JSON 可与原型创造版互通（方便测试）。',
                 '      数据保存在本浏览器（localStorage），换浏览器/设备不互通。<br>\n'
                 '      建议定期「导出」备份，或在不同设备间手动搬运。', 'E 说明')
    # ── 补丁 F：无账号卡
    text = '\n'.join(L)
    fi = text.find('  // ── 账号（v1.37')
    assert fi > 0
    fj = text.find('\n\n', text.find('</div>`;\n  }', fi))
    block = text[fi:fj]
    assert '账号' in block and len(block) < 2000, '账号卡块定位异常'
    L = (text[:fi] + text[fj + 2:]).split('\n')
    # ── 补丁 H：creator 钩子
    L = sub_once(L, '    document.getElementById("tab-"+b.dataset.t).classList.add("on");',
                 '    document.getElementById("tab-"+b.dataset.t).classList.add("on");\n' + creator_hook, 'H creator')
    # ── 补丁 G：尾部启动段
    new_main = '\n'.join(L).rstrip('\n') + '\n\n' + proto_tail

    new_file = pt[:pi0 + 8] + new_main + pt[pi1:]
    io.open(OUT, 'w', encoding='utf-8', newline='\n').write(new_file)
    print('dry-run 完成：%s（原 %d 行 → 新 %d 行；主块 %d 行 → %d 行）'
          % (OUT, pt.count('\n') + 1, new_file.count('\n') + 1,
             pcode.count('\n') + 1, new_main.count('\n') + 1))
    if '--apply' in sys.argv:
        shutil.copy(PROTO, PROTO + '.bak_sync')
        io.open(PROTO, 'w', encoding='utf-8', newline='\n').write(new_file)
        print('已应用：%s（备份 %s.bak_sync）' % (PROTO, PROTO))


if __name__ == '__main__':
    main()
