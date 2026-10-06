// C1 双端公式对拍 · JS 侧：以确定输入跑原型公式，导出结果供 Flask版/_parity_check.py 对比
// 运行：node _parity_dump.js  → 生成 _parity_out.json 到本目录
const fs = require('fs');

global.localStorage = {
  _d: {},
  getItem(k){ return this._d[k] || null; },
  setItem(k,v){ this._d[k] = v; },
  removeItem(k){ delete this._d[k]; }
};
const fakeEl = () => ({
  textContent: "", innerHTML: "", style: {}, value: "",
  classList: { add(){}, remove(){}, contains(){ return false; } },
  onclick: null, focus(){}, addEventListener(){}, dataset: {},
  querySelectorAll(){ return []; }
});
const elCache = {};
const qsCache = {};
global.document = {
  getElementById: (id) => (elCache[id] = elCache[id] || fakeEl()),
  querySelector: (sel) => (qsCache[sel] = qsCache[sel] || fakeEl()),
  querySelectorAll: () => [],
  addEventListener: () => {}
};
global.alert = () => {};
global.confirm = () => true;
global.setInterval = () => 0;

// v1.50：对拍目标改为 Flask 前端（game.html 原型层 ↔ Flask 服务端）；桥接层截除不参与
const html = fs.readFileSync(__dirname + '/健康的冒险者的一天.html', 'utf-8');  // v1.51：dump 创造模式原型（与前端/服务端对拍）
let code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
// 原型文件无 Flask boot 段：主块整体参与（与 _smoke_creator.js 同策略）

const test = `
(function(){
_roll3D = false;
S = newState();                       // 干净档：无装备 / 无宠物 / 无料理 / 无历史（仅默认字段）
const OUT = { successRate: [], matDropRate: [], matQtyRange: [],
              expNeed: CFG.expNeed, sucBase: CFG.sucBase,
              matDrop: CFG.matDrop, drawCount: CFG.drawCount };
const diffs = ["简单", "普通", "困难", "噩梦"];
for(let qi = 0; qi < 5; qi++){
  const qname = C["Lv" + (qi + 1)][0][0];        // 真实收录名 → QUEST_LV[qname] === qi
  for(let lv = 0; lv < 5; lv++){
    S.lvIdx = lv;
    for(const d of diffs){
      const q = [qname, "采集", 0, 1, d, 100, 10, [], {}];
      OUT.successRate.push({ qi: qi, lv: lv, diff: d, name: qname, out: successRate(q) });
    }
  }
}
S.lvIdx = 0;
for(const k in M){ OUT.matDropRate.push({ name: k, out: matDropRate(k) }); }
[[1, 3], [2, 2], 5, [4, 6]].forEach(function(v){
  OUT.matQtyRange.push({ v: v, out: matQtyRange(v) });
});
/* v1.48e：硬编码表双端一致性（防未来加表时两端漂移）+ CFG 全量 */
OUT.tables = {
  achv: ACHV.map(function(a){ return Array.isArray(a) ? a[0] : (a.n || a.name); }),
  festivals: Object.keys(FESTIVALS),
  festEff: Object.keys(FEST_EFF),
  festRanges: FESTIVAL_RANGES.map(function(x){ return x[2]; }),
  petLines: Object.keys(PET_LINES),
  subCats: SUB_CATS,
  wolfStages: WOLF_STAGES.map(function(s){ return s ? s.name : null; }),
  recipes: (CFG.recipes||[]).map(function(r){ return r.n; })
};
OUT.cfgFull = JSON.parse(JSON.stringify(CFG));
OUT.gear = GEAR.map(function(g){ return g.slice(); });   // v1.49：装备表全量（防双端 data 漂移）
/* v1.51：全部数据表对拍（MONTH_EVENTS 曾被漂移漏网——前端内嵌表必须与服务端 static_data.json 一致） */
OUT.tablesFull = {
  BUY_TIERS: BUY_TIERS, C: C, CHARM: CHARM, CON_SHOP: CON_SHOP, CRAFT: CRAFT,
  EXPLORE_EVENT_CHANCE: EXPLORE_EVENT_CHANCE, ITEM_DESC: ITEM_DESC, LEGEND: LEGEND,
  LEGEND_GOLD: LEGEND_GOLD, M: M, MASTER_SHOP: MASTER_SHOP, MONTH_EVENTS: MONTH_EVENTS,
  PET_FIND: PET_FIND, PET_GIFTS: PET_GIFTS, PET_LINES: PET_LINES, PLAT_SHOP: PLAT_SHOP, QUEST_ITEM: QUEST_ITEM, QUEST_REQ: QUEST_REQ, QUEST_STORY: QUEST_STORY,
  QUEST_TURNIN: QUEST_TURNIN, RARE: RARE, REGIONS: REGIONS, REGION_EVENTS: REGION_EVENTS,
  REP_TABLE: REP_TABLE, SHOP: SHOP, SKILLS: SKILLS, SKILL_COST: SKILL_COST, VIT_SHOP: VIT_SHOP
};
global.__PARITY__ = OUT;
})();
`;

eval(code + test);
if(!global.__PARITY__){ console.error("parity dump 失败"); process.exit(1); }
fs.writeFileSync(__dirname + '/_proto_out.json', JSON.stringify(global.__PARITY__, null, 1));
console.log("parity dump: successRate " + global.__PARITY__.successRate.length
  + " 组 / matDropRate " + global.__PARITY__.matDropRate.length
  + " 种 / 常量表 4 组 → _proto_out.json");
