// 创造模式冒烟测试：node _smoke_creator.js
// 加载 主块 + 创造块（模拟浏览器顺序），在 fakeEl 环境下验证创造面板与全部一键功能
const fs = require('fs');

global.localStorage = {
  _d: {},
  getItem(k){ return this._d[k] || null; },
  setItem(k, v){ this._d[k] = v; },
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

const html = fs.readFileSync(__dirname + '/健康的冒险者的一天.html', 'utf-8');
const main = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const creator = html.match(/<script id="creator-mode">([\s\S]*?)<\/script>/);
if(!creator){
  console.log('❌ 未找到创造模式 script 块（<script id="creator-mode">）');
  process.exit(1);
}

const test = `
const __R = { pass: 0, fail: 0, msgs: [] };
const ck = (cond, msg) => { if(cond) __R.pass++; else { __R.fail++; __R.msgs.push(msg); } };

/* 初始化（模拟新档） */
S = migrate(newState());
S.name = "创造测试";

/* 面板渲染 */
renderCreator();
ck((document.getElementById("tab-creator").innerHTML || "").indexOf("创造模式") >= 0, "renderCreator 渲染面板");

/* 一键：全部拉满 */
creMaxAll();
ck(S.lvIdx === CFG.levels.length - 1, "全部拉满：满级");
ck(S.money >= 99999999, "全部拉满：满钱");
ck(Object.keys(M).every(k => S.mats[k] === 99), "全部拉满：全材料 99");
ck(S.pets.indexOf("小狼") >= 0 && S.pets.indexOf("月光狐") >= 0, "全部拉满：宠物加入");
ck(S.pets.indexOf("星界幼龙") >= 0 && S.pets.indexOf("深渊之眼") >= 0, "全部拉满：传奇固定宠物加入");   // v1.51b
ck(S.petData["月光狐"].stage === 4, "全部拉满：宠物四阶");
ck(S.wolf && S.wolf.stage === 4, "全部拉满：小狼四阶");
ck(S.skills["体能"] === 5, "全部拉满：技能满");
ck(S.charm === CHARM.length, "全部拉满：护符满");
ck(S.blueprints["猎弓"] === true, "全部拉满：图纸全掌握");
ck(S.titles.indexOf("博物学家") >= 0 && S.titles.indexOf("传说冒险者") >= 0, "全部拉满：图鉴集齐称号");
ck(S.achv.length > 0 && S.gear.length >= GEAR.length - 1, "全部拉满：成就与装备");

/* v1.56：宠物情感系统（创造模式拉满补字段 + 原型层函数可用） */
ck(S.petData["月光狐"].mood === 100 && S.petData["月光狐"].gotDate === "2025-01-01"
   && S.petData["月光狐"].bondDone.length === 4 && S.walkCount === 10,
   "v1.56：拉满补心情/羁绊/散步字段");
ck(S.wolf && S.wolf.mood === 100 && S.wolf.bondDone.length === 4, "v1.56：小狼心情/羁绊字段");
ck(typeof petMetaOf === "function" && typeof petMoodDaily === "function"
   && typeof petPat === "function" && typeof petWalkStart === "function"
   && typeof petTheater === "function" && typeof setPetNick === "function"
   && typeof renderPet === "function" && typeof gotoPetTab === "function",
   "v1.56：情感系统函数齐全（原型层）");
ck(petMetaOf("月光狐") && petMetaOf("月光狐").mood === 100, "v1.56：petMetaOf 读取拉满心情");
renderPet();
ck((document.getElementById("tab-pet").innerHTML || "").indexOf("🐾 宠物") >= 0, "v1.56：宠物页渲染");
ck((document.getElementById("tab-pet").innerHTML || "").indexOf("抚摸") >= 0, "v1.56：宠物卡含互动按钮");
const _b56 = petBondDays("月光狐");
ck(_b56 >= 100, "v1.56：拉满羁绊天数 ≥100（" + _b56 + "）");
ck(ACHV.length === 20, "v1.56：成就表 20 条");

/* 一键：今日打卡全勾 */
creTodayDone();
ck(S.health.done.every(x => x === 1) && S.health.score > 0, "今日打卡全勾 → 健康 " + S.health.score + " 分");

/* 材料 / 道具 / 装备 */
S.mats = {}; S.seenMats = [];
creMat("松木", 10);
ck(S.mats["松木"] === 10 && S.seenMats.indexOf("松木") >= 0, "creMat：+10 与图鉴记录");
creItem("清醒符咒", 5);
ck(S.items["清醒符咒"] === 5, "creItem：+5");
S.gear = [];
creGear("猎弓", 1);
ck(S.gear.indexOf("猎弓") >= 0, "creGear：放入背包");
creEquip("猎弓", "武器");
ck(S.equipped.weapon === "猎弓", "creEquip：装备到武器槽");

/* 宠物单点操作（先清掉 creMaxAll 的进度，验证「获得」路径） */
S.pets = S.pets.filter(x => x !== "绒球兽");
delete S.petData["绒球兽"];
crePetGet("绒球兽");
ck(S.pets.indexOf("绒球兽") >= 0 && S.petData["绒球兽"].stage === 1, "crePetGet：获得宠物");
crePetSet("绒球兽", "stage", 3);
ck(S.petData["绒球兽"].stage === 3, "crePetSet：改阶段");

/* 图鉴宠物节（v1.51b）+ 装备补全（v1.52）+ v1.57 种族链 + v1.58 六域遗珍 + v1.59 弱出口补全：全图鉴解锁 → 477 / 477 */
S.pets = []; S.petData = {}; S.wolf = null;
creGalleryAll();
renderGallery();
const _galPet = document.getElementById("tab-gallery").innerHTML || "";
ck(_galPet.indexOf("477 / 477") >= 0, "图鉴全解锁：477 / 477（含 v1.58 新增 6 材料 / 7 装备 / 4 料理 + v1.59 新增 3 装备）");
ck(_galPet.indexOf("🐾 宠物") >= 0 && _galPet.indexOf("星界幼龙") >= 0 && _galPet.indexOf("捣蛋鬼") >= 0, "图鉴宠物节：固定宠物与养成线入册");
/* 小狼：已养（S.wolf 四阶）时显示当前形态名 */
S.wolf = {stage: 4, growth: 0, mutate: 0};
renderGallery();
const _galWolf = document.getElementById("tab-gallery").innerHTML || "";
ck(_galWolf.indexOf("远古魔狼") >= 0, "图鉴宠物节：小狼显示当前形态「远古魔狼」");

/* 日期工具 */
creSetCreated(true);
ck(S.created === fmtDate(new Date(parseDate(todayStr()).getTime() - 30 * 86400000)), "创建日设为 30 天前");
const _h0 = S.history.length;
creAddHist(7, true);
ck(S.history.length === _h0 + 7 && S.history[S.history.length - 1].sleep === true, "追加 7 天早睡历史");
creDelHist(7);
ck(S.history.length === _h0, "删除最近 7 天历史");

/* 模拟节日 */
delete FESTIVALS[todayStr().slice(5)];
creFest();
ck(!!FESTIVALS[todayStr().slice(5)], "模拟节日：写入今日");
delete FESTIVALS[todayStr().slice(5)];

/* 重放昨日结算 → lastDay 归位今天 */
creReplay();
ck(S.lastDay === todayStr(), "重放昨日结算：lastDay 归位");

/* 高级 JSON 往返 */
S.exp = 4321;
creJsonLoad();
ck((document.getElementById("creJson").value || "").length > 10, "JSON 载入");
creJsonApply();
ck(S.exp === 4321, "JSON 应用往返");

/* 基础数值：fakeEl 下 input 为空 → 保持原值 */
const _m0 = S.money;
creApplyBasic();
ck(S.money === _m0 && S.name === "创造测试", "无输入时基础数值保持");

/* 当日打卡编辑 */
S.health = {date: todayStr(), done: [0,0,0,0,0,0,0], multi: [0,0], score: 0, meals: [0,0,0]};
creToggleDone(0, true);
ck(S.health.done[0] === 1 && S.health.score === 20, "creToggleDone：勾早睡 → 20 分");
creSetMulti(0, {value: "3"});
ck(S.health.multi[0] === 3 && S.health.score === 26, "creSetMulti：久坐 3 次 ×2 分 → 26 分");
creToggleMeal(0); creToggleMeal(1); creToggleMeal(2);
ck(S.health.meals.every(x => x) && S.health.done[5] === 1, "creToggleMeal：三餐全点 → 联动「完整吃三餐」");
creClearToday();
ck(S.health.score === 0 && S.health.done[5] === 0 && S.health.meals.every(x => !x), "creClearToday：全部清空");

/* 状态与杂项 */
S.active = [{name: "采集草药", q: C["Lv1"][0], rate: 1.0, acceptTs: Date.now(), finishTs: Date.now() + 3600000}];
creFinishActive();
ck(S.active.length === 0, "creFinishActive：立即完成并结算");
/* v1.61c：立即完成委托锁定骰值 1（大成功）——spy 捕获结算掷骰 */
let _seenRoll = null;
const _q3orig = queueRoll3D;
queueRoll3D = function(r, name){ _seenRoll = r; return Promise.resolve(); };
S.active = [{name: "采集草药", q: C["Lv1"][0], rate: 0.01, acceptTs: Date.now(), finishTs: Date.now() + 3600000}];
creFinishActive();
queueRoll3D = _q3orig;
ck(S.active.length === 0 && _seenRoll === 1, "v1.61c：creFinishActive 锁定骰值 1（大成功，实际 " + _seenRoll + "）");
S.pool = {point:"OLD@00", list:["旧批次"], taken:false, bornTs:0}; S.poolPoint = "OLD@00";
creRerollPool();
ck(S.pool !== null && S.pool.list.length > 0 && S.pool.point !== "OLD@00", "creRerollPool：无视时间段重抽（旧批次作废替换）");
ck(Math.abs(S.pool.bornTs - Date.now()) < 5000, "creRerollPool：接取窗口已重置（bornTs≈now）");
const _v0 = S.vit;
creBuffNow();
ck(S.buffNext && S.buffNext.claimed === true && S.vit > _v0, "creBuffNow：区间奖励立即到账");
creShieldReset();
ck(S.shieldMonth === "", "creShieldReset：本月保险重置");
S.legendDay = "x"; S.legendWeek = "x"; S.wolfDone = true;
creLegendReset();
ck(S.legendDay === todayStr() && S.legendWeek === "" && S.wolfDone === false, "creLegendReset：标记清除并重判今日");
S.weekSettled = "x"; S.monthSettled = "x";
creResetSettles();
ck(S.weekSettled === "" && S.monthSettled === "", "creResetSettles：周/月结算标记清除");
S.accepted = 9; S.exploreUsed = 5; S.libDate = "x";
creResetAcceptCount();
ck(S.accepted === 0 && S.libDate === "", "creResetAcceptCount：委托次数重置");
creResetExploreCount();
ck(S.exploreUsed === 0, "creResetExploreCount：探索次数重置");
S.exploreActive = null;
creExploreNow();
ck(S.exploreActive === null && (document.getElementById("dlg").innerHTML || "").indexOf("选择区域") >= 0, "creExploreNow：弹出区域选择（不直接进入）");
clrDlg();
creExploreAt(6);
ck(S.exploreActive !== null && S.exploreActive.n === REGIONS[6].n && S.exploreUsed === 1, "creExploreAt：指定区域进入探索（虚空裂痕）");
creFinishExplore();
ck(S.exploreActive === null, "creFinishExplore：立刻完成并结算");
if(typeof resultQueue !== "undefined"){ resultQueue.length = 0; _pendingSettles = 0; _qanimBusy = false; }
creShowYesterday();
ck(S.yesterdayShown === true, "creShowYesterday：快照重新展示（标记已消费）");
const _tr0 = S.trophies.length;
creGrantLegendAll();
ck(S.trophies.length > _tr0 || S.titles.length > 0, "creGrantLegendAll：传奇奖励补全");
S.exploreActive = {idx: 0};
creCleanTransient();
ck(S.exploreActive === null, "creCleanTransient：清理卡住的瞬态");
creSetLastMeal("菌菇汤");
ck(S.lastMeal && S.lastMeal.name === "菌菇汤" && S.lastMeal.date === todayStr(), "creSetLastMeal：设置料理（当日生效）");
creSetLastMeal("");
ck(S.lastMeal === null, "creSetLastMeal：清除料理");
const _pe0 = S.permEnergy;
creApplyMisc();
ck(S.permEnergy === _pe0, "无输入时杂项数值保持");

/* v1.38f 携带宠物 */
S.pets = ["月光狐"];
S.petData = {"月光狐": {stage: 1, growth: 0, mutate: 0, fedDate: "", fedCount: 0}};
setCarryPet("月光狐");
ck(S.carryPet === "月光狐" && carryPetLabel().length > 0, "setCarryPet + carryPetLabel（创造环境）");

/* v1.38e 详情弹窗（创造界面列表点击调用同一批函数） */
showMatDetail("松木");
ck((document.getElementById("dlg").innerHTML || "").indexOf("松木") >= 0, "创造界面：材料详情弹窗");
showItemDetail("清醒符咒");
ck((document.getElementById("dlg").innerHTML || "").indexOf("清醒符咒") >= 0, "创造界面：道具详情弹窗");
showGearDetail("猎弓");
ck((document.getElementById("dlg").innerHTML || "").indexOf("猎弓") >= 0, "创造界面：装备详情弹窗");

/* v1.38r：清空存档（保留冒险者之名，其余数据归零到初始状态） */
S.name = "创造测试";
S.money = 12345; S.lvIdx = 3; S.exp = 9999; S.mats = {"松木": 5};
S.pets = ["月光狐"]; S.titles = ["x"]; S.history = [{date:"x"}];
let _wipeN = 0;
const _scOrig = showConfirm;
showConfirm = function(msg, onOk){ _wipeN++; onOk && onOk(); };   // 直接确认执行
creWipeSave();
showConfirm = _scOrig;
ck(_wipeN === 1, "creWipeSave：弹出确认并被确认");
ck(S.name === "创造测试", "清空存档：保留冒险者之名");
ck(S.money === 0 && S.lvIdx === 0 && S.exp === 0 && Object.keys(S.mats).length === 0
   && S.pets.length === 0 && S.titles.length === 0 && S.history.length === 0,
   "清空存档：其余数据归零到初始状态");

/* v1.38s：创造模式直接改等级 → 升级详情兜底弹窗（不经结算的升级路径） */
S.lvIdx = 0; _lastLvFx = 0; render();
S.lvIdx = 2; render();                    // 跳 2 级（模拟创造面板直接改等级）
clrDlg();
flushResults();                           // 同步消费队列（checkFx 的 500ms 定时不依赖，测试即时验证）
ck((document.getElementById("dlg").innerHTML || "").indexOf("升级") >= 0,
   "v1.38s：改等级弹出升级详情（创造模式路径）");
ck((document.getElementById("dlg").innerHTML || "").indexOf("新解锁") >= 0
   && (document.getElementById("dlg").innerHTML || "").indexOf("公会系统开放") >= 0,
   "v1.38s：详情为 Lv2 内容（新解锁 + 公会系统）");
levelupQueue.length = 0;

/* v1.38s3：改等级 → 当前批次按新等级重抽（数量 = 该级抽取数；修复"Lv5 档池仍显示低等级抽取数"） */
const _lp3 = latestPoint(new Date()), _pk3 = pointKey(_lp3.d, _lp3.h);
S.lvIdx = 1;
S.pool = {point:_pk3, list:[["A"],["B"],["C"]], taken:false, bornTs:Date.now(), expiredLogged:false};
S.poolPoint = _pk3;
creMaxLevel();
ck(S.lvIdx === 4 && S.pool.list.length === CFG.drawCount[4],
   "v1.38s3：改等级（满级）→ 本批按新等级重抽（" + CFG.drawCount[4] + " 个）");
const _listRef = S.pool.list;
creMaxLevel();
ck(S.pool.list === _listRef, "v1.38s3：等级未变 → 不重抽（引用不变）");

JSON.stringify(__R);
`;

const raw = eval(main + "\n" + creator[1] + "\n" + test);
const r = JSON.parse(raw);
console.log("========== 创造模式冒烟 ==========");
console.log("  断言通过 " + r.pass + " 项 | 失败 " + r.fail + " 项 " + (r.fail === 0 ? "✅ 全部通过" : "❌"));
r.msgs.forEach(m => console.log("  ❌ " + m));
process.exit(r.fail === 0 ? 0 : 1);
