// 委托奖励合理性审查（一次性工具）：输出全部委托的 难度 × 材料品质/数量 + 汇总
// 运行：node _audit_quests.js
const fs = require('fs');
global.localStorage = { _d:{}, getItem(){ return null; }, setItem(){}, removeItem(){} };
const fakeEl = () => ({ textContent:"", innerHTML:"", style:{}, value:"",
  classList:{ add(){}, remove(){}, contains(){ return false; } }, onclick:null, focus(){}, addEventListener(){}, dataset:{}, querySelectorAll(){ return []; } });
global.document = { getElementById: () => fakeEl(), querySelectorAll: () => [], addEventListener: () => {} };
global.alert = () => {}; global.confirm = () => true; global.setInterval = () => 0;

const code = fs.readFileSync(__dirname + '/健康的冒险者的一天.html', 'utf-8').match(/<script>([\s\S]*?)<\/script>/)[1];
const { C, CFG, M } = new Function(code + '\nreturn { C, CFG, M };')();

const QO = ['普通','精良','稀有','史诗','传说'];
const tierOf = (n) => (M[n] || ['','?'])[1];
const tierIdx = (n) => QO.indexOf(tierOf(n));
// 一行的"最高品质 / 有没有非主材料的低品质必掉项"
for(const lv of ['Lv1','Lv2','Lv3','Lv4','Lv5']){
  console.log('════════ ' + lv + ' ════════');
  for(const q of C[lv]){
    const keys = Object.keys(q[8]);
    const mats = keys.map((k, i) => {
      const v = q[8][k]; const rg = Array.isArray(v) ? v : [v, v];
      return (i === 0 ? '★' : '') + k + '[' + tierOf(k) + ']' + rg[0] + (rg[1] !== rg[0] ? '~' + rg[1] : '');
    });
    const top = Math.max.apply(null, keys.map(tierIdx));
    console.log(q[4] + ' | ' + q[1] + ' | ' + q[0] + ' | 最高:' + QO[top] + ' | ' + mats.join(' + '));
  }
}
console.log('\n════════ 汇总：每池 · 每难度的最高材料品质 ════════');
for(const lv of ['Lv1','Lv2','Lv3','Lv4','Lv5']){
  const g = {};
  for(const q of C[lv]){
    const keys = Object.keys(q[8]);
    const top = QO[Math.max.apply(null, keys.map(tierIdx))];
    const mainTier = tierOf(keys[0]);
    (g[q[4]] = g[q[4]] || []).push(q[0] + '(' + top + '/主:' + mainTier + ')');
  }
  const line = Object.keys(g).map(d => d + ' ×' + g[d].length + ': ' + g[d].join('、')).join('  ||  ');
  console.log(lv + ' | ' + line);
}
