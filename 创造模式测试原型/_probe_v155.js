// v1.55 前端沙箱验证：月光狐阅读驱动 + 4 条传奇链（携带/喂食/进化/变异）
// 运行：node _probe_v155.js
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
let _alerts = [], _dlgs = [], _confirms = [];
showAlert = function(m,t){ _alerts.push(String(m)); };
dlg = function(title, body, buttons){ _dlgs.push(String(title)); };
showConfirm = function(m, fn, t){ _confirms.push(String(m)); if(fn) fn(); };

/* ══ 场景 1：月光狐（阅读驱动）══ */
S = newState(); S.name = "探针"; S.lvIdx = 4; S.rep = 999999;
S.mats = {"蜂蜜":9, "月光草":9, "龙血":9, "世界树汁液":9, "龙心":9};
S.pets = ["月光狐"]; petDataOf("月光狐");
const fox = function(){ return S.petData["月光狐"]; };
ok(fox().stage === 1, "月光狐初始 stage1");
/* v1.56c：加成携带生效 */
ok(petBonus().mat === 0 && petBonus().rate === 0 && petBonus().pay === 0, "未携带 → 宠物加成全 0");
S.carryPet = "月光狐";
ok(petBonus().pay === 0.01 && petBonus().mat === 0, "携带月光狐（一阶）→ 报酬+1%");

S.histStats = {read: 44};
ok(syncReadPets() === false, "44 次阅读：不进化");
S.histStats.read = 45;
ok(syncReadPets() === true && fox().stage === 2, "45 次阅读 → 月影狐");
S.histStats.read = 59;
ok(syncReadPets() === false, "59 次：停在月影狐");
S.histStats.read = 60;
ok(syncReadPets() === true && fox().stage === 3, "60 次阅读 → 幻月九尾");
ok(syncReadPets() === false, "满阶后幂等");
ok(petGrowthTxt("月光狐").indexOf("已满阶") >= 0, "成长文案：已满阶");
ok(petBonus().mat === 0.04 && petBonus().rate === 0.01 && petBonus().sp === 0, "幻月九尾加成 mat.04/rate.01（v1.56b 探索点已移除）");

// 满阶后喂普通食材 → 拦截
_alerts = [];
feedPet("月光狐", "蜂蜜");
ok(_alerts.length === 1 && _alerts[0].indexOf("成长已经完成") >= 0, "满阶普通食材拦截");
ok(S.mats["蜂蜜"] === 9, "拦截不扣材料");

// 一阶喂高级材料 → 拦截（v1.55 补丁）
fox().stage = 1; _alerts = [];
feedPet("月光狐", "月光草");
ok(_alerts.length === 1 && _alerts[0].indexOf("二阶起") >= 0, "一阶喂高级材料拦截");
ok(S.mats["月光草"] === 9, "拦截不扣高级材料");
// 一阶喂普通食材 → 阅读提示
fox().stage = 1; _alerts = [];
feedPet("月光狐", "蜂蜜");
ok(_alerts.length === 1 && _alerts[0].indexOf("阅读 60 / 45") >= 0, "一阶普通食材提示阅读进度");
ok(S.mats["蜂蜜"] === 9, "拦截不扣普通食材");

// 二阶喂高级材料 → 积累变异值
fox().stage = 2; fox().fedDate = ""; _alerts = [];
feedPet("月光狐", "月光草");
ok(S.mats["月光草"] === 8, "二阶喂月光草扣 1");
ok(fox().mutate === 8, "二阶变异 +8（月光草偏好）");
ok(fox().growth === 0, "阅读驱动成长值不涨");

// 三阶：携带 + 委托成长（变异前测）
fox().stage = 3;
S.carryPet = "";
setCarryPet("月光狐");
ok(S.carryPet === "月光狐", "月光狐可携带");
ok(carryPetLabel().indexOf("幻月九尾") >= 0, "携带标签显示当前形态");
const gtxt = petQuestGain(["x", "精英", 3, 5, "普通", 1], true, 0);
ok(gtxt.indexOf("成长来自阅读") >= 0, "委托成长提示：来自阅读");

// 三阶变异
fox().mutate = 260;
_confirms = [];
evolvePet("月光狐");
ok(_confirms.length === 1, "变异需确认");
ok(fox().stage === 4, "变异成功 → 星月狐仙");
ok(fox().mutate === 0 && fox().growth === 0, "变异后数值清零");
ok(petBonus().mat === 0.06 && petBonus().rate === 0.02 && petBonus().sp === 0, "星月狐仙加成 mat.06/rate.02（v1.56b 探索点已移除）");
ok(carryPetLabel().indexOf("星月狐仙") >= 0, "携带标签显示变异名");

// v1.55c：品阶营养（未列出材料按品阶给成长）
ok(petFeedValue("捣蛋鬼", "龙心").v === 15, "品阶营养：未列出传说 +15");
ok(petFeedValue("捣蛋鬼", "月光草").v === 4, "品阶营养：未列出稀有托底（月光草 +4）");
ok(petFeedValue("深渊之眼", "暗影草").v === 10, "品阶营养：口味与品阶取较高者（暗影草 口味 10 > 史诗基数 8）");
ok(petFeedValue("月光狐", "龙心").v === 0, "阅读驱动不吃营养");

// 界面不炸
S.daily = S.daily || {events: []};
showPetDetail("月光狐"); openPetFeed("月光狐"); render();
ok(_dlgs.length >= 2, "详情/喂食/渲染均可打开");

/* ══ 场景 2：4 条传奇链 ══ */
const CHAINS = [
  ["星界幼龙", "星辉龙", "星界巨龙", "星穹之龙", "星尘"],
  ["龙神幼崽", "龙神子嗣", "龙神使者", "龙神化身", "兽肉"],
  ["幼龙群", "幼龙小队", "龙群之首", "万龙之群", "兽肉"],
  ["深渊之眼", "深渊凝视者", "深渊主宰之眼", "深渊之瞳·终焉", "河鱼"]
];
S.mats = {"蜂蜜":99, "兽肉":99, "蘑菇":99, "河鱼":99, "星尘":99, "龙血":99, "龙心":99, "暗影草":99, "晨露花":99};
CHAINS.forEach(function(c){
  const n = c[0];
  grantPet(n);
  const pd = S.petData[n];
  ok(pd && pd.stage === 1, n + " 可获得（petData 建立）");
  ok((S.pets||[]).indexOf(n) >= 0, n + " 加入宠物列表（可携带）");
  setCarryPet(n);
  ok(S.carryPet === n, n + " 可携带");
  const qg = petQuestGain(["x", "精英", 3, 5, "普通", 1], true, 0);
  ok(qg.indexOf("成长 +") >= 0, n + " 委托成长生效");
  // 一阶 → 二阶（喂到 60）
  pd.fedDate = ""; pd.growth = 56;
  _alerts = [];
  feedPet(n, c[4]);
  ok(pd.stage === 2, n + " 喂满 60 → " + c[1]);
  ok(_alerts.length && _alerts[0].indexOf(c[1]) >= 0, n + " 升阶提示含 " + c[1]);
  // 二阶 → 三阶（喂到 180）
  pd.fedDate = ""; pd.growth = 176;
  feedPet(n, c[4]);
  ok(pd.stage === 3, n + " 喂满 180 → " + c[2]);
  // 二阶起变异值积累
  pd.fedDate = ""; pd.mutate = 0;
  feedPet(n, "龙血");
  ok(pd.mutate > 0, n + " 高级材料积累变异值");
  // 三阶变异（growth 满 + mutate 满）
  pd.stage = 3; pd.growth = 999; pd.mutate = 300;
  _confirms = [];
  evolvePet(n);
  ok(pd.stage === 4, n + " 变异 → " + c[3]);
  ok(petBonusNote(n).length > 0, n + " 变异后加成文案存在");
  stopCarry();
});
function stopCarry(){ S.carryPet = ""; }

// 怪物：图鉴渲染 + 宠物全列表
S.pets = Object.keys(PET_LINES).concat(["小狼"]);
Object.keys(PET_LINES).forEach(function(n){ petDataOf(n); S.petData[n].stage = 4; S.petData[n].mutate = 0; });
S.wolf = {stage: 4, growth: 0, mutate: 0, fedDate: "", fedCount: 0};
render();
ok(true, "全部 8 链 stage4 渲染无异常");

console.log(PASS + " 通过 / " + FAIL + " 失败");
if(FAIL > 0) process.exit(1);
`;

eval(code + "\n" + probe);
