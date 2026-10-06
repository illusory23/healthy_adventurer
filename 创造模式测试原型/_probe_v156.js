// v1.56 前端沙箱验证：宠物情感系统（心情/互动/羁绊/散步/小剧场/昵称/成就/宠物页）
// 运行：node _probe_v156.js
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
let PASS = 0, FAIL = 0;
function ok(cond, msg){ if(cond){ PASS++; } else { FAIL++; console.log("❌ " + msg); } }
let _dlgs = [];
dlg = function(title, body, buttons){ _dlgs.push({t:String(title), b:String(body)}); };
showAlert = function(m,t){ _dlgs.push({t:String(t||""), b:String(m)}); };
showConfirm = function(m, fn){ if(fn) fn(); };

/* ── 准备 ── */
S = newState(); S.name = "探针"; S.lvIdx = 4; S.mats = {"蘑菇":5};
S.pets = ["月光狐", "史莱姆"]; petDataOf("月光狐"); petDataOf("史莱姆");
S.wolf = {stage: 2, growth: 10, mutate: 0, fedDate: "", fedCount: 0};
S.daily = {date: todayStr(), done:0, gold:0, exp:0, rep:0, con:0, vit:0, quests:[], events:[]};

/* ══ 1. petMetaOf 初始化 ══ */
const mf = petMetaOf("月光狐");
ok(mf && mf.mood === 50 && !!mf.gotDate && mf.happyStreak === 0 && Array.isArray(mf.bondDone), "petMetaOf 初始化（mood/gotDate/bondDone）");
ok(petMetaOf("小狼") && petMetaOf("小狼").mood === 50, "小狼 meta 走 wolf 路径");
ok(petMetaOf("不存在") === null, "未知宠物返回 null");

/* ══ 2. 心情日结算 ══ */
petMoodDaily(95, true);
ok(petMetaOf("月光狐").mood === 65, "高分+早睡 → +15（50→65）");
petMoodDaily(30, false);
ok(petMetaOf("月光狐").mood === 60, "低分 → −5");
// 连续 7 天心意事件
petMetaOf("月光狐").happyStreak = 6; petMetaOf("月光狐").mood = 80;
const _total0 = Object.keys(S.mats).reduce(function(a,k){ return a + S.mats[k]; }, 0);
petMoodDaily(95, true);
const _total1 = Object.keys(S.mats).reduce(function(a,k){ return a + S.mats[k]; }, 0);
ok(petMetaOf("月光狐").happyStreak === 7 && _total1 === _total0 + 1, "连续 7 天 → 心意事件（有礼物）");
ok(S.daily.events.some(function(e){ return e.indexOf("心意事件") >= 0; }), "心意事件写入当日事件");

/* ══ 3. 羁绊 ══ */
ok(petBondDays("月光狐") === 1, "羁绊第 1 天");
petMetaOf("月光狐").gotDate = "2026-08-01";
const _today = todayStr();
const _expect = Math.floor((new Date(_today+"T00:00:00") - new Date("2026-08-01T00:00:00"))/86400000) + 1;
ok(petBondDays("月光狐") === _expect, "羁绊按 gotDate 计算（" + _expect + "）");
petMetaOf("月光狐").gotDate = _today;
const d2 = new Date(new Date(_today+"T00:00:00") - 30*86400000);
petMetaOf("月光狐").gotDate = d2.getFullYear() + "-" + String(d2.getMonth()+1).padStart(2,"0") + "-" + String(d2.getDate()).padStart(2,"0");
const _ch = petBondTick();
ok(_ch === true && petMetaOf("月光狐").bondDone.indexOf(7) >= 0 && petMetaOf("月光狐").bondDone.indexOf(30) >= 0, "羁绊 31 天 → 解锁 7/30");
ok(petBondTick() === false, "羁绊解锁幂等");

/* ══ 4. 抚摸 ══ */
_dlgs = [];
const _mBefore = petMetaOf("月光狐").mood;
petPat("月光狐");
const pm = petMetaOf("月光狐");
ok(pm.mood === Math.min(100, _mBefore + 5) && pm.ptDate === todayStr() && pm.ptCount === 1, "抚摸 +5 心情并记录");
ok(_dlgs.length >= 1 && _dlgs[0].b.indexOf(petShowName("月光狐")) >= 0 || _dlgs[0].b.length > 0, "抚摸弹窗展示回复");
_dlgs = [];
petPat("月光狐");
ok(_dlgs.length === 1 && _dlgs[0].b.indexOf("明天") >= 0, "每日 1 次限制");

/* ══ 5. 散步 ══ */
const _slBefore = petMetaOf("史莱姆").mood;
_dlgs = [];
petWalkStart("史莱姆");
ok(S.petWalk && S.petWalk.n === "史莱姆", "散步出发");
_dlgs = [];
petWalkStart("月光狐");
ok(_dlgs.length === 1 && _dlgs[0].b.indexOf("散步") >= 0 && S.petWalk.n === "史莱姆", "同时只能 1 只");
ok(petWalkSettle() === false, "未到点不结算");
S.petWalk.ts = Date.now() - PET_WALK_MS - 1000;
const _mats0 = JSON.stringify(S.mats);
ok(petWalkSettle() === true && S.petWalk === null && S.walkCount === 1, "到点结算 + 计数");
ok(petMetaOf("史莱姆").mood === Math.min(100, _slBefore + 3), "散步 +3 心情");

/* ══ 6. 小剧场 ══ */
const _logN0 = S.log.length;
ok(petTheater() === true && S.log.length === _logN0 + 1, "小剧场触发");
const _theaterLine = S.log[0];   // addLog 用 unshift：新日志在头部
ok(JSON.stringify(_theaterLine).indexOf("🎪") >= 0, "小剧场日志格式");
S.pets = ["史莱姆"]; S.wolf = null;
ok(petTheater() === false, "单宠不触发");

/* ══ 7. 昵称 ══ */
S.wolf = {stage: 2, growth: 10, mutate: 0, fedDate: "", fedCount: 0};
setPetNick("史莱姆", "泡泡");
ok(S.petNick["史莱姆"] === "泡泡" && petShowName("史莱姆") === "泡泡", "昵称设置与显示");
_dlgs = [];
setPetNick("史莱姆", "一二三四五六七");
ok(_dlgs.length === 1, "超长昵称拒绝");
S.petNick["史莱姆"] = "泡泡";
setPetNick("史莱姆", "");
ok(!S.petNick["史莱姆"] && petShowName("史莱姆") === "史莱姆", "清空昵称");

/* ══ 8. 成就条件 ══ */
ok(ACHV.find(function(a){ return a.n === "蜕变之始"; }).cond() === false, "蜕变之始：未变异为 false");
S.petData["史莱姆"].stage = 4;
ok(ACHV.find(function(a){ return a.n === "蜕变之始"; }).cond() === true, "蜕变之始：变异后 true");
S.walkCount = 10;
ok(ACHV.find(function(a){ return a.n === "林间常客"; }).cond() === true, "林间常客：散步 10 次");
S.walkCount = 0;
S.pets = ["月光狐", "史莱姆"];              // 恢复成员（前节临时改过）
petMetaOf("月光狐").gotDate = "2025-01-01";
ok(ACHV.find(function(a){ return a.n === "形影不离"; }).cond() === true, "形影不离：羁绊 ≥100 天");

/* ══ 9. 宠物页渲染 ══ */
render();
const _petH = document.getElementById("tab-pet").innerHTML || "";
ok(_petH.indexOf("🐾 宠物") >= 0, "宠物页标题");
ok(_petH.indexOf("抚摸") >= 0 && _petH.indexOf("散步") >= 0 && _petH.indexOf("改名") >= 0, "宠物卡按钮（抚摸/散步/改名）");
ok(_petH.indexOf("羁绊") >= 0 && _petH.indexOf("心情") >= 0, "心情/羁绊展示");
ok(_petH.indexOf("小提示") >= 0, "小提示卡");
const _bagH = document.getElementById("tab-bag").innerHTML || "";
ok(_bagH.indexOf("前往宠物页") >= 0, "背包导流卡");

/* ══ 10. 详情与故事 ══ */
_dlgs = [];
showPetDetail("月光狐");
ok(_dlgs.length === 1 && _dlgs[0].b.indexOf("品阶") >= 0 && _dlgs[0].b.indexOf("羁绊") >= 0 && _dlgs[0].b.indexOf("心情") >= 0, "详情含品阶/心情/羁绊");
ok(_dlgs[0].b.indexOf("📖") >= 0 && _dlgs[0].b.indexOf("30 天") >= 0, "详情展示羁绊故事入口");
_dlgs = [];
showPetStory("月光狐", 30);
ok(_dlgs.length === 1 && _dlgs[0].b.indexOf("它开始学你") >= 0, "羁绊故事内容可读");
_dlgs = [];
showPetStory("月光狐", 365);
ok(_dlgs.length === 0, "未解锁故事不可读");
showPetDetail("小狼");
ok(_dlgs.length === 1 && _dlgs[0].b.indexOf("小狼成长链") >= 0 && _dlgs[0].b.indexOf("羁绊") >= 0, "小狼详情含陪伴信息");

/* ══ 11. 节日问候 ══ */
FESTIVALS[todayStr().slice(5)] = ["🧪 测试节", "测试描述"];
S.petNick = {};
const _fl = petFestLine("史莱姆");
ok(_fl.indexOf("测试节") >= 0 || _fl.indexOf("史莱姆") >= 0, "节日问候生成（" + _fl.slice(0,20) + "）");
delete FESTIVALS[todayStr().slice(5)];

console.log(PASS + " 通过 / " + FAIL + " 失败");
if(FAIL > 0) process.exit(1);
`;

eval(code + "\n" + probe);
