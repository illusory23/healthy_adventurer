/* ══════════════════════════════════════════════════════════════
   数据表生成器（v1.41）
   从原型《健康的冒险者的一天.html》提取最新数据 → 输出 UTF-8(BOM) CSV
   运行：node 数据表/_生成数据表.js
   （每次游戏数据更新后重跑本脚本，即可让全部数据表同步到最新）
   ══════════════════════════════════════════════════════════════ */
const fs = require('fs');
const path = require('path');

/* ── 极简浏览器 stub（供原型 eval；与冒烟测试同款）── */
global.localStorage = { _d: {}, getItem(k){ return this._d[k] ?? null; }, setItem(k,v){ this._d[k]=v; }, removeItem(k){ delete this._d[k]; } };
const fakeEl = () => ({ textContent:"", innerHTML:"", style:{}, value:"", classList:{add(){},remove(){},contains(){return false}}, onclick:null, focus(){}, addEventListener(){}, dataset:{}, querySelectorAll(){return[]} });
const elCache = {};
global.document = { getElementById:(id)=>(elCache[id]=elCache[id]||fakeEl()), querySelector:()=>fakeEl(), querySelectorAll:()=>[], addEventListener:()=>{} };
global.alert = () => {}; global.confirm = () => true; global.setInterval = () => 0;

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, '创造模式测试原型', '健康的冒险者的一天.html'), 'utf-8');
const code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const EXPO = ["CFG","M","GEAR","LEGEND","ACHV","ACHV_DESC","MAT_DESC","MAT_USE","ITEM_DESC",
  "SKILLS","SKILL_COST","MONTH_EVENTS","REGIONS","C","SHOP","VIT_SHOP","CON_SHOP","PLAT_SHOP",
  "MASTER_SHOP","BP_SHOP","QUALITY_ORDER","MORDER","QUEST_REQ","QUEST_TURNIN","CHARM","MAT_ICON",
  "WOLF_STAGES","PET_LINES","PET_FIXED","TITLE_DESC","FESTIVALS","FESTIVAL_RANGES","CN_FEST_META","CN_LUNAR_FEST","FEST_EFF",
  "CRAFT","QUEST_ITEM"];
const FN = ["fmtMoney","fmtDur","cookTier","gearMainTxt","legendRep"];
eval(code + "\n;global.__DS = {" +
  EXPO.map(function(k){ return k + ":" + k; }).join(",") + "," +
  FN.map(function(k){ return k + ":" + k; }).join(",") + "};");
const D = global.__DS;

/* ── CSV 工具 ── */
function esc(v){ v = String(v == null ? "" : v); return /[",\r\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
function csv(file, header, data){
  const lines = [header.join(",")].concat(data.map(function(r){ return r.map(esc).join(","); }));
  fs.writeFileSync(path.join(__dirname, file), "﻿" + lines.join("\r\n"), "utf-8");
  console.log("  " + file + "：" + data.length + " 行");
}
function fmtIng(ing){   // {名:数量 或 [min,max]} → "名×3、名×2~4"
  return Object.keys(ing||{}).map(function(k){
    const v = ing[k];
    return k + "×" + (Array.isArray(v) ? (v[0] === v[1] ? v[0] : v[0]+"~"+v[1]) : v);
  }).join("、");
}
const QI = function(q){ return D.QUALITY_ORDER.indexOf(q); };

console.log("生成数据表 → " + __dirname);

/* ── ① 材料总表（含介绍 / 品类用途）── */
csv("材料总表.csv",
  ["材料名","品类","品阶","基准价","介绍","品类用途"],
  Object.keys(D.M).sort(function(a,b){
    return D.MORDER.indexOf(D.M[a][0]) - D.MORDER.indexOf(D.M[b][0]) || QI(D.M[a][1]) - QI(D.M[b][1]);
  }).map(function(k){
    const _cats = D.M[k][3] ? D.M[k][0] + " / " + D.M[k][3].join(" / ") : D.M[k][0];   // v1.48c：多品类展示
    return [k, _cats, D.M[k][1], D.fmtMoney(D.M[k][2]), D.MAT_DESC[k]||"", D.MAT_USE[D.M[k][0]]||""];
  }));

/* ── ② 装备总表（85 件 · 含来源）── */
const _masterGear = {}; (D.MASTER_SHOP.gear||[]).forEach(function(x){ _masterGear[x.n] = x; });
const _achvOf = {}; D.ACHV.forEach(function(a){ if(a.gear) _achvOf[a.gear] = a.n; });
csv("装备总表.csv",
  ["装备名","品质","槽位","主属性","副属性","主材料","来源"],
  D.GEAR.map(function(g){
    let src;
    if(g[5] !== "—"){
      const info = D.BP_SHOP[g[1]];
      src = "打造 · 图纸：" + g[1] + "档（公会 " + D.CFG.guildName[info.guild] + " 级）";
    } else if(_masterGear[g[0]]){
      src = "大师商店购入（成就「大师」解锁）";
    } else if(_achvOf[g[0]]){
      src = "成就奖励（成就「" + _achvOf[g[0]] + "」）";
    } else {
      src = "特殊获得";
    }
    return [g[0], g[1], g[2], D.gearMainTxt(g), g[4], g[5], src];
  }));

/* ── ③ 图纸总表 ── */
csv("图纸总表.csv",
  ["图纸名","对应装备","品质","解锁公会","价格"],
  D.GEAR.filter(function(g){ return g[5] !== "—"; }).map(function(g){
    const info = D.BP_SHOP[g[1]];
    return [g[0] + "图纸", g[0], g[1], D.CFG.guildName[info.guild] + " 级", info.price + " " + info.cur];
  }));

/* ── ④ 委托总表（130 条 · 含链前置 / 上交 / 多日）── */
const _qRows = [];
D.CFG.levels.forEach(function(lv, i){
  (D.C[lv] || []).forEach(function(q){
    const rate0 = Math.min(D.CFG.hardCap[i], Math.max(D.CFG.floor[i], D.CFG.sucBase[i] + (D.CFG.diffMod[q[4]] || 0)));
    let cond = "";
    if(D.QUEST_REQ[q[0]]) cond += "链条：需先完成「" + D.QUEST_REQ[q[0]] + "」";
    if(D.QUEST_TURNIN && D.QUEST_TURNIN[q[0]]) cond += (cond ? "；" : "") + "资源指定：持有「" + D.QUEST_TURNIN[q[0]] + "」→ 结算自动上交，报酬翻倍";
    if(q[3] >= 4300) cond += (cond ? "；" : "") + "追踪类：3 天多日委托（跨天次日结算）";
    _qRows.push([lv, q[0], q[1], q[2], D.fmtDur(q[3]), q[4], Math.round(rate0*100) + "%",
      D.fmtMoney(q[5]), q[6], q[7], fmtIng(q[8]), cond]);
  });
});
csv("委托总表.csv",
  ["等级","委托名","标签","时间窗","耗时","难度","基础成功率","报酬","经验","精力","材料","特殊条件"], _qRows);

/* ── ⑤ 商店商品（6 商店 + 交易所规则）── */
const _sRows = [];
D.SHOP.forEach(function(it){ _sRows.push(["公会商店","E","铜币", it.n, D.fmtMoney(it.c), it.lim ? ("每" + it.lim[0] + " " + it.lim[1]) : "—", it.d||""]); });
D.VIT_SHOP.forEach(function(it){ _sRows.push(["活力点商店","—","活力点", it.n, it.vit + " 点", "—", it.d||""]); });
D.CON_SHOP.forEach(function(it){ _sRows.push(["贡献商店","D","贡献", it.n, it.con + " 贡献", it.lim ? ("每" + it.lim[0] + " " + it.lim[1]) : "—", (it.g ? ("公会 " + D.CFG.guildName[it.g] + " 级解锁　") : "") + (it.d||"")]); });
D.PLAT_SHOP.forEach(function(it){ _sRows.push(["铂金商店","S", it.goldC ? "金币" : "铂金币", it.n, it.goldC ? (it.goldC + " 金币") : (it.platC + " 铂金币"), it.lim ? ("每" + it.lim[0] + " " + it.lim[1]) : "—", (it.sel ? it.sel.join(" / ") : "规则道具：当日健康锁定 100 分")]); });
(D.MASTER_SHOP.gear||[]).forEach(function(x){ _sRows.push(["大师商店","成就「大师」","铂金币+材料", x.n, x.platC + " 铂金币 + " + fmtIng(x.mats), "一次性", x.desc||""]); });
_sRows.push(["大师商店","成就「大师」","铂金币", "指定传说材料 ×2", "6 铂金币", "每周 1", D.PLAT_SHOP[0].sel.join(" / ")]);
_sRows.push(["大师商店","成就「大师」","铂金币", "大师的馈赠（活力点 +500）", "20 铂金币", "不限", "终局活力点出口"]);
_sRows.push(["交易所","E","金币/银币", "买入材料（买入价 = 卖出价 ×3）", "—", "—", "仅普通 / 精良 / 稀有；史诗走贡献商店、传说走铂金商店"]);
csv("商店商品.csv",
  ["商店","解锁","货币","商品","价格","限购","说明"], _sRows);

/* ── ⑥ 料理总表（21 道 · 品阶门槛）── */
csv("料理总表.csv",
  ["料理","品阶","开放等级","配方","效果","生效方式"],
  D.CFG.recipes.map(function(r){
    const t = D.cookTier(r);
    const mode = (r.bonus || r.rate) ? "接取前最后食用生效" : (r.cap ? "当日精力上限" : "即时");
    return [r.n, t, "Lv" + (QI(t) + 1), fmtIng(r.ing), r.desc || "", mode];
  }));

/* ── ⑦ 传奇事件总表（12 个 · 含静态条件）── */
function _legendCond(L){
  const c = L[8] || {};
  if(c.q) return "需完成前置委托「" + c.q + "」";
  if(c.q40) return "累计完成 40 次 Lv5 以下委托";
  if(c.sleep30) return "最近 30 天 ≥27 天 23:30 前入睡";
  if(c.legend) return "需完成传奇事件「" + c.legend + "」";
  if(c.allLegend) return "完成其余全部 11 个传奇事件";
  return "—";
}
csv("传奇事件总表.csv",
  ["事件名","标签","耗时(天)","难度","报酬","经验","声望","必得材料","奖励","专属条件","低语预览"],
  D.LEGEND.map(function(L){
    return [L[0], L[1], L[2], L[3], L[4], L[5], D.legendRep(L), L[6] || "—", L[7] || "—", _legendCond(L), "✅ 可窥见"];
  }));

/* ── ⑧ 成就总表（17 条）── */
csv("成就总表.csv",
  ["成就","达成条件","奖励","可见性"],
  D.ACHV.map(function(a){
    let reward = "—";
    if(a.gear) reward = "成就饰品「" + a.gear + "」";
    else if(a.title) reward = "称号「" + a.title + "」";
    return [a.n, D.ACHV_DESC[a.n] || "—", reward, a.hide ? "隐藏（达成前不可见）" : "常显"];
  }));

/* ── ⑨ 探索区域总表（16 个 · 含门槛与掉落）── */
csv("探索区域总表.csv",
  ["区域","开放时间","探索点","耗时","门槛","掉落（概率）"],
  D.REGIONS.map(function(r){
    const gate = [];
    if(r.unlock) gate.push("完成委托「" + r.unlock.quest + "」");
    if(r.g !== undefined) gate.push("公会 " + D.CFG.guildName[r.g] + " 级");
    if(r.lv) gate.push("冒险者 Lv" + r.lv);
    if(r.deep) gate.push("深处层");
    const drops = (r.d || []).filter(function(p){ return p[0]; }).map(function(p){ return p[0] + " " + p[1] + "%"; }).join(" / ");
    return [r.n, r.t, r.c, r.h + "h", gate.length ? gate.join(" + ") : "—", drops];
  }));

/* ── ⑩ 月度世界事件表（12 个月池）── */
csv("月度世界事件表.csv",
  ["月份","事件","进度类型","需要","奖励金币","奖励材料","当月称号","描述"],
  D.MONTH_EVENTS.map(function(e){
    const tTxt = e.t === "task" ? "规律打卡日" : (e.t === "quest" ? "完成委托" : "探索次数");
    return [e.m + " 月", e.n, tTxt, e.need, D.fmtMoney(e.gold), fmtIng(e.mats), e.title, e.desc];
  }));

/* ── ⑪ 技能树表 ── */
csv("技能树表.csv",
  ["技能","效果","Lv1~Lv5 贡献消耗","核心条件"],
  D.SKILLS.map(function(s){
    return [s.n, s.d, D.SKILL_COST.join(" → ") + "（每级消耗）", s.tag ? ("吃「" + (Array.isArray(s.tag) ? s.tag.join("/") : s.tag) + "」类委托加成") : "通用"];
  }));

/* ── ⑫ 道具总表 ── */
const _itemSrc = {};
D.SHOP.forEach(function(it){ if(it.item) _itemSrc[it.item] = "公会商店（" + D.fmtMoney(it.c) + "）"; });
D.VIT_SHOP.forEach(function(it){ if(it.item) _itemSrc[it.item] = (_itemSrc[it.item] ? _itemSrc[it.item] + " / " : "") + "活力点商店（" + it.vit + " 点）"; });
D.CON_SHOP.forEach(function(it){ if(it.item) _itemSrc[it.item] = (_itemSrc[it.item] ? _itemSrc[it.item] + " / " : "") + "贡献商店（" + it.con + " 贡献）"; });
Object.keys(D.CRAFT).forEach(function(k){   // v1.46：准备物可合成（追加来源）
  _itemSrc[k] = (_itemSrc[k] ? _itemSrc[k] + " / " : "") + "炼金台合成";
});
csv("道具总表.csv",
  ["道具","效果说明","获取途径"],
  Object.keys(D.ITEM_DESC).map(function(k){
    return [k, D.ITEM_DESC[k], _itemSrc[k] || "探索 / 事件掉落"];
  }));

/* ── ⑬ 节日总表（v1.41f：公历单日 + 假期区间 + 农历节日 + 专属效果）── */
function festEff(matcher){ const e = D.FEST_EFF[matcher] || {}; return e.desc || "—"; }
const _festRows = [];
function frow(name, type, rule, d2026, greet, eff, note){ _festRows.push([name, type, rule, d2026, greet, eff, note]); }
/* 公历单日（1 天） */
Object.keys(D.FESTIVALS).sort().forEach(function(mmdd){
  const f = D.FESTIVALS[mmdd];
  frow(f[0], "公历单日", "每年 " + mmdd, "2026-" + mmdd, "节日快乐", festEff(f[0]), f[1] || "");
});
/* 公历假期区间 */
D.FESTIVAL_RANGES.forEach(function(r){
  frow(r[2], "公历区间", "每年 " + r[0] + " ~ " + r[1] + "（整段每天生效）", "2026-" + r[0] + " ~ 2026-" + r[1], "节日快乐", festEff(r[2]), r[3] || "");
});
/* 农历节日（2026 年日期取自 CN_LUNAR_FEST；日期规则为农历固定/节气） */
const _lunar2026 = {};
(D.CN_LUNAR_FEST["2026"] || "").split("|").forEach(function(item){
  const d = item.slice(0, 5), n = item.slice(6);
  (_lunar2026[n] = _lunar2026[n] || []).push(d);
});
const _lunarRule = {
  "除夕": "农历腊月最后一天", "春节": "农历正月初一 ~ 初六", "元宵节": "农历正月十五",
  "清明节": "清明节气（公历 4-04 / 4-05 前后）", "端午节": "农历五月初五", "七夕节": "农历七月初七",
  "中秋节": "农历八月十五", "重阳节": "农历九月初九", "腊八节": "农历腊月初八", "小年": "农历腊月廿三"
};
Object.keys(D.CN_FEST_META).forEach(function(k){
  const meta = D.CN_FEST_META[k];
  const ds = _lunar2026[k] || [];
  const dstr = ds.length > 1
    ? ("2026-" + ds[0] + " ~ 2026-" + ds[ds.length-1] + "（" + ds.length + " 天）")
    : (ds[0] ? "2026-" + ds[0] : "—");
  frow(meta[0], "农历单日", _lunarRule[k] || "农历", dstr, meta[1], festEff(meta[0]), meta[2] || "");
});
_festRows.sort(function(a, b){ return a[3] < b[3] ? -1 : (a[3] > b[3] ? 1 : 0); });
csv("节日总表.csv",
  ["节日","类型","日期规则","2026 年日期","问候语","专属效果（v1.41f）","备注（基础机制：接取窗口 +1 小时 / 三餐 ±30 分钟 / 入睡·起床打卡尾部 +1 小时）"],
  _festRows.map(function(r){ return [r[0], r[1], r[2], r[3], r[4], r[5], r[6]]; }));

/* ── ⑭ 宠物总表（小狼成长链 + 八条养成线 + 品阶；v1.55b：品阶列 / 阅读驱动文案）── */
function petBonusTxt(s){
  const b = [];
  if(s.mat) b.push("材料掉落 +" + Math.round(s.mat * 100) + "%");
  if(s.rate) b.push("成功率 +" + Math.round(s.rate * 100) + "%");
  if(s.sp) b.push("探索点 +" + s.sp + "/天");
  if(s.pay) b.push("委托报酬 +" + Math.round(s.pay * 100) + "%");
  if(s.exp) b.push("经验 +" + Math.round(s.exp * 100) + "%");
  return b.length ? b.join("、") : "—";
}
const _petRows = [];
/* 小狼成长链（探索事件「受伤小狼」；喂食材料成长） */
D.WOLF_STAGES.slice(1).forEach(function(s, i, arr){
  _petRows.push(["🐺 " + s.name, "史诗", "小狼成长链", petBonusTxt(s),
    s.need ? ("成长值 " + s.need + " → " + (arr[i+1] ? arr[i+1].name : "—")) : "成长值满后进入「变异值」积累期",
    "探索事件「受伤小狼」（喂食材料积累成长值）"]);
});
/* 可喂养链（3 阶段 + 变异） */
Object.keys(D.PET_LINES).forEach(function(n){
  const L = D.PET_LINES[n];
  L.stages.forEach(function(s, i){
    const nxt = i < L.stages.length - 1 ? L.stages[i+1].name : "变异期";
    let prog;                                   // v1.55b：阅读驱动 = 阅读次数进级；三阶可无成长要求
    if(s.need === null || s.need === undefined) prog = "无成长要求 → " + nxt;
    else prog = (L.readDriven ? ("阅读 " + s.need + " 次") : ("成长值 " + s.need)) + " → " + nxt;
    _petRows.push([L.icon + " " + s.name, L.rank || "—", "成长链（" + n + "）", petBonusTxt(s), prog, L.from]);
  });
  _petRows.push([L.icon + " " + L.mut.name, L.rank || "—", "成长链（" + n + "·变异）", petBonusTxt(L.mut),
    (L.readDriven ? "变异值累计 " : "变异期累计 ") + L.need + " → 变异", "同上（" + L.mut.note + "）"]);
});
/* 固定加成宠物（传奇 / 事件授予） */
Object.keys(D.PET_FIXED).forEach(function(n){
  const F = D.PET_FIXED[n];
  _petRows.push(["🐾 " + n, F.rank || "—", "固定加成", petBonusTxt(F), "—（无成长阶段）", F.note || "传奇事件 / 事件授予"]);
});
csv("宠物总表.csv", ["宠物","品阶","类别","加成","成长 / 阶段","来源"], _petRows);

/* ── ⑮ 称号总表（图鉴收集 / 隐藏成就 / 当月 / 月度世界事件 / 传奇事件 / 公会里程碑）── */
const _titleCat = {
  "博物学家·银": ["图鉴收集", "材料收集 ≥50%"], "博物学家·金": ["图鉴收集", "材料收集 ≥80%"],
  "军械大师·银": ["图鉴收集", "装备收集 ≥50%"], "军械大师·金": ["图鉴收集", "装备收集 ≥80%"],
  "博物学家": ["图鉴集齐", "材料图鉴集齐"], "军械大师": ["图鉴集齐", "装备图鉴集齐"],
  "宫廷主厨": ["图鉴集齐", "料理图鉴集齐"], "传说冒险者": ["图鉴集齐", "委托图鉴全数完成"],
  "常青": ["隐藏成就", "成就「周全绿」"], "归夜者": ["隐藏成就", "成就「夜猫子的救赎」"],
  "恒行者": ["隐藏成就", "成就「滴水穿石」"], "万卷": ["隐藏成就", "成就「书中自有」"],
  "传奇旅人": ["隐藏成就", "成就「传奇之旅」"], "满仓": ["隐藏成就", "成就「囤积家」"],
  "安眠守护者": ["当月称号", "月打卡·早睡黄金（30 天内有效）"], "公会中坚": ["当月称号", "月打卡·委托黄金（30 天内有效）"],
  "作息守护者": ["当月称号", "连续 30 天规律作息（30 天内有效）"]
};
function titleEffect(n){
  if(n === "安眠守护者") return "健康加成 +2pp（当月）";
  if(n === "公会中坚" || n === "作息守护者") return "委托报酬 +5%（当月）";
  return "纯荣誉称号（收集加成：每 1 个 +1% 报酬，上限 +10%）";
}
const _titleRows = [];
Object.keys(D.TITLE_DESC).forEach(function(n){
  const c = _titleCat[n] || ["称号", ""];
  _titleRows.push([n, c[0], titleEffect(n), c[1] || D.TITLE_DESC[n]]);
});
D.MONTH_EVENTS.forEach(function(e){
  _titleRows.push([e.title, "月度世界事件", titleEffect(e.title),
    "完成月度世界事件「" + e.n + "」（" + e.desc + "，报酬 " + D.fmtMoney(e.gold) + "）"]);
});
D.LEGEND.forEach(function(L){
  const m = /称号「(.+?)」/.exec(L[7] || "");
  if(m) _titleRows.push([m[1], "传奇事件", titleEffect(m[1]), "完成传奇事件「" + L[0] + "」"]);
});
[["世界行者", 7], ["英雄", 8], ["至尊", 9]].forEach(function(p){
  _titleRows.push([p[0], "公会里程碑", titleEffect(p[0]), "公会等级 " + D.CFG.guildName[p[1]] + "（" + D.CFG.guildReq[p[1]] + " 声望）"]);
});
csv("称号总表.csv", ["称号","类别","效果","来源"], _titleRows);

/* ── ⑯ 参数速查（分组键值）── */
const P = [];
function p(cat, k, v){ P.push([cat, k, v]); }
p("货币","换算","1 铂金 = 100 金 = 10,000 银 = 1,000,000 铜");
p("货币","交易所买入","买入价 = 卖出价 ×3（仅普通/精良/稀有）");
p("等级","Lv1~Lv5 基础成功率 B", D.CFG.sucBase.map(function(x){ return Math.round(x*100)+"%"; }).join(" / "));
p("等级","Lv1~Lv5 E 上限", D.CFG.eCap.map(function(x){ return Math.round(x*100)+"%"; }).join(" / "));
p("等级","Lv1~Lv5 硬上限 Cap", D.CFG.hardCap.map(function(x){ return Math.round(x*100)+"%"; }).join(" / "));
p("等级","Lv1~Lv5 最低 Floor", D.CFG.floor.map(function(x){ return Math.round(x*100)+"%"; }).join(" / "));
p("等级","升级所需累计经验", D.CFG.expNeed.join(" / "));
p("等级","Lv1~Lv5 精力上限", D.CFG.energyMax.join(" / "));
p("等级","Lv1~Lv5 单次抽取数", D.CFG.drawCount.join(" / "));
p("委托","每日接取上限","4 次（公会有额外委托 +1）");
p("委托","刷新点","" + D.CFG.refreshHours.join(" / ") + " 点（常规 1 小时内可接；最后一次 21:00~23:30——v1.41f3；节日各 +1 小时）");
p("委托","成功率公式","min(Cap, max(Floor, B + D + Δ + 健康×0.2% + E + N))");
p("委托","难度修正","简单 +10% / 普通 0 / 困难 −10% / 噩梦 −20%");
p("委托","等级差修正 Δ","每高 1 级 +12pp，上限 +36pp");
p("委托","熬夜惩罚 N","−15%（未熬夜 0）");
p("传奇","出现概率","每日 8:00 判定 15%（冥念护符满级 +5%）");
p("传奇","低语预览","未达资格时每日 2% 概率窥见（红字迹象 → 风味窗 → 不可参与）");
p("传奇","成功率公式","min(65%, max(5%, 5% + D + 健康×0.5% + E(≤10%) + 护符/饰品)）");
p("传奇","每周接取","每周 1 次（公会 P 级「至尊」2 次）");
p("传奇","全局资格","Lv5 + 经验≥30000 + 公会 A + 近 7 天均分≥60 + 近 30 天早睡≥25");
p("公会","F~P 各等级声望", D.CFG.guildName.map(function(n, i){ return n + ":" + D.CFG.guildReq[i]; }).join(" / "));
p("公会","技能树上限", "F~S：0/0/5/10/15/20/25（W/H/P 保持 25）");
p("探索","每日次数","2 次；前一日健康 <60 当日不可探索");
p("探索","区域门槛","委托解锁 / 公会等级 / 等级（三重判定，未解锁区域不显示）");
p("酒馆料理","品阶开放","Lv1 普通 / Lv2 精良 / Lv3 稀有 / Lv4 史诗 / Lv5 传说（v1.41f4：公会厨房迁入酒馆）");
p("商店","可见性","未解锁内容完全隐藏（贡献 D / 铂金 S / 大师 成就 / 图纸档位按等级 / 护符级别）");
p("护符","冥念护符 Lv1~Lv5 消耗", D.CHARM.map(function(c){ return c.cost; }).join(" / ") + " 活力点");
p("护符","冥念护符 Lv1~Lv5 报酬", D.CHARM.map(function(c){ return Math.round(c.pay*100)+"%"; }).join(" / "));
p("护符","冥念护符 Lv1~Lv5 成功率", D.CHARM.map(function(c){ return Math.round(c.rate*100)+"%"; }).join(" / "));
p("护符","解锁条件", "各级：公会 C/B/A/S + V 需完成 ≥1 次传奇事件");
p("大师层","解锁","完成 ≥4 个不同传奇事件 → 成就「大师」+ 大师徽章（活力点获取 +10%）");
p("大师层","大师商店","大师之证 18 铂金+星核×3 / 宗师手套 16 铂金+世界树心×3 / 终焉披风 16 铂金+龙心×3 / 传说材料×2 6 铂金·周1 / 活力点+500 20 铂金");
p("图鉴","分层称号","材料/装备收集 50%「·银」/ 80%「·金」/ 100% 集齐称号");
p("称号","收集加成","每 1 个永久称号 +1% 委托报酬（上限 +10%）");
p("时间","日界线","早 6:00（00:00~05:59 属前一游戏日）");
p("时间","委托截止","23:30 后不能发起新委托");
p("节日","假期区间","国庆 10-01~10-07 整段按节日生效（v1.41c；其余为单日节日）");
p("节日","窗口延长","接取窗口 +1 小时 / 三餐打卡前后各 +30 分钟 / 入睡·起床打卡尾部 +1 小时（v1.41c）");
p("节日","专属效果","逐节日差异化加成（v1.41f）——国庆报酬成功率 / 清明采集探索率 / 腊八料理翻倍 / 重阳探索翻倍等，17 个节日详见《节日总表》");
csv("参数速查.csv", ["分类","条目","值"], P);

/* ── ⑰ 势力与种族总表（v1.45：六色龙 / 恶魔 / 魔鬼 / 中立与敌对种族；引用自动校验）── */
const _qnames = new Set(); Object.keys(D.C).forEach(function(lv){ (D.C[lv]||[]).forEach(function(q){ _qnames.add(q[0]); }); });
const _FACTIONS = [
  ["龙族（六色龙）","中立",
   "六色龙各据一方：绿龙牧毒雾、火龙焚山脊、白龙求知、金龙重契、蓝龙驭雷、黑龙游影。龙材是终局料理与神兵的核心，猎龙悬赏从不缺勇者。",
   ["狩猎火龙","驱赶绿龙","与白龙探讨魔法","金龙宝藏的谈判","平息蓝龙之怒","追踪黑龙的阴翳","弑龙者","古龙遗骸采集","巨龙巢穴侦察","猎杀双足飞龙","龙血商人的订单","龙巢外围巡查"],
   ["金龙鳞","龙炎结晶","魔力结晶","雷霆龙牙","暗影龙鳞","剧毒龙牙","绿龙胆囊","龙鳞","龙骨","龙血","龙牙","龙角","龙心","巨龙竖瞳","大块龙肉"]],
  ["深渊恶魔","敌对",
   "深渊领主封印之后漏网的低阶恶魔与裂隙造物，黑雾过处生机断绝。恶魔之角与混沌碎片，是它们存在过的唯一证据。",
   ["镇压恶魔裂隙","猎杀深渊恶魔","血战遗迹考察","深渊领主封印","潜入深渊神殿","深渊回响·远征"],
   ["恶魔之角","混沌碎片","暗影草"]],
  ["地狱魔鬼","敌对（可缔约）",
   "地狱的驻使与放贷者，以契约为兵刃。硫磺是它的气味，灵魂币是它的通货——与魔鬼谈生意，遗嘱要先写好。深渊之下的熔炉永不熄火，王座上的那位只与念得完炉膛名字的人谈价。",
   ["魔鬼的谈判","地狱钟声","血战遗迹考察","硫磺深渊·探井","地狱熔炉"],
   ["魔鬼徽记","灵魂币","硫磺结晶","混沌碎片"]],
  ["九头蛇","中立（凶兽）",
   "湖底多头巨蛇，断首即生双首。毒液浸透巢域，讨伐它需要的不只是剑——还有解毒剂与退路。",
   ["讨伐九头蛇","沼心巨蟒"],
   ["九头蛇心脏","九头蛇鳞片","剧毒蛇齿","九头蛇胆囊","再生蛇髓"]],
  ["亡灵","敌对",
   "执念不散者。雾起时谷中灯火自熄——亡灵谷的浓雾，便是它们的哀鸣。墓道深处另有一条回廊，两侧刻着同一张脸：那是死者自己认路的地方。",
   ["净化亡灵谷","魂灯引渡","古墓封印","亡者回廊·踏勘","亡者回廊·镇魂","幽都渡口"],
   ["幽魂灯","暗影草","星尘"]],
  ["仙灵 / 妖精","中立（友善）",
   "林间微光之民，性情好奇，知恩必报。迷路的仙灵会记得你的善意——并以森林从不示人的秘密相报。",
   ["迷路的仙灵","仙灵的谢礼"],
   ["仙灵之尘","紫藤花","晨露花"]],
  ["巨人族 / 泰坦遗脉","中立",
   "远古泰坦的血裔，身形如山，行事直接。独眼巨人性烈如火；泰坦遗骸里，沉睡着上一个时代的重量——有人听见那颗心还在跳。",
   ["讨伐独眼巨人","独眼巨人的石碑","泰坦遗骸发掘","泰坦之心"],
   ["巨人骨","陨铁","星核"]],
  ["哥布林 / 地精","敌对",
   "边境的劫掠者与偷粮贼，单只不足惧，成群则成灾。哥布林图腾是它们的信仰，也是猎人的军功凭证。",
   ["讨伐哥布林","驱赶偷粮地精"],
   ["哥布林图腾"]],
  ["半兽人","敌对",
   "凶悍的边境部族，营寨依山而建。侦察易，强攻难——公会的行动指令永远是「先看清楚」。",
   ["半兽人营地侦察"],
   ["粗麻布","野猪獠牙"]],
  ["魔狼与荒野兽群","敌对",
   "狼群记仇，也记恩。远古巨狼记得每一个伤害过它族群的猎人——而月色之下，狼嚎就是最好的警报。",
   ["狼群驱赶","暮色狼群清剿","月下狼嚎追踪","猎杀远古巨狼"],
   ["狼牙","魔狼鬃毛","兽肉"]],
  ["枭熊与猛禽","敌对",
   "枭熊守巢，双头狮鹫巡天。枭羽轻而韧，风蚕丝韧而滑——都是猎人最爱的战利品。",
   ["枭熊巢穴讨伐","猎杀双头狮鹫"],
   ["枭羽","风蚕丝"]],
  ["石魔像与元素","中立（无智）",
   "矿脉深处沉睡的守陵者与元素领主。它们不问来者是善是恶，只问来者是否越界。",
   ["讨伐石魔像","元素领主讨伐"],
   ["青石","石英","陨铁","星核"]],
  ["沼泽异种（蛇怪 / 巨蛛）","敌对",
   "腐化森林与沼泽的住民：石化蜥蜴的凝视、巨蛛的丝网、蛇怪的毒牙——它们的共同语言是「别靠近」。沼心塌陷处盘着一条巨蟒，鳞下压着半座沉村。",
   ["沼泽蛇怪狩猎","石化蜥蜴巢穴","猎杀巨型蜘蛛","毒沼腹地·踏勘","沼心巨蟒"],
   ["蛇怪之眼","风蚕丝","剧毒蛇齿","九头蛇鳞片","净化石"]],
  ["海怪与深水","中立（凶兽）",
   "沉船与暗流之间游弋的庞然身影。船长们出价悬赏它的行踪，却没人愿意正面遭遇——船骸裂缝里伸出的，只是它的手指。",
   ["海怪追踪","深海船骸","海渊之主"],
   ["蛇怪之眼","九头蛇鳞片","月长石","混沌碎片"]],
  ["圣兽","中立（祥瑞）",
   "雪原之上的古老瑞兽，不伤人、不避人，只考验来者。驯服它靠的不是绳索，是耐心；沿着旧蜕走完一圈，才配说见过雪原。",
   ["圣兽驯服","雪原巡礼"],
   ["圣兽之蜕","魔狼鬃毛","月长石"]],
  ["星界存在","中立 / 敌对",
   "星穹的信使与噬星者：一个带来远方的信件，一个吞吃星星的碎屑。它们证明星空比其他任何地方都更「活着」。",
   ["星界信使·初见","星界信使·传讯","星界信使·回响","噬星者讨伐"],
   ["星界尘","星尘结晶","星核","虚空结晶"]],
  ["盗匪与黑市","敌对（人类势力）",
   "王法之外的生意人。追捕盗匪追的是刀，黑市追缉追的是人——而赃物，往往比悬赏更值钱。",
   ["追捕盗匪","黑市追缉","潜入敌国要塞"],
   []],
];
const _factWarn = [];
_FACTIONS.forEach(function(f){
  f[3].forEach(function(n){ if(!_qnames.has(n)) _factWarn.push(f[0] + " 委托缺：" + n); });
  f[4].forEach(function(n){ if(!D.M[n]) _factWarn.push(f[0] + " 材料缺：" + n); });
});
csv("势力与种族总表.csv", ["种族/势力","阵营","简介","相关委托","相关材料"],
  _FACTIONS.map(function(f){ return [f[0], f[1], f[2], f[3].join("、"), f[4].length ? f[4].join("、") : "—"]; }));
if(_factWarn.length) console.log("  ⚠ 势力表引用校验：" + _factWarn.join("；"));
else console.log("  势力表引用校验：全部委托 / 材料引用有效 ✅");

/* ── ⑱ 委托准备物表（v1.46：任务门槛；v1.53：需求量随委托等级 Lv3→1 / Lv4→2 / Lv5→3；商店购买 + 炼金台合成）── */
const _qlvOf = (function(){
  const o = {};
  Object.keys(D.C).forEach(function(lv){ (D.C[lv]||[]).forEach(function(q){ if(o[q[0]] === undefined) o[q[0]] = lv; }); });
  return o;
})();
const _needOf = function(lv){ return lv === "Lv5" ? 3 : (lv === "Lv4" ? 2 : 1); };
{
  const _pbad = [];
  Object.keys(D.QUEST_ITEM).forEach(function(k){
    if(!_qnames.has(k)) _pbad.push("委托缺：" + k);
    if(!D.CRAFT[D.QUEST_ITEM[k]]) _pbad.push("配方缺：" + D.QUEST_ITEM[k]);
    if(!_qlvOf[k]) _pbad.push("等级缺：" + k);
  });
  if(_pbad.length) console.log("  ⚠ 准备物表引用校验：" + _pbad.join("；"));
  else console.log("  准备物表引用校验：全部委托 / 配方 / 等级引用有效 ✅");
}
csv("委托准备物表.csv",
  ["准备物","商店价","合成配方","接取消耗","适用委托","委托数"],
  Object.keys(D.CRAFT).map(function(n){
    const r = D.CRAFT[n];
    const qs = Object.keys(D.QUEST_ITEM).filter(function(k){ return D.QUEST_ITEM[k] === n; });
    const lvs = [];
    qs.forEach(function(k){ const lv = _qlvOf[k]; if(lv && lvs.indexOf(lv) < 0) lvs.push(lv); });
    lvs.sort();
    return [n, D.fmtMoney(r.buy),
      Object.keys(r.ing).map(function(k){ return k + "×" + r.ing[k]; }).join("、"),
      lvs.map(function(lv){ return lv + "→×" + _needOf(lv); }).join(" / "),
      qs.join("、"), qs.length];
  }));

console.log("全部完成 ✅（共 18 张表）");
