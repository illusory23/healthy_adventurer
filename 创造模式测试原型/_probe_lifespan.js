/* _probe_lifespan.js —— 一次性分析探针（只读，不改任何数据）：
   对比「v1.59 增强旧传奇报酬」与「改为削弱 v1.57 新传奇」两种方案对经济速率 / 游戏周期的影响。
   输出写入 _probe_lifespan_out.txt（UTF-8）。 */
const fs = require('fs');
const ROOT = 'D:/游戏/健康的冒险者的一天/';
const read = f => fs.readFileSync(ROOT + f, 'utf8').replace(/^\uFEFF/, '');

function parseCSV(txt){
  const rows = [];
  let row = [], cell = '', q = false;
  for(let i = 0; i < txt.length; i++){
    const c = txt[i];
    if(q){ if(c === '"'){ if(txt[i+1] === '"'){ cell += '"'; i++; } else q = false; } else cell += c; }
    else if(c === '"') q = true;
    else if(c === ','){ row.push(cell); cell = ''; }
    else if(c === '\r') continue;
    else if(c === '\n'){ row.push(cell); rows.push(row); row = []; cell = ''; }
    else cell += c;
  }
  if(cell !== '' || row.length){ row.push(cell); rows.push(row); }
  return rows;
}
const CUR = {'铂金': 1000000, '金': 10000, '银': 100, '铜': 1};
function money(s){
  const m = /([\d.]+)\s*(铂金|金|银|铜)/.exec((s || '').trim());
  if(!m) return 0;
  return Math.round(parseFloat(m[1]) * CUR[m[2]]);
}
const f金 = c => (c / 10000).toFixed(1);

const out = [];
const P = s => out.push(s);

/* ════ 1. 委托经济（按等级） ════ */
const qRows = parseCSV(read('数据表/委托总表.csv'));
const qHead = qRows[0];
const iLv = qHead.indexOf('等级'), iPay = qHead.indexOf('报酬'), iEn = qHead.indexOf('精力'), iDiff = qHead.indexOf('难度');
const byLv = {};
for(let i = 1; i < qRows.length; i++){
  const r = qRows[i]; if(!r[iLv]) continue;
  const lv = r[iLv], pay = money(r[iPay]), en = parseFloat(r[iEn]) || 1;
  (byLv[lv] = byLv[lv] || {n: 0, pay: 0, en: 0, max: 0, min: 1e12}).n++;
  byLv[lv].pay += pay; byLv[lv].en += en;
  byLv[lv].max = Math.max(byLv[lv].max, pay);
  byLv[lv].min = Math.min(byLv[lv].min, pay);
}
P('══ 1. 委托经济（按等级，报酬单位：金） ══');
P('等级 | 委托数 | 平均报酬 | 平均精力 | 铜/精力 | 最低 | 最高 | 4次/日收入');
for(const lv of ['Lv1','Lv2','Lv3','Lv4','Lv5']){
  const b = byLv[lv]; if(!b) continue;
  const ap = b.pay / b.n, ae = b.en / b.n;
  P(`${lv} | ${b.n} | ${f金(ap)} | ${ae.toFixed(1)} | ${(ap/ae).toFixed(0)} | ${f金(b.min)} | ${f金(b.max)} | ${f金(ap*4)}/日 = ${f金(ap*28)}/周`);
}
const lv5 = byLv['Lv5'];
const lv5Avg = lv5.pay / lv5.n;

/* ════ 2. 金币消耗端（一次性大额） ════ */
const gRows = parseCSV(read('数据表/装备总表.csv'));
const gHead = gRows[0];
const iQ = gHead.indexOf('品质'), iMat = gHead.indexOf('主材料');
const CRAFT = {'普通': 5000, '精良': 30000, '稀有': 150000, '史诗': 600000, '传说': 3000000};
const BP = {'普通': 2000, '精良': 15000, '稀有': 90000, '史诗': 420000, '传说': 5000000};
const cnt = {}, craft = {}, bp = {};
let craftable = 0, totalCraftable = 0;
for(let i = 1; i < gRows.length; i++){
  const r = gRows[i]; if(!r[iQ]) continue;
  totalCraftable++;
  if(r[iMat] === '—') continue;   // 无图纸（专属获取）
  craftable++;
  cnt[r[iQ]] = (cnt[r[iQ]] || 0) + 1;
  craft[r[iQ]] = (craft[r[iQ]] || 0) + CRAFT[r[iQ]];
  bp[r[iQ]] = (bp[r[iQ]] || 0) + BP[r[iQ]];
}
P('');
P('══ 2. 金币消耗端（一次性：图纸 + 加工费；单位：金） ══');
let sumBP = 0, sumCraft = 0;
P('品质 | 可造数 | 图纸总价 | 加工费总额');
for(const q of ['普通','精良','稀有','史诗','传说']){
  P(`${q} | ${cnt[q]} | ${f金(bp[q])} | ${f金(craft[q])}`);
  sumBP += bp[q]; sumCraft += craft[q];
}
P(`合计 | ${craftable} 件（另 ${totalCraftable - craftable} 件专属无图纸） | 图纸 ${f金(sumBP)} | 加工费 ${f金(sumCraft)}`);
P(`一次性金币总池 ≈ 图纸 ${f金(sumBP)} + 加工 ${f金(sumCraft)} + 大师商店 50铂金(=50金×100 → ${f金(50 * 1000000)}) = ${f金(sumBP + sumCraft + 50 * 1000000)}`);
P(`（另有循环消耗：大师商店材料 6铂金/周、铂金商店、交易所买入、活力点兑换 20铂金→500 点）`);

/* ════ 3. 传奇事件 EV 表（旧值 vs v1.59 新值） ════ */
const RATE = {'噩梦': 0.45, '困难': 0.55};   // H≈90 + 满配 E 的典型值（legendRate：0.05+D+H*0.005+0.10+词条）
const LEGENDS = [   // [名, 耗时天, 难度, 旧面额铜, 新面额铜]
  ['屠龙传说',       5, '噩梦', 1 * 1e6,   2 * 1e6],
  ['星界远征',       7, '噩梦', 2 * 1e6,   3 * 1e6],
  ['公会大师试炼',  12, '困难', 500000,    2 * 1e6],
  ['世界树种子',     4, '困难', 1 * 1e6,   1 * 1e6],
  ['魔神封印',       5, '噩梦', 3 * 1e6,   3 * 1e6],
  ['时间回廊',       3, '噩梦', 1.5 * 1e6, 1.5 * 1e6],
  ['陨星核心',       3, '困难', 2 * 1e6,   2 * 1e6],
  ['龙神契约',      12, '噩梦', 5 * 1e6,   7 * 1e6],
  ['虚空王座',       9, '噩梦', 6 * 1e6,   6 * 1e6],
  ['创世碎片',      14, '噩梦', 10 * 1e6,  10 * 1e6],
  ['万龙之宴',      14, '噩梦', 8 * 1e6,   9 * 1e6],
  ['深渊回响',      10, '噩梦', 7 * 1e6,   7 * 1e6],
  ['亡者君王',       6, '噩梦', 4 * 1e6,   4 * 1e6],
  ['硫磺王座',       9, '噩梦', 5 * 1e6,   5 * 1e6],
  ['泰坦苏醒',       7, '噩梦', 4.5 * 1e6, 4.5 * 1e6]
];
// 1/周上限 + 同时 1 个 → 每周可跑次数 = min(1, 7/耗时)
const runsW = d => Math.min(1, 7 / d);
P('');
P('══ 3. 传奇事件：单次 EV 与每周速率（面额×成功率；单位：金） ══');
P('事件 | 耗时 | 难度 | 旧EV/次 | 新EV/次 | 旧EV/周 | 新EV/周 | ΔEV/周');
const LEG = {};
for(const L of LEGENDS){
  const r = RATE[L[2]];
  const evO = L[3] / 10000 * r, evN = L[4] / 10000 * r;
  const wO = evO * runsW(L[1]), wN = evN * runsW(L[1]);
  LEG[L[0]] = {d: L[1], evO, evN, wO, wN};
  P(`${L[0]} | ${L[1]}天 | ${L[2]} | ${evO.toFixed(1)} | ${evN.toFixed(1)} | ${wO.toFixed(1)} | ${wN.toFixed(1)} | ${wN-wO >= 0 ? '+' : ''}${(wN-wO).toFixed(1)}`);
}
const sumOld = LEGENDS.reduce((a, L) => a + LEG[L[0]].wO, 0);
const sumNew = LEGENDS.reduce((a, L) => a + LEG[L[0]].wN, 0);
const sweepOld = LEGENDS.reduce((a, L) => a + LEG[L[0]].evO, 0);
const sweepNew = LEGENDS.reduce((a, L) => a + LEG[L[0]].evN, 0);
P(`全员单次扫一遍 EV：旧 ${sweepOld.toFixed(1)} 金 → 新 ${sweepNew.toFixed(1)} 金（+${(sweepNew/sweepOld*100-100).toFixed(1)}%）`);

/* ════ 4. 玩家阶段：最佳可用传奇 → 每周传奇收入 ════ */
const PROFILE = {
  'P1 早期（屠龙/时间回廊/大师试炼）': ['屠龙传说','时间回廊','公会大师试炼'],
  'P1b 早期+陨星（未做魔神前置）': ['屠龙传说','时间回廊','公会大师试炼','陨星核心'],
  'P2 中期（+陨星/世界树/魔神）': ['屠龙传说','时间回廊','公会大师试炼','陨星核心','世界树种子','魔神封印'],
  'P3 中后期（+星界/虚空/深渊/三新）': ['屠龙传说','时间回廊','公会大师试炼','陨星核心','世界树种子','魔神封印','星界远征','虚空王座','深渊回响','亡者君王','硫磺王座','泰坦苏醒'],
  'P3b 打完三新链但未解锁虚空/深渊': ['屠龙传说','时间回廊','公会大师试炼','陨星核心','世界树种子','魔神封印','星界远征','亡者君王','硫磺王座','泰坦苏醒'],
  'P4 终局（全部 15 个）': LEGENDS.map(L => L[0])
};
P('');
P('══ 4. 各阶段「每周传奇收入」= 已解锁事件中 EV/周 的最大值 ══');
P('阶段 | 旧最佳 | 旧/周 | 新最佳 | 新/周 | Δ/周');
const PROF = {};
for(const k in PROFILE){
  const set = PROFILE[k];
  let bo = null, so = -1, bn = null, sn = -1;
  for(const n of set){
    if(LEG[n].wO > so){ so = LEG[n].wO; bo = n; }
    if(LEG[n].wN > sn){ sn = LEG[n].wN; bn = n; }
  }
  PROF[k] = {bo, so, bn, sn};
  P(`${k} | ${bo} | ${so.toFixed(1)} | ${bn} | ${sn.toFixed(1)} | ${sn-so >= 0 ? '+' : ''}${(sn-so).toFixed(1)}`);
}

/* ════ 5. 方案 B：削弱新传奇（假设回到旧刻度） ════ */
// B 假设：为恢复「旧<新」阶梯而不动旧值，把 v1.57 三事件按 ~30% 下调（4→2.8 / 5→3.5 / 4.5→3.2 铂金，取整 3/3.5/3）
const B_NEW = {'亡者君王': 3 * 1e6, '硫磺王座': 3.5 * 1e6, '泰坦苏醒': 3 * 1e6};
P('');
P('══ 5. 方案 B（削弱 v1.57 新传奇 4→3 / 5→3.5 / 4.5→3 铂金）对各阶段周收入的影响 ══');
P('阶段 | 方案A(v1.59) | 方案B | Δ(A−B)');
const PROF_B = {};
for(const k in PROFILE){
  const set = PROFILE[k];
  let bb = null, sb = -1;
  for(const n of set){
    const ev = B_NEW[n] ? B_NEW[n] / 10000 * RATE['噩梦'] : LEG[n].evN;
    const w = ev * runsW(LEG[n].d);
    if(w > sb){ sb = w; bb = n; }
  }
  PROF_B[k] = {bb, sb};
  P(`${k} | ${PROF[k].sn.toFixed(1)}（${PROF[k].bn}） | ${sb.toFixed(1)}（${bb}） | ${(PROF[k].sn - sb).toFixed(1)}`);
}
// B 方案下「全员扫一遍」EV：旧面额不动 + 三新下调（3 / 3.5 / 3 铂金）
const sweepB = LEGENDS.reduce((a, L) => a + (B_NEW[L[0]] ? B_NEW[L[0]] / 10000 * RATE['噩梦'] : LEG[L[0]].evO), 0);
P(`全员单次扫一遍 EV：A(v1.59) ${sweepNew.toFixed(1)} 金 | 保持旧值 ${sweepOld.toFixed(1)} 金 | 方案B ${sweepB.toFixed(1)} 金（较旧值 ${(sweepB/sweepOld*100-100).toFixed(1)}%）`);

/* ════ 6. 每周总收入与通关周期（终局 Lv5 满勤） ════ */
const questWk = lv5Avg * 4 * 7 / 10000;             // 4 次/日 × 7 天
const settleWk = (96000) / 10000 + (2560000 / 10000 / 30 * 7);   // 周结算 + 月结算摊周
P('');
P('══ 6. 终局（Lv5 满勤）每周金币总收入 ══');
P(`委托 4 次/日：${questWk.toFixed(0)} 金/周（均报酬 ${f金(lv5.pay/lv5.n)}/次）`);
P(`周/月结算摊周：约 ${settleWk.toFixed(1)} 金/周（按高指标档）`);
const legWkA = PROF['P4 终局（全部 15 个）'].sn, legWkOld = PROF['P4 终局（全部 15 个）'].so, legWkB = PROF_B['P4 终局（全部 15 个）'].sb;
P(`传奇（1/周上限）：旧 ${legWkOld.toFixed(1)} → 新(A) ${legWkA.toFixed(1)} → B ${legWkB.toFixed(1)} 金/周`);
const totOld = questWk + settleWk + legWkOld, totA = questWk + settleWk + legWkA, totB = questWk + settleWk + legWkB;
P(`总周收入：旧 ${totOld.toFixed(0)} | A ${totA.toFixed(0)} | B ${totB.toFixed(0)} 金/周`);
const sink = sumBP + sumCraft + 50 * 1e6;
P(`一次性总消耗 ${f金(sink)} 金 → 通关周数：旧 ${(sink/10000/totOld).toFixed(1)} 周 | A ${(sink/10000/totA).toFixed(1)} 周 | B ${(sink/10000/totB).toFixed(1)} 周`);
P(`（A 相对旧的周期差：终局 ${((sink/10000/totOld) - (sink/10000/totA)).toFixed(2)} 周；唯一受影响窗口 = 新解锁传奇且未做陨星/魔神，+22.5 金/周 ≈ 该阶段总收入 +2%；扫一遍 EV 增量 307.5 金 = 一次性总池的 +${(307.5/(sink/10000)*100).toFixed(2)}%）`);

/* ════ 7. 非金币闸门（不受报酬改动影响） ════ */
P('');
P('══ 7. 周期真正的闸门（与报酬无关） ══');
const totalDays = LEGENDS.reduce((a, L) => a + L[1], 0);
P(`传奇全通：15 事件串行（同时仅 1 个）= ${totalDays} 天 ≈ ${(totalDays/7).toFixed(0)} 周 ≈ ${(totalDays/30).toFixed(1)} 个月（最短下限，未计失败重跑）`);
P(`Lv5 经验门槛：30000（累计），传奇经验/周 ≈ 450~2300×成功率`);
P(`数据无关性：A/B 均不改耗时、不改成功率、不改 1/周上限 → 传奇侧日历周期完全不变`);

fs.writeFileSync(ROOT + '创造模式测试原型/_probe_lifespan_out.txt', out.join('\n'), 'utf8');
console.log('done', out.length, 'lines');
