// 一次性工具：从原型 HTML 提取全部静态数据 → data/static_data.json
// 用法：node tools_export_data.js
const fs = require('fs');
const path = require('path');

global.localStorage = { _d:{}, getItem(k){return this._d[k]||null;}, setItem(k,v){this._d[k]=v;}, removeItem(k){delete this._d[k];} };
const fakeEl = () => ({ textContent:"", innerHTML:"", style:{}, value:"",
  classList:{ add(){}, remove(){}, contains(){return false;} }, onclick:null,
  focus(){}, addEventListener(){}, dataset:{}, querySelectorAll(){return []; } });
const elCache = {};
global.document = { getElementById:(id)=>(elCache[id]=elCache[id]||fakeEl()), querySelectorAll:()=>[], addEventListener:()=>{} };
global.alert = ()=>{}; global.confirm = ()=>false; global.setInterval = ()=>0;

const html = fs.readFileSync(path.join(__dirname, '..', '创造模式测试原型', '健康的冒险者的一天.html'), 'utf-8');
const code = html.match(/<script>([\s\S]*?)<\/script>/)[1];

const pack = `
(function(){
  return JSON.stringify({
    C: C, M: M, GEAR: GEAR, LEGEND: LEGEND, REGIONS: REGIONS, RARE: RARE,
    CFG: CFG, SHOP: SHOP, VIT_SHOP: VIT_SHOP, CON_SHOP: CON_SHOP,
    PLAT_SHOP: PLAT_SHOP, BUY_TIERS: BUY_TIERS, QUEST_REQ: QUEST_REQ, QUEST_ITEM: QUEST_ITEM, CRAFT: CRAFT,
    MONTH_EVENTS: MONTH_EVENTS, QUEST_TURNIN: QUEST_TURNIN, MASTER_SHOP: MASTER_SHOP,
    CHARM: CHARM, SKILLS: SKILLS, SKILL_COST: SKILL_COST,
    ITEM_DESC: ITEM_DESC, QUEST_STORY: QUEST_STORY,
    EXPLORE_EVENT_CHANCE: EXPLORE_EVENT_CHANCE, REP_TABLE: REP_TABLE,
    LEGEND_GOLD: LEGEND_GOLD, REGION_EVENTS: REGION_EVENTS
  });
})()
`;

const out = eval(code + pack);
fs.writeFileSync(path.join(__dirname, 'data', 'static_data.json'), out);
const d = JSON.parse(out);
console.log('导出完成：');
console.log('  委托池:', Object.keys(d.C).map(k => k + '=' + d.C[k].length).join(' '));
console.log('  材料:', Object.keys(d.M).length, '| 装备:', d.GEAR.length, '| 传奇:', d.LEGEND.length);
console.log('  区域:', d.REGIONS.length, '| 稀有事件:', d.RARE.length, '| 描写:', Object.keys(d.QUEST_STORY).length);
console.log('  → data/static_data.json');
