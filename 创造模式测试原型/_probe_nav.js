// 导航拦截回归：无宠物时点击「🐾 宠物」→ 弹窗提示且不进入；有宠物（含小狼/历史档）→ 正常进入
// 另含：背包导流卡走同一拦截、导流卡计数不重复
// 运行：node _probe_nav.js
const fs = require('fs');
global.localStorage = { _d:{}, getItem(k){ return this._d[k]||null; }, setItem(k,v){ this._d[k]=v; }, removeItem(k){ delete this._d[k]; } };

const mkClass = () => { const s = new Set(); return { add:(c)=>s.add(c), remove:(c)=>s.delete(c), contains:(c)=>s.has(c), toggle:(c)=>s.has(c)?s.delete(c):s.add(c), _s:s }; };
const fakeEl = () => ({ textContent:"", innerHTML:"", style:{}, value:"", classList:mkClass(), onclick:null, focus(){}, addEventListener(){}, dataset:{}, querySelectorAll(){ return []; } });

const elCache = {};
const _btnMap = {};
["quest","tavern","health","bag","pet","shop","gallery","log"].forEach(t=>{
  const el = fakeEl(); el.dataset = {t}; _btnMap[t] = el;
});
const _tabpages = {};
["quest","tavern","health","bag","pet","shop","gallery","log"].forEach(t=>{
  _tabpages["tab-"+t] = fakeEl();
});
/* click() 桥接：gotoPetTab 用 querySelector 找按钮再 .click() */
Object.values(_btnMap).forEach(el=>{ el.click = () => { if(el.onclick) el.onclick(); }; });

global.document = {
  getElementById: (id)=> (elCache[id] = elCache[id] || _tabpages[id] || fakeEl()),
  querySelector: (sel)=>{
    const m = sel.match(/data-t="(\w+)"/);
    return m && _btnMap[m[1]] ? _btnMap[m[1]] : fakeEl();
  },
  querySelectorAll: (sel)=>{
    if(sel === "#tabs button") return Object.values(_btnMap);
    if(sel === ".tabpage") return Object.values(_tabpages);
    return [];
  },
  addEventListener: ()=>{}
};
global.alert = () => {}; global.confirm = () => true; global.setInterval = () => 0;

const html = fs.readFileSync(__dirname + '/../Flask版/static/game.html', 'utf-8');
let code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
code = code.slice(0, code.indexOf('(async function boot(){'));

const probe = `
let PASS = 0, FAIL = 0;
function ok(cond, msg){ if(cond){ PASS++; console.log("✅ " + msg); } else { FAIL++; console.log("❌ " + msg); } }

let _dlgs = [];
dlg = function(title, body){ _dlgs.push({t:String(title), b:String(body)}); };
showAlert = function(m,t){ _dlgs.push({t:String(t||""), b:String(m)}); };
showConfirm = function(m, fn){ _dlgs.push({t:"confirm", b:String(m)}); if(fn) fn(); };

function reset(on){
  document.querySelectorAll("#tabs button").forEach(x=>x.classList.remove("on"));
  document.querySelectorAll(".tabpage").forEach(x=>x.classList.remove("on"));
  if(on){ _btnMap.quest.classList.add("on"); _tabpages["tab-quest"].classList.add("on"); }
}

/* ─ 场景 1：无宠物 → 拦截 ─ */
S = newState(); S.name = "探针";
S.pets = []; S.wolf = null;
S.daily = {date: todayStr(), done:0, gold:0, exp:0, rep:0, con:0, vit:0, quests:[], events:[]};
render();
reset(true);
_dlgs = [];
_btnMap.pet.onclick();
ok(_dlgs.length === 1, "无宠物点击宠物按钮 → 弹窗（实际 " + _dlgs.length + " 个）");
ok(_dlgs.length === 1 && _dlgs[0].b.indexOf("您还没有伙伴") >= 0 && _dlgs[0].b.indexOf("去探索看看吧") >= 0, "弹窗文案正确");
ok(_dlgs.length === 1 && _dlgs[0].t === "宠物", "弹窗标题「宠物」");
ok(!_tabpages["tab-pet"].classList.contains("on"), "宠物页未进入");
ok(_tabpages["tab-quest"].classList.contains("on"), "停留在原页签");

/* ─ 场景 2：仅小狼 → 正常进入 ─ */
S.wolf = {stage: 1, growth: 0, mutate: 0, fedDate: "", fedCount: 0};
reset(true);
_dlgs = [];
_btnMap.pet.onclick();
ok(_dlgs.length === 0, "有小狼：不弹窗");
ok(_tabpages["tab-pet"].classList.contains("on"), "有小狼：正常进入宠物页");

/* ─ 场景 3：普通宠物（历史档 S.pets 含小狼的兼容）→ 正常进入 ─ */
S = newState(); S.name = "探针";
S.pets = ["月光狐"]; S.wolf = null;
render(); reset(true);
_dlgs = [];
_btnMap.pet.onclick();
ok(_dlgs.length === 0 && _tabpages["tab-pet"].classList.contains("on"), "有普通宠物：正常进入");

/* 历史档真实链路：老档无 wolf 键、pets 里有小狼 → migrate 补入 S.wolf → 正常进入 */
S = newState(); S.name = "探针";
S.pets = ["小狼"]; delete S.wolf;
S = migrate(S);
reset(true); _dlgs = [];
_btnMap.pet.onclick();
ok(S.wolf !== null && _dlgs.length === 0 && _tabpages["tab-pet"].classList.contains("on"), "历史档经 migrate 补入小狼 → 正常进入");

/* ─ 场景 4：背包导流卡 gotoPetTab 走同一拦截 ─ */
S.pets = []; S.wolf = null;
reset(true); _dlgs = [];
gotoPetTab();
ok(_dlgs.length === 1 && _dlgs[0].b.indexOf("您还没有伙伴") >= 0, "无宠物时导流卡 → 同样弹窗");

/* ─ 背包导流卡计数（小狼不重复计） ─ */
S.pets = ["小狼", "月光狐"]; S.wolf = {stage: 1, growth: 0, mutate: 0, fedDate: "", fedCount: 0};
render();
const _bag = document.getElementById("tab-bag").innerHTML || "";
ok(_bag.indexOf("🐾 宠物（2）") >= 0, "导流卡计数正确（小狼+月光狐 = 2，不重复）");

console.log(PASS + " 通过 / " + FAIL + " 失败");
if(FAIL > 0) process.exit(1);
`;

eval(code + "\n" + probe);
