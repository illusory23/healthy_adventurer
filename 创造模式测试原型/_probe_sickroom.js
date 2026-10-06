// 探针：验证「疗养圣所」卡片渲染——v1.61：无门槛（0 声望可见）/ 每月 3 天 / 病假日评分锁定 59 + 打卡封存
// 运行：node _probe_sickroom.js
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
  querySelector: () => fakeEl(),
  querySelectorAll: () => [],
  addEventListener: () => {}
};
global.alert = () => {};
global.confirm = () => true;
global.setInterval = () => 0;

const html = fs.readFileSync(__dirname + '/../Flask版/static/game.html', 'utf-8');
let code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const _bi = code.indexOf('(async function boot(){');
if(_bi < 0) throw new Error("game.html 结构变化：未找到 boot 段");
code = code.slice(0, _bi);

const test = `
(async function(){
let PASS = 0, FAIL = 0;
function check(c, m){ c ? PASS++ : (FAIL++, console.log("  FAIL: " + m)); }

function seed(rep){
  S = newState();
  S.rep = rep;
  S.health.date = todayStr();
  S.health.done = [0,0,0,0,0,0,0]; S.health.multi = [0,0];
  S.history = []; S.sickDays = []; S.shieldDays = [];
  save = function(){}; render = function(){};   // 探针内跳过全量渲染/存档
}

/* 场景 1：0 声望（F 级）→ 卡片即可见（v1.61 无门槛） */
seed(0); renderHealth();
const h0 = document.getElementById("tab-health").innerHTML;
check(h0.indexOf("🕊️ 疗养圣所") >= 0, "0 声望即显示疗养圣所卡");
check(h0.indexOf('<div class="card"><h3>🕊️ 疗养圣所') >= 0, "独立通栏块");
check(h0.indexOf('</div><div class="card"><h3>🕊️ 疗养圣所') >= 0, "卡片位于双栏容器之后（v1.61b 防重叠结构）");
check(h0.indexOf("3 / 3 天") >= 0, "初始剩余 3/3 天");
check(h0.indexOf("takeSickLeave('today')") >= 0 && h0.indexOf("takeSickLeave('yesterday')") >= 0, "两个按钮均在");
check(h0.indexOf('onclick="takeSickLeave(\\'today\\')" disabled') < 0, "今日按钮可用");
check(h0.indexOf('onclick="takeSickLeave(\\'yesterday\\')" disabled') >= 0, "昨日按钮禁用（无记录）");
check(h0.indexOf("暂无记录") >= 0, "提示昨日状态：暂无记录");
check(h0.indexOf("评分锁定 59") >= 0, "卡面说明含 59 锁定规则");

/* 场景 2：今日病假 → 评分锁定 59 / 打卡按钮置灰 / 评分卡显示封存 */
seed(0);
S.sickDays = [S.health.date];
check(sickToday() === true, "sickToday 判定");
check(calcHealth() === 59, "0 分基线 → 锁定 59");
renderHealth();
const hS = document.getElementById("tab-health").innerHTML;
check(hS.indexOf("病假封存 · 评分锁定 59 · 打卡关闭") >= 0, "卡片显示今日封存状态");
check(hS.indexOf("病假封存 · 评分锁定 59") >= 0 && hS.indexOf("今日健康评分") >= 0, "评分卡显示病假封存");
check(hS.indexOf('onclick="toggleTask(1)" disabled') >= 0, "任务按钮置灰禁用");
check(hS.indexOf('onclick="toggleMeal(0)" disabled') >= 0, "三餐按钮置灰禁用");
check(hS.indexOf('onclick="addMulti(0,1)" disabled') >= 0, "多次任务按钮置灰禁用");
check(hS.indexOf("今日已请假 ✓") >= 0, "今日按钮变为已请假");

/* 场景 3：补请昨日（本地实现）→ 昨日记录评分改写 59 / 月度剩 2 */
seed(0);
const _y = parseDate(S.health.date); _y.setDate(_y.getDate()-1);
S.history = [{date: todayStr(_y), sleep: false, score: 30, done: 0, tasks: [], multi: [0,0]}];
const _cs = confirmSpend; confirmSpend = function(t, b, fn){ fn && fn(); };
takeSickLeave("yesterday");
confirmSpend = _cs;
check(S.sickDays.indexOf(todayStr(_y)) >= 0, "补请昨日写入 sick_days");
check(S.history[S.history.length-1].score === 59, "昨日记录评分改写为 59");
check(sickLeftNow() === 2, "本月剩余病假 2/3");

/* 场景 4：月度 3 天上限 */
seed(0);
const _m = S.health.date.slice(0,7);
S.sickDays = [_m + "-01", _m + "-02", _m + "-03"];
check(sickLeftNow() === 0, "用满 3 天 → 剩余 0");
renderHealth();
const hF = document.getElementById("tab-health").innerHTML;
check(hF.indexOf('onclick="takeSickLeave(\\'today\\')" disabled') >= 0, "额度用尽 → 今日按钮禁用");

console.log("  RENDER PASS=" + PASS + " FAIL=" + FAIL);
if(FAIL) process.exitCode = 1;
})();
`;
eval(code + test);
