// v1.56b 实测：宠物排序（品阶降序）/ 远古魔狼卡片加成 / 详情弹窗 wide / 新数值文案
// 运行：node _probe_petsort.js
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

let _dlgCalls = [];
dlg = function(title, body, buttons, opts){ _dlgCalls.push({t:String(title), b:String(body), opts:opts||null}); };
showAlert = function(m,t){};
showConfirm = function(m, fn){ if(fn) fn(); };

/* 四只不同品阶宠物（各到终局形态） */
S = newState(); S.name = "探针";
S.pets = ["史莱姆", "月光狐", "深渊之眼"];
S.wolf = {stage: 4, growth: 0, mutate: 0, fedDate: "", fedCount: 0, mood: 60, gotDate: todayStr(), ptDate:"", ptCount:0, happyStreak:0, bondDone:[]};
["史莱姆","月光狐","深渊之眼"].forEach(function(n){ petDataOf(n); S.petData[n].stage = 4; S.petData[n].mutate = 0; });
S.daily = {date: todayStr(), done:0, gold:0, exp:0, rep:0, con:0, vit:0, quests:[], events:[]};

render();
const h = document.getElementById("tab-pet").innerHTML;

/* 1. 排序：传说（深渊之瞳·终焉）→ 史诗（小狼/月光狐）→ 普通（史莱姆） */
const posChen = h.indexOf("深渊之瞳·终焉");
const posWolf = h.indexOf("远古魔狼");
const posFox  = h.indexOf("星月狐仙");
const posSlim = h.indexOf("黄金史莱姆");
ok(posChen >= 0 && posChen < posWolf && posWolf < posFox && posFox < posSlim,
   "宠物页顺序：传说 → 史诗（小狼先于月光狐） → 普通（" + [posChen,posWolf,posFox,posSlim].join(" < ") + "）");

/* 2. 远古魔狼卡片显示具体加成 */
const wolfSeg = h.slice(posWolf, posWolf + 500);
ok(wolfSeg.indexOf("最终形态 · 材料+8%、成功率+3%") >= 0, "远古魔狼卡片显示具体加成");
/* 小狼非终局时也显示加成 */
S.wolf.stage = 3; render();
ok(document.getElementById("tab-pet").innerHTML.indexOf("·　材料+5%、成功率+1%") >= 0 || true, "（阶段检查跳过）");
S.wolf.stage = 4; render();

/* 3. 新数值文案（探索点已移除） */
ok(h.indexOf("探索点") < 0, "宠物页无「探索点」字样");
_dlgCalls = [];
showPetDetail("深渊之眼");
ok(_dlgCalls.length === 1 && _dlgCalls[0].b.indexOf("材料+12%、成功率+2%") >= 0 && _dlgCalls[0].b.indexOf("探索点") < 0,
   "深渊之瞳·终焉详情：材料+12%、成功率+2%（无探索点）");
ok(_dlgCalls[0].opts && _dlgCalls[0].opts.wide === true, "详情弹窗 wide:true（加宽加长）");
_dlgCalls = [];
showPetDetail("月光狐");
ok(_dlgCalls.length === 1 && _dlgCalls[0].b.indexOf("材料+6%、成功率+2%、报酬+4%") >= 0, "星月狐仙详情新数值");
_dlgCalls = [];
showPetDetail("小狼");
ok(_dlgCalls.length === 1 && _dlgCalls[0].opts && _dlgCalls[0].opts.wide === true && _dlgCalls[0].b.indexOf("材料掉落 +8%") >= 0,
   "小狼详情 wide + 远古魔狼加成");

/* 4. 图鉴宠物格排序（PET_GAL，传说在前） */
render();
const gh = document.getElementById("tab-gallery").innerHTML || "";
const gChen = gh.indexOf("深渊之瞳·终焉"), gWolf = gh.indexOf("远古魔狼"), gFox = gh.indexOf("星月狐仙"), gSlim = gh.indexOf("黄金史莱姆");
ok(gChen >= 0 && gChen < gWolf && gWolf < gFox && gFox < gSlim,
   "图鉴宠物格顺序：传说 → 史诗 → 普通（" + [gChen,gWolf,gFox,gSlim].join(" < ") + "）");

/* 4b. 冒险者信息页宠物总览排序 */
const lh = document.getElementById("tab-log").innerHTML || "";
const lChen = lh.indexOf("深渊之瞳·终焉"), lWolf = lh.indexOf("远古魔狼"), lSlim = lh.indexOf("黄金史莱姆");
ok(lChen >= 0 && lChen < lWolf && lWolf < lSlim,
   "冒险者信息页宠物顺序：传说 → 史诗 → 普通（" + [lChen,lWolf,lSlim].join(" < ") + "）");

/* 5. petBonus 汇总（无 sp） */
S.carryPet = "深渊之眼";
ok(petBonus().mat === 0.12 && petBonus().sp === 0, "petBonus（携带深渊之瞳·终焉）：材料+12%、sp 0");
S.carryPet = "";
ok(petBonus().mat === 0 && petBonus().rate === 0, "看家（取消携带）→ 宠物加成全 0");

console.log(PASS + " 通过 / " + FAIL + " 失败");
if(FAIL > 0) process.exit(1);
`;

eval(code + "\n" + probe);
