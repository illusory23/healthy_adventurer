// v1.56e 实测：本命材料体系——主题材料入食谱（星尘 / 星核 / 深渊素材 / 龙材 / 月之织物……），非本宠拒食
// 运行：node _probe_v156e.js
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
function ok(cond, msg){ if(cond){ PASS++; console.log("✅ " + msg); } else { FAIL++; console.log("❌ " + msg); } }

let _dlgCalls = [], _alerts = [];
dlg = function(title, body, buttons, opts){ _dlgCalls.push({t:String(title), b:String(body), btn:(buttons||[]).map(function(x){ return String(x.text||""); }).join("|")}); };
showAlert = function(m, t){ _alerts.push(String(m)); };
showConfirm = function(m, fn){ if(fn) fn(); };

S = newState(); S.name = "探针";
S.pets = ["星界幼龙", "深渊之眼", "史莱姆", "月光狐"];
["星界幼龙","深渊之眼","史莱姆","月光狐"].forEach(function(n){ petDataOf(n); });
S.daily = {date: todayStr(), done:0, gold:0, exp:0, rep:0, con:0, vit:0, quests:[], events:[]};

/* 1. 本命材料值（非食材 / 草药的主题材料） */
ok(petFeedValue("星界幼龙", "星核").v === 17 && petFeedValue("星界幼龙", "星尘").v === 8
   && petFeedValue("星界幼龙", "星陨岩").v === 16, "星界幼龙：星核 +17 / 星尘 +8 / 星陨岩 +16（星主题）");
ok(petFeedValue("深渊之眼", "暗影龙鳞").v === 17 && petFeedValue("深渊之眼", "混沌碎片").v === 10
   && petFeedValue("深渊之眼", "虚空结晶").v === 10, "深渊之眼：暗影龙鳞 +17 / 混沌碎片 +10 / 虚空结晶 +10（深渊素材）");
ok(petFeedValue("史莱姆", "净化石").v === 6 && petFeedValue("史莱姆", "石英").v === 5, "史莱姆：净化石 +6 / 石英 +5（水与晶石）");
ok(petFeedValue("捣蛋鬼", "古董钱币").v === 6 && petFeedValue("捣蛋鬼", "哥布林图腾").v === 5, "捣蛋鬼：古董钱币 +6 / 哥布林图腾 +5（偷藏癖）");
ok(petFeedValue("绒球兽", "天鹅绒").v === 6, "绒球兽：天鹅绒 +6（绒的同类）");
ok(PET_LINES["月光狐"].favs["月长石"] === 10 && PET_LINES["月光狐"].favs["月影纱"] === 8
   && petFeedValue("月光狐", "月长石").refuse === false, "月光狐：月长石 / 月影纱收入口味（月之物；阅读驱动 v 恒 0，供展示与引导）");
ok(petFeedValue("龙神幼崽", "龙瞳结晶").v === 17 && petFeedValue("幼龙群", "龙骨").v === 9
   && petFeedValue("幼龙群", "巨人骨").v === 9, "龙系：龙瞳结晶 +17 / 龙骨 +9 / 巨人骨 +9");

/* 2. 本命材料只有本宠能吃 */
ok(petFeedValue("史莱姆", "星核").refuse === true && petFeedValue("月光狐", "星核").refuse === true, "别家拒食星核（史莱姆 / 月光狐）");
ok(petFeedValue("星界幼龙", "混沌碎片").refuse === true && petFeedValue("深渊之眼", "星尘").refuse === true, "跨主题拒食（星界幼龙拒混沌碎片 / 深渊之眼拒星尘）");
ok(petFeedValue("星界幼龙", "星核").refuse === false && petFeedValue("史莱姆", "净化石").refuse === false, "本宠可吃自己的本命材料");

/* 3. 基础食物仍全体可喂（品阶营养兜底） */
ok(petFeedValue("史莱姆", "山珍").v === 4, "基础材料品阶托底不变（史莱姆喂山珍 +4）");

/* 4. 喂食窗：只列基础食物 + 本宠本命材料 */
S.mats = {"星核":3, "星尘":3, "混沌碎片":3, "暗影龙鳞":3, "月长石":3, "石英":3, "山珍":3};
_dlgCalls = [];
openPetFeed("星界幼龙");
const fbX = _dlgCalls[0] ? _dlgCalls[0].b : "";
ok(fbX.indexOf("星核") >= 0 && fbX.indexOf("星尘") >= 0 && fbX.indexOf("★喜爱") >= 0 && fbX.indexOf("混沌碎片") < 0,
   "喂食窗（星界幼龙）：列出星核 / 星尘（★喜爱），不列混沌碎片");
_dlgCalls = [];
openPetFeed("深渊之眼");
const fbC = _dlgCalls[0] ? _dlgCalls[0].b : "";
ok(fbC.indexOf("混沌碎片") >= 0 && fbC.indexOf("暗影龙鳞") >= 0 && fbC.indexOf("星核") < 0, "喂食窗（深渊之眼）：列出混沌碎片 / 暗影龙鳞，不列星核");
_dlgCalls = [];
openPetFeed("史莱姆");
const fbS = _dlgCalls[0] ? _dlgCalls[0].b : "";
ok(fbS.indexOf("石英") >= 0 && fbS.indexOf("星核") < 0 && fbS.indexOf("山珍") >= 0, "喂食窗（史莱姆）：列出石英 + 基础山珍，不列星核");

/* 5. 详情「❤️ 喜爱」含本命材料 */
_dlgCalls = [];
showPetDetail("星界幼龙");
ok(_dlgCalls.length === 1 && _dlgCalls[0].b.indexOf("星核") >= 0 && _dlgCalls[0].b.indexOf("星尘") >= 0, "详情：❤️ 喜爱列出星核 / 星尘");

/* 6. 集成喂食：星界幼龙吃星核 +17 并扣 1 */
S.petData["星界幼龙"].growth = 0; S.petData["星界幼龙"].fedDate = ""; S.petData["星界幼龙"].fedCount = 0;
feedPet("星界幼龙", "星核");
ok(S.petData["星界幼龙"].growth === 17 && S.mats["星核"] === 2, "feedPet：星核 +17 且扣 1");

/* 7. 拦截面文案 */
_alerts = [];
feedPet("史莱姆", "星核");
ok(_alerts.length === 1 && _alerts[0].indexOf("不能喂食") >= 0, "史莱姆喂星核 → 弹窗「不能喂食……本命材料」");
_alerts = [];
S.petData["月光狐"].fedDate = ""; S.petData["月光狐"].fedCount = 0;
feedPet("月光狐", "月长石");
ok(_alerts.length === 1 && _alerts[0].indexOf("阅读") >= 0, "月光狐（阅读驱动）喂月长石 → 引导阅读（不浪费）");

console.log(PASS + " 通过 / " + FAIL + " 失败");
if(FAIL > 0) process.exit(1);
`;

eval(code + "\n" + probe);
