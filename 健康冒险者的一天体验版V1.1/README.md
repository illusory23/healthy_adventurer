# 《健康的冒险者的一天》· Flask 版

> 单机服务器架构：**Windows 电脑跑 Flask + SQLite**，电脑 / 手机（局域网）/ 异地（樱花穿透，见 [../10_远程访问.md](../10_远程访问.md)）访问；**每台设备独立账号与存档**（v1.37），跨设备用接入码找回。

## 快速开始

```bash
双击 run.bat          # 或命令行：python app.py
```

启动后：

| 设备 | 地址 |
|---|---|
| 电脑 | `http://localhost:5899`（免口令 · 首访自动认领旧档） |
| 手机（同一 WiFi） | `http://电脑IP:5899`（启动时会打印；首次需输访问口令） |
| 出门在外 | 樱花内网穿透域名（配置见 [10_远程访问.md](../10_远程访问.md)） |

iPhone：Safari 打开 → 分享 → 添加到主屏幕 → 全屏运行（v1.38b 起支持 PWA：独立窗口 + 应用图标）。

## 目录结构

```
Flask版/
├─ app.py                  # Flask 服务（端口 5899）+ API 路由 + 账号体系
├─ game.py                 # 游戏核心逻辑（Python 移植，与原型一致）
├─ db.py                   # SQLite 持久化：users 账号表 + event_log（复制即备份）
├─ test_game.py            # 核心逻辑测试（python test_game.py）
├─ test_api.py             # 端到端 API 测试（python test_api.py）
├─ tools_export_data.js    # 一次性工具：从原型 HTML 导出静态数据
├─ data/
│  ├─ static_data.json     # 静态数据（委托/材料/装备/传奇/区域/配方…）
│  └─ adventurer.db        # SQLite 存档（自动创建）
└─ static/
   ├─ game.html            # 前端 = 原型完整界面 + 桥接层
   └─ dice3d/              # 3D 物理骰子引擎（来自「尘封之卷」骰娘项目）
```

## 账号体系（v1.37）

- **设备静默登录**：每台设备首次访问自动创建独立账号，令牌 Cookie 记住 1 年
- **接入码**：每账号 8 位（如 `K7F2-9QZ3`），「冒险者信息 → 账号」页可复制；新设备输入即绑定 / 找回
- **旧档迁移**：升级前的单存档，由**本机（localhost）首次打开**自动继承
- **本机账号管理**：localhost 同页可查看全部账号（名字 / 接入码 / 最近登录）
- 访问口令门保留（防公网扫描）；账号数据在 `users` 表

## 架构说明

- **状态**：每账号一份 JSON 存 SQLite `users` 表 `data` 列（复制 `data/adventurer.db` 即完整备份）
- **补算引擎**：每次 API 请求前 `game.catch_up()`——逐日结算、精力恢复、刷新点重建、委托完成
  （护栏：单次最多补 7 天；幂等）
- **事件日志**：内存 + `event_log` 表双写（watermark 去重，按账号隔离）
- **结算结果**：后端入队 `state.results`，前端依次弹出（含 3D 骰子播放，播放失败自动回退）
- **静态数据**：由 `tools_export_data.js` 从原型提取，保证两边数值完全一致

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/state` | 全量状态 + 派生数据 + 账号信息（自动补算） |
| POST | `/api/action` | `{"action": "...", ...}`，返回新状态 |
| GET | `/api/accounts` | 本机账号管理（仅 localhost） |
| GET | `/api/logs` | 事件日志（最近 120 条，当前账号） |

动作清单：`name` `checkin` `multi` `use_item` `gale` `cook` `buy` `buy_vit` `buy_con`
`sell` `equip` `unequip` `craft` `blueprint` `skill` `charm` `accept` `accept_bonus`
`abandon` `explore` `take_legend` `results_ack` `yesterday_ack` `bind_code`（接入码换绑）

## 测试

```bash
python test_game.py     # 核心逻辑（484 项：补算/结算/掉落/周月/成就/宠物/图鉴…）
python test_api.py      # 端到端（93 项：流程/口令门/多账号…，使用独立 test_api.db）
```

## 与原型的关系

本版是原型（`../创造模式测试原型/健康的冒险者的一天.html`）的服务化移植：
- 数值、公式、掉落、周月打卡、成就等逻辑**与原型一致**（用同一批静态数据 + 逐条移植）
- 前端 `static/game.html` = 原型界面镜像 + 桥接层（同名函数后者覆盖）；账号体系为 Flask 独有
- 3D 骰子动画 `static/dice3d/` 直接复用原型同款引擎

## 常见问题

| 问题 | 处理 |
|---|---|
| 手机打不开 | 确认同一 WiFi；Windows 防火墙放行"专用网络"；异地用樱花穿透（见 10 号文档） |
| 端口冲突 | 改 `app.py` 末尾的 `port=5899`（空闲备选 8000/8080/8888） |
| 存档损坏 | 删除 `data/adventurer.db` 重新开始（或先备份；旧档可由本机首访自动迁移） |
| 换手机 / 清缓存后没了进度 | 用接入码找回：「冒险者信息 → 账号」→ 输入其他接入码 |
