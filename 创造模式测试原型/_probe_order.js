// v1.54 排序实测：渲染背包 / 图鉴，打印各处列表的实际显示顺序
// 运行：node _probe_order.js
const fs = require('fs');
global.localStorage = { _d:{}, getItem(k){ return this._d[k]||null; }, setItem(k,v){ this._d[k]=v; }, removeItem(k){ delete this._d[k]; } };
const fakeEl = () => ({ textContent:"", innerHTML:"", style:{}, value:"", classList:{ add(){}, remove(){}, contains(){ return false; } }, onclick:null, focus(){}, addEventListener(){}, dataset:{}, querySelectorAll(){ return []; } });
const elCache = {};
global.document = { getElementById:(id)=>(elCache[id]=elCache[id]||fakeEl()), querySelector:()=>fakeEl(), querySelectorAll:()=>[], addEventListener:()=>{} };
global.alert = () => {}; global.confirm = () => true; global.setInterval = () => 0;

const html = fs.readFileSync(__dirname + '/../Flask版/static/game.html', 'utf-8');
let code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
code = code.slice(0, code.indexOf('(async function boot(){'));

const probe = `
S = newState(); S.name = "排序探针"; S.lvIdx = 4; S.rep = 999999;
S.mats = {"松木":5, "凤凰木":1, "龙血":1, "黑檀木":2, "止血草":9, "圣兽之蜕":1};
S.items = {"谈判卷轴":1, "安眠护符":2, "神秘地图":3, "解毒剂":4, "圣水":1};
const _gOf = function(q){ return GEAR.filter(function(g){ return g[1]===q; })[0][0]; };
S.gear = [_gOf("普通"), _gOf("传说"), _gOf("史诗")];
S.blueprints = {}; S.gear.forEach(function(n){ S.blueprints[n] = true; });
S.cooked = ["巨龙盛宴", "菌菇汤"];
S.seenMats = Object.keys(S.mats);
render();
function seq(tab, re){
  const h = document.getElementById(tab).innerHTML || "";
  const out = []; let m;
  while((m = re.exec(h))) out.push(m[1]);
  return out.join(" → ");
}
const R_GEAR = /showGearDetail\\('([^']+)'/g;
const R_ITEM = /showItemDetail\\('([^']+)'/g;
const R_PREP = /craftItem\\('([^']+)'/g;
const R_MAT  = /showMatDetail\\('([^']+)'/g;
console.log("背包 · 材料：  " + seq("tab-bag", R_MAT));
console.log("背包 · 道具：  " + seq("tab-bag", R_ITEM));
console.log("背包 · 装备：  " + seq("tab-bag", R_GEAR));
console.log("背包 · 炼金台：" + seq("tab-bag", R_PREP));
console.log("图鉴 · 材料：  " + seq("tab-gallery", R_MAT));
console.log("图鉴 · 装备：  " + seq("tab-gallery", R_GEAR));
console.log("图鉴 · 道具：  " + seq("tab-gallery", R_ITEM));
console.log("商店 · 图纸档位：" + (function(){
  const h = document.getElementById("tab-shop").innerHTML || "";
  const out = []; let m; const re = /(\\S+) 图纸</g;
  while((m = re.exec(h))) out.push(m[1]);
  return out.join(" → ");
})());
`;

eval(code + "\n" + probe);
