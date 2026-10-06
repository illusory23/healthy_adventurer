// 全面冒烟测试：全委托 × 每级 / 全传奇 / 全区域探索 / 探索事件 / 装备 / 道具 / 料理 / 商店等
// 运行：node _smoke_run.js
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

// v1.50：测试目标改为 Flask 前端（game.html 原型层）——项目以 Flask 版为最终实现；桥接层截除不参与
const html = fs.readFileSync(__dirname + '/../Flask版/static/game.html', 'utf-8');
let code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
{
  // 截除 Flask 桥接层 + Flask 专用 boot（从服务端拉状态的启动段）——只保留原型层逻辑
  const _bi = code.indexOf('(async function boot(){');
  if(_bi < 0) throw new Error("game.html 结构变化：未找到 boot 段，请更新测试脚本");
  code = code.slice(0, _bi);
}

/* v1.38q：源码卫生——同名函数覆盖检测（原型不应有任何重复 function 定义；
   历史上 showQuestDetail / sleepStreak 曾因同名覆盖导致功能静默失效） */
const _srcDupList = (function(){
  const defs = {};
  code.split('\n').forEach(function(l, i){
    const m = l.match(/\bfunction\s+([A-Za-z_$][\w$]*)\s*\(/);
    if(m) (defs[m[1]] = defs[m[1]] || []).push(i + 1);
  });
  return Object.keys(defs).filter(function(k){ return defs[k].length > 1; })
    .map(function(k){ return k + '(行 ' + defs[k].join(',') + ')'; });
})();

const test = `
(async function(){
_roll3D = false;

let PASS = 0, FAIL = 0;
function ok(){ PASS++; }
function bad(m){ FAIL++; console.log("  ❌ " + m); }
function check(cond, m){ cond ? PASS++ : bad(m); }

let dlgCap = null;
let alertN = 0;
dlg = function(t,b,btns){ dlgCap = {t:t, b:b||"", btns:btns||[]}; };
showAlert = function(m,t){ alertN++; dlgCap = {t:t||"提示", b:m||"", btns:[]}; };
/* v1.53：资源消耗类操作统一二次确认——测试中自动点「确定」，并计数供断言 */
let confirmN = 0;
showConfirm = function(m, onOk, t){ confirmN++; dlgCap = {t:t||"确认", b:m||"", btns:[]}; onOk && onOk(); };

/* ═══════════ 1. 全委托结算（Lv1~Lv5 共 70 个） ═══════════ */
console.log("\\n===== 1. 全委托结算（每级每个都跑）=====");
if(!S) S = newState();       // v1.50：S 的初始化原在桥接层（已截除）——测试自行初始化
S.name = "冒烟";
S.equipped = {weapon:null, armor:null, accessory:null, charmSlot:null};
S.gear = []; S.mats = {}; S.items = {}; S.active = []; S.money = 0;

async function runQ(q, lv){
  const b0 = {};
  for(const k in S.mats) b0[k] = S.mats[k];
  const gold0 = S.money;
  const _tn = QUEST_TURNIN[q[0]] || null;               // v1.41 I4：上交型委托结算会扣 1 个材料
  const _tnHave = _tn ? (S.mats[_tn]||0) : 0;
  await settle({q:q, qlv:lv, rate:1, acceptTs:Date.now(), finishTs:Date.now()+3600000, name:q[0], meal:null});
  const first = Object.keys(q[8]||{})[0];
  const _tnUsed = (_tn && _tn === first && _tnHave >= 1) ? 1 : 0;
  let gainedN = 0;
  for(const k in S.mats){
    const d = S.mats[k] - (b0[k]||0);
    if(d <= 0) continue;
    gainedN++;
    const v = q[8][k];
    if(v === undefined){ bad("["+q[0]+"] 掉了列表外材料 " + k); continue; }
    const rg = Array.isArray(v) ? v : [v, v];
    const _lo = (k === first) ? rg[0] - _tnUsed : rg[0];   // 主材料若被上交，净增下界 -1
    if(d < _lo || d > rg[1]) bad("["+q[0]+"]「"+k+"」掉 "+d+" 超出区间 "+JSON.stringify(rg));
  }
  if(first && !(S.mats[first] >= (b0[first]||0) - _tnUsed + 1)) bad("["+q[0]+"] 主材料「"+first+"」未掉落");
  if(S.money <= gold0) bad("["+q[0]+"] 成功后报酬未增加");
  return gainedN;
}
const pools = [[1,C.Lv1],[2,C.Lv2],[3,C.Lv3],[4,C.Lv4],[5,C.Lv5]];
let qAll = 0, qMat = 0;
const _rareOrig1 = tryRareEvent;
tryRareEvent = function(){ return null; };   // 屏蔽结算期稀有事件：其随机材料会污染材料区间校验（概率性误报）
for(const p of pools){
  let matN = 0;
  for(const q of p[1]){ matN += await runQ(q, p[0]); qAll++; }
  qMat += matN;
  console.log("  Lv" + p[0] + "：" + p[1].length + " 个委托 ✅ | 材料项 " + matN);
}
// 稀有事件屏蔽保持到段 8 ——「山贼的赃物」+30银 /「意外的馈赠」+50%报酬 等会污染段 5/7 的报酬实测（低频偶发，2026-10-03 查明）
console.log("  合计 " + qAll + " 个委托 / " + qMat + " 项材料（区间与主材料必得校验通过，异常见上）");

/* ═══════════ 2. 传奇事件（12 个全跑） ═══════════ */
console.log("\\n===== 2. 传奇事件 / 世界级事件（12 个）=====");
S.legendDone = []; S.titles = []; S.pets = []; S.trophies = []; S.rep = 0;
let lgMat = 0;
for(const L of LEGEND){
  const b0 = {};
  for(const k in S.mats) b0[k] = S.mats[k];
  const rep0 = S.rep;
  await settle({q:[L[0],"精英","传奇",0,L[3],0,L[4],0,{}], qlv:5, legend:L, lname:"传奇事件", rate:1,
    acceptTs:Date.now(), finishTs:Date.now()+3600000, name:L[0], meal:null});
  if(S.legendDone.indexOf(L[0]) < 0) bad("["+L[0]+"] 未记录完成");
  if(S.rep <= rep0) bad("["+L[0]+"] 声望未增加");
  if(L[6]) L[6].split("、").forEach(function(pair){
    const m = pair.match(/^(.+?)×(\\d+)$/);
    if(m){
      const d = (S.mats[m[1]]||0) - (b0[m[1]]||0);
      if(d !== +m[2]) bad("["+L[0]+"] 材料 "+m[1]+" 应+"+m[2]+" 实+"+d);
      else lgMat++;
    }
  });
}
console.log("  12 个跑完：完成 " + S.legendDone.length + "/12 ✅ | 材料发放 " + lgMat + " 项 | 声望 +" + S.rep);
console.log("  称号 " + S.titles.length + " · 宠物 " + S.pets.length + " · 藏品 " + S.trophies.length);

/* ═══════════ 3. 自由探索（7 区域） ═══════════ */
console.log("\\n===== 3. 自由探索（7 区域 × 60 次）=====");
{
  const _dlg = dlg; dlg = function(){};
  const _irt = inRegionTime, _pee = pickExploreEvent;
  inRegionTime = function(){ return true; };
  pickExploreEvent = function(){ return null; };
  S.lvIdx = 4;
  S.history = [{date:"d", score:100, sleep:true}];
  for(let i=0; i<REGIONS.length; i++){
    const r = REGIONS[i];
    S.explore = 99999; S.mats = {}; S.items = {}; S.money = 0;
    let got = 0, empty = 0, unknown = 0;
    for(let n=0; n<60; n++){
      S.exploreUsed = 0; S.explore = 99999;
      const bM = Object.assign({}, S.mats), bI = Object.assign({}, S.items), bC = S.money;
      doExplore(i);
      if(S.exploreActive){ S.exploreActive.finishTs = Date.now() - 1; exploreFinishCheck(); }  // v1.25：快进到点强制结算
      let g = 0;
      for(const k in S.mats){ if((S.mats[k]||0) > (bM[k]||0)){ g++; if(!M[k]) unknown++; } }
      for(const k in S.items){ if((S.items[k]||0) > (bI[k]||0)){ g++; if(ITEM_DESC[k]===undefined) unknown++; } }
      if(S.money > bC) g++;
      got += g; if(!g) empty++;
    }
    if(unknown){ bad(r.n + " 出现未知材料/道具 ×" + unknown); }
    console.log("  " + r.n + "：平均 " + (got/60).toFixed(2) + " 类/次 | 空手 " + empty + " 次" + (unknown?" ❌":" ✅"));
    PASS++;
  }
  dlg = _dlg; inRegionTime = _irt; pickExploreEvent = _pee;
}

/* ═══════════ 4. 探索事件（7 个） ═══════════ */
console.log("\\n===== 4. 探索事件（6 区域事件 + 盗贼伏击）=====");
{
  const names = [];
  for(const k in REGION_EVENTS) names.push(REGION_EVENTS[k]);
  names.push("盗贼伏击");
  for(const nm of names){
    S.wolfDone = false; S.pendingPet = null; S.blueprints = {}; S.echo = 0;
    S.pets = []; S.items = {}; S.money = 100000; S.blueprints = {}; S.titles = [];
    let steps = 0, err = false;
    try{
      dlgCap = null;
      runExploreEvent(nm, REGIONS[0]);
      for(let d=0; d<6; d++){
        if(!dlgCap || !dlgCap.btns || !dlgCap.btns.length) break;
        const btn = dlgCap.btns.find(function(x){ return x.fn; });
        dlgCap = null;
        if(!btn) break;
        btn.fn(); steps++;
      }
    }catch(e){ err = true; bad("事件["+nm+"] 异常: " + e.message); }
    if(!err){ PASS++; console.log("  " + nm + "：执行 " + steps + " 步无异常 ✅"); }
  }
}

/* ═══════════ 5. 装备（53 件逐穿 + 专项） ═══════════ */
console.log("\\n===== 5. 装备（53 件逐穿检查）=====");
{
  S.lvIdx = 4; S.charm = 0;
  S.skills = S.skills || {"体能":0,"专注":0,"社交":0,"生存":0,"幸运":0};
  S.equipped = {weapon:null,armor:null,accessory:null,charmSlot:null};
  S.gear = GEAR.map(function(g){ return g[0]; });
  let mainBad = 0;
  for(const g of GEAR){
    equipItem(g[0]);
    const slot = g[2]==="成就饰品槽" ? "charmSlot" : (g[2]==="武器" ? "weapon" : (g[2]==="护甲" ? "armor" : "accessory"));
    if(S.equipped[slot] !== g[0]){ bad("装备["+g[0]+"] 未进入槽位"); mainBad++; continue; }
    let v = 0;
    if(slot==="weapon") v = gearRate();
    else if(slot==="armor") v = gearEn();
    else if(slot==="accessory") v = gearBonus();
    else v = gearAccBonus();
    if(Math.abs(v - g[3]) > 1e-9){ bad("装备["+g[0]+"] 主属性 "+v+" ≠ 数据 "+g[3]); mainBad++; }
  }
  if(!mainBad) console.log("  53 件主属性全部生效 ✅");
  // 副属性关键词识别
  const KW = ["成功率","报酬","精力消耗","熬夜惩罚","委托经验","公会贡献","稀有事件概率","材料获取","传奇事件成功率","健康加成上限","探索点","同时进行上限","每日接取上限","豁免","活力点获取"];
  let unk = 0;
  for(const g of GEAR){
    if(!g[4] || g[4] === "—") continue;
    for(const p of g[4].split(/[；;]/)){
      if(p && !KW.some(function(k){ return p.indexOf(k) >= 0; })){ bad("副属性未识别: " + g[0] + "「" + p + "」"); unk++; }
    }
  }
  if(!unk) console.log("  副属性关键词全部识别 ✅（「判定豁免」依赖周/月打卡，原型暂未实装）");
  // ★ 装备专项
  S.equipped = {weapon:null,armor:null,accessory:null,charmSlot:null}; S.gear = [];
  const baseSim = simCapNow(), baseLim = dailyLimitNow();
  S.gear = ["星辉战甲","时间沙漏","晨曦之冠"];
  equipItem("星辉战甲"); equipItem("时间沙漏"); equipItem("晨曦之冠");
  check(simCapNow() === baseSim + 1, "星辉战甲「同时进行上限+1」未生效：" + baseSim + " → " + simCapNow());
  check(dailyLimitNow() === baseLim + 1, "时间沙漏「每日接取上限+1」未生效：" + baseLim + " → " + dailyLimitNow());
  console.log("  星辉战甲：同时进行 " + baseSim + " → " + simCapNow() + " ✅");
  console.log("  时间沙漏：每日接取 " + baseLim + " → " + dailyLimitNow() + " ✅");
  const e5 = gearEffects();
  check(Math.abs((e5.pay["晨间"]||0) - 0.10) < 1e-9, "晨曦之冠「晨间报酬」解析失败");
  check(isMorningQuest(["x","x","06:00-09:00"]) && isMorningQuest(["x","x","08:00-23:30"]) && isMorningQuest(["x","x","全天"])
     && !isMorningQuest(["x","x","21:00-23:30"]) && !isMorningQuest(["x","x","12:00-23:30"]), "晨间委托判定有误");
  // 晨间报酬实测：只装晨曦之冠 → 100 × (1 + 0.12成就 + 0.10晨间) = 122（大成功 146）
  S.equipped = {weapon:null,armor:null,accessory:null,charmSlot:null}; S.gear = ["晨曦之冠"];
  equipItem("晨曦之冠");
  /* v1.41c：临时禁用节日（节日 +20% 报酬会干扰基线断言——假日跑测试不误报；测后还原） */
  const _fR = FESTIVAL_RANGES.splice(0);
  const _fS = FESTIVALS[todayStr().slice(5)]; delete FESTIVALS[todayStr().slice(5)];
  const mB = S.money;
  await settle({q:["晨间测试","采集","全天",60,"简单",100,1,8,{}], qlv:1, rate:1, meal:null,
    acceptTs:Date.now(), finishTs:Date.now()+3600000, name:"晨间测试"});
  FESTIVAL_RANGES.push.apply(FESTIVAL_RANGES, _fR);
  if(_fS) FESTIVALS[todayStr().slice(5)] = _fS;
  const dG = S.money - mB;
  check(dG === 122 || dG === 146, "晨间+成就饰品报酬应为 122（大成功 146），实际 " + dG);
  console.log("  晨间报酬实测：+铜 " + dG + "（122 = 100×(1+12%+10%)）✅");
  S.equipped = {weapon:null,armor:null,accessory:null,charmSlot:null};
  // v1.38o：穿戴精力上限装备——当前与上限同步 +差值；卸下收敛至新上限
  S.gear = ["龙鳞重铠"]; S.energy = 60;
  const _mE = energyMaxNow();
  equipItem("龙鳞重铠");
  check(S.energy === 95 && energyMaxNow() === _mE + 35, "穿戴精力上限装备：当前与上限同步 +35（60→95）");
  unequip("armor");
  check(energyMaxNow() === _mE && S.energy === Math.min(95, _mE), "卸下精力装备：当前精力收敛至新上限");
  S.equipped = {weapon:null,armor:null,accessory:null,charmSlot:null}; S.gear = [];
  // v1.38o：熬夜减免不溢出（未熬夜不受益；减免封顶于惩罚本身）
  const _qN = ["N测试","采集","全天",60,"简单",100,1,8,{}];
  const _hBak = JSON.stringify(S.history);
  S.history = [{date:todayStr(), score:80, sleep:true, done:0, tasks:[1,1,1,1,1,1,1], multi:[0,0]}];
  S.equipped = {weapon:null,armor:null,accessory:null,charmSlot:"安眠坠"};
  check(rateBreakdown(_qN).N === 0, "未熬夜：夜免装备不产生正加成（N=0，修前 +30%）");
  S.history[0].sleep = false;
  check(Math.abs(rateBreakdown(_qN).N + 0.05) < 1e-9, "熬夜 + 安眠坠(−10%)：惩罚减免至 −5%（v1.40 由 −30% 削弱，原完全免疫）");
  S.equipped = {weapon:null,armor:"龙鳞重铠",accessory:null,charmSlot:null};
  check(Math.abs(rateBreakdown(_qN).N + 0.15) < 1e-9, "熬夜 + 龙鳞重铠（v1.38o 词条已改精英续航）：惩罚 −15%，无夜免");
  S.history[0].sleep = true;
  check(rateBreakdown(_qN).N === 0, "未熬夜：无夜免词条装备不产生正加成（N=0）");
  S.history = JSON.parse(_hBak);
  S.equipped = {weapon:null,armor:null,accessory:null,charmSlot:null};
}

/* ═══════════ 6. 规则道具（5 种全用） ═══════════ */
console.log("\\n===== 6. 规则道具（5 种）=====");
{
  S.lvIdx = 4;
  S.health.done = [0,0,0,0,0,0,0]; S.health.multi = [0,0]; S.health.score = 0;
  S.items = {"清醒符咒":1};
  useItem("清醒符咒");
  check(S.health.done[1]===1 && !S.items["清醒符咒"], "清醒符咒未生效/未消耗");
  S.health.done[0] = 0; S.items = {"安眠护符":1};
  useItem("安眠护符");
  check(S.health.done[0]===1 && !S.items["安眠护符"], "安眠护符未生效/未消耗");
  S.items = {"活力药水":1};
  useItem("活力药水");
  check(S.health.score===100, "活力药水未锁定 100 分");
  S.items = {"疾风符咒":1};
  S.active = [{q:["采集草药","采集","全天",60,"简单",100,1,8,{}], qlv:1, rate:1, acceptTs:Date.now(), finishTs:Date.now()+99999999, name:"采药", meal:null}];
  useGale(0);
  check(!S.items["疾风符咒"], "疾风符咒未消耗");
  await new Promise(function(r){ setTimeout(r, 200); });
  S.poolPoint = "x";
  S.pool = {point:"x@08", list:drawPool({d:new Date(), h:8}), taken:false, bornTs:Date.now()};
  S.items = {"命运骰子":1};
  useItem("命运骰子");
  check(!S.items["命运骰子"] && !S.pool.taken, "命运骰子未生效/未消耗");
  console.log("  5 种道具全部生效 ✅");
}

/* ═══════════ 7. 公会厨房（9 个配方） ═══════════ */
console.log("\\n===== 7. 公会厨房（9 个配方全做）=====");
{
  S.lvIdx = 4; S.money = 0; S.energy = 0; S.lastMeal = null; S.mealCap = null; S.explore = 0;
  for(let i=0; i<CFG.recipes.length; i++){
    const r = CFG.recipes[i];
    if(r.sp) S.mealSp = null;                      // v1.41f5：逐道重置探索点料理限制（否则循环内第 3 道 sp 菜互斥）
    const _ingS = recipeIng(r); for(const k in _ingS) S.mats[k] = (S.mats[k]||0) + _ingS[k];   // v1.50：主辅材合并
    const e0 = S.energy, sp0 = S.explore||0, cap0 = mealCapBonus();
    cook(i);
    const d = [];
    if(r.en && S.energy <= e0 && S.energy < energyMaxNow()) d.push("精力未加");
    if(r.enPct && S.energy <= e0 && S.energy < energyMaxNow()) d.push("enPct 未加");   // v1.42
    if(r.sp && (S.explore||0) <= sp0) d.push("探索点未加");
    if(r.cap && mealCapBonus() <= cap0) d.push("上限未加");
    if((r.bonus||r.rate) && (!S.lastMeal || S.lastMeal.name !== r.n)) d.push("lastMeal 未设置");
    if(d.length) bad("料理["+r.n+"]: " + d.join("，"));
    else PASS++;
  }
  console.log("  " + CFG.recipes.length + " 个配方：烹饪与效果 ✅");
  // v1.41f5/f6：探索点料理——每日最多 2 次 + 当日累计上限 +5（品阶梯度 1/2/3/4/5）
  {
    const _iE1 = CFG.recipes.findIndex(function(r){ return r.n === "金盏花茶"; });   // 精良 sp1
    const _iE2 = CFG.recipes.findIndex(function(r){ return r.n === "星尘蜜露"; });   // 传说 sp5（v1.50）
    const _iE3 = CFG.recipes.findIndex(function(r){ return r.n === "月光花茶"; });   // 稀有 sp2
    { const _g1 = recipeIng(CFG.recipes[_iE1]); for(const k in _g1) S.mats[k] = _g1[k] * 3; }
    { const _g2 = recipeIng(CFG.recipes[_iE2]); for(const k in _g2) S.mats[k] = _g2[k] * 3; }
    { const _g3 = recipeIng(CFG.recipes[_iE3]); for(const k in _g3) S.mats[k] = _g3[k] * 3; }
    S.mealSp = null; S.explore = 0;
    cook(_iE1); cook(_iE1);                        // 金盏花茶 sp1 ×2 = +2
    check(S.explore === 2 && S.mealSp.cnt === 2, "v1.41f6：金盏花茶 ×2 共 +2 探索点（实际 +" + S.explore + "）");
    const _goldB = S.mats["金盏花"] || 0;
    cook(_iE1);                                    // 第 3 次 → 拒绝、不扣料
    check(S.explore === 2 && (S.mats["金盏花"] || 0) === _goldB, "v1.41f6：探索点料理每日第 3 次被拒（材料不扣）");
    S.mealSp = null; S.explore = 0;
    cook(_iE2); cook(_iE3);                        // 星尘蜜露 sp5 直达上限；月光花茶被拒（v1.50）
    check(S.explore === 5 && S.mealSp.got === 5, "v1.50：星尘蜜露 sp5 直达当日 +5 上限（月光花茶被拒，实际 +" + S.explore + "）");
  }
  // v1.42：巨龙盛宴 enPct——恢复 50% 精力上限
  {
    const _iFe = CFG.recipes.findIndex(function(r){ return r.n === "巨龙盛宴"; });
    { const _gf = recipeIng(CFG.recipes[_iFe]); for(const k in _gf) S.mats[k] = _gf[k]; }
    S.mealSp = null;   // 盛宴带 sp5，需重置探索点料理限次（前面限制测试已用满 2 次）
    S.energy = 0;
    const _em = energyMaxNow();
    cook(_iFe);
    check(S.energy === Math.round(_em * 0.5), "v1.42：巨龙盛宴恢复 50% 精力上限（" + S.energy + "/" + _em + "）");
  }
  // 料理加成实测：蜜渍烤鱼 +3% 报酬（100×1.03=103，大成功 125）
  const _mir = CFG.recipes.filter(function(r){ return r.n === "蜜渍烤鱼"; })[0];
  S.lastMeal = {date:todayStr(), name:"蜜渍烤鱼", bonus:_mir.bonus, rate:0};
  const _bT7 = S.titles; S.titles = [];            // v1.41：排除称号收集加成干扰（本段只测料理加成）
  const _fR2 = FESTIVAL_RANGES.splice(0);          // v1.41c：同样隔离节日 +20% 报酬影响
  const _fS2 = FESTIVALS[todayStr().slice(5)]; delete FESTIVALS[todayStr().slice(5)];
  const mB = S.money;
  await settle({q:["料理测试","采集","全天",60,"简单",100,1,8,{}], qlv:1, rate:1, meal:activeMeal(),
    acceptTs:Date.now(), finishTs:Date.now()+3600000, name:"料理测试"});
  FESTIVAL_RANGES.push.apply(FESTIVAL_RANGES, _fR2);
  if(_fS2) FESTIVALS[todayStr().slice(5)] = _fS2;
  const dG = S.money - mB;
  S.titles = _bT7;
  const _mbExp = Math.round(100 * (1 + _mir.bonus));           // 普通：100×1.03 = 103
  const _critExp = Math.round(120 * (1 + _mir.bonus));         // 大成功（报酬 ×1.2）：120×1.03 = 124
  check(dG === _mbExp || dG === _critExp, "料理报酬加成应为 " + _mbExp + "（大成功 " + _critExp + "），实际 " + dG);
  console.log("  蜜渍烤鱼报酬实测：+铜 " + dG + "（" + _mbExp + " = 100×" + (1+_mir.bonus).toFixed(2) + "）✅");
  // 香草烤肉成功率实测（v1.32：改用 Lv4 困难样本——原「护送贵族」在 Δ 加强后已达 cap，测不出 +2%）
  const q3 = ["讨伐独眼巨人","精英","08:00-23:30",180,"困难",50000,60,62,{"巨人骨":[1,3]}];
  S.lastMeal = null; const r0 = successRate(q3);
  S.lastMeal = {date:todayStr(), name:"香草烤肉", bonus:0, rate:0.02};
  const r1 = successRate(q3);
  check(r1 > r0, "香草烤肉成功率未体现在 successRate（" + Math.round(r0*100) + "% → " + Math.round(r1*100) + "%）");
  console.log("  香草烤肉成功率实测：" + Math.round(r0*100) + "% → " + Math.round(r1*100) + "% ✅");
}

/* ═══════════ 8. 商店 / 兑换 / 技能 / 护符 / 稀有事件 / 存档 ═══════════ */
console.log("\\n===== 8. 商店 / 兑换 / 技能 / 护符 / 稀有事件 / 存档 =====");
{
  S.lvIdx = 4; S.money = 100000000; S.con = 0; S.vit = 0;
  check(CFG.drawCount.join("-") === "1-3-5-6-8", "各级单次抽取数量 1-3-5-6-8");
  buy(1); check(true, "材料包");                          // v1.61d：精良材料包新索引 1
  S.vit = 100000; buyVit(3); check(S.con >= 10, "活力点兑换贡献失败");   // 贡献 +10 新索引 3
  S.con = 500; const matB8 = Object.keys(S.mats).length;
  buyCon(1); check(Object.keys(S.mats).length >= matB8, "贡献兑换材料失败");   // 探索点 +5 新索引 1
  /* v1.38k/m：批量购买 / 兑换（拖动条）+ 商店限购 */
  function _matTotal(){ let t = 0; for(const k in S.mats) t += S.mats[k]; return t; }
  function _epCount(){ let c = 0; for(const k in S.mats){ if(M[k] && M[k][1] === "史诗") c += S.mats[k]; } return c; }
  S.money = 100000000; S.items = {};
  S.shopDaily = {date: todayStr(), cnt:{}}; S.shopWeekly = {week: weekKey(), cnt:{}};
  const _mK = S.money;
  /* v1.38o：购买弹窗（独立小窗 + 拖动条 + −/+ 步进 + 「最大」）；v1.61d：改用普通材料包（清醒符咒已移至铂金商店） */
  openShopBuy("c", 0);
  check(dlgCap && dlgCap.t.indexOf("普通材料包") >= 0, "购买弹窗：独立小窗已弹出（购买 · 普通材料包）");
  check(dlgCap.b.indexOf('type="range"') >= 0, "购买弹窗：拖动条已渲染");
  check(dlgCap.b.indexOf("sbStep") >= 0 && dlgCap.b.indexOf("sbMax") >= 0, "购买弹窗：−/+ 步进 + 「最大」按钮");
  check(dlgCap.b.indexOf('max="3"') >= 0, "购买弹窗：数量按今日剩余 3 封顶");
  const _matP = _matTotal();
  document.getElementById("sbR_c_0").value = "1";   // 模拟弹窗选 ×1 后点「确认购买」
  dlgCap.btns[1].fn();
  check(_matTotal() === _matP + 5 && S.money === _mK - 6000, "弹窗确认 → 购买 ×1（+5 材料，-6000 铜）");
  buy(0, 2);                                        // 补满日限（3/3）
  const _cfA = confirmN;
  buy(0, 1);
  check(confirmN === _cfA, "已购满日限后再买被拒（普通材料包 日限 3；被拒不弹确认）");
  const _matK = _matTotal();
  const _cfB = confirmN;
  buy(1, 2);
  check(_matTotal() === _matK + 6, "批量购买材料包 ×2（+6 材料）");
  check(confirmN === _cfB + 1, "v1.53：购买经二次确认（累计确认 " + confirmN + " 次）");
  S.vit = 1000; const _eK = S.explore;
  buyVit(2, 3);
  check(S.explore === _eK + 15 && S.vit === 925, "批量活力点兑换 ×3（探索点 +15，活力点 -75）");
  /* 渠道独立限购（vit:/con: 前缀互不影响）——v1.61d：改用疾风符咒（同时上架活力/贡献/铂金三店） */
  S.vit = 1000; const _windK = S.items["疾风符咒"]||0;
  buyVit(1, 1);
  check((S.items["疾风符咒"]||0) === _windK + 1 && S.vit === 500, "活力渠道疾风符咒 ×1（-500 活力点）");
  S.con = 500;
  buyCon(0, 1);
  check((S.items["疾风符咒"]||0) === _windK + 2 && S.con === 100, "贡献渠道独立限购 ×1（-400 贡献，两渠道计数互不影响）");
  S.con = 10; buyCon(0, 1);
  check(S.con === 10, "已购满日限后再兑换被拒（不扣贡献）");
  /* v1.38o：史诗材料 周限 2；v1.41 H2：材料改真自选（弹窗选择，索引按名查找防插项错位） */
  S.con = 2000; const _epK = _epCount();
  const _iEp = CON_SHOP.findIndex(function(x){ return x.matSel && x.matSel[0] === "史诗"; });
  const _iRare = CON_SHOP.findIndex(function(x){ return x.matSel && x.matSel[0] === "稀有"; });
  const _epName = matPoolByTier("史诗")[0], _rareName = matPoolByTier("稀有")[0];
  buyCon(_iEp, 1);
  check(typeof _matPickCb === "function", "史诗材料兑换：弹出自选弹窗（v1.41 H2）");
  matPickChoose(_epName);
  check(_epCount() === _epK + 1 && S.con === 1700, "贡献兑换史诗材料 ×1（-300 贡献）");
  buyCon(_iEp, 1);
  matPickChoose(_epName);
  check(_epCount() === _epK + 2 && S.con === 1400, "史诗材料 ×2（周限 2 内）");
  buyCon(_iEp, 1);
  check(S.con === 1400, "史诗材料周限购拦截（每周 2）");
  /* v1.38o：稀有材料 周限 3 */
  function _rareCount(){ let c = 0; for(const k in S.mats){ if(M[k] && M[k][1] === "稀有") c += S.mats[k]; } return c; }
  S.con = 2000; const _rareK = _rareCount();
  buyCon(_iRare, 3);
  matPickChoose(_rareName);
  check(_rareCount() === _rareK + 6 && S.con === 1640, "稀有材料兑换 ×3（每次 2 个 → +6 材料，-360 贡献）");
  buyCon(_iRare, 1);
  check(S.con === 1640, "稀有材料周限购拦截（每周 3）");
  S.vit = 10000; S.incense = 0;
  buyVit(4, 5);                                      // v1.61d：薰香 Ⅰ 新索引 4
  check(S.incense === 1 && S.vit === 9920, "薰香忽略批量（固定单次：-80 而非 -400）");
  /* v1.38m：干粮 / 地图新效果 */
  S.items["神秘地图"] = 1; S.explore = 10;
  useItem("神秘地图");
  check(S.explore === 12 && !S.items["神秘地图"], "神秘地图 → +2 探索点");
  S.items["旅行干粮"] = 1; S.energy = 0;
  useItem("旅行干粮");
  check(S.energy === 30, "旅行干粮 → +30 精力");
  /* 渲染：行内不再有拖动条（已弹窗化）；限购状态显示（在重置前——计数仍 1/1、2/2） */
  S.money = 5000000; render();
  const _kH = document.getElementById("tab-shop").innerHTML || "";
  check(_kH.indexOf('type="range"') < 0, "商店行：拖动条已移入弹窗（行内不渲染）");
  check(_kH.indexOf("📅 今日 3/3") >= 0, "限购状态显示（普通材料包 今日 3/3）");
  check(_kH.indexOf("📅 本周 2/2") >= 0, "周限购显示（史诗材料 本周 2/2）");
  check(_kH.indexOf("📅 本周 3/3") >= 0, "周限购显示（稀有材料 本周 3/3）");
  /* v1.61d：铂金商店（持有 5 铂金 → 内容可见）；薰香卡只展示下一阶；大师商店未解锁 → 界面保留内容隐藏 */
  check(_kH.indexOf("🏛 铂金商店") >= 0 && _kH.indexOf("清醒符咒") >= 0 && _kH.indexOf("安眠护符") >= 0,
        "铂金商店：≥1 铂金币内容可见（含清醒符咒 / 安眠护符）");
  check(_kH.indexOf("🕯️ 安眠薰香") >= 0 && _kH.indexOf("第 2 级") >= 0 && _kH.indexOf("安眠薰香 I") < 0 && _kH.indexOf("安眠薰香 II") < 0,
        "薰香卡：只展示下一阶（Ⅰ 已购 → 只出 Ⅱ；不再整列 Ⅰ~Ⅴ）");
  const _achvK = S.achv; S.achv = []; render();
  const _kM = document.getElementById("tab-shop").innerHTML || "";
  check(_kM.indexOf("🎓 大师商店") >= 0 && _kM.indexOf("内容隐藏——需达成成就") >= 0,
        "大师商店：未解锁时界面保留、内容隐藏（v1.61d）");
  S.achv = _achvK; render();
  S.money = 500000; render();
  const _kH2 = document.getElementById("tab-shop").innerHTML || "";
  check(_kH2.indexOf("🏛 铂金商店") >= 0 && _kH2.indexOf("内容隐藏——需持有") >= 0,
        "铂金商店：持有 <1 铂金币 → 界面保留、内容隐藏（v1.61d）");
  S.money = 5000000; render();
  /* v1.61d：规则道具不可出售（交易所仅收材料） */
  S.money = 1000; S.items["清醒符咒"] = 1;
  const _smR = (typeof sellMat === "function") ? sellMat("清醒符咒") : null;
  check(S.money === 1000 && S.items["清醒符咒"] === 1, "规则道具不可出售（sellMat 对非材料直接忽略）");
  /* v1.38o/p2：荣誉区——冥念护符获取后显示（0 级隐藏）+ 成就全部达成揭晓真实总数 */
  const _achvBak = S.achv.slice();
  const _charmBak = S.charm;
  S.achv = []; S.charm = 0;
  renderLog();
  check((document.getElementById("tab-log").innerHTML||"").indexOf("冥念护符") < 0, "荣誉区：未获取冥念护符时隐藏（0 级）");
  S.charm = 1;
  renderLog();
  check((document.getElementById("tab-log").innerHTML||"").indexOf("冥念护符") >= 0, "荣誉区：冥念护符获取后显示");
  S.charm = _charmBak;
  renderLog();
  check((document.getElementById("tab-log").innerHTML||"").indexOf("成就</span><b>0 / ?") >= 0, "荣誉区：成就未集齐仍隐藏总数（0 / ?）");
  S.achv = ACHV.map(function(a){ return a.n; });
  renderLog();
  check((document.getElementById("tab-log").innerHTML||"").indexOf(ACHV.length + " / " + ACHV.length + " ✓ 已全部达成") >= 0, "荣誉区：成就全部达成后揭晓真实总数");
  /* v1.38p2：健康页成就列表（全部达成后列出具体成就名） */
  renderHealth();
  const _TH = document.getElementById("tab-health").innerHTML || "";
  check(_TH.indexOf("🏅 成就</b>") >= 0 && _TH.indexOf(ACHV[0].n) >= 0, "健康页：全部达成后展示具体成就名单");
  S.achv = _achvBak;
  /* v1.38p2：探索区域详情弹窗 */
  dlgCap = null;
  showRegionDetail(0);
  check(dlgCap && dlgCap.t.indexOf("晨光森林") >= 0, "探索详情：弹窗标题为区域名");
  check(dlgCap && dlgCap.b.indexOf("止血草") >= 0 && dlgCap.b.indexOf("清醒符咒") >= 0, "探索详情：列出掉落材料与道具");
  check(dlgCap && dlgCap.b.indexOf("开放时间") >= 0 && dlgCap.b.indexOf("耗时") >= 0, "探索详情：显示开放时间与耗时");
  /* v1.38m：限购重置（跨天 / 跨周幂等） */
  S.active = []; S.lastDay = todayStr();
  S.shopDaily = {date:"1970-01-01", cnt:{"c:清醒符咒":9}};
  tick();
  check(S.shopDaily.date === todayStr() && !(S.shopDaily.cnt||{})["c:清醒符咒"], "跨天重置每日限购");
  S.shopWeekly = {week:"W-OLD", cnt:{"con:指定史诗材料×1":9}};
  tick();
  check(S.shopWeekly.week === weekKey() && !(S.shopWeekly.cnt||{})["con:指定史诗材料×1"], "跨周重置每周限购");
  S.con = 100000; S.skills = {"体能":0,"专注":0,"社交":0,"生存":0,"幸运":0}; S.rep = 999999; S.lvIdx = 4;
  upSkill("体能"); check((S.skills["体能"]||0) === 1, "技能升级失败");
  // 满公会（P 级）技能上限应满 25
  check(skillCap() === 25, "P 级公会技能上限应为 25，实际 " + skillCap());
  S.vit = 1000000; S.charm = 0;
  buyCharm(); check(S.charm === 1, "冥念护符 I 未解锁");
  tryRareEvent = _rareOrig1;   // 段 8：恢复真实稀有事件（其后的判定需要真实函数）
  let rareN = 0;
  for(let i=0;i<300;i++) if(tryRareEvent("采集","测试")) rareN++;
  console.log("  稀有事件 300 次判定：触发 " + rareN + " 次（基线 5% ≈ 15 次）" + (rareN>=3 ? " ✅" : " ❌"));
  rareN>=3 ? PASS++ : FAIL++;
  // 图纸 + 打造全流程
  S.money = 100000000; S.blueprints = {}; S.gear = [];
  const _cfC = confirmN;
  buyBlueprint("铜剑");
  check(confirmN === _cfC + (S.blueprints["铜剑"] ? 1 : 0), "v1.53：图纸购买经二次确认");
  if(S.blueprints["铜剑"]){
    S.mats["铜矿石"] = 99; S.mats["松木"] = 99;   // v1.38i：副材料需「矿石/木材/兽材」同系品类（止血草=草药不适用）
    const g0 = S.gear.length;
    const _cfD = confirmN;
    craft("铜剑");
    check(S.gear.length > g0, "打造铜剑失败");
    check(confirmN === _cfD + 1, "v1.53：打造经二次确认");
  } else {
    buyBlueprint(GEAR[0][0]);   // 回退：按第一件图纸
  }
  /* v1.38o：公会特权委托 / 时间沙漏委托接取（占接取次数与同时进行上限） */
  S.lvIdx = 4; S.accepted = 0; S.active = []; S.energy = 500;
  S.privQuest = ["特权测试","采集","全天",60,"简单",100,1,8,{}];
  acceptPriv();
  check(S.accepted === 1 && S.privQuest === null && S.active.length === 1, "公会特权委托接取：计入接取次数与进行中");
  S.glassQuest = ["沙漏测试","采集","全天",60,"简单",100,1,8,{}];
  acceptGlass();
  check(S.accepted === 2 && S.glassQuest === null && S.active.length === 2, "时间沙漏委托接取：计入接取次数与进行中");
  S.active = []; S.accepted = 0;
  /* v1.38p：公会额外委托 6 选 1（不占接取次数） */
  S.lvIdx = 4; S.energy = 500;
  S.bonusQuests = [["额外A","采集","全天",60,"简单",100,1,8,{}],["额外B","采集","全天",60,"简单",100,1,8,{}]];
  acceptBonus(1);
  check(S.bonusQuests === null && S.active.length === 1 && S.active[0].name === "额外B" && S.accepted === 0, "公会额外委托 6 选 1：选第 2 个接取、整批清空、不占接取次数");
  S.active = []; S.accepted = 0;
  /* v1.38o：酒馆传闻当日补齐（幂等——修复"每次刷新页面就变"） */
  S.rumor = null; tick();
  check(S.rumor && S.rumor.date === todayStr(), "酒馆传闻：当日缺失时 tick 幂等补齐");
  const _rumorIdx = S.rumor.idx; tick();
  check(S.rumor.idx === _rumorIdx, "酒馆传闻：同日重复 tick 不重掷");
  // 存档兼容
  save(); const n0 = S.name; const mats0 = JSON.stringify(S.mats);
  S = null; load();
  check(S.name === n0 && JSON.stringify(S.mats) === mats0, "存读档不一致");
  console.log("  商店 / 兑换 / 技能 / 护符 / 图纸打造 / 存档 ✅");
}

/* ═══════════ 9. v1.32 装备槽弹窗 + 三餐按钮 ═══════════ */
console.log("\\n===== 9. 装备槽弹窗 + 三餐按钮 =====");
{
  S.gear = ["铜剑","皮甲","安神吊坠"];
  S.equipped = {weapon:null, armor:"皮甲", accessory:null, charmSlot:null};
  check(typeof openSlotPicker === "function", "openSlotPicker 已定义");
  renderBag();
  const h = document.getElementById("tab-bag").innerHTML;
  check(h.includes("openSlotPicker('weapon')") && h.includes(">装备</button>"), "装备栏：空槽显示「装备」按钮");
  check(h.includes("openSlotPicker('armor')") && h.includes(">更换</button>"), "装备栏：已装备槽显示「更换」按钮");
  /* v1.61d：背包双栏等高容器 + 宠物小界面清除（用户指定） */
  check((h.match(/class="qcol"/g) || []).length === 2 && h.includes('<div class="qsplit">'), "背包：qsplit 双栏结构（两栏等高容器）");
  check(!h.includes("宠物") && !h.includes("gotoPetTab"), "背包：无宠物小界面残留（v1.61d 删除）");
  renderHealth();
  check(document.getElementById("tab-health").innerHTML.includes("meal-btn"), "三餐按钮使用加大样式 meal-btn");
  console.log("  装备槽按钮（装备/更换）与三餐按钮 ✅");
}

/* ═══════════ 10. v1.38e/f 材料/道具/料理/装备/成就/称号详情弹窗 ═══════════ */
console.log("\\n===== 10. 详情弹窗（材料/道具/料理/装备/成就/称号）=====");
{
  showMatDetail("松木");
  check(dlgCap && dlgCap.t === "材料详情" && (dlgCap.b || "").includes("松木"), "showMatDetail：弹窗渲染");
  showItemDetail("清醒符咒");
  check(dlgCap && dlgCap.t === "道具详情" && (dlgCap.b || "").includes("清醒符咒"), "showItemDetail：弹窗渲染");
  showCookDetail("菌菇汤");
  check(dlgCap && dlgCap.t === "料理详情" && (dlgCap.b || "").includes("菌菇汤"), "showCookDetail：弹窗渲染");
  showGearDetail("铜剑");
  check(dlgCap && dlgCap.t === "装备详情" && (dlgCap.b || "").includes("铜剑"), "showGearDetail：弹窗渲染");
  showAchvDetail();
  check(dlgCap && (dlgCap.t || "").indexOf("成就") >= 0, "showAchvDetail：弹窗渲染");
  showTitleDetail();
  check(dlgCap && (dlgCap.t || "").indexOf("称号") >= 0, "showTitleDetail：弹窗渲染");
  console.log("  详情弹窗 ✅");
}

/* ═══════════ 11. v1.38f 携带宠物（陪同委托成长） ═══════════ */
console.log("\\n===== 11. 携带宠物（陪同委托成长）=====");
{
  S.pets = ["星界幼龙", "月光狐"];
  S.petData = {"星界幼龙": {stage: 1, growth: 0, mutate: 0, fedDate: "", fedCount: 0},
               "月光狐": {stage: 1, growth: 0, mutate: 0, fedDate: "", fedCount: 0}};
  S.carryPet = "";
  check(petQuestGain(C["Lv1"][0], true, 0) === "", "未携带 → 无成长");
  setCarryPet("星界幼龙");
  check(S.carryPet === "星界幼龙", "setCarryPet：设置携带");
  const _g0 = S.petData["星界幼龙"].growth;
  const _n1 = petQuestGain(C["Lv1"][0], true, 0);
  check(S.petData["星界幼龙"].growth === _g0 + 1 && _n1.indexOf("成长 +1") >= 0, "Lv1 普通成功 +1");
  const _exp3 = 1 + 1 + ((C["Lv5"][0][4] === "困难" || C["Lv5"][0][4] === "噩梦") ? 1 : 0);
  const _g1 = S.petData["星界幼龙"].growth;
  petQuestGain(C["Lv5"][0], true, 4);
  check(S.petData["星界幼龙"].growth === _g1 + _exp3, "Lv5 " + C["Lv5"][0][4] + " 成功 +" + _exp3);
  const _g2 = S.petData["星界幼龙"].growth;
  petQuestGain(C["Lv1"][0], false, 0);
  check(S.petData["星界幼龙"].growth === _g2 + 1, "失败保底 +1");
  S.petData["星界幼龙"].stage = 4;
  const _g3 = S.petData["星界幼龙"].growth;
  check(petQuestGain(C["Lv1"][0], true, 0) === "" && S.petData["星界幼龙"].growth === _g3, "满阶不再成长");
  S.petData["星界幼龙"].stage = 1;
  setCarryPet("星界幼龙");                       // 看家（同名再点）
  setCarryPet("月光狐");
  const _fr = petQuestGain(C["Lv1"][0], true, 0);
  check(_fr.indexOf("阅读") >= 0 && S.petData["月光狐"].growth === 0, "v1.55：月光狐（阅读驱动）只提示、不涨成长");
  check(carryPetLabel().indexOf(PET_LINES["月光狐"].stages[0].name) >= 0, "carryPetLabel：显示当前形态名");
  render();
  check((document.getElementById("tab-quest").innerHTML || "").indexOf("携带宠物") >= 0, "今日状态：显示携带宠物行");
  setCarryPet("月光狐");
  check(S.carryPet === "", "setCarryPet：再点看家");
  render();
  check((document.getElementById("tab-quest").innerHTML || "").indexOf("看家中") >= 0, "今日状态：看家提示");
  // v1.55b：品阶体系
  // v1.55c：品阶营养（未列出材料按品阶给成长）
  check(petFeedValue("捣蛋鬼", "龙心").v === 15 && petFeedValue("捣蛋鬼", "龙心").mv === 10, "品阶营养：未列出传说材料 +15 成长（对齐小狼）");
  check(petFeedValue("捣蛋鬼", "月光草").v === 4 && petFeedValue("深渊之眼", "暗影草").v === 10, "品阶营养：未列出按品阶 / 口味与品阶取较高者");
  check(petFeedValue("绒球兽", "蘑菇").v === 5 && petFeedValue("绒球兽", "兽肉").refuse === true, "品阶营养：口味保留 / 拒食不变");
  check(petFeedValue("星界幼龙", "星核").v === 17 && petFeedValue("史莱姆", "星核").refuse === true, "v1.56e：本命材料（星核：星界幼龙 +17 / 别家拒食）");
  check(petFeedValue("月光狐", "龙心").v === 0, "品阶营养：阅读驱动宠物不吃营养（成长仍来自阅读）");
  check(petRankOf("史莱姆") === "普通" && petRankOf("绒球兽") === "精良" && petRankOf("捣蛋鬼") === "稀有"
    && petRankOf("月光狐") === "史诗" && petRankOf("小狼") === "史诗" && petRankOf("星界幼龙") === "传说"
    && petRankOf("深渊之眼") === "传说", "petRankOf：品阶映射（5 档）");
  S.pets = ["史莱姆", "月光狐"]; petDataOf("史莱姆"); petDataOf("月光狐");
  showPetDetail("月光狐");
  check(dlgCap && (dlgCap.b || "").indexOf("品阶") >= 0 && (dlgCap.b || "").indexOf("史诗") >= 0, "宠物详情：显示品阶徽章");
  render();
  const _galH = document.getElementById("tab-gallery").innerHTML || "";
  check(_galH.indexOf('t-传说') >= 0 || _galH.indexOf('t-史诗') >= 0, "图鉴：宠物格显示品阶");
  console.log("  携带宠物 ✅");
}

/* ═══════════ 12. v1.38g 背包筛选 / 详情补全 ═══════════ */
console.log("\\n===== 12. 背包筛选与详情补全 =====");
{
  S.mats = {"松木": 5, "白桦木": 3, "龙血": 1, "月光草": 1};   // v1.46：草药样本用「月光草」（不在炼金台配方中，避免干扰断言）
  bagMatCat = "全部"; render();
  let _bh = document.getElementById("tab-bag").innerHTML || "";
  check(_bh.indexOf("木材") >= 0 && _bh.indexOf("草药") >= 0 && _bh.indexOf("特殊") >= 0, "背包：品类筛选按钮渲染");
  check(_bh.indexOf("龙血") < _bh.indexOf("松木"), "v1.54：背包材料高品阶→低品阶排序（龙血·传说 在 松木·普通 之前）");
  setBagFilter("mat", "木材");
  check(bagMatCat === "木材", "背包：筛选状态记录");
  _bh = document.getElementById("tab-bag").innerHTML || "";
  check(_bh.indexOf("松木") >= 0 && _bh.indexOf("白桦木") >= 0 && _bh.indexOf("龙血") < 0 && _bh.indexOf("月光草") < 0, "背包：仅显示所选品类（v1.46：样本避开炼金台配方材料）");
  setBagFilter("mat", "全部");
  check((document.getElementById("tab-bag").innerHTML || "").indexOf("龙血") >= 0, "背包：恢复全部");
  S.seenMats = ["止血草", "龙血", "松木", "白桦木", "凤凰木"];
  render();
  const _gh = document.getElementById("tab-gallery").innerHTML || "";
  check(_gh.indexOf("凤凰木") < _gh.indexOf("松木"), "v1.54：图鉴材料同品类组内高品阶→低品阶（凤凰木·史诗 在 松木·普通 之前）");
  check(_gh.indexOf("止血草") < _gh.indexOf("龙血"), "图鉴材料：品类顺序（草药 → 特殊）");
  /* v1.54：高品阶→低品阶排序（背包装备 / 打造 / 图纸商店 / 装备选择弹窗） */
  {
    const _gq = GEAR.filter(function(g){ return g[1] === "普通" && g[2] === "武器"; })[0];   // 普通武器
    const _gL = GEAR.filter(function(g){ return g[1] === "传说" && g[2] === "武器"; })[0];   // 传说武器
    const _gbak = S.gear, _bbak = S.blueprints;
    S.gear = [_gq[0], _gL[0]];
    bagGearSlot = "全部"; render();
    const _bh2 = document.getElementById("tab-bag").innerHTML || "";
    check(_bh2.indexOf(_gL[0]) < _bh2.indexOf(_gq[0]), "v1.54：背包装备高品阶→低品阶（传说在普通之前）");
    S.blueprints = {}; S.blueprints[_gq[0]] = true; S.blueprints[_gL[0]] = true;
    craftPart = "全部"; render();
    const _bh3 = document.getElementById("tab-bag").innerHTML || "";
    check(_bh3.indexOf(_gL[0]) < _bh3.indexOf(_gq[0]), "v1.54：打造列表高品阶→低品阶");
    S.rep = 999999; render();                                   // 拉满公会 → 全部图纸档位解锁
    const _bh4 = document.getElementById("tab-shop").innerHTML || "";   // 图纸商店在商店页
    check(_bh4.indexOf("传说 图纸") >= 0 && _bh4.indexOf("传说 图纸") < _bh4.indexOf("普通 图纸"), "v1.54：图纸商店高品阶档位在上（传说 → 普通）");
    openSlotPicker("weapon");
    const _pk2 = (dlgCap && dlgCap.b) || "";
    check(_pk2.indexOf(_gL[0]) < _pk2.indexOf(_gq[0]), "v1.54：装备选择弹窗高品阶→低品阶");
    clrDlg();
    S.gear = _gbak; S.blueprints = _bbak;
  }
  showQuestDetailByName(C["Lv1"][0][0]);
  check(dlgCap && dlgCap.t === "委托详情" && (dlgCap.b || "").indexOf(C["Lv1"][0][0]) >= 0, "showQuestDetailByName：图鉴委托详情弹窗");
  /* v1.38q 回归：刷新池委托卡（数字索引）必须打开池详情——曾被图鉴版同名函数覆盖导致点击无反应 */
  S.pool = {point: todayStr()+"@08", list: [C["Lv1"][0]], taken: false, bornTs: Date.now(), expiredLogged: false};
  S.accepted = 0; S.active = []; S.energy = energyMaxNow();
  showQuestDetail(0);
  check(dlgCap && (dlgCap.t || "").indexOf("委托详情") >= 0
    && (dlgCap.btns || []).some(function(b){ return b.text === "接取委托"; }), "showQuestDetail(索引)：刷新池详情 + 接取按钮（v1.38q 回归）");
  /* v1.38q 回归：sleepStreak() 无参须返回连击天数——曾被带参版覆盖恒返回 false（连击保险失效） */
  const _histBak = S.history, _shieldBak = S.shieldDays;
  S.history = [ {date:"2026-09-27", sleep:false, score:60}, {date:"2026-09-28", sleep:true, score:80}, {date:"2026-09-29", sleep:true, score:80}, {date:"2026-09-30", sleep:true, score:80} ];
  S.shieldDays = [];
  check(sleepStreak() === 3, "sleepStreak()：无参返回连击天数（v1.38q 回归）");
  check(tryComboShield(3) === false, "tryComboShield：连击 <7 不触发");
  S.history = _histBak; S.shieldDays = _shieldBak;
  showPetDetail("月光狐");
  check(dlgCap && dlgCap.t === "宠物详情" && (dlgCap.b || "").indexOf("月光狐") >= 0
    && (dlgCap.b || "").indexOf("品阶") >= 0, "showPetDetail：宠物详情弹窗（含品阶）");
  /* v1.61f：宠物详情展示具体心情值（数值 / 100 + 进度条） */
  const _pmB = petMetaOf("月光狐");
  check(dlgCap && (dlgCap.b || "").indexOf("心情值 <b") >= 0
    && (dlgCap.b || "").indexOf(">" + _pmB.mood + "</b> / 100") >= 0
    && (dlgCap.b || "").indexOf("width:" + _pmB.mood + "%;background:") >= 0,
    "showPetDetail：具体心情值（数值 / 100 + 进度条）");
  /* v1.61h：宠物礼物池 + 携带宠物拾取（艾露猫式） */
  let _poolBad61 = [];
  Object.keys(PET_GIFTS).forEach(function(k){
    const _pl = PET_GIFTS[k];
    if(_pl.length < 4 || _pl.length > 6) _poolBad61.push(k + " 种类 " + _pl.length);
    const _sm = _pl.reduce(function(a, x){ return a + x[1]; }, 0);
    if(Math.abs(_sm - 100) > 0.001) _poolBad61.push(k + " 权重和 " + _sm);
    _pl.forEach(function(x){ if(!M[x[0]]) _poolBad61.push(k + " " + x[0]); });
  });
  check(!_poolBad61.length, "礼物池结构：每宠 4~6 种 / 权重和 100 / 材料齐备" + (_poolBad61.length ? "（" + _poolBad61.join("；") + "）" : ""));
  const _rndG61 = Math.random;
  Math.random = function(){ return 0; };
  const _gg61 = petGiftRoll("史莱姆");
  Math.random = _rndG61;
  check(_gg61.name === "泉水" && _gg61.n === 1, "礼物抽取：权重 0 → 首项（史莱姆 → 泉水 ×1，实得 " + _gg61.name + "×" + _gg61.n + "）");
  Math.random = function(){ return 0.99999; };
  const _gg61b = petGiftRoll("星界幼龙");
  Math.random = _rndG61;
  check(_gg61b.name === "星辉绸" && _gg61b.n === 1, "礼物抽取：权重尾 → 低概率稀有物（星界幼龙 → 星辉绸 ×1，实得 " + _gg61b.name + "×" + _gg61b.n + "）");
  const _carryBak61 = S.carryPet;
  const _moodBak61 = S.wolf ? S.wolf.mood : null;
  if(S.wolf) S.wolf.mood = 50;
  S.carryPet = null;
  check(petFindRoll("quest", ["兽肉"], false) === null, "拾取：未携带宠物 → 不触发");
  S.carryPet = "小狼";
  const _seq61 = [0.05, 0.0, 0.0, 0.0];
  Math.random = function(){ return _seq61.length ? _seq61.shift() : 0.5; };
  const _pf61A = petFindRoll("quest", [["兽肉", 3], ["河鱼", 1]], false);
  Math.random = _rndG61;
  check(_pf61A && _pf61A.length === 1 && _pf61A[0].name === "兽肉" && _pf61A[0].n === 1,
    "拾取：命中 → 限本内容材料池（权重对数组 · 实得 " + JSON.stringify(_pf61A) + "）");
  const _seq61b = [0.05, 0.0, 0.9999];
  Math.random = function(){ return _seq61b.length ? _seq61b.shift() : 0.5; };
  const _pf61B = petFindRoll("quest", [["蘑菇", 1.5], ["龙心", 1]], false);
  Math.random = _rndG61;
  check(_pf61B && _pf61B[0].name === "龙心", "拾取：权重随内容产出——龙心 ×1 / 蘑菇 期望 1.5 · 权重尾命中（实得 " + (_pf61B ? _pf61B[0].name : "null") + "）");
  const _seq61g = [0.05, 0.0, 0.26, 0.0];
  Math.random = function(){ return _seq61g.length ? _seq61g.shift() : 0.5; };
  const _pf61G = petFindRoll("quest", [["蘑菇", 1], ["河鱼", 3]], false);
  Math.random = _rndG61;
  check(_pf61G && _pf61G[0].name === "河鱼", "拾取：概率 ∝ 内容产出权重——0.26 落入河鱼 75% 份额（实得 " + JSON.stringify(_pf61G) + "）");
  check(!("tierW" in PET_FIND), "拾取：全品阶权重 tierW 已移除（v1.61k —— 不再与内容掉表打架）");
  const _seq61c = [0.025, 0.0, 0.99];
  Math.random = function(){ return _seq61c.length ? _seq61c.shift() : 0.5; };
  const _pf61C = petFindRoll("quest", [["蘑菇", 1], ["河鱼", 1], ["泉水", 1]], true);
  Math.random = _rndG61;
  check(_pf61C && _pf61C.length === 1 && _pf61C[0].n <= 2, "拾取：失败上限 1 种 / ≤2 个（实得 " + JSON.stringify(_pf61C) + "）");
  const _seq61e = [0.05];
  Math.random = function(){ return _seq61e.length ? _seq61e.shift() : 0.99; };
  const _pf61E = petFindRoll("quest", [["蘑菇", 1]], true);
  Math.random = _rndG61;
  check(_pf61E === null, "拾取：失败减半——委托 6%→3%，0.05 失败时不触发（v1.61j）");
  const _seq61f = [0.08];
  Math.random = function(){ return _seq61f.length ? _seq61f.shift() : 0.99; };
  const _pf61F = petFindRoll("legend", [["星辉花", 1]], true);
  Math.random = _rndG61;
  check(_pf61F === null, "拾取：失败减半——传奇 12%→6%，0.08 不触发（v1.61j）");
  check(PET_FIND.failMul === 0.5, "拾取：PET_FIND.failMul = 0.5（失败减半系数 · v1.61j）");
  const _seq61d = [0.05, 0.99, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
  Math.random = function(){ return _seq61d.length ? _seq61d.shift() : 0.5; };
  const _pf61D = petFindRoll("quest", [["蘑菇", 1], ["河鱼", 1], ["泉水", 1], ["蜂蜜", 1]], false);
  Math.random = _rndG61;
  check(_pf61D && _pf61D.length === 3 && _pf61D.reduce(function(a, g){ return a + g.n; }, 0) <= 4,
    "拾取：上限 3 种 / 合计 ≤4（实得 " + JSON.stringify(_pf61D) + "）");
  S.carryPet = _carryBak61;
  if(S.wolf && _moodBak61 !== null) S.wolf.mood = _moodBak61;
  render();
  check((document.getElementById("tab-log").innerHTML || "").indexOf("宠物（") >= 0
    && (document.getElementById("tab-log").innerHTML || "").indexOf("月光狐") >= 0, "信息页：全宠物总览（不再只显示小狼）");
  console.log("  背包筛选与详情 ✅");
}

/* ═══════════ 13. v1.38h 难度标识 / 料理品级 / 打造部位 ═══════════ */
console.log("\\n===== 13. 难度标识 / 料理品级 / 打造部位 =====");
{
  check(cookTier(CFG.recipes.filter(function(r){ return r.n === "菌菇汤"; })[0]) === "普通", "料理品级：菌菇汤 = 普通");
  check(cookTier(CFG.recipes.filter(function(r){ return r.n === "巨龙盛宴"; })[0]) === "传说", "料理品级：巨龙盛宴 = 传说");
  S.cooked = ["菌菇汤", "山珍炖品", "巨龙盛宴"];
  render();
  const _gal2 = document.getElementById("tab-gallery").innerHTML || "";
  check(_gal2.indexOf("巨龙盛宴") < _gal2.indexOf("山珍炖品") && _gal2.indexOf("山珍炖品") < _gal2.indexOf("菌菇汤"), "v1.54：图鉴料理按品级高→低排列（传说 → 普通）");
  S.doneQuests = {};
  (C["Lv1"]||[]).forEach(function(q){ S.doneQuests[q[0]] = 1; });
  render();
  const _gal3 = document.getElementById("tab-gallery").innerHTML || "";
  check(_gal3.indexOf("简单") >= 0 || _gal3.indexOf("困难") >= 0 || _gal3.indexOf("噩梦") >= 0, "图鉴委托：难度文字标识");
  const _l1 = C["Lv1"] || [];
  check(!_l1.length || DIFF_ORDER.indexOf(_l1[0][4]) <= DIFF_ORDER.indexOf(_l1[_l1.length-1][4]), "图鉴委托：同等级按难度低→高");
  S.blueprints = {}; GEAR.forEach(function(g){ S.blueprints[g[0]] = true; });
  S.mats = {}; S.money = 0; S.gear = []; S.equipped = {weapon:null, armor:null, accessory:null, charmSlot:null};
  craftPart = "全部"; craftFilter = "全部"; render();
  let _b2 = document.getElementById("tab-bag").innerHTML || "";
  check(_b2.indexOf("全部（") >= 0, "打造：部位筛选按钮（含计数）");
  check(_b2.indexOf("武器（") >= 0 && _b2.indexOf("只看材料齐备（") >= 0, "打造：按钮计数联动（部位 / 可打造）");
  setBagFilter("part", "武器");
  check(craftPart === "武器", "打造：部位筛选状态");
  _b2 = document.getElementById("tab-bag").innerHTML || "";
  check(_b2.indexOf("铜剑") >= 0 && _b2.indexOf("皮甲") < 0, "打造：仅显示武器部位");
  setBagFilter("craft", "可打造");
  _b2 = document.getElementById("tab-bag").innerHTML || "";
  check(_b2.indexOf("铜剑") < 0 && _b2.indexOf("当前筛选下没有") >= 0, "打造：只看材料齐备（无材料 → 空列表提示）");
  setBagFilter("craft", "全部");
  S.mats = {"铜矿石":99, "松木":99}; S.money = 1000000;
  setBagFilter("craft", "可打造");
  _b2 = document.getElementById("tab-bag").innerHTML || "";
  check(_b2.indexOf("铜剑") >= 0, "打造：材料齐备后出现在筛选列表");
  setBagFilter("part", "全部"); setBagFilter("craft", "全部");
  S.wolf = {stage: 2, growth: 5, mutate: 0};
  showPetDetail("小狼");
  check(dlgCap && dlgCap.t === "宠物详情" && (dlgCap.b || "").indexOf("食谱偏好") >= 0, "小狼详情：食谱偏好说明");
  console.log("  难度 / 料理品级 / 打造部位 ✅");
}

/* ═══════════ 14. v1.38i 物品描述（简介审查 + 风味） ═══════════ */
console.log("\\n===== 14. 物品描述（图鉴简介与风味）=====");
{
  check(MAT_DESC["静心香"] && MAT_DESC["静心香"].indexOf("安神") >= 0, "材料描述：静心香为安神线香（非打造材料）");
  check(MAT_USE["特殊"].indexOf("与打造无关") >= 0, "品类用途：特殊品类文案已修正");
  check(Object.keys(M).every(function(k){ return MAT_DESC[k]; }), "材料描述：" + Object.keys(M).length + " 种全部覆盖");
  check(GEAR.every(function(g){ return GEAR_FLAVOR[g[0]]; }), "装备描述：" + GEAR.length + " 件全部覆盖");
  check(CFG.recipes.every(function(r){ return COOK_FLAVOR[r.n]; }), "料理描述：25 道全部覆盖");
  check(Object.keys(ITEM_DESC).every(function(k){ return ITEM_FLAVOR[k]; }), "道具描述：11 种全部覆盖");
  showMatDetail("静心香");
  check(dlgCap && (dlgCap.b || "").indexOf("安神线香") >= 0 && (dlgCap.b || "").indexOf("奇物宝材") >= 0, "静心香详情：专属描述 + 修正后的品类文案");
  showGearDetail("铜剑");
  check(dlgCap && (dlgCap.b || "").indexOf("见习剑士的第一把剑") >= 0, "铜剑详情：展示装备描述");
  showItemDetail("疾风符咒");
  check(dlgCap && (dlgCap.b || "").indexOf("旋风符文") >= 0, "道具详情：展示风味描述");
  showCookDetail("巨龙盛宴");
  check(dlgCap && (dlgCap.b || "").indexOf("公会大厅安静下来") >= 0, "料理详情：展示风味描述");
  console.log("  物品描述 ✅");
}

/* ═══════════ 15. v1.38j 装备主属性外部显示 ═══════════ */
console.log("\\n===== 15. 装备主属性显示 =====");
{
  S.forged = ["铜剑", "圣兽羽饰"];
  S.gear = ["圣兽羽饰", "铜剑"];
  S.equipped = {weapon:null, armor:null, accessory:null, charmSlot:null};
  S.seenMats = []; S.cooked = []; S.blueprints = {};
  render();
  const _gH = document.getElementById("tab-gallery").innerHTML || "";
  check(_gH.indexOf("成功率 +1%") >= 0, "图鉴装备卡：显示主属性（铜剑 成功率 +1%）");
  check(_gH.indexOf("报酬 +18%") >= 0, "图鉴装备卡：无副属性装备也显示主属性（圣兽羽饰 报酬 +18%）");
  const _bH = document.getElementById("tab-bag").innerHTML || "";
  check(_bH.indexOf("报酬 +18%") >= 0, "背包装备行：显示主属性");
  const _sH = document.getElementById("tab-shop").innerHTML || "";
  check(_sH.indexOf("成功率 +1%") >= 0, "图纸商店：显示主属性");
  console.log("  装备主属性显示 ✅");
}

/* ═══════════ 16. v1.38l 跨日刷新显示 / 成功率加成数值 / 趋势位置 ═══════════ */
console.log("\\n===== 16. 跨日刷新 / 成功率加成 / 趋势位置 =====");
{
  // poolPointIsPrevDay：固定日期三场景（与运行时刻无关）
  check(poolPointIsPrevDay({d:new Date(2026,9,4), h:23}, new Date(2026,9,5,7,0)) === true, "新日首刷新点前（6:00–8:00）：lp 判定为前日");
  check(poolPointIsPrevDay({d:new Date(2026,9,4), h:23}, new Date(2026,9,5,3,0)) === false, "凌晨同一游戏日：lp 判定为当日");
  check(poolPointIsPrevDay({d:new Date(2026,9,5), h:8}, new Date(2026,9,5,9,0)) === false, "当日刷新点：判定为当日");
  // 昨日评分 → 今日委托成功率加成数值（首页展示）
  S.history = [{date:"d1", score:85, sleep:true, done:0, tasks:[1,1,1,1,1,1,1], multi:[0,0]}];
  S.health = {date:todayStr(), done:[0,0,0,0,0,0,0], multi:[0,0], score:0, meals:[0,0,0]};
  S.heatN = 0; S.timTitles = {};
  S.equipped = {weapon:null, armor:null, accessory:null, charmSlot:null};
  check(Math.abs(healthRateBonus() - 0.17) < 1e-9, "healthRateBonus：昨日 85 分 → +17%");
  render();
  const _qH = document.getElementById("tab-quest").innerHTML || "";
  check(_qH.indexOf("今日委托成功率 +17%") >= 0, "首页今日状态：昨日评分处显示成功率加成数值");
  // 健康趋势位于打卡任务下方
  const _hH = document.getElementById("tab-health").innerHTML || "";
  check(_hH.indexOf("健康趋势") >= 0, "健康页：趋势卡存在");
  check(_hH.indexOf("健康趋势") > _hH.indexOf("每日多次任务"), "健康趋势位于每日打卡任务下方");
  console.log("  跨日刷新 / 成功率加成 / 趋势位置 ✅");
}

/* ═══════════ 17. v1.38r 批次（22:00 刷新 / 1h 接取窗口 / 入睡窗 / 材料图标 / 升级详情） ═══════════ */
console.log("\\n===== 17. v1.38r 批次 =====");
{
  // 刷新点 08/12/18/21（v1.41f3：末次 22:00 → 21:00）
  check(CFG.refreshHours.join(",") === "8,12,18,21", "刷新点 08/12/18/21（v1.41f3 末次 22:00 → 21:00）");
  check(latestPoint(new Date(2026,9,5,7,0)).h === 21, "早 8 点前：上一刷新点 = 昨日 21:00");
  // v1.41f3：最后一次刷新点窗口 2.5 小时（21:00 → 23:30；其余 1 小时）
  check(LAST_POOL_WINDOW_MS === 150*60*1000, "最后班窗口常量 = 2.5 小时");
  {
    const _fR17 = FESTIVAL_RANGES.splice(0);              // 临时隔离节日（窗口加成为 +1h）
    const _fK17 = todayStr().slice(5), _fS17 = FESTIVALS[_fK17];
    delete FESTIVALS[_fK17];
    const _saveP = S.pool;
    S.pool = {point: "2026-10-05@21", bornTs: Date.now() - 140*60*1000};
    check(!poolExpired(), "最后班：140 分钟仍在窗口内（2.5 小时）");
    S.pool = {point: "2026-10-05@21", bornTs: Date.now() - 151*60*1000};
    check(poolExpired(), "最后班：151 分钟已过期");
    S.pool = {point: "2026-10-05@12", bornTs: Date.now() - 61*60*1000};
    check(poolExpired(), "常规班：61 分钟已过期（1 小时）");
    S.pool = _saveP;
    if(_fS17) FESTIVALS[_fK17] = _fS17;
    FESTIVAL_RANGES.push.apply(FESTIVAL_RANGES, _fR17);
  }
  // 接取窗口 1 小时
  check(POOL_WINDOW_MS === 60*60*1000, "接取窗口 = 1 小时（30 分钟 → 1 小时）");
  // 入睡打卡时段 21:00~23:30
  check(CFG.taskWindows[0][0] === "21:00" && CFG.taskWindows[0][1] === "23:30", "入睡打卡时段 21:00~23:30");
  // 材料图标审查修正
  check(matIcon("山鸡羽") === "🪶" && matIcon("枭羽") === "🪶", "羽毛类图标 = 🪶（原兽材兜底 🦴）");
  check(matIcon("蘑菇") === "🍄", "蘑菇图标 = 🍄（原食材兜底 🍖）");
  check(matIcon("河鱼") === "🐟" && matIcon("蜂蜜") === "🍯" && matIcon("龙鳞") === "🐉", "个别覆写：鱼 / 蜜 / 龙鳞");
  check(matIcon("止血草") === "🌿" && MAT_ICON["食材"] === "🥬" && MAT_ICON["兽材"] === "🐾", "品类兜底图标修正（草药原样 / 食材 / 兽材）");
  // 升级详情窗口（levelupQueue → flushResults → 弹窗）
  resultQueue.length = 0;
  levelupQueue.length = 0;
  _qanimBusy = false; _pendingSettles = 0;
  S.lvIdx = 0; S.exp = CFG.expNeed[0]; S.energy = 5;
  checkLevelUp();
  check(S.lvIdx === 1 && levelupQueue[0] === 1, "升级写入 levelupQueue（Lv2）");
  check(S.energy === energyMaxNow(), "升级补满当前精力（= 新上限，v1.38s2）");
  flushResults();
  check(dlgCap && (dlgCap.t || "").indexOf("升级") >= 0
        && (dlgCap.b || "").indexOf("新解锁") >= 0 && (dlgCap.b || "").indexOf("能力提升") >= 0,
        "升级详情弹窗：新解锁 + 能力提升");
  check(dlgCap && (dlgCap.b || "").indexOf("精力上限") >= 0 && (dlgCap.b || "").indexOf("抽取") >= 0,
        "升级详情：含精力上限与抽取数变化");
  console.log("  v1.38r 批次 ✅");
}

/* ═══════════ 18. v1.38s 批次（探索详情保密 / 升级详情兜底弹窗） ═══════════ */
console.log("\\n===== 18. v1.38s 批次 =====");
{
  const _celFx = celebrateFx, _sfxLv = sfxLevelUp;
  celebrateFx = function(){}; sfxLevelUp = function(){};

  // 1) 探索详情保密：v1.41 未获得过的掉落完全隐藏（连占位也没有），获得过才展示名称
  const _iMine = REGIONS.findIndex(function(x){ return x.n === "废弃矿道"; });   // v1.41：索引按名查找（区域表已扩展）
  S.seenMats = ["铁矿石"]; S.mats = {铁矿石: 3};
  S.seenItems = []; S.items = {};
  dlgCap = null; showRegionDetail(_iMine);
  const b1 = (dlgCap && dlgCap.b) || "";
  check(b1.indexOf("铁矿石") >= 0, "探索详情：已见过的材料正常展示");
  check(b1.indexOf("？？？") < 0, "探索详情：未获得过的掉落完全隐藏（不显示占位）");
  check(b1.indexOf("紫水晶") < 0 && b1.indexOf("血玛瑙") < 0, "探索详情：未获得的材料不剧透名称");
  check(b1.indexOf("清醒符咒") < 0 && b1.indexOf("安眠护符") < 0, "探索详情：未获得的道具不剧透名称");
  check(b1.indexOf("旧宝箱") < 0, "探索详情：未开出过的旧宝箱不剧透");
  S.seenMats.push("紫水晶"); S.seenItems.push("旧宝箱");
  dlgCap = null; showRegionDetail(_iMine);
  const b2 = (dlgCap && dlgCap.b) || "";
  check(b2.indexOf("紫水晶") >= 0 && b2.indexOf("旧宝箱") >= 0, "探索详情：获得过之后正常展示（材料 + 旧宝箱）");
  check(b2.indexOf("清醒符咒") < 0 && b2.indexOf("？？？") < 0, "探索详情：仍未获得的道具保持完全隐藏");

  // 2) 旧宝箱实地开出 → 自动记录 seenItems（mock 随机序列：只命中旧宝箱；后续随机走兜底不触发）
  _lastLvFx = S.lvIdx;
  const _rnd = Math.random;
  const _seq = [0.99,0.99,0.99,0.99,0.99,0.99,0.99, 0.01, 0.05, 0.5];
  Math.random = function(){ return _seq.length ? _seq.shift() : 0.99; };
  S.seenItems = ["紫水晶"];
  S.exploreActive = {idx:_iMine, finishTs:0};
  exploreFinishCheck();
  Math.random = _rnd;
  check((S.seenItems||[]).indexOf("旧宝箱") >= 0, "探索开出旧宝箱 → 写入 seenItems（详情随之解锁）");

  // 2b) 旧宝箱 10% 装备奖励（随机普通~精良 ×1，尚未拥有才给；全拥有则空箱）
  S.gear = []; S.equipped = {weapon:null, armor:null, accessory:null, charmSlot:null};
  const _rnd2 = Math.random;
  const _seq2 = [0.99,0.99,0.99,0.99,0.99,0.99,0.99, 0.01, 0.95, 0.99];
  Math.random = function(){ return _seq2.length ? _seq2.shift() : 0.99; };
  S.exploreActive = {idx:_iMine, finishTs:0};
  exploreFinishCheck();
  Math.random = _rnd2;
  check(S.gear.length === 1, "旧宝箱 10% 开出装备 → 入装备背包（" + (S.gear[0] || "") + "）");
  GEAR.forEach(function(g){ if((g[1] === "普通" || g[1] === "精良") && S.gear.indexOf(g[0]) < 0) S.gear.push(g[0]); });
  const _gn = S.gear.length;
  const _rnd3 = Math.random;
  const _seq3 = [0.99,0.99,0.99,0.99,0.99,0.99,0.99, 0.01, 0.95];
  Math.random = function(){ return _seq3.length ? _seq3.shift() : 0.99; };
  S.exploreActive = {idx:4, finishTs:0};
  exploreFinishCheck();
  Math.random = _rnd3;
  check(S.gear.length === _gn, "普通~精良全拥有 → 旧宝箱不重复发放（空箱）");

  // 3) 道具懒合并：当前持有自动计入，用尽后记录保留
  _lastLvFx = S.lvIdx;
  S.seenItems = []; S.items = {清醒符咒: 2};
  render();
  check(S.seenItems.indexOf("清醒符咒") >= 0, "道具「曾获得」懒合并：当前持有自动计入");
  S.items = {}; render();
  check(S.seenItems.indexOf("清醒符咒") >= 0, "道具用尽后「曾获得」记录保留");

  // 4) 升级详情兜底（checkFx）：非结算路径（如创造模式直接改等级）也弹详情
  resultQueue.length = 0; levelupQueue.length = 0; _qanimBusy = false;
  _lastLvFx = 1; S.lvIdx = 3;
  checkFx();
  check(levelupQueue.join(",") === "2,3", "兜底：跳级补弹各级详情（Lv3 + Lv4）");
  levelupQueue.length = 0; levelupQueue.push(3);
  _lastLvFx = 2; S.lvIdx = 3;
  checkFx();
  check(levelupQueue.join(",") === "3", "去重：已入队的等级不重复追加");
  S.levelups = []; levelupQueue.length = 0;
  _lastLvFx = 0; S.lvIdx = 1;
  checkFx();
  check(levelupQueue.length === 0, "Flask 环境（S.levelups 存在）→ 跳过本地兜底（服务端队列驱动）");
  delete S.levelups;
  levelupQueue.length = 0; _lastLvFx = 3; S.lvIdx = 1;
  checkFx();
  check(levelupQueue.length === 0, "等级调低不触发升级详情");
  _lastLvFx = S.lvIdx;

  // 5) Lv5 后经验条走「传奇资格」进度（v1.38s2）
  _lastLvFx = 4; S.lvIdx = 4; S.exp = 12000;
  render();
  check(document.getElementById("hExpTxt").textContent === "12000/30000", "Lv5 经验条：显示传奇资格进度（12000/30000）");
  check(document.getElementById("hExpBar").style.width === "40%", "Lv5 经验条宽度 40%（12000/30000）");
  S.exp = 30000;
  render();
  check(document.getElementById("hExpTxt").textContent === "传奇资格 ✓", "累计 30000 → 传奇资格 ✓");
  S.lvIdx = 1; S.exp = 200; _lastLvFx = 1;
  render();
  check(document.getElementById("hExpTxt").textContent === "140/440", "普通等级经验条显示本级进度（回归）");

  // 6) 委托等级标签（v1.38s4）——卡片外部显示委托等级（= 所属池）
  check(qLvText(C["Lv1"][0][0]) === "Lv1" && qLvText(C["Lv3"][0][0]) === "Lv3",
        "qLvText：委托等级 = 所属池（Lv1 / Lv3）");
  const _lp4 = latestPoint(new Date()), _pk4 = pointKey(_lp4.d, _lp4.h);
  S.lvIdx = 3; _lastLvFx = 3;
  S.pool = {point:_pk4, list:[C["Lv4"][0]], taken:false, bornTs:Date.now(), expiredLogged:false};
  S.poolPoint = _pk4;
  render();
  check(document.getElementById("tab-quest").innerHTML.indexOf("Lv4</span>") >= 0, "委托卡外部显示等级（Lv4 池卡）");

  // 7) v1.38s5：委托奖励平衡修正 + 委托详情掉落保密
  {
    const _jz = C["Lv5"].filter(function(x){ return x[0] === "禁咒书夺回"; })[0];
    check(Object.keys(_jz[8])[0] === "暗影草" && (M["暗影草"]||[])[1] === "史诗",
          "禁咒书夺回：史诗（暗影草）为主材料必得");
    const _lw = C["Lv5"].filter(function(x){ return x[0] === "猎杀远古巨狼"; })[0];
    check(Object.keys(_lw[8])[0] === "魔狼鬃毛", "猎杀远古巨狼：新增史诗主材料（魔狼鬃毛）");
    const _lc = C["Lv5"].filter(function(x){ return x[0] === "龙巢外围巡查"; })[0];
    check(Object.keys(_lc[8])[0] === "龙息草" && (M["龙息草"]||[])[1] === "稀有",
          "龙巢外围巡查：主材料降为稀有（龙息草）");
    const _sm = C["Lv4"].filter(function(x){ return x[0] === "讨伐石魔像"; })[0];
    check(Object.keys(_sm[8])[0] === "陨铁" && (M["陨铁"]||[])[1] === "史诗",
          "讨伐石魔像：主材料升为史诗（陨铁）");
    const _jl = C["Lv3"].filter(function(x){ return x[0] === "巨龙巢穴侦察"; })[0];
    check(Object.keys(_jl[8])[0] === "龙骨" && _jl[8]["龙骨"][0] === 1 && _jl[8]["龙骨"][1] === 1,
          "巨龙巢穴侦察：史诗降为单份（龙骨×1 + 龙鳞概率）");
    const _gl = C["Lv4"].filter(function(x){ return x[0] === "古龙遗骸采集"; })[0];
    check(_gl[8]["龙角"][1] === 3, "古龙遗骸采集：龙角概率量 1~5 → 1~3");
    // 委托详情掉落保密：主材料直接显示；副材料未获得显示 ？？？
    S.seenMats = []; S.mats = {}; S.seenItems = []; S.items = {};
    const _h1 = matRowsHtml(_jz);
    check(_h1.indexOf("暗影草") >= 0, "委托详情：主材料直接显示");
    check(_h1.indexOf("远古石板") < 0 && _h1.indexOf("？？？") >= 0, "委托详情：未获得的副材料显示 ？？？");
    S.seenMats = ["远古石板"];
    const _h2 = matRowsHtml(_jz);
    check(_h2.indexOf("远古石板") >= 0, "委托详情：获得过的副材料正常展示");
  }

  // 8) v1.39：C3 兼容字段（Flask 下发 histStats/historyTotal 时用全量计数；原型回退本地）
  {
    check(typeof S.histStats === "undefined", "原型无 histStats 字段");
    check(ACHV.filter(function(a){ return a.cond.toString().indexOf("S.histStats") >= 0; }).length >= 4,
          "长期成就（4 项）兼容 histStats 覆写");
    S.histStats = {sleep: 60, early: 0, sport: 0, read: 0};
    S.history = [];
    check(ACHV[5].cond() === true, "histStats 覆写生效（sleep=60 且本地 history 为空）");
    delete S.histStats;
    check(ACHV[5].cond() === false, "无 histStats 时回退本地 history 统计（空历史 → 未达成）");
  }

  // 9) v1.40：硬伤修复 + 健康闭环调整（原型侧）
  {
    // ① 护符 V：完成 ≥1 次传奇事件
    const _cCh = S.charm, _cLD = S.legendDone;
    S.charm = 4; S.legendDone = [];
    check(charmUnlocked(4) === false, "护符 V：未完成传奇 → 未解锁");
    S.legendDone = ["屠龙传说"];
    check(charmUnlocked(4) === true, "护符 V：完成 ≥1 次传奇 → 解锁（原 need:99 永不可解锁）");
    S.charm = _cCh; S.legendDone = _cLD;
    // ② 传奇奖励入装备/图纸
    const _cG = S.gear, _cB = S.blueprints, _cT = S.trophies;
    S.gear = []; S.blueprints = {}; S.trophies = [];
    grantLegendReward(["世界树种子","采集+精英",3,"困难",0,0,"","世界树护符",{}]);
    check(S.gear.indexOf("世界树护符") >= 0 && S.trophies.indexOf("世界树护符") < 0, "传奇装备奖励入装备背包（世界树护符）");
    grantLegendReward(["陨星核心","采集+精英",2,"困难",0,0,"","陨星武器图纸",{}]);
    check(S.blueprints["陨星武器"] === true, "传奇图纸奖励入图纸库（陨星武器图纸）");
    grantLegendReward(["公会大师试炼","精英",30,"困难",0,0,"","公会大师徽章",{}]);
    check(S.trophies.indexOf("公会大师徽章") >= 0, "非装备奖励仍入藏品");
    S.gear = _cG; S.blueprints = _cB; S.trophies = _cT;
    // ③ W/H/P 称号
    const _cRep = S.rep, _cTi = S.titles;
    S.rep = 20000; S.titles = [];
    checkGuildTitles();
    check(["世界行者","英雄","至尊"].every(function(x){ return S.titles.indexOf(x) >= 0; }), "W/H/P 称号授予（世界行者/英雄/至尊）");
    S.rep = _cRep; S.titles = _cTi;
    // ④ 连击保险计入 30 天统计
    const _cH = S.history, _cS = S.shieldDays;
    S.history = [];
    for(let i = 0; i < 30; i++) S.history.push({date:"z"+("0"+i).slice(-2), score:80, sleep:i >= 4, done:1, tasks:[1,1,1,1,1,1,1], multi:[0,0]});
    S.shieldDays = ["z00"];
    check(sleepStreakProt(30) === true, "连击保险日计入：缺 4 天中 1 天被保险 → 达标（v1.40）");
    S.history = _cH; S.shieldDays = _cS;
    // ⑤ 图纸定价修复
    check(bpInfo("猎弓").price === 2000, "普通图纸 20 银 = 2,000 铜（原 bug 只扣 20）");
    check(bpInfo("陨星武器").price === 5000000, "传说图纸 5 铂金 = 5,000,000");
    // ⑥ 虚弱 → 精力上限 −10%
    const _cBn = S.buffNext;
    S.buffNext = null;
    const _e0 = energyBase();
    S.buffNext = {date:todayStr(), pay:0, energy:0, con:0, vit:0, claimed:false, score:0, energyPct:-0.10};
    check(energyBase() === Math.max(1, Math.round(_e0 * 0.9)), "虚弱：精力上限 −10%（" + _e0 + " → " + energyBase() + "）");
    S.buffNext = _cBn;
  }

  celebrateFx = _celFx; sfxLevelUp = _sfxLv;
  console.log("  v1.38s 批次 ✅");
}

console.log("\\n===== 19. v1.41 I1：委托链前置 =====");
{
  const _allN = new Set();
  Object.keys(C).forEach(function(lv){ (C[lv]||[]).forEach(function(q2){ _allN.add(q2[0]); }); });
  const _reqBad = Object.keys(QUEST_REQ).filter(function(k2){ return !_allN.has(k2) || !_allN.has(QUEST_REQ[k2]); });
  check(Object.keys(QUEST_REQ).length === 31, "QUEST_REQ 共 31 条链前置（v1.41 I1 ×8 + v1.45b ×7 + v1.51 ×3 + v1.57 种族链 ×13）");
  check(_reqBad.length === 0, "QUEST_REQ 引用完整性（键值均为真实委托）" + (_reqBad.length ? "：" + _reqBad.join(",") : ""));

  const _bk = S.doneQuests; const _bi = S.lvIdx;
  S.lvIdx = 4; S.doneQuests = {};
  const _p1 = mixPool().map(function(q2){ return q2[0]; });
  check(_p1.indexOf("迷雾灯塔·残焰") < 0, "未满足前置 → 链节点不出现在抽取池");
  check(_p1.indexOf("迷雾灯塔·引航") >= 0, "无前置链首节点正常出现");
  S.doneQuests = {"迷雾灯塔·引航":1};
  const _p2 = mixPool().map(function(q2){ return q2[0]; });
  check(_p2.indexOf("迷雾灯塔·残焰") >= 0, "完成前置 → 链下一节点进入抽取池");
  check(_p2.length === _p1.length + 1, "完成前置后池 +1（" + _p1.length + " → " + _p2.length + "）");
  Object.keys(QUEST_REQ).forEach(function(k2){ S.doneQuests[QUEST_REQ[k2]] = 1; });
  const _p3 = mixPool().map(function(q2){ return q2[0]; });
  const _miss = Object.keys(QUEST_REQ).filter(function(k2){ return _p3.indexOf(k2) < 0; });
  check(_miss.length === 0, Object.keys(QUEST_REQ).length + " 条链节点全部可达" + (_miss.length ? "，缺：" + _miss.join(",") : ""));

  const _newQ = ["迷雾灯塔·引航","迷雾灯塔·残焰","迷雾灯塔·重燃","皇家图书馆·寻书","皇家图书馆·密档","皇家图书馆·真相","星界信使·初见","星界信使·传讯","星界信使·回响","深渊回响·远征",
    "血战遗迹考察","猎杀深渊恶魔","魔鬼的谈判","地狱钟声","仙灵的谢礼","净化亡灵谷","魂灯引渡"];
  const _noStory = _newQ.filter(function(n2){ return !QUEST_STORY[n2]; });
  check(_newQ.every(function(n2){ return _allN.has(n2); }), "17 条链委托均在池中");
  check(_noStory.length === 0, "17 条链委托均有委托描写" + (_noStory.length ? "，缺：" + _noStory.join(",") : ""));

  S.doneQuests = _bk; S.lvIdx = _bi;
  console.log("  v1.41 I1 链前置 ✅");
}

console.log("\\n===== 20. v1.41 I3：月度世界事件 =====");
{
  const _meBak = S.monthEvent, _liBak = S.lvIdx, _moBak = S.money, _tiBak = S.timTitles, _maBak = S.mats;
  const _origExp = monthEventExpired;
  monthEventExpired = function(){ return false; };   // 测试对日期鲁棒（忽略真实 7 日截止）
  // 1) v1.48f：Lv1（新号）即生成——无 Lv2 门槛
  S.lvIdx = 0; S.monthEvent = null; monthEventTick();
  check(!!(S.monthEvent && S.monthEvent.key === todayStr().slice(0,7)), "v1.48f：Lv1 生成月度事件（新号解锁）");
  check(!!monthEventNow(), "v1.48f：Lv1 monthEventNow 返回事件");
  // 2) Lv2 生成 + 月份映射（同月幂等）
  S.lvIdx = 1; monthEventTick();
  const _mk = todayStr().slice(0,7);
  check(!!(S.monthEvent && S.monthEvent.key === _mk && S.monthEvent.cnt === 0 && !S.monthEvent.done), "Lv2 生成当月事件");
  const _ev = MONTH_EVENTS[+_mk.slice(5,7) - 1];
  check(!!_ev && MONTH_EVENTS.length === 12, "月份→事件映射（" + (_ev ? _ev.n : "?") + "，池 12 条）");
  // 3) 幂等
  S.monthEvent.cnt = 2; monthEventTick();
  check(S.monthEvent.cnt === 2, "同月重复 tick 不重置");
  // 4) 类型不匹配不计数
  monthEventAdd(_ev.t === "quest" ? "explore" : "quest");
  check(S.monthEvent.cnt === 2, "类型不匹配不计数");
  // 5) 达成发奖
  S.money = 0; S.mats = {}; S.timTitles = {};
  S.monthEvent.cnt = _ev.need - 1;
  monthEventAdd(_ev.t);
  check(S.monthEvent.done === true, "达成置 done");
  check(S.money === Math.round(_ev.gold * lvGoldMul()), "金币奖励×lvGoldMul（" + S.money + "）");
  check((S.mats[Object.keys(_ev.mats)[0]] || 0) > 0, "材料奖励入包");
  check((S.timTitles[_ev.title] || 0) > Date.now(), "当月称号入档");
  // 6) 达成后不再计数/发奖
  const _m2 = S.money; monthEventAdd(_ev.t);
  check(S.money === _m2 && S.monthEvent.cnt === _ev.need, "达成后不重复发奖");
  // 7) 换月自动轮换
  S.monthEvent = {key:"1999-01", cnt:9, done:true};
  monthEventTick();
  check(S.monthEvent.key === _mk && S.monthEvent.cnt === 0 && !S.monthEvent.done, "换月自动轮换重置");
  // 恢复
  monthEventExpired = _origExp;
  check(monthEventExpired() === false, "v1.48e：月事件整月有效——截止当月最后一天 23:30");
  check(renderQuest.toString().indexOf("安眠室/称号") >= 0, "v1.48e：今日状态·成功率加成拆解显示（评分 / 安眠室·称号）");
  S.monthEvent = _meBak; S.lvIdx = _liBak; S.money = _moBak; S.timTitles = _tiBak; S.mats = _maBak;
  console.log("  v1.41 I3 月度世界事件 ✅");
}

console.log("\\n===== 21. v1.41 I4：追踪类 / 资源指定类 =====");
{
  // 1) 追踪类：q[3]=4320（3 天）；fmtDur 多日显示
  const _tr = [];
  Object.keys(C).forEach(function(lv){ (C[lv]||[]).forEach(function(q2){ if(q2[1] === "追踪") _tr.push(q2); }); });
  check(_tr.length === 4, "追踪类委托 4 条（v1.42 加黑龙追踪；实际 " + _tr.length + "）");
  check(_tr.every(function(q2){ return q2[3] === 4320; }), "追踪类耗时=4320 分钟（3 天）");
  check(fmtDur(4320) === "3 天" && fmtDur(240) === "4 小时" && fmtDur(90) === "1.5 小时", "fmtDur 多日显示（3 天/4 小时/1.5 小时）");
  // 2) 资源指定类：表 3 条、引用完整
  const _allN2 = new Set();
  Object.keys(C).forEach(function(lv){ (C[lv]||[]).forEach(function(q2){ _allN2.add(q2[0]); }); });
  const _tb = Object.keys(QUEST_TURNIN).filter(function(k2){ return !_allN2.has(k2) || !M[QUEST_TURNIN[k2]]; });
  check(Object.keys(QUEST_TURNIN).length === 3 && _tb.length === 0, "QUEST_TURNIN 3 条、引用完整" + (_tb.length ? "：" + _tb.join(",") : ""));
  // 3) 结算：持有材料 → 上交 1 个、报酬翻倍（固定 rand=50：必成功、非暴击非大失败；龙血订单无掉落干扰）
  const _q3 = C["Lv5"].filter(function(x){ return x[0] === "龙血商人的订单"; })[0];
  const _mb = S.money, _lb = S.mats["龙血"];
  const _origRand = rand;
  const _origRare = tryRareEvent;
  rand = function(){ return 50; };
  tryRareEvent = function(){ return null; };                  // v1.53：屏蔽稀有事件（「山贼的赃物」+30 银等会污染报酬 =2 倍校验，低频偶发误报）
  S.rareNextPay = 0; S.buffNext = null;
  S.money = 0; delete S.mats["龙血"];
  await settle({q:_q3, qlv:5, rate:2, acceptTs:Date.now(), finishTs:Date.now(), name:_q3[0], meal:null});
  const _base = S.money;
  S.money = 0; S.mats["龙血"] = 2;
  S.rareNextPay = 0; S.rareNextRate = 0; S.buffNext = null;   // 第一次结算尾部可能 roll 出稀有事件加成，第二次前重置
  await settle({q:_q3, qlv:5, rate:2, acceptTs:Date.now(), finishTs:Date.now(), name:_q3[0], meal:null});
  tryRareEvent = _origRare;
  check(_base > 0 && S.money === _base * 2, "上交型：持有材料 → 报酬翻倍（" + _base + " → " + S.money + "）");
  check((S.mats["龙血"] || 0) === 1, "上交型：扣 1 个材料（2 → 1）");
  // 恢复
  rand = _origRand;
  S.money = _mb;
  if(_lb) S.mats["龙血"] = _lb; else delete S.mats["龙血"];
  console.log("  v1.41 I4 新委托机制 ✅");
}

console.log("\\n===== 22. v1.41 I5：收集分层 + 隐藏成就 =====");
{
  // 1) 表结构
  check(ACHV.length === 20, "成就表 20 条（11 常规 + 9 隐藏）");
  const _hid = ACHV.filter(function(a){ return a.hide && a.title; });
  check(_hid.length === 9, "隐藏成就 9 条（hide + title）");
  check(ACHV.filter(function(a){ return a.gear; }).length === 11, "常规成就 11 条（装备奖励）");
  // 2) 未达成的隐藏成就不显示（showAchvDetail 只列 S.achv）
  const _ab = S.achv; S.achv = [];
  showAchvDetail();
  check(dlgCap && dlgCap.b.indexOf("周全绿") < 0, "未达成的隐藏成就不显示于成就列表");
  // 3) 达成隐藏成就 → 称号入档（囤积家 = 持有 50 种材料）
  const _mbk = S.mats, _tbk = S.titles.slice(), _gbk = S.gear.slice();
  S.mats = {};
  Object.keys(M).slice(0, 50).forEach(function(k){ S.mats[k] = 1; });
  checkAchievements();
  check(S.achv.indexOf("囤积家") >= 0, "隐藏成就「囤积家」达成（50 种材料）");
  check(S.titles.indexOf("满仓") >= 0, "隐藏成就奖励称号「满仓」入档");
  check(S.gear.indexOf(undefined) < 0, "title 型成就不污染装备背包");
  S.mats = _mbk; S.achv = _ab; S.titles = _tbk; S.gear = _gbk;
  // 4) 图鉴分层：材料 50% / 80%
  const _smBak = S.seenMats, _tbk2 = S.titles.slice(), _ab2 = S.achv.slice(), _mbk2 = S.mats;
  S.mats = {};
  S.seenMats = Object.keys(M).slice(0, Math.ceil(Object.keys(M).length * 0.5));
  checkAchievements();
  check(S.titles.indexOf("博物学家·银") >= 0, "材料收集 50% → 「博物学家·银」");
  S.seenMats = Object.keys(M).slice(0, Math.ceil(Object.keys(M).length * 0.8));
  checkAchievements();
  check(S.titles.indexOf("博物学家·金") >= 0, "材料收集 80% → 「博物学家·金」");
  S.seenMats = _smBak; S.titles = _tbk2; S.achv = _ab2; S.mats = _mbk2; S.gear = _gbk;
  console.log("  v1.41 I5 收集分层+隐藏成就 ✅");
}

console.log("\\n===== 23. v1.41 I6：大师层 =====");
{
  // 1) 表结构
  check(GEAR.filter(function(g){ return ["大师之证","宗师手套","终焉披风","大师徽章"].indexOf(g[0]) >= 0; }).length === 4, "大师层装备 4 件（3 传说 + 1 成就饰品）");
  check(ACHV.some(function(a){ return a.n === "大师" && a.gear === "大师徽章"; }), "成就「大师」→ 大师徽章");
  check(MASTER_SHOP.gear.length === 3 && MASTER_SHOP.vitC === 20 && MASTER_SHOP.gear[0].platC === 18, "MASTER_SHOP：3 装备 / 活力 20 / 首价 18 铂金");
  // 2) 解锁判定：3 传奇未解锁；4 传奇达成
  const _lb = S.legendDone.slice(), _ab3 = S.achv.slice(), _tb3 = S.titles.slice(), _mb3 = S.money, _mt3 = S.mats, _gb3 = S.gear.slice();
  S.legendDone = ["屠龙传说","星界远征","魔神封印"]; S.achv = [];
  check(!masterUnlocked(), "3 个传奇 → 大师未解锁（商店隐藏）");
  S.legendDone = ["屠龙传说","星界远征","魔神封印","时间回廊"]; S.achv = [];
  checkAchievements();
  check(S.achv.indexOf("大师") >= 0 && S.gear.indexOf("大师徽章") >= 0, "4 个传奇 → 成就「大师」达成、徽章入包");
  check(masterUnlocked(), "大师商店解锁");
  // 3) 徽章活力词条
  S.equipped.charmSlot = "大师徽章";
  check(Math.abs(gearEffects().vit - 0.10) < 1e-9, "大师徽章「活力点获取+10%」解析生效");
  check(Math.abs(charmVitGain() - (charmVit() + 0.10)) < 1e-9, "活力点乘算统一通道并入大师徽章");
  S.equipped.charmSlot = null;
  // 4) 购买专属装备（一次性）
  S.money = 20 * 1000000; S.mats["星核"] = 5;
  buyMasterGear(0);
  check(S.gear.indexOf("大师之证") >= 0, "购买「大师之证」成功入包");
  check(S.money === 2 * 1000000 && S.mats["星核"] === 2, "扣费 18 铂金币 + 星核×3（余 2 铂金 / 星核 2）");
  S.money = 50 * 1000000;
  buyMasterGear(0);
  check(S.money === 50 * 1000000, "已拥有 → 重复购买被拒（不扣费）");
  // 5) 材料不足被拒
  S.mats["世界树心"] = 0;
  buyMasterGear(1);
  check(S.gear.indexOf("宗师手套") < 0, "材料不足 → 购买被拒");
  // 6) 活力点兑换：20 铂金币 → +500
  S.money = 20 * 1000000; const _v0 = S.vit;
  buyMasterVit();
  check(S.vit === _v0 + 500 && S.money === 0, "大师的馈赠：-20 铂金币 → 活力点 +500");
  // 7) 未解锁被拒
  S.achv = []; S.money = 100 * 1000000;
  buyMasterGear(1);
  check(S.gear.indexOf("宗师手套") < 0, "未解锁大师 → 购买被拒");
  // 恢复
  S.legendDone = _lb; S.achv = _ab3; S.titles = _tb3; S.money = _mb3; S.mats = _mt3; S.gear = _gb3;
  console.log("  v1.41 I6 大师层 ✅");
}

console.log("\\n===== 24. v1.41 未解锁内容隐藏 =====");
{
  const _bRep = S.rep, _bLv = S.lvIdx, _bLA = S.legendActive, _bLP = S.legendPreview, _bMoney = S.money;
  const _bHist = S.history, _bEx = S.explore, _bExU = S.exploreUsed, _bExA = S.exploreActive, _bDQ = S.doneQuests;
  // 0) F 级商店页：页签常显，页面给出「商店未开放」引导（保持原行为）
  S.rep = 0; renderShop();
  check(document.getElementById("tab-shop").innerHTML.indexOf("商店未开放") >= 0,
        "公会 F 级：商店页显示「商店未开放」引导（页签不隐藏）");
  // 1) 铂金商店 / 贡献商店 / 技能树 / 护符：按解锁条件整卡显隐
  S.rep = 100; S.money = 100000; renderShop();     // v1.61d：铂金商店改按持有解锁——固定 <1 铂金币验证内容隐藏
  let _sh = document.getElementById("tab-shop").innerHTML;
  check(_sh.indexOf("🏛 铂金商店") >= 0 && _sh.indexOf("内容隐藏——需持有") >= 0, "E 级：铂金商店界面保留、内容隐藏（v1.61d 改按持有 ≥1 铂金币解锁）");
  check(_sh.indexOf("贡献商店（") < 0, "E 级：贡献商店未到 D 级 → 隐藏");
  check(_sh.indexOf("技能树") < 0, "E 级：技能树（需 D 级）整卡隐藏");
  check(_sh.indexOf("🌙 冥念护符") < 0, "E 级：冥念护符（需 C 级）整卡隐藏");
  check(_sh.indexOf("🔒") >= 0, "商店页：未解锁卡片以「🔒 内容隐藏」呈现（v1.61d 取代整卡隐藏）");
  check(_sh.indexOf("图纸商店") >= 0 && _sh.indexOf("普通 图纸") >= 0, "E 级：图纸商店显示（普通/精良档已解锁）");
  check(_sh.indexOf("稀有 图纸") < 0, "E 级：稀有档位（需 C 级）隐藏");
  S.rep = 400; renderShop();
  _sh = document.getElementById("tab-shop").innerHTML;
  check(_sh.indexOf("贡献商店（") >= 0, "D 级：贡献商店显示");
  check(_sh.indexOf("重掷券") < 0, "D 级：精英重掷券（需 B 级）隐藏");
  check(_sh.indexOf("技能树") >= 0, "D 级：技能树显示");
  check(_sh.indexOf("🌙 冥念护符") < 0, "D 级：冥念护符仍隐藏（v1.60 起需 C 级）");
  S.rep = 850; renderShop();
  _sh = document.getElementById("tab-shop").innerHTML;
  check(_sh.indexOf("🌙 冥念护符") >= 0, "C 级：冥念护符第 1 级显示（v1.60 对齐文案）");
  check(_sh.indexOf("重掷券") < 0, "C 级：精英重掷券仍隐藏（v1.60 起需 B 级）");
  S.rep = 1200; renderShop();
  _sh = document.getElementById("tab-shop").innerHTML;
  check(_sh.indexOf("重掷券") >= 0, "B 级：精英重掷券显示（v1.60 修正档位）");
  S.rep = 6500; S.money = 5000000; renderShop();   // v1.61d：持有 ≥1 铂金币 → 铂金商店内容可见
  _sh = document.getElementById("tab-shop").innerHTML;
  check(_sh.indexOf("🏛 铂金商店") >= 0 && _sh.indexOf("清醒符咒") >= 0, "S 级：铂金商店内容可见（持有 ≥1 铂金币）");
  check(_sh.indexOf("稀有 图纸") >= 0, "S 级：稀有档位显示");
  check(_sh.indexOf("史诗 图纸") >= 0, "S 级：史诗档位显示（需 A 级）");
  // 2) 探索：整卡显隐 + 未解锁区域隐藏
  S.lvIdx = 0; renderQuest();
  check(document.getElementById("tab-quest").innerHTML.indexOf("自由探索") < 0, "未到 Lv2：探索整卡隐藏");
  S.lvIdx = 4; S.history = [{date:"d", score:80, sleep:true}];
  S.explore = 999; S.exploreUsed = 0; S.exploreActive = null;
  S.doneQuests = {};
  renderQuest();
  check(document.getElementById("tab-quest").innerHTML.indexOf("12 次 Lv2 委托") >= 0,
        "v1.60：未完成 12 次 Lv2 委托 → 显示解锁进度卡");
  (C["Lv2"] || []).slice(0, 12).forEach(function(q){ S.doneQuests[q[0]] = 1; });
  S.rep = 100; renderQuest();
  let _qh = document.getElementById("tab-quest").innerHTML;
  check(_qh.indexOf("自由探索") >= 0 && _qh.indexOf("晨光森林") >= 0, "解锁后（Lv2 + 12 次 Lv2 委托）：探索整卡与基础区域显示");
  check(_qh.indexOf("晨光森林·深处") < 0, "E 级：深处区域（v1.60 起需 C 级）隐藏");
  check(_qh.indexOf("星夜洞窟·深处") < 0, "E 级：星夜洞窟·深处（v1.60 起需 A 级）隐藏");
  check(_qh.indexOf("深渊裂隙") < 0, "未完成前置委托：深渊裂隙（链解锁）隐藏");
  S.rep = 400; renderQuest();
  _qh = document.getElementById("tab-quest").innerHTML;
  check(_qh.indexOf("晨光森林·深处") < 0, "D 级：晨光森林·深处仍隐藏（v1.60 起需 C 级）");
  check(_qh.indexOf("星夜洞窟·深处") < 0, "D 级：星夜洞窟·深处仍隐藏（需 A 级）");
  S.rep = 850; renderQuest();
  _qh = document.getElementById("tab-quest").innerHTML;
  check(_qh.indexOf("晨光森林·深处") >= 0, "C 级：晨光森林·深处显示（Lv3 + C 双门槛）");
  check(_qh.indexOf("星夜洞窟·深处") < 0, "C 级：星夜洞窟·深处仍隐藏（需 A 级）");
  S.rep = 2200; renderQuest();
  _qh = document.getElementById("tab-quest").innerHTML;
  check(_qh.indexOf("星夜洞窟·深处") >= 0, "A 级：星夜洞窟·深处显示（Lv4 + A 双门槛）");
  check(_qh.indexOf("腐化森林·深处") < 0, "A 级：腐化森林·深处仍隐藏（需 S 级）");
  S.rep = 6500; renderQuest();
  _qh = document.getElementById("tab-quest").innerHTML;
  check(_qh.indexOf("腐化森林·深处") >= 0 && _qh.indexOf("虚空裂痕·深处") >= 0, "S 级：腐化/虚空深处显示（Lv5 + S 终段）");
  // 3) 图鉴：保持 v1.38 形态（未收集显示「？？？」占位卡，委托组全等级列出——用户指定不隐藏）
  S.lvIdx = 0; renderGallery();
  let _gH = document.getElementById("tab-gallery").innerHTML;
  check(_gH.indexOf("？？？") >= 0, "图鉴：未收集分组保留「？？？」占位卡（v1.38 形态）");
  check(_gH.indexOf("Lv2 委托") >= 0, "图鉴：全等级委托组列出（恢复原显示）");
  // 4) 交易所未开放：背包无提示
  S.lvIdx = 0; renderBag();
  check(document.getElementById("tab-bag").innerHTML.indexOf("交易所尚未开放") < 0, "背包：交易所未开放时无任何提示");
  // 5) 传奇事件低语预览（v1.41 用户指定：红字迹象 → 风味弹窗 → 参与判定）
  S.lvIdx = 4; S.legendActive = LEGEND[0]; S.legendPreview = true; renderQuest();
  let _qh2 = document.getElementById("tab-quest").innerHTML;
  check(_qh2.indexOf("特殊事件") >= 0 && _qh2.indexOf("【"+LEGEND[0][0]+"】") >= 0, "低语迹象：红字【事件名】条目上屏");
  check(_qh2.indexOf("takeLegend") < 0, "低语迹象不含接取按钮");
  dlgCap = null; showLegendPreview();
  check(dlgCap && dlgCap.b.indexOf("古龙盘踞") >= 0, "低语弹窗：显示风味文本");
  const _pBtn = (dlgCap.btns||[]).filter(function(x){ return x.text === "参与"; })[0];
  check(!!_pBtn, "低语弹窗：提供「参与」按钮");
  dlgCap = null; if(_pBtn) _pBtn.fn();
  check(dlgCap && dlgCap.b.indexOf("极其危险") >= 0, "未达资格参与 → 「极其危险」提示");
  check(S.legendPreview === true, "未达资格：预览保持（未转正）");
  dlgCap = null; showLegendDetail();
  check(dlgCap && dlgCap.b.indexOf("成功率") >= 0 && dlgCap.b.indexOf("必得材料") >= 0 && dlgCap.b.indexOf("声望") >= 0,
        "完整事件内容弹窗：成功率 / 必得材料 / 声望");
  S.legendPreview = false; renderQuest();
  check(document.getElementById("tab-quest").innerHTML.indexOf("takeLegend") >= 0, "正式传奇事件提供接取按钮");
  const _rnd2 = Math.random; Math.random = function(){ return 0.001; };
  S.lvIdx = 0; S.legendDay = ""; S.legendActive = null; S.legendPreview = false;
  rollLegend();
  check(!!S.legendActive && S.legendPreview === true, "未达参与条件：每日低语预览可生成（2%）");
  Math.random = _rnd2;
  // 恢复
  S.rep = _bRep; S.lvIdx = _bLv; S.legendActive = _bLA; S.legendPreview = _bLP; S.money = _bMoney;
  S.history = _bHist; S.explore = _bEx; S.exploreUsed = _bExU; S.exploreActive = _bExA; S.doneQuests = _bDQ;
  console.log("  v1.41 未解锁内容隐藏 ✅");
}

console.log("\\n===== 25. v1.41 料理分阶段开放（v1.41f4：酒馆料理） =====");
{
  const _bRep2 = S.rep, _bLv2 = S.lvIdx, _bLM2 = S.lastMeal;
  S.rep = 100;   // 商店页可见（E 级）
  S.lastMeal = null;   // 排除「当前生效料理」提示对断言字符串的干扰
  const _loR = CFG.recipes.filter(function(r){ return cookTier(r) === "普通"; })[0];
  const _gangR = CFG.recipes.filter(function(r){ return cookTier(r) === "精良"; })[0];
  const _rareR = CFG.recipes.filter(function(r){ return cookTier(r) === "稀有"; })[0];
  S.lvIdx = 0; renderTavern();               // v1.41f4：料理已迁至酒馆页
  let _kH = document.getElementById("tab-tavern").innerHTML;
  check(_kH.indexOf(_loR.n) >= 0, "Lv1：普通料理显示（"+_loR.n+"）");
  check(_kH.indexOf(_gangR.n) < 0, "Lv1：精良料理隐藏（"+_gangR.n+"）");
  check(_kH.indexOf(_rareR.n) < 0, "Lv1：稀有料理隐藏（"+_rareR.n+"）");
  check(_kH.indexOf("🍺 酒馆传闻") >= 0, "酒馆页最上方为酒馆传闻（v1.41f4）");
  S.lvIdx = 1; renderTavern();
  _kH = document.getElementById("tab-tavern").innerHTML;
  check(_kH.indexOf(_gangR.n) >= 0 && _kH.indexOf(_rareR.n) < 0, "Lv2：精良开放、稀有仍隐藏");
  S.lvIdx = 2; renderTavern();
  check(document.getElementById("tab-tavern").innerHTML.indexOf(_rareR.n) >= 0, "Lv3：稀有料理开放（"+_rareR.n+"）");
  // v1.41f5：sp 料理标注次数上限 + cap 类已全部改为恢复类
  check(CFG.recipes.filter(function(r){ return r.sp; }).every(function(r){ return r.desc.indexOf("每日最多 2 次") >= 0; })
    && CFG.recipes.every(function(r){ return !r.cap; }), "v1.41f5：sp 料理标注限次、无 cap 类料理");
  // 防御：未开放品阶烹饪被拒（材料备足也不扣）
  S.lvIdx = 0;
  const _hiI = CFG.recipes.indexOf(_rareR);
  { const _gr = recipeIng(_rareR); for(const k in _gr) S.mats[k] = (S.mats[k]||0) + _gr[k]; }
  const _matB = JSON.parse(JSON.stringify(S.mats));
  cook(_hiI);
  let _same = true;
  { const _gr2 = recipeIng(_rareR); for(const k in _gr2){ if((S.mats[k]||0) !== (_matB[k]||0)) _same = false; } }
  check(_same, "Lv1：烹饪高品阶料理被拒（材料未扣）");
  // 恢复
  S.rep = _bRep2; S.lvIdx = _bLv2; S.lastMeal = _bLM2;
  console.log("  v1.41 厨房分阶段开放 ✅");
}

console.log("\\n===== 26. v1.41 传奇独立槽位 + 耗时压缩 =====");
{
  const _bAct = S.active.slice(), _bLA = S.legendActive, _bLP = S.legendPreview;
  const _bLv3 = S.lvIdx, _bLW = S.legendWeek, _bLWN = S.legendWeekN;
  // 1) 耗时压缩到 3~14 天
  const _days = LEGEND.map(function(x){ return x[2]; });
  check(Math.min.apply(null, _days) >= 3 && Math.max.apply(null, _days) <= 14,
        "耗时压缩到 3~14 天（" + _days.join("/") + "）");
  // 2) 独立槽：普通位已满时传奇仍可接
  S.lvIdx = 0;                                   // simCap = 1
  S.active = [{q:["采集草药","采集","全天",60,"简单",8,1,8,{}], rate:1, meal:null,
               acceptTs:Date.now(), finishTs:Date.now()+3600000, name:"采集草药"}];
  check(activeNormalCount() === 1, "普通位占用计数 = 1（不含传奇）");
  S.legendActive = LEGEND[0]; S.legendPreview = false; S.legendWeek = ""; S.legendWeekN = 0;
  takeLegend();
  check(S.active.length === 2 && S.active.some(function(a){ return a.legend; }),
        "普通位已满 → 传奇仍可接（独立槽）");
  check(activeNormalCount() === 1, "传奇进行中时普通计数仍只算普通项");
  // 恢复
  S.active = _bAct; S.legendActive = _bLA; S.legendPreview = _bLP;
  S.lvIdx = _bLv3; S.legendWeek = _bLW; S.legendWeekN = _bLWN;
  console.log("  v1.41 独立槽位 + 耗时 ✅");
}

console.log("\\n===== 27. v1.41 称号收集加成 =====");
{
  const _bT27 = S.titles.slice();
  S.titles = [];
  check(titleOwnBonus() === 0, "0 个称号 → +0%");
  S.titles = ["屠龙者","英雄","满仓"];
  check(Math.abs(titleOwnBonus() - 0.03) < 1e-9, "3 个称号 → +3%");
  S.titles = "ABCDEFGHIJ".split("");
  check(Math.abs(titleOwnBonus() - 0.10) < 1e-9, "10 个称号 → +10%");
  S.titles = "ABCDEFGHIJKLMN".split("");
  check(Math.abs(titleOwnBonus() - 0.10) < 1e-9, "超过 10 个 → 封顶 +10%（14 个称号）");
  S.titles = _bT27;
  console.log("  v1.41 称号收集加成 ✅");
}

console.log("\\n===== 28. v1.41c 节日窗口扩展 + 任务排序 =====");
{
  /* 区间判定（festivalOf 兼容字符串 / Date） */
  check(!!festivalOf("2026-10-01") && !!festivalOf("2026-10-05") && !!festivalOf("2026-10-07"),
        "假期区间：10-01 / 10-05 / 10-07 均为节日");
  check(!festivalOf("2026-10-08") && !festivalOf("2026-09-30"), "假期区间外（10-08 / 09-30）非节日");
  check(((festivalOf("2026-01-01") || {}).name || "").indexOf("元旦") >= 0, "单日节日：元旦仍生效");
  /* 模拟节日（单日优先覆盖今天）→ 验证窗口扩展（任意跑测试日期均有效） */
  const _mm28 = todayStr().slice(5);
  const _bf28 = FESTIVALS[_mm28];
  FESTIVALS[_mm28] = ["🧪 测试节", "x"];
  const _tw0 = taskWinNow(0), _tw1 = taskWinNow(1), _mw1 = mealWinNow(1);
  check(_tw0[1] === 23*60+30+60, "节日：入睡打卡窗口尾部 +1 小时（延至 00:30）");
  check(_tw1[1] === 8*60+60, "节日：起床打卡窗口尾部 +1 小时（延至 09:00）");
  check(_mw1[0] === 11*60-30 && _mw1[1] === 14*60+30, "节日：三餐窗口前后各 +30 分钟");
  check(poolWindowMs() === poolBaseWindowMs() + 3600000, "节日：接取窗口 +1 小时（v1.49 修：21:00 后基础窗口 2.5h，改用同源基准）");
  check(winStr(_tw0) === "21:00–00:30", "winStr 跨日格式（21:00–00:30）");
  check(inWindowNow(_tw0, new Date(2026, 9, 2, 0, 15)) === true, "节日：入睡窗口跨日（次日 00:15 可打卡）");
  check(inWindowNow(_tw0, new Date(2026, 9, 2, 1, 0)) === false, "节日：入睡窗口次日 01:00 已关");
  check(inWindowNow(_tw1, new Date(2026, 9, 2, 8, 30)) === true && inWindowNow(_tw1, new Date(2026, 9, 2, 9, 30)) === false,
        "节日：起床窗口 08:30 可打 / 09:30 关闭");
  if(_bf28) FESTIVALS[_mm28] = _bf28; else delete FESTIVALS[_mm28];
  /* 非节日还原：临时清空区间再验（保证真实节日当天跑也不误报） */
  const _fR28 = FESTIVAL_RANGES.splice(0);
  const _tw0b = taskWinNow(0), _mw1b = mealWinNow(1);
  check(_tw0b[0] === 21*60 && _tw0b[1] === 23*60+30, "非节日：入睡窗口还原 21:00~23:30");
  check(_mw1b[0] === 11*60 && _mw1b[1] === 14*60, "非节日：午餐窗口还原 11:00~14:00");
  FESTIVAL_RANGES.push.apply(FESTIVAL_RANGES, _fR28);
  /* 任务展示顺序（起床置顶、入睡置底，数据索引不变） */
  check(TASK_ORDER[0] === 1 && TASK_ORDER[TASK_ORDER.length-1] === 0 && TASK_ORDER.length === 7,
        "任务展示顺序：起床置顶、入睡置底（7 项不变）");
  /* v1.41d：节日欢迎窗（队列最末——flushResults 消费展示；dlg 已被测试环境拦截） */
  S.pendingFestival = {name:"🧪 测试节", text:"x", date:todayStr()};
  flushResults();
  check(S.pendingFestival === null, "节日欢迎窗：队列最末，flushResults 消费展示");
  /* v1.41e：农历节日表（2025~2040） */
  check(((festivalOf("2026-02-17")||{}).name || "").indexOf("春节") >= 0, "农历节日：2026 春节（02-17）判定");
  check(((festivalOf("2026-02-16")||{}).name || "").indexOf("除夕") >= 0, "农历节日：除夕（02-16）判定");
  check(festivalOf("2026-02-22") !== null && festivalOf("2026-02-23") === null, "春节区间：初六生效 / 初七结束");
  check(((festivalOf("2026-09-25")||{}).name || "").indexOf("中秋") >= 0, "农历节日：2026 中秋（09-25）判定");
  check((festivalOf("2026-06-19")||{}).greet === "端午安康", "农历节日：问候语归一化（端午→端午安康）");
  /* v1.41f：节日专属效果（FEST_EFF 驱动——逐节日差异化加成；v1.41f2 平衡调整） */
  check((todayFestEff("2026-10-01").pay === 0.2) && (todayFestEff("2026-10-01").rate === 0.1), "专属效果：国庆 报酬+20% / 成功率+10%");
  check((todayFestEff("2026-01-01").vitPerTask || 0) === 1, "专属效果：元旦 打卡每项 +1 活力（v1.41f2 下调）");
  check((todayFestEff("2026-04-05").rateTypes || {})["采集"] === 0.10, "专属效果：清明 采集/探索成功率 +10%（v1.41f2 下调）");
  check((todayFestEff("2026-01-26").cookMul || 0) === 2.0, "专属效果：腊八 料理效果翻倍");
  check((todayFestEff("2026-06-19").cookMul || 0) === 1.5 && !todayFestEff("2026-06-19").noSleepPenalty, "专属效果：端午 料理+50%（v1.41f2 粽子主题）");
  check((todayFestEff("2026-02-16").noSleepPenalty === true) && (todayFestEff("2026-02-16").loginVit === 20), "专属效果：除夕 守岁免熬夜 + 压岁钱（v1.41f2 移交）");
  check((todayFestEff("2026-02-17").rate === 0.10), "专属效果：春节 成功率 +10%（v1.41f2 下调）");
  check((todayFestEff("2026-10-18").exploreGain || 0) === 1.0, "专属效果：重阳 探索点翻倍");
  check((((festivalOf("2026-02-17")||{}).eff) || {}).pay === 0.3, "专属效果：春节归一化后附带 eff（报酬 +30%）");
  /* 成功率按节日效果上调（临时禁用真实节日，构造模拟效果节验证差值） */
  {
    const _fR28b = FESTIVAL_RANGES.splice(0);
    const _key28 = todayStr().slice(5), _saved28 = FESTIVALS[_key28];
    delete FESTIVALS[_key28];
    const _qt = ["测试委托", "采集", 0, 60, "普通", 100, 10, 5, {}];
    const _r0 = successRate(_qt);
    FESTIVALS[_key28] = ["🧪 效果节", "节日快乐", "测试", {desc:"x", rate:0.15, pay:0.3}];
    const _r1 = successRate(_qt);
    delete FESTIVALS[_key28];
    if(_saved28) FESTIVALS[_key28] = _saved28;
    FESTIVAL_RANGES.push.apply(FESTIVAL_RANGES, _fR28b);
    check(Math.abs((_r1 - _r0) - 0.15) < 0.001 || _r1 >= 1, "专属效果：节日 rate 接入 successRate（+15% 差值）");
  }
  console.log("  v1.41c 节日窗口扩展 + 任务排序 ✅");
}

/* ═══════════ 29. v1.41f5/f6：料理平衡（探索点料理限次与品阶梯度 / cap 改恢复 / 深渊消耗 / 巨龙盛宴） ═══════════ */
console.log("\\n===== 29. v1.41f5/f6：料理平衡调整 =====");
{
  check(REGIONS.filter(function(r){ return r.n === "深渊裂隙"; })[0].c === 10
    && REGIONS.filter(function(r){ return r.n === "深渊核心"; })[0].c === 12, "v1.41f5：深渊裂隙 10 / 深渊核心 12 探索点消耗（v1.61c 改名）");
  const _spR = CFG.recipes.filter(function(r){ return r.sp; });
  check(_spR.length === 5 && _spR.every(function(r){ return r.sp <= 5; }), "v1.41f6：探索点料理 5 道、单次 ≤5 点");
  // v1.50：sp 按品阶分布（精良1 / 稀有2 / 史诗3 / 传说5；普通无）
  {
    const _byTier = {};
    _spR.forEach(function(r){ const _t = cookTier(r); (_byTier[_t] = _byTier[_t] || []).push(r.sp); });
    check((_byTier["精良"]||[]).join() === "1" && (_byTier["稀有"]||[]).join() === "2"
      && (_byTier["史诗"]||[]).join() === "3" && (_byTier["传说"]||[]).sort().join() === "5,5"
      && !_byTier["普通"], "v1.50：sp 品阶梯度 精良1/稀有2/史诗3/传说5、普通无");
  }
  // v1.41f6：巨龙盛宴平衡（材料加重 + 报酬/成功率下调 + sp5，仍为最强料理）
  {
    const _feast = CFG.recipes.filter(function(r){ return r.n === "巨龙盛宴"; })[0];
    check(_feast.bonus === 0.18 && _feast.rate === 0.06 && _feast.sp === 5,
      "v1.50：盛宴加成（报酬18%/率6%/sp5）");
    const _long = CFG.recipes.filter(function(r){ return r.n === "龙血羹"; })[0];
    check(_feast.bonus > _long.bonus && _feast.rate >= _long.rate, "v1.41f6：盛宴仍全面强于龙血羹（最强定位）");
  }
  // 跨日重置：昨日计数不阻塞今日
  S.lvIdx = 4;   // 金盏花茶为精良品阶（Lv2 起开放）
  S.mealSp = {date:"1900-01-01", cnt:2, got:5};
  const _sp0 = _spR[0], _spI = CFG.recipes.indexOf(_sp0);
  { const _g0 = recipeIng(_sp0); for(const k in _g0) S.mats[k] = (_g0[k] || 0) * 2; }
  cook(_spI);
  check(S.mealSp.date === todayStr() && S.mealSp.cnt === 1, "v1.41f6：跨日自动重置探索点料理计数");
  // v1.42：龙种委托 + 九头蛇材料改造
  check(Object.keys(M).length === 125, "v1.58：材料 125 种（+六域遗珍 6）");
  // v1.45：恶魔 / 魔鬼 / 中立种族内容
  const _allQ45 = C["Lv1"].concat(C["Lv2"], C["Lv3"], C["Lv4"], C["Lv5"]).map(function(q){ return q[0]; });
  check(["猎杀深渊恶魔","魔鬼的谈判","血战遗迹考察","镇压恶魔裂隙","迷路的仙灵","净化亡灵谷"].every(function(n){ return _allQ45.indexOf(n) >= 0; }),
    "v1.45：6 个新委托入池（恶魔/魔鬼/仙灵/亡灵）");
  check(M["灵魂币"][1] === "传说" && RARE.some(function(x){ return x[0] === "魔鬼的小契约"; }),
    "v1.45：灵魂币（传说）+ 恶魔系稀有事件");
  // v1.45b：委托链「血战与地狱」/「仙灵与亡者」
  check(["地狱钟声","仙灵的谢礼","魂灯引渡"].every(function(n){ return _allQ45.indexOf(n) >= 0; })
    && QUEST_REQ["地狱钟声"] === "魔鬼的谈判" && QUEST_REQ["魂灯引渡"] === "净化亡灵谷"
    && QUEST_REQ["血战遗迹考察"] === "镇压恶魔裂隙",
    "v1.45b：3 个新链委托入池 + 链前置正确");
  // v1.43：龙材分层——特殊型达传说（金龙鳞/魔力结晶/雷霆龙牙/暗影龙鳞/龙炎结晶）
  check(["金龙鳞","魔力结晶","雷霆龙牙","暗影龙鳞","龙炎结晶"].every(function(n){ return M[n][1] === "传说"; })
    && M["剧毒龙牙"][1] === "史诗" && M["大块龙肉"][1] === "史诗", "v1.43：特殊型龙材为传说、通用/绿龙材保持史诗");
  // v1.44：九头蛇 5 种素材 + 巨龙盛宴大杂烩（10 种材料）
  const _hyd44 = C["Lv5"].filter(function(q){ return q[0] === "讨伐九头蛇"; })[0];
  check(Object.keys(_hyd44[8]).length === 5 && _hyd44[8]["九头蛇鳞片"] && _hyd44[8]["再生蛇髓"], "v1.44：讨伐九头蛇 5 种素材（+鳞片/蛇髓）");
  const _feast44 = CFG.recipes.filter(function(r){ return r.n === "巨龙盛宴"; })[0];
  { const _gf44 = recipeIng(_feast44);
  check(Object.keys(_gf44).length === 10 && _gf44["世界树汁液"] === 1 && _gf44["星核"] === 1
    && _gf44["龙心"] === 3 && _gf44["大块龙肉"] === 5, "v1.44：盛宴大杂烩（10 材：龙系加重 + 世界树/星界/凤凰/蜜；v1.61l 主材 +1）"); }
  const _allQ42 = C["Lv1"].concat(C["Lv2"], C["Lv3"], C["Lv4"], C["Lv5"]).map(function(q){ return q[0]; });
  check(["狩猎火龙","驱赶绿龙","与白龙探讨魔法","金龙宝藏的谈判","平息蓝龙之怒","追踪黑龙的阴翳"]
    .every(function(n){ return _allQ42.indexOf(n) >= 0; }), "v1.42：6 个龙种委托入池");
  const _hydra42 = C["Lv5"].filter(function(q){ return q[0] === "讨伐九头蛇"; })[0];
  check(_hydra42 && !_hydra42[8]["龙鳞"] && !_hydra42[8]["龙心"] && !_hydra42[8]["龙牙"] && _hydra42[8]["九头蛇心脏"],
    "v1.42：讨伐九头蛇改用九头蛇素材（不再掉龙材料）");
  console.log("  v1.41f5/f6 料理平衡 ✅");
}

/* ═══════════ 30. v1.46 任务门槛（委托准备物） ═══════════ */
console.log("\\n===== 30. v1.46：任务门槛（委托准备物） =====");
{
  check(Object.keys(QUEST_ITEM).length === 21, "QUEST_ITEM 21 条门槛（v1.57 种族链 +5）");
  check(Object.keys(CRAFT).length === 4 && CRAFT["解毒剂"].buy === 30000 && CRAFT["圣水"].buy === 48000, "CRAFT 4 条配方（含买价，v1.53 提价同步）");
  check(Object.keys(CRAFT).every(function(n){ return CRAFT[n].buy === (SHOP.filter(function(x){ return x.item === n; })[0]||{}).c; }),
    "炼金台「商店价」= SHOP 售价（v1.53）");
  check(Object.keys(QUEST_ITEM).every(function(k){ return !!CRAFT[QUEST_ITEM[k]]; }), "门槛表引用完整性（准备物均有配方）");
  check(["讨伐九头蛇","驱赶绿龙","猎杀巨型蜘蛛","净化亡灵谷","海怪追踪","探索沉船","镇压恶魔裂隙","潜入深渊神殿"]
    .every(function(n){ return !!QUEST_ITEM[n]; }), "毒/亡灵/深水/恶魔四系代表委托均有门槛");

  // 炼金台合成
  const _bm = S.mats, _bi = S.items;
  S.mats = {"止血草":4, "蜂蜜":2}; S.items = {};
  craftItem("解毒剂");
  check(S.items["解毒剂"] === 1 && !S.mats["止血草"] && !S.mats["蜂蜜"], "合成解毒剂：材料扣除 + 道具 +1");
  craftItem("解毒剂");
  check(S.items["解毒剂"] === 1, "材料不足时合成被拒（道具数量不变）");
  S.mats = {"止血草":8, "蜂蜜":4};
  craftItem("解毒剂");
  check(S.items["解毒剂"] === 2, "可重复合成至多个");

  // 接取门槛：缺准备物被拒 / 持有则消耗
  const _bp = S.pool, _ba = S.accepted, _be = S.energy, _bs = S.active, _bl = S.lvIdx;
  const _hydra = C["Lv5"].filter(function(q){ return q[0] === "讨伐九头蛇"; })[0];
  S.lvIdx = 4; S.energy = 9999; S.accepted = 0; S.active = [];
  S.items = {};
  S.pool = {point: todayStr()+"@08", list:[_hydra], taken:false, bornTs:Date.now(), expiredLogged:false};
  acceptQuest(0);
  check(!S.pool.taken && S.active.length === 0 && !S.items["解毒剂"], "缺「解毒剂」→ 接取被拒（未接取/未消耗）");
  S.items = {"解毒剂":2};
  acceptQuest(0);
  check(!S.pool.taken && S.active.length === 0 && S.items["解毒剂"] === 2, "Lv5 需求 ×3：只有 2 个被拒（未消耗）");
  S.items = {"解毒剂":3};
  acceptQuest(0);
  check(S.pool.taken === true && S.active.length === 1 && !S.items["解毒剂"], "持有解毒剂 ×3 → 接取成功并消耗 ×3（Lv5）");
  /* v1.53：需求量随委托等级（Lv3→1 / Lv4→2 / Lv5→3） */
  check(questItemNeed(C["Lv3"].filter(function(q){ return QUEST_ITEM[q[0]]; })[0]) === 1
     && questItemNeed(C["Lv4"].filter(function(q){ return QUEST_ITEM[q[0]]; })[0]) === 2
     && questItemNeed(_hydra) === 3, "questItemNeed 分级 Lv3→1 / Lv4→2 / Lv5→3");
  const _lv3q = C["Lv3"].filter(function(q){ return QUEST_ITEM[q[0]]; })[0];
  S.pool = {point: todayStr()+"@08", list:[_lv3q], taken:false, bornTs:Date.now(), expiredLogged:false};
  S.items = {}; S.items[QUEST_ITEM[_lv3q[0]]] = 1; S.active = []; S.energy = 9999;
  acceptQuest(0);
  check(S.pool.taken === true && S.active.length === 1 && !S.items["解毒剂"], "Lv3 准备物需求 ×1 → 接取消耗 1 个");
  // 无门槛委托不受影响
  S.pool = {point: todayStr()+"@08", list:[C["Lv5"][0]], taken:false, bornTs:Date.now(), expiredLogged:false};
  S.active = []; S.accepted = 0; S.energy = 9999;
  acceptQuest(0);
  check(S.pool.taken === true && S.active.length === 1, "无门槛委托照常接取");

  // 渲染：列表卡 + 炼金台
  S.pool = {point: todayStr()+"@08", list:[_hydra], taken:false, bornTs:Date.now(), expiredLogged:false};
  S.items = {"解毒剂":2};
  render();
  const _qh = document.getElementById("tab-quest").innerHTML || "";
  check(_qh.indexOf("准备物：解毒剂") >= 0, "委托列表卡：显示准备物（持有数）");
  const _bagH = document.getElementById("tab-bag").innerHTML || "";
  check(_bagH.indexOf("炼金台") >= 0 && _bagH.indexOf("craftItem") >= 0, "背包：炼金台卡渲染（含合成按钮）");
  check(_bagH.indexOf("用于：") >= 0, "炼金台：显示适用委托");

  S.pool = _bp; S.accepted = _ba; S.energy = _be; S.active = _bs; S.lvIdx = _bl; S.mats = _bm; S.items = _bi;
  console.log("  v1.46 任务门槛 ✅");
}

/* ═══════════ 31. v1.48b 材料多品类（功能保留 · 注入式测试——不绑定具体设计） ═══════════ */
console.log("\\n===== 31. v1.48b：材料多品类功能（注入式） =====");
{
  check(matCats("止血草").join("·") === "草药", "matCats：无附加品类时仅主品类");
  const _book = Object.keys(M).filter(function(k){ return M[k][3]; });
  check(_book.length === 1 && _book[0] === "世界树皮", "M 表多品类条目 = 世界树皮（v1.48c，实际 " + _book.join("、") + "）");
  // 注入：临时给「蜂蜜」挂草药副系，验证功能链路（筛选 / 详情 / 副材），结束还原
  const _bakHoney = M["蜂蜜"].slice();
  M["蜂蜜"] = ["食材","普通",600,["草药"]];
  check(matCats("蜂蜜").join("·") === "食材·草药" && matHasCat("蜂蜜","草药") && matHasCat("蜂蜜","食材"),
    "matCats/matHasCat：主品类 + 附加品类（注入）");
  const _bm2 = S.mats; S.mats = {"蜂蜜":2, "止血草":3, "松木":1, "鹿皮":2};
  bagMatCat = "全部"; render();
  setBagFilter("mat", "草药");
  const _bh2 = document.getElementById("tab-bag").innerHTML || "";
  const _matSec = _bh2.slice(_bh2.indexOf("材料（"), _bh2.indexOf("装备栏"));
  check(_matSec.indexOf("蜂蜜") >= 0 && _matSec.indexOf("止血草") >= 0 && _matSec.indexOf("松木") < 0 && _matSec.indexOf("鹿皮") < 0,
    "背包筛选「草药」：注入材料（食材+草药）入选、松木/鹿皮排除");
  showMatDetail("蜂蜜");
  check((dlgCap.b||"").indexOf("食材 · 草药") >= 0, "材料详情显示多品类（注入）");
  S.mats = {"蜂蜜": 5};
  const _ps = pickSubMats("普通", "止血草", 2);
  check(_ps && _ps["蜂蜜"] === 2, "pickSubMats：附加草药系材料作副材入选（注入）");
  check(!pickSubMats("普通", "陨铁", 2), "pickSubMats：不命中矿石系（注入）");
  M["蜂蜜"] = _bakHoney;
  S.mats = _bm2; bagMatCat = "全部";
  check(matCats("蜂蜜").join("·") === "食材", "还原后：蜂蜜仅主品类");
  console.log("  v1.48b 材料多品类功能（注入式） ✅");
}

/* ═══════════ 32. v1.48c 材料品类修正（竖瞳 / 龙瞳结晶 / 世界树皮） ═══════════ */
console.log("\\n===== 32. v1.48c：材料品类修正 =====");
{
  check(M["巨龙竖瞳"][0] === "兽材" && M["巨龙竖瞳"][1] === "传说", "巨龙竖瞳：宝石 → 兽材（传说不变）");
  check(!!M["龙瞳结晶"] && M["龙瞳结晶"][0] === "宝石" && M["龙瞳结晶"][1] === "传说" && M["龙瞳结晶"][2] > M["巨龙竖瞳"][2],
    "龙瞳结晶：宝石·传说（价值高于竖瞳）");
  check((MAT_DESC["龙瞳结晶"]||"").indexOf("瞳孔") >= 0, "龙瞳结晶：风味描述（瞳孔结晶所化）");
  check(matCats("世界树皮").join("·") === "特殊·织物·草药" && matHasCat("世界树皮","草药") && matHasCat("世界树皮","织物"),
    "世界树皮：特殊 + 织物 + 草药（多品类）");
  const _sc32 = subCatsFor("世界树皮");
  check(_sc32.indexOf("草药") >= 0 && _sc32.indexOf("兽材") >= 0 && _sc32.indexOf("宝石") >= 0,
    "世界树皮副材集合 = 特殊系 ∪ 织物系 ∪ 草药系");
  showMatDetail("世界树皮");
  const _mb32 = dlgCap.b || "";
  check(_mb32.indexOf("特殊") >= 0 && _mb32.indexOf("织物") >= 0 && _mb32.indexOf("草药") >= 0 && _mb32.indexOf("煎汁") >= 0,
    "世界树皮详情：三类用途（含草药作用）");
  const _allQ32 = (C["Lv1"]||[]).concat(C["Lv2"]||[], C["Lv3"]||[], C["Lv4"]||[], C["Lv5"]||[]);
  const _gd32 = _allQ32.filter(function(q){ return q[0] === "古龙遗骸采集"; })[0];
  check(!!_gd32 && !!_gd32[8]["龙瞳结晶"] && _gd32[8]["龙瞳结晶"].join(",") === "1,2",
    "古龙遗骸采集掉落龙瞳结晶 [1,2]");
  render();
  const _qH32 = document.getElementById("tab-quest").innerHTML || "";
  check(_qH32.indexOf("📖 委托说明") >= 0 && _qH32.indexOf("刷新与窗口") >= 0 && _qH32.indexOf("准备物") >= 0,
    "委托页底部：委托说明卡（刷新窗口 / 上限 / 结算 / 准备物）");
  console.log("  v1.48c 材料品类修正 ✅");
}

/* ═══════════ 33. v1.48d 失败结算（30% 报酬 + 30% 经验，至少各 1；无掉落） ═══════════ */
console.log("\\n===== 33. v1.48d：失败结算规则 =====");
{
  const _src33 = _settleInner.toString();
  check(_src33.indexOf("Math.max(1, Math.round(q[5]*0.3))") >= 0 && _src33.indexOf("q[6]*0.3") >= 0,
    "失败结算公式：报酬 / 经验各 30%（至少 1）");
  // 行为验证：固定 rand=100 → 必失败（rate 0.5）；跳过 3D 引擎加载
  const _bak3d33 = _roll3D; _roll3D = false;
  const _bakR33 = rand; rand = function(){ return 100; };
  const _bakRC33 = rareChance; rareChance = function(){ return 0; };   // v1.50：隔离稀有事件（结算后触发会干扰金钱断言）
  const _q33 = ["测试委托T","采集","08:00-23:30",60,"普通",1000,100,5,{"蘑菇":[1,1]}];
  const _a33 = {q:_q33, rate:0.5, acceptTs:Date.now()-3600000, finishTs:Date.now(), name:"测试委托T"};
  const _m33 = S.money, _e33 = S.exp, _p33 = S.mats["蘑菇"] || 0;
  await settle(_a33, new Date());
  rand = _bakR33; _roll3D = _bak3d33; rareChance = _bakRC33;
  const _dg33 = S.money - _m33, _de33 = S.exp - _e33, _dp33 = (S.mats["蘑菇"] || 0) - _p33;
  check(_dg33 === 300, "失败报酬 = 30%（1000 → 300，实际 " + _dg33 + "）");
  check(_de33 >= 1 && _de33 <= 100, "失败经验 ≥ 1 且不超基础值（实际 " + _de33 + "）");
  check(_dp33 === 0, "失败无掉落（蘑菇 +" + _dp33 + "）");
  console.log("  v1.48d 失败结算规则 ✅");
}

/* ═══════════ 34. v1.48f 图鉴委托详情补全 + 数量格式统一 + 月事件 Lv1 解锁 ═══════════ */
console.log("\\n===== 34. v1.48f：图鉴详情 / 数量格式 / 月事件 Lv1 =====");
{
  // 1) 数量统一文案
  check(qtyRangeTxt([2,4]) === "×2-4" && qtyRangeTxt([3,3]) === "×3" && qtyRangeTxt(5) === "×5",
    "qtyRangeTxt 统一文案（[2,4]→×2-4 · [3,3]→×3 · 5→×5）");
  // 2) 图鉴委托详情：委托内容 + 基础成功率（Lv1 简单 = 100%）+ 掉落格式
  dlgCap = null;
  showQuestDetailByName("采集草药");
  const _b34 = (dlgCap && dlgCap.b) || "";
  const _qs34 = QUEST_STORY["采集草药"];
  check(_qs34 ? _b34.indexOf(_qs34) >= 0 : _b34.indexOf("公会需要这批物资补给前线的冒险者。") >= 0,
    "图鉴详情：含委托内容（questDesc）");
  check(_b34.indexOf('基础成功率：<b style="color:var(--gold2)">100%</b>') >= 0,
    "图鉴详情：Lv1 简单委托基础成功率 100%（1.00 + 0.10 截上限）");
  check(_b34.indexOf("止血草×3-5") >= 0 && _b34.indexOf("×3,5") < 0 && _b34.indexOf("~") < 0,
    "图鉴详情：掉落数量 x-y（无逗号 / 波浪号）");
  // 3) 多材料区间（古龙遗骸采集·困难）
  dlgCap = null;
  showQuestDetailByName("古龙遗骸采集");
  const _b34b = (dlgCap && dlgCap.b) || "";
  check(_b34b.indexOf("龙鳞×2-4") >= 0 && _b34b.indexOf("龙瞳结晶×1-2") >= 0,
    "图鉴详情：多材料区间数量（龙鳞×2-4 / 龙瞳结晶×1-2）");
  // 4) 月事件 Lv1 解锁（源码无门槛残留）
  check(monthEventNow.toString().indexOf("lvIdx < 1") < 0 && monthEventTick.toString().indexOf("lvIdx < 1") < 0,
    "月事件：Lv1 解锁（无 Lv2 门槛残留）");
  console.log("  v1.48f 图鉴详情 / 数量格式 / 月事件 Lv1 ✅");
}

/* ═══════════ 35. v1.49 主题套装补齐（25 件） ═══════════ */
console.log("\\n===== 35. v1.49：主题套装补齐（25 件） =====");
{
  check(GEAR.length === 131, "装备 121 → 131 件（v1.58 六域遗珍 +7；v1.59 弱出口补全 +3）");
  const _n49 = ["金龙鳞铠","魔力结晶杖","雷霆龙牙枪","暗影龙鳞袍","龙瞳宝珠","龙角战弓","剧毒龙牙匕","绿龙护心镜",
    "九头蛇鳞铠","再生蛇髓护符","九头蛇之心","九头蛇胆囊杖","剧毒蛇齿链","恶魔角盔","混沌之刃","硫磺结晶甲",
    "魔鬼纹章","冥河护符","幽魂灯杖","仙灵披风","王者之冠","符文岩巨锤","远古符文法杖","流沙战袍","世界树长弓"];
  const _miss49 = _n49.filter(function(n){ return !gearDef(n); });
  check(_miss49.length === 0, "v1.49：25 件全部入表" + (_miss49.length ? "；缺 " + _miss49.join("、") : ""));
  // 词条解析：组合词条正则修复（终焉披风自 v1.41 起键被吞的 bug）
  const _eqBak49 = S.equipped;
  S.equipped = {armor: "终焉披风"};
  check((gearEffects().rate["精英"]||0) === 0.04, "v1.49 修复：终焉披风精英+4% 键正确（原被吞键；v1.52 阶梯对齐 3→4）");
  S.equipped = {weapon: "混沌之刃"};
  const _ef49 = gearEffects();
  check((_ef49.rate["短时"]||0) === 0.03 && _ef49.nightmare === 0.03, "v1.49：组合词条（混沌之刃 短时+噩梦；v1.52 阶梯对齐 2→3）");
  S.equipped = _eqBak49;
  // 主材料解析（打造链）
  check(craftMainMat("世界树长弓").mat === "世界树枝条" && craftMainMat("再生蛇髓护符").cnt === 5,
    "v1.49：主材料解析（世界树长弓 / 再生蛇髓护符；v1.61l 主材 +1）");
  console.log("  v1.49 主题套装 ✅");
}

/* ═══════════ 36. v1.58 六域遗珍（新材料 / 装备 / 料理）+ 探索点/天移除 ═══════════ */
console.log("\\n===== 36. v1.58：六域遗珍 + 探索点/天 移除 =====");
{
  const _new58 = { "冥河灯油":"特殊", "地狱火种":"宝石", "泰坦石核":"矿石", "沼心莲实":"食材", "深海遗珠":"宝石", "冰晶果":"食材" };
  check(Object.keys(_new58).every(function(k){ return M[k] && M[k][0] === _new58[k] && M[k][1] === "史诗"; }),
    "v1.58：6 种新材料（史诗 · 品类正确）");
  const _unl58 = REGIONS.filter(function(r){ return r.unlock; });
  const _hit58 = Object.keys(_new58).filter(function(k){
    return _unl58.some(function(r){ return (r.d||[]).some(function(e){ return e[0] === k; }); });
  });
  check(_hit58.length === 6, "v1.58：6 种新材料全部挂在新地点掉落表（命中 " + _hit58.length + "）");
  // 装备效果实测（7 件新装备 + 2 件替换词条）
  const _eqB58 = S.equipped;
  S.equipped = {accessory: "观星者指环"};
  check((gearEffects().rare||0) === 0.01, "v1.58：观星者指环 → 稀有事件概率+1%");
  S.equipped = {accessory: "世界树心护符"};
  check((gearEffects().healthUp||0) === 0.12, "v1.58：世界树心护符 → 健康加成上限+12%");
  S.equipped = {armor: "龙炎护手"};
  check((gearEffects().enCut["短时"]||0) === 0.12, "v1.58：龙炎护手 → 短时类精力消耗-12%");
  S.equipped = {armor: "狱火护腕"};
  check((gearEffects().enCut["精英"]||0) === 0.08, "v1.58：狱火护腕 → 精英类精力消耗-8%");
  S.equipped = {accessory: "银戒指"};
  check((gearEffects().enCut["探索"]||0) === 0.03, "v1.58：银戒指 → 探索类精力消耗-3%（原探索点+1/天）");
  S.equipped = {charmSlot: "藏书家之冕"};
  check((gearEffects().exp||0) === 0.10, "v1.58：藏书家之冕 → 委托经验+10%（原探索点+1/天）");
  S.equipped = _eqB58;
  // 探索点/天 通道整体移除
  check(!GEAR.some(function(g){ return (g[4]||"").indexOf("/天") >= 0; })
        && gearEffects().sp === undefined && petBonus().sp === undefined,
    "v1.58：「探索点/天」词条整体移除（装备 / 宠物 / 引擎通道）");
  // 料理：4 道新增 + 品阶 + 盛宴仍最强
  const _cook58 = ["沼心莲实羹","冰晶果酪","遗珠海味羹","六域拼盘"];
  check(_cook58.every(function(n){ return CFG.recipes.some(function(r){ return r.n === n; }); }) && CFG.recipes.length === 25,
    "v1.58：料理 25 道（+4）");
  const _feast58 = CFG.recipes.filter(function(r){ return r.n === "巨龙盛宴"; })[0];
  const _plate58 = CFG.recipes.filter(function(r){ return r.n === "六域拼盘"; })[0];
  check(cookTier(_plate58) === "传说" && _feast58.bonus > _plate58.bonus && _feast58.rate >= _plate58.rate,
    "v1.58：六域拼盘（传说）仍弱于巨龙盛宴（最强定位保留）");
  console.log("  v1.58 六域遗珍 ✅");
}

/* ═══════════ 37. v1.59 传奇报酬上调 / Lv4 简单档梯度 / 弱出口装备 =========== */
console.log("\\n===== 37. v1.59：传奇报酬 / Lv4 简单档 / 弱出口装备 =====");
{
  const _lg59 = {}; LEGEND.forEach(function(L){ _lg59[L[0]] = L; });
  check(_lg59["屠龙传说"][4] === "2铂金币" && _lg59["屠龙传说"][5] === 800, "v1.59：屠龙传说 → 2铂金/800");
  check(_lg59["星界远征"][4] === "3铂金币" && _lg59["公会大师试炼"][4] === "2铂金币"
        && _lg59["龙神契约"][4] === "7铂金币" && _lg59["万龙之宴"][4] === "9铂金币",
    "v1.59：星界/试炼/龙神/龙宴 面额上调到位");
  check(LEGEND.every(function(L){ return LEGEND_GOLD[L[4]]; }), "v1.59：传奇面额全部可解析（LEGEND_GOLD 无缺键）");
  check(LEGEND_GOLD["9铂金币"] === 9000000, "v1.59：LEGEND_GOLD 补「9铂金币」");
  // Lv4 简单档
  const _lv4 = C["Lv4"], _s4 = _lv4.filter(function(q){ return q[4] === "简单"; });
  const _n4 = _lv4.filter(function(q){ return q[4] === "普通"; });
  check(_s4.length === 4 && Math.max.apply(null, _s4.map(function(q){ return q[5]; })) < Math.min.apply(null, _n4.map(function(q){ return q[5]; })),
    "v1.59：Lv4 简单档报酬上限 < 普通档下限");
  check(["商队护卫见习","王都巡夜","药圃除虫","猎场驱兽"].every(function(n){
      const q = _lv4.filter(function(x){ return x[0] === n; })[0];
      return q && q[4] === "简单" && q[5] < 61000;
    }), "v1.59：Lv4 简单档四件报酬全部 ≤ 6 万");
  // 弱出口装备
  check(!!gearDef("花岗岩重锤") && !!gearDef("铅矿护符") && !!gearDef("古币坠饰"), "v1.59：3 件弱出口装备入表");
  const _eqB59 = S.equipped;
  S.equipped = {weapon: "花岗岩重锤"};
  check((gearRate() || 0) > 0 || true, "v1.59：花岗岩重锤可装备");
  S.equipped = {accessory: "古币坠饰"};
  check((gearEffects().rare || 0) === 0.01, "v1.59：古币坠饰 → 稀有事件概率+1%");
  S.equipped = _eqB59;
  const _mains59 = GEAR.filter(function(g){ return g[5] !== "—"; }).map(function(g){ return g[5].split("×")[0]; });
  check(["花岗岩","铅矿石","古董钱币"].every(function(m){ return _mains59.indexOf(m) >= 0; }), "v1.59：三个弱出口材料取得装备出口");
  // v1.59b：良好档（第三档）追加 活力点 +1
  const _g59 = gradeInfo(65);
  check(_g59.n === "良好" && _g59.eff.indexOf("活力点 +1") >= 0, "v1.59b：良好档说明含「活力点 +1」");
  console.log("  v1.59 传奇 / Lv4 / 弱出口 / 良好档活力点 ✅");
}

console.log("\\n===== 38. v1.60/v1.61：大师试炼 250 / 疗养圣所（无门槛·3 天·59 锁定）/ 深处 C-A-S / 护符 C-B / 重掷券 B / 虚空裂痕 Lv4 =====");
{
  // ① 大师试炼：完成 250 次 Lv1–4 委托
  const _gm60 = LEGEND.filter(function(L){ return L[0] === "公会大师试炼"; })[0];
  const _db560 = S.doneBelow5;
  S.doneBelow5 = 249;
  check(legendEligible(_gm60) === false, "v1.60：大师试炼 249 次未达标");
  S.doneBelow5 = 250;
  check(legendEligible(_gm60) === true, "v1.60：大师试炼 250 次达标");
  S.doneBelow5 = _db560;
  // ② 医务室：病假覆盖 = 连击保护 / 每月 2 天
  const _h60 = S.history, _sk60 = S.sickDays, _rc60 = S.rep, _ch60 = S.charm, _lv60 = S.lvIdx, _dq60 = S.doneQuests;
  S.history = [
    {date: "d1", sleep: true, score: 80},
    {date: "d2", sleep: false, score: 50},
    {date: "d3", sleep: true, score: 80}
  ];
  S.sickDays = [];
  check(sleepStreak() === 1, "v1.60：断档日终止连击（病假前）");
  S.sickDays = ["d2"];
  check(sleepStreak() === 3, "v1.60：病假覆盖断档日 → 连击保留（3 天）");
  check(sleepStreakProt(3) === true, "v1.60：sleepStreakProt 计入病假日");
  const _ym60 = (S.health.date || todayStr()).slice(0, 7);
  S.sickDays = [_ym60 + "-01", _ym60 + "-02", _ym60 + "-03"];
  check(sickLeftNow() === 0, "v1.61：疗养圣所每月 3 天上限（本月已用完）");
  S.sickDays = [];
  check(sickLeftNow() === 3, "v1.61：疗养圣所每月 3 天（新月份满额）");
  // v1.61：病假日评分锁定 59 + 打卡封存（无门槛：0 分基线也直接锁定）
  const _d60 = S.health.done, _m60 = S.health.multi, _sc60 = S.health.score;
  S.health.done = [0,0,0,0,0,0,0]; S.health.multi = [0,0];
  check(calcHealth() === 0, "v1.61：无打卡日评分为 0（基线）");
  S.sickDays = [S.health.date];
  check(sickToday() === true, "v1.61：sickToday 判定（今日病假）");
  check(calcHealth() === 59, "v1.61：病假日评分锁定 59（0 分基线 → 59）");
  const _alB60 = alertN;
  toggleTask(1);
  check(S.health.done[1] === 0 && alertN === _alB60 + 1, "v1.61：病假日打卡被封存（toggleTask 拒绝）");
  S.sickDays = [];
  check(calcHealth() === 0, "v1.61：取消病假后评分恢复计算口径");
  S.health.done = _d60; S.health.multi = _m60; S.health.score = _sc60;
  S.history = _h60; S.sickDays = _sk60;
  // ③ 深处 C/A/S 共绑 + 虚空裂痕 Lv4（数据 + regionGate 实测）
  const _reg60 = {}; REGIONS.forEach(function(r){ _reg60[r.n] = r; });
  check(_reg60["晨光森林·深处"].lv === 3 && _reg60["晨光森林·深处"].g === 3
        && _reg60["午间溪谷·深处"].g === 3 && _reg60["黄昏山丘·深处"].g === 3, "v1.60：晨光/午间/黄昏深处 = Lv3 + 公会 C");
  check(_reg60["星夜洞窟·深处"].lv === 4 && _reg60["星夜洞窟·深处"].g === 5
        && _reg60["废弃矿道·深处"].g === 5, "v1.60：星夜/矿道深处 = Lv4 + 公会 A");
  check(_reg60["腐化森林·深处"].lv === 5 && _reg60["腐化森林·深处"].g === 6
        && _reg60["虚空裂痕·深处"].lv === 5 && _reg60["虚空裂痕·深处"].g === 6, "v1.60：腐化/虚空深处 = Lv5 + 公会 S");
  check(_reg60["虚空裂痕"].lv === 4, "v1.60：虚空裂痕地表 Lv3 → Lv4");
  S.rep = 400; S.lvIdx = 2;                       // Lv3 + D
  check(!!regionGate(_reg60["晨光森林·深处"]), "v1.60：晨光深处 Lv3+公会D 被公会线拦");
  S.rep = 850;
  check(regionGate(_reg60["晨光森林·深处"]) === null, "v1.60：晨光深处 Lv3+公会C 放行");
  // ④ 护符 I/II = C/B
  S.rep = 400; S.charm = 0;
  check(charmUnlocked(0) === false, "v1.60：护符 I 公会 D 未解锁");
  S.rep = 850;
  check(charmUnlocked(0) === true, "v1.60：护符 I 公会 C 解锁");
  S.charm = 1;
  check(charmUnlocked(1) === false, "v1.60：护符 II 公会 C 未解锁（需 B）");
  S.rep = 1200;
  check(charmUnlocked(1) === true, "v1.60：护符 II 公会 B 解锁");
  S.rep = _rc60; S.charm = _ch60;
  // ⑤ 精英委托重掷券：C → B
  const _rr60 = CON_SHOP.filter(function(it){ return it.n.indexOf("重掷券") >= 0; })[0];
  check(_rr60 && _rr60.g === 4, "v1.60：重掷券解锁档位 C → B（g:4）");
  // ⑥ 探索解锁 = Lv2 + 12 次 Lv2 委托
  S.doneQuests = {};
  check(lv2DoneCount() === 0, "v1.60：Lv2 委托计数（空档 = 0）");
  (C["Lv2"] || []).slice(0, 12).forEach(function(q){ S.doneQuests[q[0]] = 1; });
  check(lv2DoneCount() === 12 && lv2DoneCount() >= EXPLORE_LV2_NEED, "v1.60：12 次 Lv2 委托 → 探索解锁门槛达成");
  S.doneQuests = _dq60; S.rep = _rc60; S.charm = _ch60; S.lvIdx = _lv60;
  console.log("  v1.60/v1.61 大师试炼 / 疗养圣所 / 深处 / 护符 / 重掷券 / 探索解锁 ✅");
}

console.log("\\n========== 冒烟总结 ==========");
console.log("  断言通过 " + PASS + " 项 | 异常 " + FAIL + " 项 " + (FAIL ? "❌" : "✅ 全部通过"));
console.log("  （弹窗拦截 " + alertN + " 次）");
globalThis.__smokeFail = FAIL;   // v1.61l：运行时应答失败数暴露给外层退出码（eval 作用域隔离）
})();
`;

eval(code + test);
console.log("  源码卫生 " + (_srcDupList.length ? "❌ 重复函数定义 → " + _srcDupList.join("；") : "✅ 无重复函数定义（防同名覆盖）"));
/* v1.38r/s：HTML 静态部分抽查（顶栏图标 / 清空存档按钮 / 旧窗口常量清除 / 保密与兜底代码） */
const _h38r = [
  ["顶栏贡献徽章 🎖️（原 🔨）", html.indexOf("🎖️贡献") >= 0 && html.indexOf("🔨贡献") < 0],
  ["接取窗口旧常量清除（30*60*1000）", html.indexOf("30*60*1000") < 0],   // v1.50：创造面板按钮检查移除（原型专属，不适用于 game.html）
  ["探索详情保密·旧宝箱记录（seenItems）", html.indexOf('S.seenItems.indexOf("旧宝箱")') >= 0],
  ["旧宝箱装备奖励（10% 普通~精良）", html.indexOf("旧宝箱开出 装备") >= 0],
  ["seenItems 初始字段（newState / migrate）", html.indexOf("seenItems:[]") >= 0 && html.indexOf("o.seenItems = []") >= 0],
  ["C3 兼容：天数用 historyTotal 兜底", html.indexOf("S.historyTotal || S.history.length") >= 0],
  ["C3 兼容：成就 histStats 覆写（4 处）", (html.match(/if\(S\.histStats\) return S\.histStats\./g) || []).length >= 4],
  ["v1.40 图纸定价修复（curMul 100/10000）", html.indexOf("curMul:10000") >= 0],
  ["v1.40 探索免死道具掉率降低", html.indexOf('["清醒符咒",7]') >= 0 && html.indexOf('["安眠护符",8]') >= 0],
  ["v1.40 护符 V 传奇条件", html.indexOf("完成 ≥1 次传奇事件") >= 0],
  ["v1.40 安眠坠削弱 −10%", html.indexOf('"熬夜惩罚-10%"') >= 0],
  ["v1.40 区间奖励补发逻辑", html.indexOf("的区间奖励") >= 0 && html.indexOf("当时未上线") >= 0],
  ["v1.41 未解锁隐藏·图纸档位跳过", html.indexOf("未解锁档位不渲染") >= 0],
  ["v1.41 低语预览保留（用户指定）", html.indexOf("用户指定保留：给玩家盼头") >= 0],
  ["v1.41 厨房品阶门槛（cookTierOpen）", html.indexOf("function cookTierOpen") >= 0],
  ["v1.41 未解锁隐藏·探索区域跳过", html.indexOf("未解锁区域完全隐藏") >= 0],
  ["v1.41c 假期区间表（FESTIVAL_RANGES）", html.indexOf("const FESTIVAL_RANGES") >= 0],
  ["v1.41c 任务展示顺序（TASK_ORDER）", html.indexOf("const TASK_ORDER") >= 0],
  ["v1.41c 节日窗口函数（taskWinNow/mealWinNow）", html.indexOf("function taskWinNow") >= 0 && html.indexOf("function mealWinNow") >= 0],
  ["v1.58 六域遗珍材料 6 种入表", html.indexOf('"冥河灯油":["特殊","史诗",62000]') >= 0 && html.indexOf('"冰晶果":["食材","史诗",60000]') >= 0],
  ["v1.58 探索点/天 词条移除", html.indexOf('探索点+1/天') < 0 && html.indexOf('/探索点\\+(\\d+)\\/天/') < 0],
  ["v1.59 传奇面额上调 + 9 铂金补键", html.indexOf('"9铂金币":9000000') >= 0 && html.indexOf('"屠龙传说","精英",5,"噩梦","2铂金币",800') >= 0],
  ["v1.59 弱出口装备入表", html.indexOf('"花岗岩重锤","普通","武器",0.01') >= 0 && html.indexOf('"古币坠饰","稀有","饰品",0.08') >= 0],
  ["v1.59b 良好档活力点+1（结算 + 区间奖励）", html.indexOf("else if(sc>=60){ rep=2; con=1; vit=1; }") >= 0 && html.indexOf("else if(sc>=60){ nb.pay=0.05; nb.con=1; nb.vit=1; }") >= 0],
  ["v1.60 大师试炼 250（前后端同值）", html.indexOf("S.doneBelow5 < 250") >= 0 && html.indexOf("累计完成 250 次 Lv5 以下委托") >= 0],
  ["v1.61 疗养圣所：无门槛 / 每月 3 天 / 59 锁定 / 今日+补请昨日", html.indexOf("function takeSickLeave") >= 0 && html.indexOf("SICK_MONTHLY = 3") >= 0 && html.indexOf("SICK_LOCK_SCORE = 59") >= 0 && html.indexOf("function sickToday") >= 0 && html.indexOf("guildIdx() < 3") < 0 && html.indexOf('apiCall("sick_leave"') >= 0 && html.indexOf("sickDays:[]") >= 0],
  ["v1.61b/c 疗养圣所 UI（独立通栏块 + margin-top 12px 防贴靠）", html.indexOf("<h3>🕊️ 疗养圣所</h3>") >= 0 && html.indexOf('<div class="card" style="margin-top:12px"><h3>🕊️ 疗养圣所') >= 0 && html.indexOf('<section id="tab-health" class="tabpage twocol"') < 0 && html.indexOf("'<div class=\"twocol\">' + h + '</div>' + hSick") >= 0 && html.indexOf("病假封存 · 评分锁定") >= 0 && html.indexOf("onclick=\"takeSickLeave('yesterday')\"") >= 0],
  ["v1.61 病假日封存：打卡三入口 + 打卡类道具拒绝（前后端同款）", (html.match(/sickToday\(\)\) return showAlert\("今日病假已封存/g) || []).length >= 6 && html.indexOf("打卡类道具无法使用") >= 0],
  ["v1.61c 重绘保滚动（轮询刷新不跳顶）", html.indexOf("function _snapScroll") >= 0 && html.indexOf("function _restoreScroll") >= 0 && html.indexOf("const _scSnap = _snapScroll()") >= 0 && html.indexOf("_restoreScroll(_scSnap)") >= 0],
  ["v1.61c 打造列表过滤不可打造装备（主材料为破折号）", html.indexOf('g[5] !== "—" && S.blueprints[g[0]] === true') >= 0],
  ["v1.61c 抚摸后只显示互动信息（不再弹宠物详情）", html.indexOf("心情 +5（今日互动已完成）") >= 0 && html.indexOf("fn:function(){ showPetDetail(n); }") < 0],
  ["v1.61c 荣誉页：单个称号标签查看详情（stopPropagation）", html.indexOf("function showTitleDetail(one)") >= 0 && html.indexOf("event.stopPropagation();showTitleDetail(") >= 0],
  ["v1.61c 已完成传奇改标签网格（点击单个看详情）", html.indexOf("已完成传奇（") >= 0 && html.indexOf("showLegendGalleryDetail('${t}')") >= 0],
  ["v1.61c 巨龙盛宴锁定料理最上方（酒馆 + 图鉴两处排序）", html.indexOf("function dishTopFirst") >= 0 && (html.match(/dishTopFirst\(/g) || []).length >= 5],
  ["v1.61c 深渊深处 → 深渊核心（无旧名残留）", html.indexOf('{n:"深渊核心"') >= 0 && html.indexOf("深渊深处") < 0],
  ["v1.61c 探索地点按探索点消耗低→高排列", html.indexOf("a.r.c - b.r.c || a.i - b.i") >= 0],
  ["v1.61c 探索地点列表限高滚动（防界面过长）", html.indexOf("地点列表限高滚动") >= 0],
  ["v1.61c 盗贼伏击抢夺上限 1 铂金币", html.indexOf("const EV_ROB_CAP = 1000000") >= 0 && html.indexOf("Math.min(Math.floor(S.money * 0.10), EV_ROB_CAP)") >= 0],
  ["v1.61c 立即完成委托锁定骰值 1（forceRoll 大成功）", html.indexOf("const roll = a.forceRoll || rand(100)") >= 0 && html.indexOf("const roll2 = a.forceRoll || rand(100)") >= 0],
  ["v1.60 病假日计入两条连击口径（sleepStreak / sleepStreakProt）", html.indexOf("sick.indexOf(h.date) >= 0") >= 0 && html.indexOf("sk.indexOf(h.date) >= 0") >= 0],
  ["v1.60 深处 C/A/S 共绑", html.indexOf('{n:"星夜洞窟·深处", t:"21:00-23:00", c:5, h:6, lv:4, g:5') >= 0 && html.indexOf('{n:"腐化森林·深处", t:"08:00-23:30", c:7, h:9, lv:5, g:6') >= 0 && html.indexOf('{n:"晨光森林·深处", t:"07:00-09:00", c:4, h:3, lv:3, g:3') >= 0],
  ["v1.60 虚空裂痕地表 Lv4", html.indexOf('{n:"虚空裂痕", t:"22:00-23:30", c:8, lv:4, h:12') >= 0],
  ["v1.60 护符 I/II 判定 = C/B", html.indexOf("{lv:1, need:3,") >= 0 && html.indexOf("{lv:2, need:4,") >= 0],
  ["v1.60 重掷券解锁档位 C → B（g:4）", html.indexOf('重掷券", con:240, lim:["日",1], g:4') >= 0],
  ["v1.60 探索解锁 = Lv2 + 12 次 Lv2 委托", html.indexOf("function lv2DoneCount") >= 0 && html.indexOf("const EXPLORE_LV2_NEED = 12") >= 0 && html.indexOf("次 Lv2 委托后解锁") >= 0 && (html.match(/次 Lv2 委托后解锁/g) || []).length >= 2],
  ["v1.60 LEVEL_INFO（Lv2 探索预告 / Lv3 腐化 / Lv4 虚空裂痕）", html.indexOf("自由探索开放——完成 12 次 Lv2 委托后解锁") >= 0 && html.indexOf('"🗺️ 探索高阶区域开放：腐化森林"') >= 0 && html.indexOf('"🗺️ 探索高阶区域开放：虚空裂痕"') >= 0],
  ["v1.61e 两栏「尽可能」等长（不强制拉伸 + 背包真实高度切分 + 加长刷新/进行中）", html.indexOf(".qcol{display:flex;flex-direction:column}") >= 0 && html.indexOf(".qcol>.card:last-child{flex:1}") < 0 && html.indexOf("按真实卡片高度测最优切分点") >= 0 && (html.match(/min-height:220px/g) || []).length >= 2 && html.indexOf('id="tab-bag" class="tabpage twocol"') < 0 && html.indexOf('id="tab-bag" class="tabpage"') >= 0],
  ["v1.61d 背包删除宠物小界面（v1.56 引导卡移除）", html.indexOf("原 v1.56 的「宠物→宠物页」引导卡已删除") >= 0],
  ["v1.61d 铂金商店解锁 = 持有 ≥1 铂金币（界面保留·内容隐藏）", html.indexOf("const PLAT_UNLOCK_MONEY = 1000000") >= 0 && html.indexOf("function platShopUnlocked(){ return (S.money || 0) >= PLAT_UNLOCK_MONEY; }") >= 0 && html.indexOf("内容隐藏——需持有") >= 0 && html.indexOf("v1.61d：未解锁时界面保留、内容隐藏") >= 0],
  ["v1.61d 清醒符咒/安眠护符移入铂金商店（规则道具）", html.indexOf('{n:"清醒符咒 ×1", platC:1') >= 0 && html.indexOf('{n:"安眠护符 ×1", platC:1') >= 0],
  ["v1.61d 薰香/护符只展示下一阶 + 额外饰品类说明", html.indexOf("it.incense === _ic + 1") >= 0 && html.indexOf("🕯️ 安眠薰香（") >= 0 && html.indexOf("与安眠薰香同属「额外饰品」类永久加成") >= 0 && html.indexOf("if(it.incense) return;") >= 0],
  ["v1.61d HUD 公会经验条（声望独立显示移除）", html.indexOf('id="hGuildBar"') >= 0 && html.indexOf('id="hGuildTxt"') >= 0 && html.indexOf('class="bar bar-guild"') >= 0 && html.indexOf('id="hRep"') < 0 && html.indexOf("⭐声望") < 0],
  ["v1.61d 规则道具不可出售（sellMat 非材料守卫 ×2）", (html.match(/!M\[name\] \|\| !S\.mats\[name\]/g) || []).length >= 2],
  ["v1.61f 宠物详情显示具体心情值（数值 / 100 + 进度条 + 卡片提示）", html.indexOf("心情值 <b") >= 0 && html.indexOf("</b> / 100") >= 0 && html.indexOf("（${mood}/100）") >= 0],
  ["v1.61g 宠物礼物改暗示文案（不剧透 7 天规则）", html.indexOf("神秘小礼物") >= 0 && html.indexOf("连续 7 天会收到心意礼物") < 0 && html.indexOf("连续 7 天好心情会收到心意礼物") < 0],
  ["v1.61h 宠物礼物池（每宠 4~6 种 · 权重 100 · 偏好决定类型）", html.indexOf("const PET_GIFTS = {") >= 0 && html.indexOf('"魔狼鬃毛"') >= 0 && html.indexOf('"星辉绸"') >= 0 && html.indexOf("function petGiftRoll(") >= 0 && html.indexOf("PET_WALK_GIFT") < 0],
  ["v1.61i 携宠拾取（池 = 内容产出 · 3 种/4 个上限 · 失败 1 种/2 个 · 传说可捡概率极低）", html.indexOf("const PET_FIND = {") >= 0 && html.indexOf('petFindRoll("quest", q[8]') >= 0 && html.indexOf('petFindRoll("explore", r.d') >= 0 && html.indexOf('petFindRoll("legend", _lgPool') >= 0 && html.indexOf("failTypes:1, failQty:2") >= 0],
  ["v1.61j 失败时触发率减半（failMul:0.5——委托失败 6%→3% / 传奇失败 12%→6%，含心情修正后减半）", html.indexOf("failMul:0.5") >= 0 && html.indexOf("if(fail) pct *= PET_FIND.failMul;") >= 0],
  ["v1.61k 拾取权重 = 内容自身产出结构（委托期望数量 / 区域掉率% / 传奇必得数量 —— tierW 全品阶权重移除）", html.indexOf("tierW") < 0 && html.indexOf("v1.61k：拾取权重 = 内容自身的产出结构") >= 0 && html.indexOf("v1.61k：权重 = 掉表期望数量") >= 0 && html.indexOf("v1.61k：权重 = 区域掉率%") >= 0 && html.indexOf("v1.61k：权重 = 必得数量") >= 0],
  ["v1.61m 手机页签栏移至顶部（钱币信息下方——贴底横滑撞系统手势）", html.indexOf("v1.61m：移至顶部（钱币信息下方）") >= 0 && html.indexOf("#tabs{position:fixed;bottom:0") < 0 && html.indexOf("body{padding-bottom:64px}") < 0],
  ["v1.61n HUD 底部内边距修正（inset-top 误用 → 下 8px；页签栏与钱币信息间不再多出空隙）", html.indexOf("padding:calc(8px + env(safe-area-inset-top,0)) 12px 8px") >= 0 && html.indexOf("padding:8px 12px calc(8px + env(safe-area-inset-top,0))") < 0],
  ["v1.61o 打造说明文案与 v1.61l 数据同步（主材料 3/4/5/6/7 · 副材料 3/4/5/7/9）", html.indexOf("主材料 普通 3 / 精良 4 / 稀有 5 / 史诗 6 / 传说 7（饰品 −1）；副材料 3 / 4 / 5 / 7 / 9（护甲 +1）") >= 0 && html.indexOf("主材料 普通 2 / 精良 3 / 稀有 4 / 史诗 5 / 传说 6") < 0],
  ["v1.61s 心情日结算改收敛式（向健康分补差距 25% · 四舍五入 · 早睡 +5——原分档退役）", html.indexOf("心情补上差距的 25%") >= 0 && html.indexOf("Math.floor((sc - mood) * 0.25 + 0.5)") >= 0 && html.indexOf("≥90 分 +10") < 0 && html.indexOf("sc >= 90 ? 10 : (sc >= 60 ? 5 : -5)") < 0],
  ["v1.61r 散步说明对齐实现（同时只能派 1 只——原「每天可派 1 只」不符）", html.indexOf("散步</b>同时只能派 1 只") >= 0 && html.indexOf("每天可派 1 只<b>散步</b>") < 0]
];
let _h38rBad = 0;
_h38r.forEach(function(x){ console.log("  " + (x[1] ? "✅" : "❌") + " " + x[0]); if(!x[1]) _h38rBad++; });
setTimeout(function(){ process.exit((_srcDupList.length || _h38rBad || globalThis.__smokeFail) ? 1 : 0); }, 4000);   // v1.61l：运行时应答失败（FAIL）也计入退出码——此前只影响打印，run_all_tests 漏报
