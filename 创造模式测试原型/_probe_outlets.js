// 一次性分析：材料出口覆盖（node _probe_outlets.js）——为新材料/装备/料理扩充选料用
const fs = require('fs');
global.localStorage = { _d:{}, getItem(k){return this._d[k]||null;}, setItem(k,v){this._d[k]=v;}, removeItem(k){delete this._d[k];} };
const fakeEl = () => ({ textContent:"", innerHTML:"", style:{}, value:"", classList:{add(){},remove(){},contains(){return false;}}, onclick:null, focus(){}, addEventListener(){}, dataset:{}, querySelectorAll(){return [];} });
const elCache = {}, qsCache = {};
global.document = { getElementById:(id)=>(elCache[id]=elCache[id]||fakeEl()), querySelector:(s)=>(qsCache[s]=qsCache[s]||fakeEl()), querySelectorAll:()=>[], addEventListener:()=>{} };
global.alert=()=>{}; global.confirm=()=>true; global.setInterval=()=>0;
const html = fs.readFileSync(__dirname + '/../Flask版/static/game.html', 'utf-8');
let code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const _bi = code.indexOf('(async function boot(){');
if(_bi < 0) throw new Error("未找到 boot 段");
code = code.slice(0, _bi);
const test = `
(function(){
const q = s => console.log(s);
q("=== 计数 ===");
q("M 材料 " + Object.keys(M).length + " / GEAR " + GEAR.length + " / CRAFT " + Object.keys(CRAFT).length + " / 料理 " + CFG.recipes.length);
// 出口统计
const exit = {};
Object.keys(M).forEach(k => exit[k] = new Set());
GEAR.forEach(g => { if(g[5]!=="—"){ const mm=g[5].match(/^(.+?)×\\d+$/); if(mm && exit[mm[1]]) exit[mm[1]].add("装备"); } });
Object.entries(CRAFT).forEach(([n,c]) => Object.keys(c.ing||{}).forEach(k => exit[k] && exit[k].add("配方:"+n)));
CFG.recipes.forEach(r => { Object.keys(r.main||{}).forEach(k=>exit[k]&&exit[k].add("料理主:"+r.n)); Object.keys(r.sub||{}).forEach(k=>exit[k]&&exit[k].add("料理辅:"+r.n)); });
// 入口统计（哪来的）
const entry = {};
Object.keys(M).forEach(k => entry[k] = new Set());
Object.entries(C).forEach(([lv,qs]) => qs.forEach(qq => Object.keys(qq[8]||{}).forEach(k => entry[k] && entry[k].add("委托"))));
REGIONS.forEach(r => (r.d||[]).forEach(e => { if(e[0] && entry[e[0]]) entry[e[0]].add("区域:"+r.n); }));
MONTH_EVENTS.forEach(ev => Object.keys(ev.mats||{}).forEach(k => entry[k] && entry[k].add("月事件")));
PLAT_SHOP.forEach(s => (s.sel||[]).forEach(k => entry[k] && entry[k].add("铂金")));
const rSeg = JSON.stringify(RARE), lSeg = JSON.stringify(LEGEND), cSeg = JSON.stringify(CRAFT), qSeg = JSON.stringify(SHOP)+JSON.stringify(VIT_SHOP)+JSON.stringify(CON_SHOP)+JSON.stringify(MASTER_SHOP);
Object.keys(M).forEach(k => { const p = '"'+k+'"'; if(rSeg.indexOf(p)>=0) entry[k].add("稀有事件"); if(lSeg.indexOf(p)>=0) entry[k].add("传奇"); if(cSeg.indexOf(p)>=0) entry[k].add("配方产"); if(qSeg.indexOf(p)>=0) entry[k].add("商店"); });
// 无装备出口的材料（按品阶）
["普通","精良","稀有","史诗","传说"].forEach(t => {
  const list = Object.keys(M).filter(k => M[k][1]===t && !exit[k].has("装备"));
  q("");
  q("=== " + t + " 无装备出口（" + list.length + "）===");
  list.forEach(k => q("  " + k + "（" + M[k][0] + "·" + M[k][2] + "） 入口: " + [...entry[k]].join(",") + " 其他出口: " + [...exit[k]].join(",")));
});
// 无料理出口的食材类
q("");
q("=== 食材类（全部）===");
Object.keys(M).filter(k => M[k][0]==="食材").forEach(k => q("  " + k + "（" + M[k][1] + "） 料理出口: " + [...exit[k]].filter(x=>x.indexOf("料理")===0).join(",") + " | 入口: " + [...entry[k]].join(",")));
// 无任何非卖钱出口
q("");
const weak = Object.keys(M).filter(k => exit[k].size === 0);
q("=== 完全无出口（" + weak.length + "）: " + weak.map(k=>k+"("+M[k][1]+M[k][0]+")").join(" / "));
// 装备品阶分布
const gq = {}; GEAR.forEach(g => gq[g[1]] = (gq[g[1]]||0)+1);
q("");
q("=== GEAR 品阶分布: " + JSON.stringify(gq));
const gt = {}; GEAR.forEach(g => gt[g[2]] = (gt[g[2]]||0)+1);
q("=== GEAR 部位分布: " + JSON.stringify(gt));
// CRAFT 一览
q("");
q("=== CRAFT（" + Object.keys(CRAFT).length + "）===");
Object.entries(CRAFT).forEach(([n,c]) => q("  " + n + " 品阶" + (c.q||"?") + " 价" + (c.price||"?") + " ing=" + JSON.stringify(c.ing||{}) + (c.d?" | "+c.d:"")));
// 料理一览（主辅材）
q("");
q("=== 料理材料一览 ===");
CFG.recipes.forEach(r => q("  " + r.n + " 主" + JSON.stringify(r.main) + " 辅" + JSON.stringify(r.sub||{})));
})();
`;
try { eval(code + test); } catch(e) { console.log("加载异常:", e.message); if(e.stack) console.log(e.stack.split("\n").slice(0,4).join("\n")); }
