// v1.56d 实测：「看家」文案 / 偏好按品阶重设计 / 喂食范围扩展（食材·草药全量）
// 运行：node _probe_v156d.js
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
S.pets = ["星界幼龙", "捣蛋鬼", "史莱姆"];
["星界幼龙","捣蛋鬼","史莱姆"].forEach(function(n){ petDataOf(n); });
S.carryPet = "星界幼龙";
S.daily = {date: todayStr(), done:0, gold:0, exp:0, rep:0, con:0, vit:0, quests:[], events:[]};

/* 1. 卡片按钮「🏠 看家」 */
render();
const h = document.getElementById("tab-pet").innerHTML;
ok(h.indexOf("🏠 看家") >= 0 && h.indexOf("📌 携带中 · 加成生效") >= 0 && h.indexOf("📌 卸下") < 0,
   "卡片：携带中显示「🏠 看家」按钮 + 标记（「卸下」已不存在）");

/* 2. 详情标注「看家中」 */
_dlgCalls = [];
showPetDetail("捣蛋鬼");
ok(_dlgCalls.length === 1 && _dlgCalls[0].b.indexOf("（看家中——不生效）") >= 0, "详情：未携带标注「看家中——不生效」");
_dlgCalls = [];
showPetDetail("星界幼龙");
ok(_dlgCalls.length === 1 && _dlgCalls[0].b.indexOf("（携带中 · 生效）") >= 0 && _dlgCalls[0].btn.indexOf("🏠 看家") >= 0,
   "详情：携带中标「携带中 · 生效」、按钮为「🏠 看家」");

/* 3. 偏好值（按品阶重设计） */
ok(petFeedValue("星界幼龙", "星尘蜜").v === 18, "星界幼龙 星尘蜜（传说）成长 +18");
ok(petFeedValue("龙神幼崽", "大块龙肉").v === 10, "龙神幼崽 大块龙肉（史诗）成长 +10");
ok(petFeedValue("深渊之眼", "暗影草").v === 10, "深渊之眼 暗影草 口味 10 > 史诗基数 8（取较高者）");
ok(petFeedValue("深渊之眼", "蘑菇").v === 1, "未列出普通材料按品阶托底 +1");
ok(petFeedValue("捣蛋鬼", "蜂王浆").v === 8, "捣蛋鬼 蜂王浆（稀有）成长 +8（偷蜜小鬼本命）");

/* 4. 喂食窗：新食材可喂 + ★喜爱 标记 */
S.mats = {"星尘蜜":2, "大块龙肉":2, "蜂王浆":2, "浆果":2, "雪盐":2, "薄荷叶":2};
_dlgCalls = [];
openPetFeed("星界幼龙");
const fb = _dlgCalls[0] ? _dlgCalls[0].b : "";
ok(fb.indexOf("星尘蜜") >= 0 && fb.indexOf("★喜爱") >= 0, "喂食窗：星尘蜜可喂并标 ★喜爱");
ok(fb.indexOf("浆果") >= 0 && fb.indexOf("雪盐") >= 0 && fb.indexOf("薄荷叶") >= 0, "喂食窗：食材/草药全量开放（浆果 / 雪盐 / 薄荷叶）");
_dlgCalls = [];
openPetFeed("捣蛋鬼");
ok((_dlgCalls[0]||{b:""}).b.indexOf("蜂王浆") >= 0, "喂食窗：蜂王浆可喂（捣蛋鬼）");

/* 5. 看家日志 + 重新携带 */
S.log = [];
setCarryPet("星界幼龙");   // 再点 = 看家
ok(S.carryPet === "" && S.log[0] && S.log[0].m.indexOf("看家") >= 0, "再点 → 看家日志（加成暂停）");
setCarryPet("星界幼龙");
ok(S.carryPet === "星界幼龙" && S.log[0].m.indexOf("陪同冒险") >= 0, "重新携带 → 加成生效");

/* 6. 喂食集成：星界幼龙喂星尘蜜 → 成长 +18、扣 1 */
petDataOf("星界幼龙");
S.petData["星界幼龙"].growth = 0; S.petData["星界幼龙"].fedDate = ""; S.petData["星界幼龙"].fedCount = 0;
feedPet("星界幼龙", "星尘蜜");
ok(S.petData["星界幼龙"].growth === 18 && S.mats["星尘蜜"] === 1, "feedPet：星尘蜜 +18 且扣 1");

console.log(PASS + " 通过 / " + FAIL + " 失败");
if(FAIL > 0) process.exit(1);
`;

eval(code + "\n" + probe);
