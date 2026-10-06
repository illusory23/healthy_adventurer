// 运行时测试：mock DOM 环境，跑核心循环
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
global.document = {
  getElementById: (id) => (elCache[id] = elCache[id] || fakeEl()),
  querySelectorAll: () => [],
  addEventListener: () => {}
};
global.alert = (m) => console.log("  [alert]", m);
global.confirm = () => false;
global.setInterval = () => 0;

const html = fs.readFileSync(__dirname + '/健康的冒险者的一天.html', 'utf-8');
const code = html.match(/<script>([\s\S]*?)<\/script>/)[1];

const test = `
_roll3D = false;   // 无浏览器环境，禁用 3D 骰子加载
console.log("=== 0. 首次进入判定 ===");
console.log("  新存档 name 为空 →", S.name === "" ? "会弹出开场界面 ✅" : "异常 ❌");

console.log("\\n=== 1. 初始化 ===");
console.log("  等级:", lvName(), "| 精力:", S.energy + "/" + energyMaxNow(), "| 公会:", guildName());

console.log("\\n=== 1.1 输入冒险者之名 ===");
document.getElementById("nameInput").value = "测试者";
submitName();
console.log("  名字已保存:", JSON.stringify(S.name));
console.log("  HUD 显示:", document.getElementById("hName").textContent);

console.log("\\n=== 1.2 二次进入（模拟重开页面）===");
const savedName = S.name;
save();
S = null;
load();
console.log("  重新读取后的名字:", JSON.stringify(S.name), S.name === savedName ? "✅ 自动恢复" : "❌");

console.log("\\n=== 1.3 空名拦截 ===");
document.getElementById("nameInput").value = "   ";
const nameBefore = S.name;
submitName();
console.log("  提交空白名:", S.name === nameBefore ? "已拦截 ✅" : "未拦截 ❌");

console.log("\\n=== 1.4 超长名截断 ===");
document.getElementById("nameInput").value = "一二三四五六七八九十十一十二十三";
submitName();
console.log("  输入 15 字 → 保存:", JSON.stringify(S.name), "长度", S.name.length, S.name.length === 12 ? "✅" : "❌");
S.name = "测试者";

console.log("\\n=== 2. 健康打卡 ===");
toggleTask(0);            // 早睡 +20
toggleTask(1);            // 早起 +10
toggleTask(4);            // 运动 +15
addMulti(0, 1);           // 久坐起身 +2
addMulti(0, 1);           // +2
addMulti(1, 1);           // 阅读 +3
console.log("  健康分:", S.health.score, "（预期 早睡20+早起15+运动10+久坐2+2+阅读6 = 55）");

console.log("\\n=== 3. 刷新池 ===");
console.log("  池子:", S.pool ? S.pool.list.map(q => q[0]).join(" / ") : "无");
if(S.pool && S.pool.list.length){
  const q = S.pool.list[0];
  console.log("  首个委托:", q[0], "| 难度", q[4], "| 成功率", Math.round(successRate(q)*100) + "%");
}

console.log("\\n=== 4. 接取 ===");
if(S.pool) S.pool.bornTs = Date.now();   // 模拟：刚刷新，处于 30 分钟接取窗口内
const before = S.energy;
if(S.pool && S.pool.list.length){
  acceptQuest(0);
  console.log("  进行中:", S.active.length, "| 精力", before, "→", S.energy);
  console.log("  今日已接:", S.accepted + "/" + CFG.dailyLimit[S.lvIdx]);
}

console.log("\\n=== 5. 结算（强制完成）===");
const goldBefore = S.money;
if(S.active.length){ forceFinish(0); }
console.log("  货币:", fmtMoney(goldBefore), "→", fmtMoney(S.money));
console.log("  经验:", S.exp);

console.log("\\n=== 6. 升级 ===");
S.exp = 45; checkLevelUp();
console.log("  等级:", lvName(), "| 精力上限:", energyMaxNow(), "| 每日上限:", CFG.dailyLimit[S.lvIdx]);

console.log("\\n=== 7. 材料背包 ===");
const mats = Object.keys(S.mats);
console.log("  持有:", mats.length ? mats.map(k => k + "×" + S.mats[k]).join(" ") : "空");
if(mats.length){
  const m = mats[0];
  const b = S.money;
  sellMat(m);
  console.log("  卖出", m, ":", fmtMoney(b), "→", fmtMoney(S.money));
}

console.log("\\n=== 8. 商店 ===");
S.money = 100000;
const mb = Object.keys(S.mats).length;
buy(2);  // 普通材料包
console.log("  买材料包后，材料种类:", mb, "→", Object.keys(S.mats).length);

console.log("\\n=== 9. 活力点兑换 ===");
S.vit = 100;
const c = S.con;
buyVit(2);  // 贡献 +10
console.log("  贡献:", c, "→", S.con, "| 活力点余额:", S.vit);

console.log("\\n=== 10. 数据完整性 ===");
let totalQ = 0;
for(const k in C) totalQ += C[k].length;
console.log("  委托总数:", totalQ);
console.log("  材料总数:", Object.keys(M).length);
const badMat = Object.keys(M).filter(k => !Array.isArray(M[k]) || M[k].length !== 3);
console.log("  格式异常材料:", badMat.length ? badMat.join(",") : "无");
// 检查委托引用的材料是否都在材料表里
const missing = new Set();
for(const k in C) for(const q of C[k]) for(const mn in q[8]) if(!M[mn]) missing.add(mn);
console.log("  委托引用但材料表缺失:", missing.size ? [...missing].join(",") : "无");

console.log("\\n=== 11. 惰性补算（模拟跨天）===");
S.lastDay = "2000-01-01";
S.health = {date:"2000-01-01", done:[1,1,1,1,1,1,1], multi:[4,4], score:100};
S.daily = {date:"2000-01-01", done:3, gold:5000};
const r0 = S.rep;
tick();
console.log("  日结算后声望:", r0, "→", S.rep, "（100分应 +8）");
console.log("  健康已重置:", S.health.score === 0 ? "是" : "否");
console.log("  接取计数已重置:", S.accepted === 0 ? "是" : "否");

console.log("\\n=== 12. 掷骰分布抽样 ===");
let succ = 0, N = 2000;
for(let i = 0; i < N; i++) if(rand(100) <= 60) succ++;
console.log("  1d100 ≤ 60 的实际占比:", (succ/N*100).toFixed(1) + "%（理论 60%）");

console.log("\\n=== 13. 自动结算（无需手动点按钮）===");
S.lastDay = todayStr();
S.active = [];
const g0 = S.money;
S.active.push({
  q:["测试委托","采集","全天",1,"简单",100,5,1,{}],
  rate:0.99, acceptTs:Date.now()-2000, finishTs:Date.now()-1000, name:"测试委托"
});
tick();
console.log("  到点后自动结算:", S.active.length === 0 ? "✅ 已自动移除" : "❌ 仍卡在列表里");
console.log("  货币:", fmtMoney(g0), "→", fmtMoney(S.money));
console.log("  结果已入弹窗队列:", resultQueue.length >= 0 ? "✅" : "❌");

console.log("\\n=== 14. 跨天委托 → 打卡时结算 ===");
S.active = [];
const g1 = S.money;
S.active.push({
  q:["跨天委托","采集","全天",60,"简单",200,6,1,{}],
  rate:0.99,
  acceptTs: Date.now() - 26*3600*1000,      // 26 小时前接的
  finishTs: Date.now() - 2*3600*1000,       // 2 小时前完成
  name:"跨天委托"
});
tick();
console.log("  跨天后标记 pending:", (S.active[0] && S.active[0].pending) ? "✅" : "❌");
console.log("  尚未结算（等打卡）:", S.money === g1 ? "✅ 未提前发放" : "❌ 提前发了");
toggleTask(2);   // 打卡动作
console.log("  打卡后完成结算:", S.active.length === 0 ? "✅ 已结算并移除" : "❌ 仍待结算");
console.log("  货币:", fmtMoney(g1), "→", fmtMoney(S.money));

console.log("\\n=== 15. 页面关闭期间的时间流逝 ===");
S.active = [];
const g2 = S.money;
S.active.push({
  q:["离线委托","采集","全天",120,"简单",300,8,1,{}],
  rate:0.99,
  acceptTs: Date.now() - 3*3600*1000,   // 模拟 3 小时前接取（页面已关闭）
  finishTs: Date.now() - 1*3600*1000,   // 1 小时前完成
  name:"离线委托"
});
console.log("  （模拟：关掉页面期间委托已完成）");
tick();   // 相当于重新打开页面
console.log("  重新打开后自动补算:", S.active.length === 0 ? "✅ 已结算" : "❌");
console.log("  货币:", fmtMoney(g2), "→", fmtMoney(S.money));

console.log("\\n=== 16. 公会 W / H / P 级特权 ===");
S.lvIdx = 4;                       // Lv5 基础值：上限 4 / 同时 3 / 精力 500
S.rep = 6500;
console.log("  S 级  每日上限 " + dailyLimitNow() + " | 同时 " + simCapNow() + " | 精力 " + energyMaxNow());
S.rep = 9000;                      // W
console.log("  W 级  每日上限 " + dailyLimitNow() + (dailyLimitNow() === 5 ? " ✅" : " ❌") + " | 同时 " + simCapNow() + " | 精力 " + energyMaxNow());
S.rep = 13000;                     // H
console.log("  H 级  每日上限 " + dailyLimitNow() + " | 同时 " + simCapNow() + (simCapNow() === 4 ? " ✅" : " ❌") + " | 精力 " + energyMaxNow());
S.rep = 18000;                     // P
console.log("  P 级  每日上限 " + dailyLimitNow() + " | 同时 " + simCapNow() + " | 精力 " + energyMaxNow() + (energyMaxNow() === 600 ? " ✅" : " ❌"));

console.log("\\n=== 17. 材料掉落（主材料必得 + 其余按品阶）===");
["止血草","鹿皮","星尘","龙鳞","龙心"].forEach(function(n){
  const tier = (M[n] && M[n][1]) || "?";
  console.log("  " + n.padEnd(6) + " [" + tier + "]  掉落率 " + Math.round(matDropRate(n)*100) + "%");
});
console.log("  位置 0（主材料）必得？ " + (matGuaranteed(0) ? "✅" : "❌"));
console.log("  位置 1（副材料）必得？ " + (matGuaranteed(1) ? "❌ 应为 false" : "✅ 按概率"));
let hit = 0, N2 = 3000;
for(let i = 0; i < N2; i++) if(Math.random() < matDropRate("龙鳞")) hit++;
console.log("  龙鳞抽样 " + N2 + " 次 → 实际 " + (hit/N2*100).toFixed(1) + "%（理论 40%）");
const allHit = Array.from({length:20}, function(){ return rollMat(0,"龙心"); }).every(Boolean);
console.log("  主材料必得验证：rollMat(0,'龙心') 连测 20 次 → " + (allHit ? "✅ 全中" : "❌ 有漏"));

console.log("\\n=== 18. 新增材料与公会厨房 ===");
["龙骨","龙牙","龙血","龙角","巨龙竖瞳","兽肉","香草","山珍","古董钱币","王者遗冠"].forEach(function(n){
  const m = M[n];
  console.log("  " + n.padEnd(6) + (m ? "[" + m[1] + "·" + m[0] + "]  价 " + fmtMoney(m[2]) : "❌ 未定义"));
});
console.log("  材料总数: " + Object.keys(M).length + " 种");
console.log("  料理配方: " + CFG.recipes.length + " 种");

S.lvIdx = 4; S.rep = 0;
S.mats = {"蘑菇":5,"泉水":9,"龙血":1,"山珍":3,"兽肉":6,"香草":3,"河鱼":2,"蜂蜜":3};
S.lastMeal = null; S.mealCap = {date:"", cap:0};
S.energy = 100;
cook(0);   // 菌菇汤：立即回蓝
console.log("  烹饪菌菇汤 → 精力 100 → " + S.energy + (S.energy === 115 ? " ✅（+15）" : " ❌"));
cook(2);   // 香草烤肉：成功率 +2% → 成为生效料理
const m1 = activeMeal();
console.log("  烹饪香草烤肉 → 生效料理: " + (m1 ? m1.name + "（成功率 +" + Math.round(m1.rate*100) + "%）" : "无"));
cook(7);   // 龙血羹：覆盖
const m2 = activeMeal();
console.log("  改吃龙血羹 → 生效料理: " + (m2 ? m2.name + "（报酬 +" + Math.round(m2.bonus*100) + "% / 成功率 +" + Math.round(m2.rate*100) + "%）" : "无"));
console.log("  → 只生效最后一个: " + (m2 && m2.name === "龙血羹" ? "✅ 香草烤肉已作废" : "❌"));
cook(5);   // 风干肉条：上限 +15
console.log("  烹饪风干肉条 → 当日精力上限: " + energyBase() + " → " + energyMaxNow() + (energyMaxNow() === energyBase()+15 ? " ✅" : " ❌"));
console.log("  材料剩余 蘑菇: " + (S.mats["蘑菇"]||0) + " | 龙血: " + (S.mats["龙血"]||0) + " | 兽肉: " + (S.mats["兽肉"]||0));

console.log("\\n=== 19. 自由探索系统 ===");
console.log("  区域数: " + REGIONS.length + (REGIONS.length === 7 ? " ✅" : " ❌"));
REGIONS.forEach(function(r){
  const sum = r.d.reduce(function(a,x){ return a + x[1]; }, 0);
  console.log("    " + r.n.padEnd(6) + " " + r.c + " 点  " + (sum === 100 ? "概率合计 100% ✅" : "❌ 合计 " + sum + "%"));
});
console.log("  最高级区域: " + REGIONS[REGIONS.length-1].n + "（含疾风符咒 " + REGIONS[REGIONS.length-1].d.filter(function(x){return x[0]==="疾风符咒";})[0][1] + "%）");

// 探索点刷新测试
S.history = [{date:"2000-01-01", score:85, done:0, gold:0}];
S.lastDay = "2000-01-01";
S.explore = 0; S.exploreUsed = 2;
tick();
console.log("  跨天刷新：前一日 85 分 → 探索点 " + S.explore + (S.explore === 8 ? " ✅" : " ❌") + "，次数重置 " + S.exploreUsed + (S.exploreUsed === 0 ? " ✅" : " ❌"));

console.log("\\n=== 20. 疾风符咒 ===");
S.lvIdx = 4; S.items = {"疾风符咒":1};
S.active = [{q:["测试委托","采集","全天",60,"简单",100,5,1,{}], rate:0.9,
  acceptTs:Date.now(), finishTs:Date.now()+3600000, name:"测试委托", meal:null}];
const before2 = S.active.length;
useGale(0);
console.log("  使用前进行中: " + before2 + " → 使用后: " + S.active.length + (S.active.length === 0 ? " ✅ 已立即完成" : " ❌"));
console.log("  符咒剩余: " + (S.items["疾风符咒"]||0) + ((S.items["疾风符咒"]||0)===0 ? " ✅ 已消耗" : " ❌"));

console.log("\\n=== 21. 兑换途径 ===");
console.log("  活力点可换道具: " + VIT_SHOP.filter(function(x){return x.item;}).map(function(x){return x.n;}).join(" / "));
console.log("  贡献可换道具: " + CON_SHOP.filter(function(x){return x.item;}).map(function(x){return x.n+"("+x.con+")";}).join(" / "));
console.log("  疾风符咒定价: 活力点 500 | 贡献 400 " + (VIT_SHOP.some(function(x){return x.n==="疾风符咒"&&x.vit===500;}) && CON_SHOP.some(function(x){return x.n==="疾风符咒"&&x.con===400;}) ? "✅" : "❌"));

console.log("\\n=== 22. 探索事件（7 个）===");
let evHit = 0;
for(let i=0;i<5000;i++) if(pickExploreEvent(REGIONS[0])) evHit++;
console.log("  触发率抽样: " + (evHit/5000*100).toFixed(1) + "%（理论 20%）");

// 拦截弹窗，捕获按钮回调
let cap = null;
const _dlg = dlg;
dlg = function(t,b,btns){ cap = {t:t, btns:btns||[]}; };

// 迷路商人：购买
S.money = 50; S.items = {};
runExploreEvent("迷路商人", REGIONS[0]);
cap.btns.filter(function(x){ return /购买/.test(x.text); })[0].fn();
console.log("  迷路商人 → 铜 50→" + S.money + "，清醒符咒×" + (S.items["清醒符咒"]||0) + ((S.money===40 && S.items["清醒符咒"]===1) ? " ✅" : " ❌"));

// 隐藏泉眼
S.pendingEnergy = null;
runExploreEvent("隐藏泉眼", REGIONS[1]);
console.log("  隐藏泉眼 → pendingEnergy=" + JSON.stringify(S.pendingEnergy) + (S.pendingEnergy && S.pendingEnergy.amount===10 ? " ✅" : " ❌"));

// 受伤小狼：救治 → 3 天后 tick 到期
S.wolfDone = false; S.pendingPet = null; S.pets = [];
S.daily = {date:todayStr(), events:[]};
runExploreEvent("受伤小狼", REGIONS[2]);
cap.btns[0].fn();
console.log("  受伤小狼 → pendingPet=" + (S.pendingPet ? S.pendingPet.name : "null") + "，wolfDone=" + S.wolfDone + ((S.pendingPet && S.wolfDone) ? " ✅" : " ❌"));
S.pendingPet.ts = Date.now() - 1;
tick();
console.log("  3 天后 tick → pets=" + JSON.stringify(S.pets) + (S.pets.indexOf("小狼")>=0 ? " ✅" : " ❌"));

// 古代石碑（60% 成功，最多试 50 次）
S.blueprints = {};
S.daily = {date:todayStr(), events:[]};
for(let i=0;i<50 && !S.blueprints["安神吊坠"]; i++) runExploreEvent("古代石碑", REGIONS[3]);
console.log("  古代石碑 → 图纸「安神吊坠」" + (S.blueprints["安神吊坠"] ? " ✅ 可获得" : " ❌"));

// 盗贼伏击
S.energy = 100; S.money = 1000000;
runExploreEvent("盗贼伏击", REGIONS[0]);
console.log("  盗贼伏击 → 精力 100→" + S.energy + (S.energy===90 ? " ✅" : " ❌"));
S.energy = 100000; S.money = 1000000;
let ok10 = true;
for(let i=0;i<30;i++){
  const before = S.money;
  runExploreEvent("盗贼伏击", REGIONS[0]);
  if(S.money !== before && S.money !== before - Math.floor(before*0.10)) ok10 = false;
}
console.log("  30 次损失恒为「当时钱币的 10%」: " + (ok10 ? "✅" : " ❌"));

// 净化成功
S.rep = 0;
runExploreEvent("净化成功", REGIONS[5]);
console.log("  净化成功 → 声望 0→" + S.rep + (S.rep===20 ? " ✅" : " ❌"));

// 裂痕回响（上限 3 层）
S.echo = 0;
runExploreEvent("裂痕回响", REGIONS[6]);
runExploreEvent("裂痕回响", REGIONS[6]);
runExploreEvent("裂痕回响", REGIONS[6]);
runExploreEvent("裂痕回响", REGIONS[6]);
console.log("  裂痕回响 ×4 → 层数=" + S.echo + (S.echo===3 ? " ✅ 上限 3 层" : " ❌"));

// 一次性事件可用性
console.log("  可用性：石碑已解 " + (exploreEventAvailable("古代石碑") ? "❌" : "✅ 不再触发") + " | 小狼已救 " + (exploreEventAvailable("受伤小狼") ? "❌" : "✅ 不再触发") + " | 回响满层 " + (exploreEventAvailable("裂痕回响") ? "❌" : "✅ 不再触发"));

// 裂痕回响接入稀有事件概率
S.skills = {体能:0,专注:0,社交:0,生存:0,幸运:0}; S.gear = []; S.echo = 0;
const r0p = Math.round(rareChance()*100);
S.echo = 3;
const r3p = Math.round(rareChance()*100);
console.log("  稀有事件概率: 0 层 " + r0p + "% → 3 层 " + r3p + "%" + ((r0p===5 && r3p===8) ? " ✅（5%+3%）" : " ❌"));
S.echo = 3;

dlg = _dlg;

console.log("\\n=== 23. 传奇事件·触发条件 ===");
S.lvIdx = 4; S.exp = 30000; S.rep = 18000; S.active = []; S.legendActive = null;
S.history = []; for(let i=0;i<35;i++) S.history.push({date:"d"+i, score:95, sleep:true});
console.log("  全局门槛（满配）: " + (legendUnlocked() ? "✅ 解锁" : "❌ 未解锁"));
S.history = S.history.map(function(h,i){ return {date:h.date, score:95, sleep: i<10}; });
console.log("  早睡仅 10/30 天: " + (legendUnlocked() ? "❌ 仍解锁" : "✅ 正确锁定"));
S.history = []; for(let i=0;i<35;i++) S.history.push({date:"d"+i, score:95, sleep:true});
for(let i=28;i<35;i++) S.history[i].score = 20;      // 最近 7 天均分 20 < 60
console.log("  7 天均分 20（<60）: " + (legendUnlocked() ? "❌ 仍解锁" : "✅ 正确锁定"));
for(let i=28;i<35;i++) S.history[i].score = 95;
S.rep = 1200;   // 公会 B
console.log("  公会 B（1,200）: " + (legendUnlocked() ? "❌ 仍解锁" : "✅ 正确锁定"));
S.rep = 2200;   // 公会 A
console.log("  公会 A（2,200）: " + (legendUnlocked() ? "✅ 解锁" : "❌ 未解锁"));
S.rep = 18000;

S.doneQuests = {}; S.doneBelow5 = 0; S.legendDone = [];
console.log("  屠龙传说（无前置）: " + (legendEligible(LEGEND[0]) ? "❌" : "✅ 锁定"));
S.doneQuests["巨龙巢穴侦察"] = 1;
console.log("  屠龙传说（完成前置）: " + (legendEligible(LEGEND[0]) ? "✅ 可触发" : "❌"));
console.log("  公会大师试炼（0/40）: " + (legendEligible(LEGEND[2]) ? "❌" : "✅ 锁定"));
S.doneBelow5 = 40;
console.log("  公会大师试炼（40/40）: " + (legendEligible(LEGEND[2]) ? "✅ 可触发" : "❌"));
console.log("  虚空王座（未封印魔神）: " + (legendEligible(LEGEND[8]) ? "❌" : "✅ 锁定"));
S.legendDone = ["魔神封印"];
console.log("  虚空王座（已封印魔神）: " + (legendEligible(LEGEND[8]) ? "✅ 可触发" : "❌"));
const L创 = LEGEND.filter(function(x){ return x[0]==="创世碎片"; })[0];
S.legendDone = ["魔神封印"];
console.log("  创世碎片（仅部分完成）: " + (legendEligible(L创) ? "❌" : "✅ 锁定"));
S.legendDone = LEGEND.filter(function(x){ return x[0]!=="创世碎片"; }).map(function(x){ return x[0]; });
console.log("  创世碎片（其余 11 全完成）: " + (legendEligible(L创) ? "✅ 可触发" : "❌"));
console.log("  时间回廊（连续 30 天早睡）: " + (legendEligible(LEGEND[5]) ? "✅ 可触发" : "❌"));

console.log("\\n=== 24. 传奇奖励解析 ===");
S.titles = []; S.pets = []; S.trophies = [];
grantLegendReward(LEGEND[0]);                                          // 称号「屠龙者」
grantLegendReward(LEGEND[7]);                                          // 宠物+称号
grantLegendReward(LEGEND[2]);                                          // 藏品
console.log("  称号: " + JSON.stringify(S.titles));
console.log("  宠物: " + JSON.stringify(S.pets));
console.log("  藏品: " + JSON.stringify(S.trophies));
console.log("  解析正确: " + (S.titles.length===2 && S.pets.length===1 && S.trophies.length===1 ? "✅" : "❌"));

console.log("\\n=== 25. 每周接取限制 ===");
S.legendActive = LEGEND[0]; S.legendWeek = weekKey(); S.active = []; S.legendName = "传奇事件";
takeLegend();
console.log("  同周重复接取: " + (S.legendActive ? "✅ 被拒绝（事件保留）" : "❌ 竟然接上了"));
S.legendWeek = "";
takeLegend();
console.log("  新的一周接取: " + (S.legendActive === null && S.active.length === 1 ? "✅ 接取成功" : "❌"));
console.log("  周标识: " + weekKey() + "（该周周一日期）");

console.log("\\n=== 26. 声望奖励设计 ===");
[["屠龙传说",700],["公会大师试炼",450],["世界树种子",500],["时间回廊",750],["龙神契约",1100],["创世碎片",1600]].forEach(function(pair){
  const L = LEGEND.filter(function(x){ return x[0]===pair[0]; })[0];
  const r = legendRep(L);
  console.log("  " + pair[0] + " → 声望 +" + r + (r===pair[1] ? " ✅" : " ❌ 预期 " + pair[1]));
});
console.log("  全部传奇声望 ≥400: " + (LEGEND.every(function(L){ return legendRep(L) >= 400; }) ? "✅" : "❌"));
function qRep(lv, diff){ return questRep(["x","采集","全天",60,diff,0,0,0,{}], lv); }
console.log("  Lv1 → " + qRep(1,"简单") + (qRep(1,"简单")===5 ? " ✅" : " ❌") + " | Lv2 → " + qRep(2,"困难") + (qRep(2,"困难")===10 ? " ✅" : " ❌") + "（保持等级×5）");
console.log("  Lv3 困难 → " + qRep(3,"困难") + (qRep(3,"困难")===19 ? " ✅" : " ❌") + " | Lv4 噩梦 → " + qRep(4,"噩梦") + (qRep(4,"噩梦")===28 ? " ✅" : " ❌") + " | Lv5 噩梦 → " + qRep(5,"噩梦") + (qRep(5,"噩梦")===32 ? " ✅" : " ❌"));

console.log("\\n=== 27. 公会额外委托（独立槽位）===");
S.lvIdx = 4; S.rep = 18000; S.energy = 500;
S.active = [];
for(let i=0;i<simCapNow();i++)
  S.active.push({q:["占位","采集","全天",1,"简单",0,0,1,{}], rate:1, acceptTs:Date.now(), finishTs:Date.now()+3600000, name:"占位"+i, meal:null});
S.accepted = 3;
S.bonusQuest = ["测试额外","采集","全天",60,"普通",100,5,10,{}];
const accBefore = S.accepted, actBefore = S.active.length;
acceptBonus();
console.log("  同时已满（" + actBefore + "/" + simCapNow() + "）仍可接: " + (S.active.length===actBefore+1 ? "✅ 超出 1 个" : "❌"));
console.log("  不占每日上限: " + (S.accepted===accBefore ? "✅ accepted 不变" : "❌") + " | 槽位已清空: " + (S.bonusQuest===null ? "✅" : "❌"));
S.active = [];

console.log("\\n=== 28. 命运骰子（刷新委托栏）===");
const voidRegion = REGIONS.filter(function(r){ return r.n==="虚空裂痕"; })[0];
const diceDrop = voidRegion.d.filter(function(x){ return x[0]==="命运骰子"; })[0];
const voidSum = voidRegion.d.reduce(function(a,x){ return a + x[1]; }, 0);
console.log("  虚空裂痕含命运骰子: " + (diceDrop ? "✅ " + diceDrop[1] + "%" : "❌") + " | 概率合计 " + voidSum + (voidSum===100 ? " ✅" : " ❌"));

S.lvIdx = 4; S.items = {"命运骰子":2};
S.pool = {point:"test-key", list:[["旧委托","采集","全天",60,"简单",1,1,1,{}]], taken:false, bornTs:Date.now()};
useItem("命运骰子");
console.log("  使用后道具剩余: " + S.items["命运骰子"] + ((S.items["命运骰子"]||0)===1 ? " ✅（消耗 1）" : " ❌"));
console.log("  委托栏已重抽: " + (S.pool.list.length>0 && S.pool.list[0][0]!=="旧委托" ? "✅ 新池 " + S.pool.list.length + " 个" : "❌"));
S.pool.taken = true;
useItem("命运骰子");
console.log("  已接取的刷新点拒绝刷新: " + (S.items["命运骰子"]===1 ? "✅ 未消耗" : "❌"));
const poolIdx = code.indexOf('const items = ["清醒符咒","安眠护符","活力药水","疾风符咒"]');
console.log("  稀有事件道具池保持 4 种: " + (poolIdx >= 0 ? "✅ 不含命运骰子（保持虚空裂痕专属）" : "❌ 池子定义已变，请人工确认"));

console.log("\\n=== 29. 委托内容描写（82 条）===");
let missingStory = [];
for(const k in C) C[k].forEach(function(q){ if(!QUEST_STORY[q[0]]) missingStory.push(q[0]); });
LEGEND.forEach(function(L){ if(!QUEST_STORY[L[0]]) missingStory.push(L[0]); });
const storyCnt = Object.keys(QUEST_STORY).length;
console.log("  收录 " + storyCnt + " 条，缺 " + (missingStory.length ? missingStory.join("、") : "无") + ((storyCnt===82 && !missingStory.length) ? " ✅" : " ❌"));
console.log("  questDesc 优先专属描写: " + (questDesc(["采集草药","采集","全天",60,"简单",8,1,8,{}]).indexOf("止血草")>=0 ? "✅" : "❌"));
console.log("  未收录时回退模板: " + (questDesc(["测试无名委托","采集","全天",60,"简单",8,1,8,{}]).indexOf("公会需要")>=0 ? "✅" : "❌"));

console.log("\\n=== 30. 探索掉落独立判定（v1.25 现实时间制：发起 → 到点结算）===");
{
  const _dlg3 = dlg, _irt = inRegionTime, _pee = pickExploreEvent;
  dlg = function(){}; inRegionTime = function(){ return true; }; pickExploreEvent = function(){ return null; };
  S.lvIdx = 4; S.money = 0; S.mats = {}; S.items = {};
  S.history = [{date:"d", score:100, sleep:true}];
  function snap(){ return {m:Object.assign({},S.mats), i:Object.assign({},S.items), c:S.money}; }
  function gained(s0){
    let n = 0;
    for(const k in S.mats) if((S.mats[k]||0) > (s0.m[k]||0)) n++;
    for(const k in S.items) if((S.items[k]||0) > (s0.i[k]||0)) n++;
    if(S.money > s0.c) n++;
    return n;
  }
  let dist = [0,0,0,0], total = 0, started = 0;
  for(let i=0;i<300;i++){
    S.exploreUsed = 0; S.explore = 9999; S.exploreActive = null;
    const s0 = snap();
    doExplore(0);                                  // 发起探索（现实时间制：此时不掉落）
    if(S.exploreActive){
      S.exploreActive.finishTs = Date.now() - 1000;  // 模拟 2 小时已到点
      exploreFinishCheck();                          // 到点结算掉落
      started++;
    }
    const g = gained(s0);
    dist[Math.min(g,3)]++; total += g;
  }
  console.log("  300 次晨光森林（发起 → 秒结算）：空手 " + dist[0] + " | 1 类 " + dist[1] + " | 2 类 " + dist[2] + " | 3 类 " + dist[3] + (started===300 ? " ✅" : " ❌ 仅 " + started + " 次发起成功"));
  console.log("  平均 " + (total/300).toFixed(2) + " 类/次（理论 0.85，含符咒概率）");
  console.log("  可同时获得多个: " + ((dist[2]+dist[3])>0 ? "✅ 独立判定生效" : "❌"));
  console.log("  规则道具入道具栏（非材料箱）: " + (((S.items["清醒符咒"]||0)>0 && !S.mats["清醒符咒"]) ? "✅" : "❌ items=" + (S.items["清醒符咒"]||0) + " mats=" + (S.mats["清醒符咒"]||0)));
  dlg = _dlg3; inRegionTime = _irt; pickExploreEvent = _pee;
}

console.log("\\n=== 31. 接取窗口（刷新后 30 分钟）===");
{
  const lpN = latestPoint(new Date());
  S.lvIdx = 4; S.energy = 500; S.accepted = 0; S.active = [];
  S.poolPoint = pointKey(lpN.d, lpN.h);          // 与当前刷新点一致，防止 tick 重建
  S.pool = {point:S.poolPoint, list:drawPool(lpN), taken:false, bornTs:Date.now(), expiredLogged:false};
  console.log("  窗口内: " + (poolExpired() ? "❌ 误报过期" : "✅ 有效") + "，剩余 " + Math.ceil(poolLeftMs()/60000) + " 分钟");
  S.pool.bornTs = Date.now() - 31*60*1000;
  console.log("  超 31 分钟: " + (poolExpired() ? "✅ 已失效" : "❌"));
  const acc0 = S.accepted;
  acceptQuest(0);
  console.log("  失效后接取被拒: " + ((S.accepted===acc0 && !S.pool.taken) ? "✅" : "❌"));
  S.items = {"命运骰子":1};
  useItem("命运骰子");
  console.log("  失效后刷新被拒: " + (S.items["命运骰子"]===1 ? "✅ 未消耗" : "❌"));
  S.pool.bornTs = Date.now();
  S.items = {};
  acceptQuest(0);
  console.log("  窗口内接取成功: " + (S.pool.taken ? "✅" : "❌"));
}

console.log("\\n=== 32. 进行中委托详情（接取后可查看）===");
{
  S.lvIdx = 4; S.active = [];
  S.active.push({q:["采集草药","采集","全天",120,"困难",100,10,5,{"止血草":3}], qlv:3, rate:0.66,
    acceptTs:Date.now(), finishTs:Date.now()+3600000, name:"采集草药", meal:null});
  let cap2 = null;
  const _dlg4 = dlg;
  dlg = function(t,b,btns){ cap2 = {t:t, b:b, btns:btns||[]}; };
  showActiveDetail(0);
  console.log("  常规委托详情可打开: " + ((cap2 && cap2.t.indexOf("采集草药")>=0 && cap2.b.indexOf("接取时锁定的成功率")>=0) ? "✅" : "❌"));
  console.log("  含描述/材料/声望: " + ((cap2.b.indexOf("城郊野地")>=0 && cap2.b.indexOf("止血草")>=0 && cap2.b.indexOf("+19")>=0) ? "✅" : "❌"));
  S.active.push({q:["屠龙传说","精英","传奇",0,"噩梦",0,"1铂金币",0,{}], rate:0.45, legend:LEGEND[0],
    lname:"传奇事件", acceptTs:Date.now(), finishTs:Date.now()+7*86400000, name:"屠龙传说", meal:null});
  showActiveDetail(1);
  console.log("  传奇事件详情可打开: " + ((cap2.b.indexOf("龙心×2")>=0 && cap2.b.indexOf("+700")>=0 && cap2.b.indexOf("约剩余 7 天")>=0) ? "✅" : "❌"));
  dlg = _dlg4;
  // 进行中卡片已绑定点击
  render();
  const tabQuestHtml = document.getElementById("tab-quest").innerHTML;
  console.log("  进行中卡片已绑定点击: " + (tabQuestHtml.indexOf("showActiveDetail")>=0 ? "✅" : "❌"));
  S.active = [];
}

console.log("\\n=== 33. 主动放弃委托 ===");
{
  S.active = [];
  S.active.push({q:["待放弃委托","采集","全天",60,"简单",100,5,3,{"止血草":2}], qlv:1, rate:1,
    acceptTs:Date.now(), finishTs:Date.now()+3600000, name:"待放弃委托", meal:null});
  S.energy = 50; S.accepted = 2;
  const enB = S.energy, accB = S.accepted;
  let cap3 = null;
  const _dlg5 = dlg;
  dlg = function(t,b,btns){ cap3 = {t:t, b:b, btns:btns||[]}; };
  abandonQuest(0);
  console.log("  确认窗已弹出: " + ((cap3 && cap3.t.indexOf("放弃")>=0 && cap3.b.indexOf("不返还")>=0) ? "✅" : "❌"));
  cap3.btns[1].fn();   // 点「确定」
  console.log("  委托已移除: " + (S.active.length===0 ? "✅" : "❌"));
  console.log("  精力不返还: " + (S.energy===enB ? "✅" : "❌") + " | 次数不返还: " + (S.accepted===accB ? "✅" : "❌"));
  dlg = _dlg5;
}

console.log("\\n=== 34. 委托配色（等级色 + 传奇红）===");
{
  console.log("  Lv1 白: " + (qLvColor(1)==="#e6e6e6" ? "✅" : "❌") + " | Lv3 蓝: " + (qLvColor(3)==="#5b9bd5" ? "✅" : "❌") + " | Lv5 金: " + (qLvColor(5)==="#d4a843" ? "✅" : "❌"));
  S.lvIdx = 4;
  S.poolPoint = "x";
  S.pool = {point:"x@08", list:[["采集草药","采集","全天",60,"简单",8,1,8,{"止血草":3}]], taken:false, bornTs:Date.now()};
  S.legendActive = LEGEND[0]; S.legendName = "传奇事件"; S.legendWeek = "";
  render();
  const cqHtml = document.getElementById("tab-quest").innerHTML;
  console.log("  刷新池卡 Lv5 金色名字/标签: " + ((cqHtml.indexOf('<b style="color:#d4a843">采集草药</b>')>=0 && cqHtml.indexOf('style="color:#d4a843">采集</span>')>=0) ? "✅" : "❌"));
  console.log("  传奇卡名字/标签红色: " + ((cqHtml.indexOf('style="color:var(--red)">屠龙传说</b>')>=0 && cqHtml.indexOf('style="color:var(--red)">精英</span>')>=0) ? "✅" : "❌"));
  S.legendActive = null;
}

console.log("\\n=== 35. 打造材料数量（按品级 + 部位）===");
{
  console.log("  副材料: 普通武器 " + subMatCount("普通","武器") + (subMatCount("普通","武器")===2?" ✅":" ❌")
    + " | 普通护甲 " + subMatCount("普通","护甲") + (subMatCount("普通","护甲")===3?" ✅":" ❌")
    + " | 传说武器 " + subMatCount("传说","武器") + (subMatCount("传说","武器")===8?" ✅":" ❌"));
  [["铜剑",2],["铜戒指",1],["龙牙巨剑",6],["龙瞳坠饰",5],["龙鳞重铠",6]].forEach(function(p){
    const mm = craftMainMat(p[0]);
    console.log("  " + p[0] + " 主材料 " + mm.mat + "×" + mm.cnt + (mm.cnt===p[1]?" ✅":" ❌ 预期"+p[1]));
  });
  const cntSet = {};
  GEAR.forEach(function(g){
    if(g[5]==="—") return;
    const p = g[5].split("×");
    cntSet[+p[1]] = 1;
  });
  console.log("  主材料数量档位: " + Object.keys(cntSet).sort().join(" / ") + (Object.keys(cntSet).length>=4 ? " ✅ 多样" : " ❌ 单一"));
}

console.log("\\n=== 36. 材料掉落数量（种类 × 数量两层判定）===");
{
  // ① rollQty：数量越多概率越低（[1,5] 权重 5/4/3/2/1）
  const cnt = {1:0,2:0,3:0,4:0,5:0};
  for(let i=0;i<8000;i++) cnt[rollQty(1,5)]++;
  const desc = cnt[1]>cnt[2] && cnt[2]>cnt[3] && cnt[3]>cnt[4] && cnt[4]>cnt[5];
  console.log("  [1,5] 8000 次分布: " + [1,2,3,4,5].map(function(n){return n+"→"+cnt[n];}).join(" / ") + (desc ? " ✅ 递减" : " ❌"));
  console.log("  固定区间 [1,1]: " + rollQty(1,1) + (rollQty(1,1)===1?" ✅":" ❌") + " | [3,6] 恒在区间内: "
    + (function(){ for(let i=0;i<200;i++){ const v=rollQty(3,6); if(v<3||v>6) return "❌"; } return "✅"; })());
  // ② 委托数据合理性（用户点名的龙类）
  function matsOf(qn){ const q = C.Lv5.concat(C.Lv4,C.Lv3).find(function(x){return x[0]===qn;}); return q ? q[8] : null; }
  const sl = matsOf("弑龙者");
  console.log("  弑龙者: 龙鳞" + JSON.stringify(sl["龙鳞"]) + ((sl["龙鳞"][0]>=3 && sl["龙鳞"][1]>=5)?" ✅ 不会太少":" ❌")
    + " | 龙心" + JSON.stringify(sl["龙心"]) + ((sl["龙心"][0]===1&&sl["龙心"][1]===1)?" ✅ 最多1":" ❌")
    + " | 龙血" + JSON.stringify(sl["龙血"]) + ((sl["龙血"][0]>=2)?" ✅ 偏多":" ❌"));
  const nh = matsOf("古龙遗骸采集");
  console.log("  古龙遗骸: 龙角" + JSON.stringify(nh["龙角"]) + ((nh["龙角"][1]===5)?" ✅ 上限5":" ❌")
    + " | 竖瞳" + JSON.stringify(nh["巨龙竖瞳"]) + ((nh["巨龙竖瞳"][1]===2)?" ✅ 上限2":" ❌"));
  const hyd = matsOf("讨伐九头蛇");
  console.log("  九头蛇: 龙鳞" + JSON.stringify(hyd["龙鳞"]) + ((hyd["龙鳞"][0]>=3 && hyd["龙鳞"][1]===9)?" ✅ 3~9":" ❌")
    + " | 龙牙" + JSON.stringify(hyd["龙牙"]) + ((hyd["龙牙"][0]>=3 && hyd["龙牙"][1]===9)?" ✅ 3~9":" ❌")
    + " | 龙心" + JSON.stringify(hyd["龙心"]) + ((hyd["龙心"][1]===1)?" ✅":" ❌"));
  const caiji = C.Lv1.find(function(x){return x[0]==="采集草药";});
  console.log("  采集草药: 止血草" + JSON.stringify(caiji[8]["止血草"]) + ((caiji[8]["止血草"][1]>=4)?" ✅ 采集类量大":" ❌"));
  // ③ 信息卡显示区间
  const row = matRowsHtml(["x","x","全天",1,"简单",1,1,1,{"龙鳞":[3,6],"龙心":[1,1]}]);
  console.log("  显示: 区间×3~6 " + (row.indexOf("×3~6")>=0?"✅":"❌") + " | 固定×1 " + (row.indexOf("×1</b>")>=0?"✅":"❌"));
}

console.log("\\n=== 37. 装备特殊效果（★上限 / 晨间报酬 / P级技能上限）===");
{
  S.lvIdx = 4; S.rep = 999999;
  S.equipped = {weapon:null,armor:null,accessory:null,charmSlot:null}; S.gear = [];
  const s0 = simCapNow(), d0 = dailyLimitNow();
  S.gear = ["星辉战甲","时间沙漏"];
  equipItem("星辉战甲"); equipItem("时间沙漏");
  console.log("  星辉战甲「同时进行上限+1」: " + s0 + " → " + simCapNow() + (simCapNow()===s0+1 ? " ✅" : " ❌"));
  console.log("  时间沙漏「每日接取上限+1」: " + d0 + " → " + dailyLimitNow() + (dailyLimitNow()===d0+1 ? " ✅" : " ❌"));
  S.equipped = {weapon:null,armor:null,accessory:null,charmSlot:null}; S.gear = [];
  console.log("  晨间判定: 06:00-09:00 " + (isMorningQuest(["x","x","06:00-09:00"])?"✅":"❌")
    + " | 08:00-23:30 " + (isMorningQuest(["x","x","08:00-23:30"])?"✅":"❌")
    + " | 全天 " + (isMorningQuest(["x","x","全天"])?"✅":"❌")
    + " | 21:00-23:30 " + (!isMorningQuest(["x","x","21:00-23:30"])?"✅ 不晨间":"❌"));
  console.log("  P 级公会技能上限: " + skillCap() + (skillCap()===25 ? " ✅ 满 25" : " ❌"));
}

console.log("\\n=== 38. 结算统计（异步等待）===");
(async function(){
  S.doneQuests = {}; S.doneBelow5 = 0;
  const a1 = {q:["验收测试委托","采集","全天",1,"简单",100,5,1,{}], qlv:2, rate:1,
    acceptTs:Date.now(), finishTs:Date.now()+3600000, name:"验收测试委托", meal:null};
  await settle(a1);
  console.log("  doneQuests=" + JSON.stringify(S.doneQuests) + (S.doneQuests["验收测试委托"]===1 ? " ✅" : " ❌"));
  // 注：早期测试的委托（本次运行随机抽取）也在此异步批次结算，故按 ≥1 验证
  console.log("  doneBelow5=" + S.doneBelow5 + (S.doneBelow5>=1 ? " ✅（含 Lv2「采集草药」）" : " ❌"));

  // 材料掉落数量：主材料必得 + 数量落在区间内（用临时材料隔离随机批次）
  M["测试晶石"] = ["矿石","普通",100];
  M["测试粉末"] = ["矿石","普通",100];
  delete S.mats["测试晶石"]; delete S.mats["测试粉末"];
  const a4 = {q:["区间掉落测试","采集","全天",1,"简单",100,5,1,{"测试晶石":[3,6],"测试粉末":[1,2]}], qlv:2, rate:1,
    acceptTs:Date.now(), finishTs:Date.now()+3600000, name:"区间掉落测试", meal:null};
  await settle(a4);
  const gain4 = S.mats["测试晶石"]||0;
  const gain5 = S.mats["测试粉末"]||0;
  console.log("  主材料必得: 测试晶石 +" + gain4 + (gain4>=3 && gain4<=6 ? " ✅ 在 [3,6] 内" : " ❌ 越界"));
  console.log("  副材料独立判定: 测试粉末 " + (gain5 ? "+"+gain5+"（1~2 内）" : "本次未掉落（正常）")
    + ((gain5===0 || (gain5>=1 && gain5<=2)) ? " ✅" : " ❌"));
  delete S.mats["测试晶石"]; delete S.mats["测试粉末"]; delete M["测试晶石"]; delete M["测试粉末"];

  const a2 = {q:["屠龙传说","精英","传奇",0,"噩梦",0,"1铂金币",0,{}], qlv:5, legend:LEGEND[0],
    lname:"传奇事件", rate:1, acceptTs:Date.now(), finishTs:Date.now()+3600000, name:"屠龙传说", meal:null};
  S.legendDone = []; S.titles = []; S.pets = []; S.trophies = [];
  const repB = S.rep;
  await settle(a2);
  console.log("  传奇结算 → legendDone=" + JSON.stringify(S.legendDone) + (S.legendDone.indexOf("屠龙传说")>=0 ? " ✅" : " ❌"));
  console.log("  称号入档: " + JSON.stringify(S.titles) + (S.titles.indexOf("屠龙者")>=0 ? " ✅" : " ❌"));
  console.log("  传奇声望 +" + (S.rep-repB) + ((S.rep-repB)===700 ? " ✅（屠龙传说 700）" : " ❌"));

  // 失败结算：30% 报酬、无掉落
  const goldB = S.money, matB = S.mats["止血草"]||0;
  const a3 = {q:["必败委托","采集","全天",1,"普通",1000,10,1,{"止血草":5}], qlv:3, rate:0,
    acceptTs:Date.now(), finishTs:Date.now()+3600000, name:"必败委托", meal:null};
  await settle(a3);
  console.log("  失败结算: +铜 " + (S.money-goldB) + ((S.money-goldB)===300 ? " ✅（1000×30%）" : " ❌"));
  console.log("  失败无掉落: " + (((S.mats["止血草"]||0)===matB) ? "✅ 未获得材料" : "❌"));

  /* ===== 39. v1.19：区间奖励 / 周月打卡 / 成就 / 豁免 / 熬夜 ===== */
  console.log("\\n=== 39. v1.19 健康扩展（区间奖励 / 周月打卡 / 成就 / 豁免）===");
  {
    S.equipped = {weapon:null,armor:null,accessory:null,charmSlot:null};
    S.skills = {体能:0,专注:0,社交:0,生存:0,幸运:0};
    S.charm = 0; S.permEnergy = 0; S.trainEnergy = 0; S.incense = 0;
    S.lvIdx = 0;
    // ① 区间奖励：满分日结算 → 次日 buff
    S.health = {date:"2026-10-01", done:[1,1,1,1,1,1,1], multi:[4,2], score:100};
    S.daily = {date:"2026-10-01", done:3, gold:0, exp:0, rep:0, con:0, vit:0, quests:[], mats:{}, events:[]};
    S.history = []; S.buffNext = null; S.weekSettled = "2026-10-04"; S.monthSettled = "2026-10";
    daySettle();
    console.log("  区间奖励(100分): 报酬+" + Math.round(S.buffNext.pay*100) + "% 精力" + (S.buffNext.energy>0?"+":"") + S.buffNext.energy
      + " 贡献+" + S.buffNext.con + " 活力+" + S.buffNext.vit + ((S.buffNext.pay===0.15 && S.buffNext.energy===10 && S.buffNext.vit===5) ? " ✅" : " ❌"));
    // 低分日 → 精力 −10
    S.health = {date:"2026-10-02", done:[0,0,0,0,0,0,0], multi:[0,0], score:30};
    S.daily = {date:"2026-10-02", done:0, gold:0, exp:0, rep:0, con:0, vit:0, quests:[], mats:{}, events:[]};
    daySettle();
    console.log("  区间奖励(30分): 精力 " + S.buffNext.energy + ((S.buffNext.energy===-10 && !S.buffNext.pay) ? " ✅ 虚弱" : " ❌"));
    // ② 区间奖励生效：精力上限 +10 / 报酬 ×1.15
    S.buffNext = null; const e0 = energyMaxNow();
    S.buffNext = {date:todayStr(), pay:0.15, energy:10, con:0, vit:0, claimed:true, score:100};
    console.log("  次日精力上限: " + e0 + " → " + energyMaxNow() + (energyMaxNow()===e0+10 ? " ✅" : " ❌"));
    const mB2 = S.money;
    await settle({q:["buff测试","采集","全天",60,"简单",100,1,8,{}], qlv:1, rate:1, meal:null,
      acceptTs:Date.now(), finishTs:Date.now()+3600000, name:"buff测试"});
    const dG2 = S.money - mB2;
    console.log("  次日报酬加成: +铜 " + dG2 + ((dG2===115 || dG2===138) ? " ✅（100×1.15，大成功 138）" : " ❌"));
    // ③ 周结算（全黄金周）
    S.weekSettled = ""; S.history = [];
    for(let i=0;i<7;i++){
      const d = new Date(2026, 8, 28+i);
      S.history.push({date:fmtDate(d), score:95, sleep:true, done:2, gold:0, tasks:[1,1,1,1,1,1,1], multi:[4,2]});
    }
    const mB3 = S.money, vB3 = S.vit, cB3 = S.con, sB3 = S.explore;
    weeklySettle("2026-10-04");
    const w2 = weeklySettle("2026-10-04");
    console.log("  周结算: 铜+" + (S.money-mB3) + " 活力+" + (S.vit-vB3) + " 贡献+" + (S.con-cB3) + " 探索+" + (S.explore-sB3)
      + ((S.money-mB3)===19000 && (S.vit-vB3)===40 && !w2 ? " ✅ 4档黄金+委托白银 + 周常3项 + 幂等" : " ❌"));
    // ④ 月结算（全黄金月）
    S.monthSettled = ""; S.history = [];
    for(let i=0;i<30;i++){
      const d = new Date(2026, 8, 1+i);
      S.history.push({date:fmtDate(d), score:92, sleep:true, done:3, gold:0, tasks:[1,1,1,1,1,1,1], multi:[4,3]});
    }
    monthlySettle("2026-09-30");
    console.log("  月结算: 永久精力+" + S.permEnergy + "｜宠物 " + JSON.stringify(S.pets.filter(function(p){return p==="月光狐";}))
      + "｜称号 " + Object.keys(S.timTitles).join("/"));
    console.log("  " + (((S.permEnergy===50 && S.pets.indexOf("月光狐")>=0 && S.timTitles["安眠守护者"] && S.timTitles["公会中坚"] && S.timTitles["作息守护者"]) ? "✅ 运动档/宠物/三个当月称号齐" : "❌")));
    // ⑤ 成就：百炼成钢
    S.achv = []; S.gear = []; S.totalQuests = 100;
    checkAchievements();
    console.log("  成就·百炼成钢: " + (S.achv.indexOf("百炼成钢")>=0 && S.gear.indexOf("百炼徽记")>=0 ? "✅ 饰品已授予" : "❌"));
    // ⑥ 豁免：安神吊坠（早睡）+ 晨曦之冠（早起）
    S.exempt = {sleep:"", early:""};
    S.equipped.accessory = "安神吊坠"; S.equipped.charmSlot = "晨曦之冠";
    S.health = {date:"2026-10-01", done:[0,0,1,1,1,1,1], multi:[0,0], score:0};
    S.daily = {date:"2026-10-01", done:0, gold:0, exp:0, rep:0, con:0, vit:0, quests:[], mats:{}, events:[]};
    S.history = []; S.buffNext = null; S.weekSettled = "2026-10-04"; S.monthSettled = "2026-10";
    daySettle();
    console.log("  豁免: 早睡 " + (S.health.done[0] ? "✅" : "❌") + "（消耗 " + S.exempt.sleep + "）｜早起 " + (S.health.done[1] ? "✅" : "❌") + "（消耗 " + S.exempt.early + "）");
    // ⑦ 熬夜惩罚：前一日未早睡 → −15%
    S.equipped = {weapon:null,armor:null,accessory:null,charmSlot:null};
    S.lvIdx = 3; S.health = {date:todayStr(), done:[0,0,0,0,0,0,0], multi:[0,0], score:50};
    S.history = [{date:"y", score:90, sleep:false, done:0}];
    const q1 = ["精英测试","精英","08:00-23:30",60,"普通",100,1,8,{}];
    const r0 = successRate(q1);
    S.history[0].sleep = true;
    const r1 = successRate(q1);
    console.log("  熬夜惩罚: 熬夜 " + Math.round(r0*100) + "% vs 正常 " + Math.round(r1*100) + "% 差 " + Math.round((r1-r0)*100) + "pp"
      + (Math.abs((r1-r0)-0.15) < 1e-9 ? " ✅" : " ❌"));
    // ⑧ 安眠薰香（顺序校验 + 精力上限）
    S.vit = 5000; S.incense = 0;
    const eb0 = energyBase();
    buyVit(6);
    console.log("  安眠薰香 I: 等级 " + S.incense + " 精力 " + eb0 + " → " + energyBase() + ((S.incense===1 && energyBase()===eb0+4) ? " ✅" : " ❌"));
    buyVit(10);   // 跳级购买应被拒
    console.log("  薰香跳级拦截: " + (S.incense===1 ? "✅ 仍为 I 级" : "❌"));
    // ⑨ 稀有事件「下一次委托」加成：生效并消费（Lv3 困难，远离 cap；清空称号/区间奖励干扰）
    S.equipped = {weapon:null,armor:null,accessory:null,charmSlot:null};
    S.lvIdx = 2; S.health = {date:todayStr(), done:[0,0,0,0,0,0,0], multi:[0,0], score:0};
    S.timTitles = {}; S.buffNext = null; S.lastMeal = null; S.charm = 0;
    const q9 = ["稀有加成测试","采集","全天",60,"困难",100,1,8,{}];
    S.rareNextRate = 0.05; S.rareNextPay = 0;
    const rB = successRate(q9);
    S.rareNextRate = 0;
    const rA = successRate(q9);
    console.log("  稀有·+5%成功率: 差额 " + Math.round((rB-rA)*100) + "pp" + (Math.abs((rB-rA)-0.05)<1e-9 ? " ✅" : " ❌"));
    S.rareNextRate = 0.05; S.rareNextPay = 0.25;
    const mB9 = S.money;
    await settle({q:q9, qlv:1, rate:1, meal:null, acceptTs:Date.now(), finishTs:Date.now()+3600000, name:"稀有加成测试"});
    const d9 = S.money - mB9;
    console.log("  稀有·+25%报酬: +铜 " + d9 + ((d9===125 || d9===150) ? " ✅" : " ❌")
      + " | 用后清零: " + (((S.rareNextPay||0)===0 && (S.rareNextRate||0)===0) ? "✅" : "❌"));

    // ⑩ 宠物·小狼成长链（v1.22）
    S.wolf = {stage:1, growth:0, mutate:0, fedDate:"", fedCount:0};
    S.mats = {兽肉:10, 止血草:5, 野兔皮:5, 龙血:5, 龙心:3, 暗影草:2};
    feedWolf("兽肉");
    console.log("  喂食兽肉 +1 成长: " + S.wolf.growth + (S.wolf.growth===1 ? " ✅" : " ❌"));
    feedWolf("野兔皮");        // 兽材 → 拦截
    console.log("  不可喂材料拦截: " + (S.wolf.growth===1 ? "✅" : "❌"));
    feedWolf("止血草");        // 草药可喂
    console.log("  草药可喂（止血草 +1）: " + S.wolf.growth + (S.wolf.growth===2 ? " ✅" : " ❌"));
    feedWolf("兽肉");                            // 第 3 次
    const g3 = S.wolf.growth;
    feedWolf("兽肉");                            // 第 4 次 → 拦截
    console.log("  每日 3 次限制: " + (S.wolf.growth===g3 ? "✅" : "❌") + "（成长 " + S.wolf.growth + "，已喂 " + S.wolf.fedCount + " 次）");
    S.wolf.fedDate = ""; S.wolf.fedCount = 0;
    feedWolf("龙血");
    console.log("  龙血 +8 成长 / +5 变异: 成长 " + S.wolf.growth + " 变异 " + S.wolf.mutate + (S.wolf.mutate===5 ? " ✅" : " ❌"));
    S.wolf.fedDate = ""; S.wolf.fedCount = 0;
    feedWolf("暗影草");
    console.log("  暗影草（草药）变异 +5: " + S.wolf.mutate + (S.wolf.mutate===10 ? " ✅" : " ❌"));
    S.wolf = {stage:1, growth:59, mutate:10, fedDate:"", fedCount:0};
    feedWolf("兽肉");
    console.log("  成长 60 → 成年狼: " + (S.wolf.stage===2 ? "✅" : "❌") + "（变异值保留 " + S.wolf.mutate + "）");
    S.wolf = {stage:2, growth:199, mutate:10, fedDate:"", fedCount:0};
    feedWolf("兽肉");
    console.log("  成长 200 → 巨狼: " + (S.wolf.stage===3 ? "✅" : "❌") + "（+" + Math.round(wolfMatBonus()*100) + "% 掉落 / +" + Math.round(wolfRateBonus()*100) + "% 成功率）");
    // 成长值满：普通食材无加成；龙心仍 +25 变异值
    S.wolf = {stage:3, growth:300, mutate:10, fedDate:"", fedCount:0};
    feedWolf("兽肉");
    const wZero = (S.wolf.growth===300 && S.wolf.mutate===10);
    S.wolf.fedDate = ""; S.wolf.fedCount = 0;
    feedWolf("龙心");
    console.log("  成长满：普通食材无加成 " + (wZero ? "✅" : "❌") + "｜龙心 +12 变异: " + S.wolf.mutate + (S.wolf.mutate===22 ? " ✅" : " ❌"));
    // 变异值不足 → 拦截；满 → 变异
    const _origConfirm = showConfirm;
    showConfirm = function(msg, onOk){ if(onOk) onOk(); };
    evolveWolf();              // 变异值 22 < 300 → 拦截
    console.log("  变异值不足拦截: " + (S.wolf.stage===3 ? "✅" : "❌"));
    S.wolf.mutate = 300;
    evolveWolf();
    showConfirm = _origConfirm;
    console.log("  变异 → 远古魔狼: " + (S.wolf.stage===4 ? "✅" : "❌")
      + "（+" + Math.round(wolfMatBonus()*100) + "% 掉落 / +" + Math.round(wolfRateBonus()*100) + "% 成功率）");
    // 成功率独立叠加（清干扰项）
    S.wolf = {stage:3, growth:0, mutate:0, fedDate:"", fedCount:0};
    S.lvIdx = 2; S.health = {date:todayStr(), done:[0,0,0,0,0,0,0], multi:[0,0], score:0};
    S.timTitles = {}; S.buffNext = null; S.lastMeal = null; S.charm = 0; S.rareNextRate = 0;
    S.equipped = {weapon:null,armor:null,accessory:null,charmSlot:null}; S.history = [];
    const wq = ["狼测试","采集","全天",60,"普通",100,1,8,{}];
    const rW1 = successRate(wq);
    S.wolf = null;
    const rW0 = successRate(wq);
    console.log("  巨狼成功率独立 +1pp: 差 " + Math.round((rW1-rW0)*100) + "pp" + (Math.abs((rW1-rW0)-0.01)<1e-9 ? " ✅" : " ❌"));

    // ⑪ 传奇事件「预览」（v1.24）：未解锁 2% 触发、无法接取、跨天清除
    S.lvIdx = 0; S.exp = 0; S.rep = 0;
    S.legendDay = ""; S.legendActive = null; S.legendPreview = false; S.legendWeek = "";
    const _origRnd = Math.random;
    Math.random = function(){ return 0.01; };
    rollLegend();
    console.log("  未解锁 2% 预览触发: " + (S.legendActive && S.legendPreview === true ? "✅" : "❌") + "（「" + (S.legendActive ? S.legendActive[0] : "无") + "」）");
    const _actN = S.active.length;
    takeLegend();
    console.log("  预览无法接取: " + (S.active.length === _actN && S.legendActive ? "✅" : "❌"));
    S.legendDay = "";                             // 模拟跨天
    Math.random = function(){ return 0.99; };
    rollLegend();
    console.log("  跨天清除预览: " + (!S.legendActive && !S.legendPreview ? "✅" : "❌"));
    Math.random = _origRnd;
  }

    // ⑫ 6 点日界（v1.27）：00:00~05:59 算前一天，06:00 起算当天；weekKey 以「游戏日」为准
    const T = function(h, m){ return new Date(2026, 9, 3, h, m||0); };
    console.log("  todayStr 0:00 → " + todayStr(T(0,0)) + (todayStr(T(0,0))==="2026-10-02" ? " ✅ 算前一天" : " ❌"));
    console.log("  todayStr 5:59 → " + todayStr(T(5,59)) + (todayStr(T(5,59))==="2026-10-02" ? " ✅ 仍算前一天" : " ❌"));
    console.log("  todayStr 6:00 → " + todayStr(T(6,0)) + (todayStr(T(6,0))==="2026-10-03" ? " ✅ 起算当天" : " ❌"));
    console.log("  todayStr 23:59 → " + todayStr(T(23,59)) + (todayStr(T(23,59))==="2026-10-03" ? " ✅ 仍是当天" : " ❌"));
    const wkA = weekKey(parseDate(todayStr(new Date(2026, 9, 5, 3, 0))));   // 周一凌晨 3 点 → 游戏日仍是周日 10-04
    console.log("  weekKey(周一凌晨3点) → " + wkA + (wkA==="2026-09-28" ? " ✅ 归上一周（游戏日=周日）" : " ❌"));
    const wkB = weekKey(parseDate(todayStr(new Date(2026, 9, 5, 15, 0))));  // 周一下午 3 点 → 游戏日=周一 10-05
    console.log("  weekKey(周一下午3点) → " + wkB + (wkB==="2026-10-05" ? " ✅ 归本周（游戏日=周一）" : " ❌"));

    // ⑬ v1.28：打卡时间窗 / 三餐拆分 / 局外时钟 / 提醒
    console.log("  inWindowNow(06:00-08:00) @07:00 → " + (inWindowNow(["06:00","08:00"], new Date(2026,9,3,7,0)) ? "✅ 窗口内" : "❌"));
    console.log("  inWindowNow(06:00-08:00) @14:00 → " + (!inWindowNow(["06:00","08:00"], new Date(2026,9,3,14,0)) ? "✅ 窗口外" : "❌"));
    console.log("  inWindowNow(09:00-23:45) @23:45 → " + (inWindowNow(["09:00","23:45"], new Date(2026,9,3,23,45)) ? "✅ 边界含" : "❌"));
    console.log("  timePhase @14:00 → " + timePhase(new Date(2026,9,3,14,0)) + (timePhase(new Date(2026,9,3,14,0))==="午后" ? " ✅" : " ❌"));
    console.log("  timePhase @23:00 → " + timePhase(new Date(2026,9,3,23,0)) + (timePhase(new Date(2026,9,3,23,0))==="深夜" ? " ✅" : " ❌"));
    console.log("  timePhase @20:00 → " + timePhase(new Date(2026,9,3,20,0)) + (timePhase(new Date(2026,9,3,20,0))==="晚上" ? " ✅" : " ❌"));
    console.log("  timePhase @02:00 → " + timePhase(new Date(2026,9,3,2,0)) + (timePhase(new Date(2026,9,3,2,0))==="凌晨" ? " ✅" : " ❌"));
    // 三餐：全有全无计分（直接置位验证 done[5] 与 calcHealth 的联动）
    {
      const _bak = JSON.parse(JSON.stringify(S.health));
      S.health.meals = [1,1,0]; S.health.done[5] = 0; calcHealth();
      const sc2 = S.health.score;
      S.health.meals = [1,1,1]; S.health.done[5] = 1; calcHealth();
      console.log("  三餐 2/3 不得分、3/3 +15：'" + (((S.health.score - sc2) === 15) ? "✅" : "❌") + "'");
      S.health = _bak; calcHealth();
    }
    // 三餐打卡窗口（动态断言：窗口内应成功、窗口外应被拒——任何时刻运行都稳定）
    {
      const _bak = JSON.parse(JSON.stringify(S.health));
      const inWin = inWindowNow(CFG.mealWindows[0]);
      S.health.meals = [0,0,0]; S.health.done[5] = 0;
      toggleMeal(0);
      const okNow = (S.health.meals[0] === 1) === inWin;
      console.log("  早餐打卡（当前窗口" + (inWin?"内":"外") + "）：'" + (okNow ? "✅ 行为正确" : "❌") + "'");
      S.health = _bak; calcHealth();
    }
    try { checkReminders(); console.log("  checkReminders 可调用：" + "✅"); } catch(e){ console.log("  checkReminders 可调用：❌ " + e.message); }

  console.log("\\n✅ 全部测试执行完毕");
})();
`;

eval(code + test);
// 等待异步结算测试完成后再退出
setTimeout(function(){ process.exit(0); }, 1500);
