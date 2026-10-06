// 全项目审计 v1.52：引用完整性 + 材料矩阵 + 数值抽查（node _audit_full.js）
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
const BAD = [], WARN = [];
const bad = (s) => BAD.push(s);
const warn = (s) => WARN.push(s);
const CQ = {};
Object.values(C).forEach(qs => qs.forEach(q => CQ[q[0]] = q));
const curAll = Object.keys(ITEM_DESC);
const petAll = new Set(Object.keys(PET_LINES).concat(["小狼"]));
Object.keys(PET_FIXED).forEach(k => petAll.add(k));
const titles = new Set(ACHV.filter(a=>a.title).map(a=>a.title));
const gearNames = new Set(GEAR.map(g=>g[0]));

/* 1 C 表掉落 in M */
Object.entries(C).forEach(([lv,qs]) => qs.forEach(q => Object.keys(q[8]||{}).forEach(k => { if(!M[k]) bad("C " + lv + " " + q[0] + " 掉落材料不存在: " + k); })));
/* 2 REGIONS 掉落 in M */
REGIONS.forEach(r => (r.d||[]).forEach(e => { if(e[0] && !M[e[0]] && curAll.indexOf(e[0]) < 0 && e[0] !== "旧宝箱") bad("区域 " + r.n + " 掉落不存在: " + e[0]); }));
/* 3 GEAR 主材 in M */
GEAR.forEach(g => { if(g[5] !== "—"){ const mm = g[5].match(/^(.+?)×\\d+$/); if(!mm) bad("装备 " + g[0] + " 主材格式异常: " + g[5]); else if(!M[mm[1]]) bad("装备 " + g[0] + " 主材不存在: " + mm[1]); } });
/* 4 CRAFT 材料 in M */
Object.entries(CRAFT).forEach(([n,c]) => Object.keys(c.ing||{}).forEach(k => { if(!M[k]) bad("道具配方 " + n + " 材料不存在: " + k); }));
/* 5 料理 main/sub in M */
CFG.recipes.forEach(r => { Object.keys(r.main||{}).forEach(k => { if(!M[k]) bad("料理 " + r.n + " 主材不存在: " + k); }); Object.keys(r.sub||{}).forEach(k => { if(!M[k]) bad("料理 " + r.n + " 辅材不存在: " + k); }); });
/* 6 商店 item in 道具 */
[["SHOP",SHOP],["VIT_SHOP",VIT_SHOP],["CON_SHOP",CON_SHOP]].forEach(([nm,arr]) => arr.forEach(s => { if(s.item && curAll.indexOf(s.item) < 0) bad(nm + " " + s.n + " 道具不存在: " + s.item); }));
PLAT_SHOP.forEach(s => { if(s.item && curAll.indexOf(s.item) < 0) bad("PLAT_SHOP " + s.n + " 道具不存在: " + s.item); (s.sel||[]).forEach(k => { if(!M[k]) bad("PLAT_SHOP " + s.n + " 自选材料不存在: " + k); }); });
/* 7 MONTH_EVENTS */
const mseen = new Set();
MONTH_EVENTS.forEach(ev => { if(mseen.has(ev.m)) bad("月事件重复月份: " + ev.m); mseen.add(ev.m); if(["task","explore","quest"].indexOf(ev.t) < 0) bad("月事件类型异常 " + ev.n + ": " + ev.t); Object.keys(ev.mats||{}).forEach(k => { if(!M[k]) bad("月事件 " + ev.n + " 奖励材料不存在: " + k); }); });
for(let m=1;m<=12;m++) if(!mseen.has(m)) bad("月事件缺月份: " + m);
/* 8 QUEST_ITEM / QUEST_TURNIN */
Object.entries(QUEST_ITEM).forEach(([q,it]) => { if(!CQ[q]) bad("QUEST_ITEM 委托不存在: " + q); if(curAll.indexOf(it) < 0) bad("QUEST_ITEM 道具不存在: " + it); });
Object.entries(QUEST_TURNIN).forEach(([q,m]) => { if(!CQ[q]) bad("QUEST_TURNIN 委托不存在: " + q); if(!M[m]) bad("QUEST_TURNIN 材料不存在: " + m); });
/* 9 QUEST_REQ 链 */
Object.entries(QUEST_REQ).forEach(([q,pre]) => { if(!CQ[q]) bad("链前置目标委托不存在: " + q); if(!CQ[pre]) bad("链前置源委托不存在: " + pre + " -> " + q); });
/* 10 LEGEND */
LEGEND.forEach(L => {
  const matTxt = L[6] || "";
  matTxt.split("、").forEach(seg => { const mm = seg.match(/^(.+?)×\\d+$/); if(mm && !M[mm[1]]) bad("传奇 " + L[0] + " 必得材料不存在: " + mm[1]); });
  const rw = L[7] || "";
  let m2;
  const rePet = /宠物「(.+?)」/g;
  while((m2 = rePet.exec(rw))) if(!petAll.has(m2[1])) bad("传奇 " + L[0] + " 奖励宠物不存在: " + m2[1]);
  const reT = /称号「(.+?)」/g;
  while((m2 = reT.exec(rw))) if(!titles.has(m2[1])) warn("传奇 " + L[0] + " 奖励称号不在 ACHV title 集合: " + m2[1]);
});
/* 11 ACHV gear */
ACHV.forEach(a => { if(a.gear && !gearNames.has(a.gear)) bad("成就 " + a.n + " 装备不存在: " + a.gear); });
/* 12 FEST_EFF keys */
try { const fe = FEST_EFF; const fnames = Object.values(FESTIVALS).map(v => v[0]); Object.keys(fe).forEach(k => { if(fnames.indexOf(k) < 0) void k; /* 农历节日属运行时表，正常 */ }); } catch(e){ warn("FEST_EFF 读取失败: " + e.message); }
/* 13 材料入口/出口矩阵 */
const entry = {}, exit = {};
Object.keys(M).forEach(k => { entry[k] = new Set(); exit[k] = new Set(); });
Object.entries(C).forEach(([lv,qs]) => qs.forEach(q => Object.keys(q[8]||{}).forEach(k => entry[k] && entry[k].add("委托"))));
REGIONS.forEach(r => (r.d||[]).forEach(e => { if(e[0] && entry[e[0]]) entry[e[0]].add("区域"); }));
Object.keys(M).forEach(k => { if(M[k][1]==="普通"||M[k][1]==="精良") entry[k].add("材料包"); });
MONTH_EVENTS.forEach(ev => Object.keys(ev.mats||{}).forEach(k => entry[k] && entry[k].add("月事件")));
PLAT_SHOP.forEach(s => (s.sel||[]).forEach(k => entry[k] && entry[k].add("铂金商店")));
const rSeg = JSON.stringify(RARE), eSeg = JSON.stringify(REGION_EVENTS), lSeg = JSON.stringify(LEGEND), cSeg = JSON.stringify(CRAFT), qSeg = JSON.stringify(SHOP) + JSON.stringify(VIT_SHOP) + JSON.stringify(CON_SHOP) + JSON.stringify(MASTER_SHOP);
Object.keys(M).forEach(k => { const probe = '"' + k + '"'; if(rSeg.indexOf(probe)>=0) entry[k].add("稀有事件"); if(eSeg.indexOf(probe)>=0) entry[k].add("区域事件"); if(lSeg.indexOf(probe)>=0) entry[k].add("传奇"); if(cSeg.indexOf(probe)>=0) entry[k].add("道具配方"); if(qSeg.indexOf(probe)>=0) entry[k].add("商店"); });
GEAR.forEach(g => { if(g[5]!=="—"){ const mm=g[5].match(/^(.+?)×\\d+$/); if(mm && exit[mm[1]]) exit[mm[1]].add("装备主材"); } });
const SUBOK = ["木材","石材","矿石","宝石","草药","织物","兽材","特殊"];
Object.keys(M).forEach(k => { if(SUBOK.indexOf(M[k][0]) >= 0) exit[k].add("副材(品类)"); });
Object.entries(CRAFT).forEach(([n,c]) => Object.keys(c.ing||{}).forEach(k => exit[k] && exit[k].add("道具配方")));
CFG.recipes.forEach(r => { Object.keys(r.main||{}).forEach(k=>exit[k]&&exit[k].add("料理")); Object.keys(r.sub||{}).forEach(k=>exit[k]&&exit[k].add("料理辅材")); });
PLAT_SHOP.forEach(s => (s.sel||[]).forEach(k=>exit[k]&&exit[k].add("铂金兑换")));
Object.keys(M).forEach(k => {
  if(!entry[k].size) bad("材料无任何入口: " + k + "（" + M[k][1] + M[k][0] + "）");
  if(!exit[k].size) bad("材料无任何出口: " + k + "（" + M[k][1] + M[k][0] + "）");
});
/* 14 装备主材数量规范 */
const want = {"普通":2,"精良":3,"稀有":4,"史诗":5,"传说":6};
GEAR.forEach(g => { if(g[5]==="—") return; if(g[2]==="成就饰品槽") return; const mm=g[5].match(/^(.+?)×(\\d+)$/); if(mm){ let w=want[g[1]]; if(w && g[2]==="饰品") w-=1; if(w && +mm[2]!==w) warn("主材数量: " + g[0] + "(" + g[1] + g[2] + ") " + mm[2] + " != 规范 " + w); } });
/* 15 等级×难度 均值 */
const lvAgg = {};
Object.entries(C).forEach(([lv,qs]) => { lvAgg[lv] = {}; qs.forEach(q => { const d=q[4]; lvAgg[lv][d] = lvAgg[lv][d] || {n:0,gold:0,exp:0,en:0}; lvAgg[lv][d].n++; lvAgg[lv][d].gold+=q[5]; lvAgg[lv][d].exp+=q[6]; lvAgg[lv][d].en+=q[7]; }); });
console.log("=== 等级 x 难度 均值（报酬/经验/精力 人均） ===");
Object.entries(lvAgg).forEach(([lv,ds]) => Object.entries(ds).forEach(([d,v]) => console.log("  " + lv + " " + d + " x" + v.n + " 报酬均 " + Math.round(v.gold/v.n) + " 经验均 " + Math.round(v.exp/v.n) + " 精力均 " + Math.round(v.en/v.n))));
/* 16 料理汇总 */
console.log("=== 料理 " + CFG.recipes.length + " 道 ===");
CFG.recipes.forEach(r => console.log("  " + r.n + ": en+" + (r.en||0) + " cap+" + (r.cap||0) + " bonus " + (r.bonus||0) + " rate " + (r.rate||0) + (r.desc?(" | " + r.desc):"")));
/* 17 商店汇总 */
console.log("=== VIT_SHOP ===");
VIT_SHOP.forEach(s => console.log("  " + s.n + " vit" + s.vit + " " + (s.d||"")));
console.log("=== CON_SHOP ===");
CON_SHOP.forEach(s => console.log("  " + s.n + " con" + (s.con||"") + " " + (s.d||"")));
console.log("=== PLAT_SHOP ===");
PLAT_SHOP.forEach(s => console.log("  " + s.n + " " + (s.platC||"?") + "铂金 " + JSON.stringify(s.lim||"")));
console.log("=== CHARM ===");
CHARM.forEach(c => console.log("  Lv" + c.lv + " need" + c.need + " cost" + c.cost + " pay+" + c.pay + " rate+" + c.rate + " vit+" + c.vit + " " + c.req + " " + (c.other||"")));
console.log("=== MASTER_SHOP ===");
console.log(JSON.stringify(MASTER_SHOP).slice(0, 900));
console.log("=== SKILLS 完整 ===");
console.log(JSON.stringify(SKILLS));
console.log("");
const weak = Object.keys(M).filter(k => { const strong = [...(exit[k]||[])].filter(x => x !== "副材(品类)"); return exit[k] && exit[k].size && !strong.length; }).map(k => k + "（" + M[k][1] + M[k][0] + "）");
if(weak.length) console.log("=== 弱出口材料（仅副材+卖钱）: " + weak.join(" / ") + " ===");
console.log("================ 审计结果 ================");
console.log("BAD 问题 " + BAD.length + " 项:");
BAD.forEach(s => console.log("  [X] " + s));
console.log("WARN 提示 " + WARN.length + " 项:");
WARN.forEach(s => console.log("  [!] " + s));
})();
`;
try { eval(code + test); } catch(e) { console.log("加载异常:", e.message); if(e.stack) console.log(e.stack.split("\n").slice(0,4).join("\n")); }
