// 探针：验证「医务室」卡片渲染——公会 C 显示（含 span2 通栏）/ 公会 F 隐藏
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
  S.history = []; S.sickDays = []; S.shieldDays = [];
}

/* 场景 1：F 级 → 完全隐藏（v1.41 可见性规则） */
seed(10); renderHealth();
const hF = document.getElementById("tab-health").innerHTML;
check(hF.length > 0, "健康页应正常渲染（F 级）");
check(hF.indexOf("医务室") < 0, "F 级(rep=10)不应显示医务室");

/* 场景 2：差一点到 C（849）→ 仍隐藏 */
seed(849); renderHealth();
check(document.getElementById("tab-health").innerHTML.indexOf("医务室") < 0, "rep=849 不应显示");

/* 场景 3：C 级（850）→ 显示，初始 2/2，今日可请、昨日因无记录禁用 */
seed(850); renderHealth();
const hC = document.getElementById("tab-health").innerHTML;
check(hC.indexOf("🏥 医务室") >= 0, "C 级(rep=850)应显示医务室卡");
check(hC.indexOf("本月剩余病假") >= 0, "应显示剩余病假计数");
check(hC.indexOf('class="card span2"') >= 0, "应为通栏 span2");
check(hC.indexOf("2 / 2 天") >= 0, "初始剩余应为 2/2");
check(hC.indexOf("takeSickLeave('today')") >= 0, "请今日病假按钮");
check(hC.indexOf("takeSickLeave('yesterday')") >= 0, "补请昨日按钮");
check(hC.indexOf('onclick="takeSickLeave(\\'today\\')" disabled') < 0, "今日按钮应可用");
check(hC.indexOf('onclick="takeSickLeave(\\'yesterday\\')" disabled') >= 0, "昨日按钮应禁用（无记录）");
check(hC.indexOf("暂无记录") >= 0, "应提示昨日状态：暂无记录");

/* 场景 4：本月已用 1 天病假 + 昨日断档 → 剩 1/2，补请昨日可用 */
seed(850);
const _y = parseDate(S.health.date); _y.setDate(_y.getDate()-1);
S.history = [{date: todayStr(_y), sleep:false, score:50}];
S.sickDays = [S.health.date.slice(0,7) + "-01"];   // 本月 1 日已用一天
renderHealth();
const hY = document.getElementById("tab-health").innerHTML;
check(hY.indexOf("1 / 2 天") >= 0, "剩余病假应显示 1/2（本月已用 1 天）");
check(hY.indexOf('onclick="takeSickLeave(\\'yesterday\\')" disabled') < 0, "昨日断档且未被覆盖 → 补请按钮应可用");
check(hY.indexOf("补请昨日（") >= 0, "补请按钮应带日期");

console.log("  RENDER PASS=" + PASS + " FAIL=" + FAIL);
if(FAIL) process.exitCode = 1;
})();
`;
eval(code + test);
