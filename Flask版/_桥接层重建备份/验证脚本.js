// 桥接层恢复验证：模拟浏览器环境加载整页脚本，检查桥接函数与关键行为
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
  querySelectorAll: () => [],
  querySelector: () => fakeEl(),
  addEventListener: () => {},
  body: { appendChild(){}, removeChild(){} },
  createElement: () => fakeEl(),
  title: ""
};
global.window = {};
global.navigator = {};
global.location = { hostname: "localhost" };
global.alert = () => {};
global.confirm = () => true;
global.setInterval = () => 0;
global.fetch = async () => { throw new Error("no server in test"); };
global.AudioContext = function(){ return { state:"running", currentTime:0, resume(){},
  createOscillator(){ return { type:"", frequency:{}, connect(){}, start(){}, stop(){} }; },
  createGain(){ return { gain:{ setValueAtTime(){}, exponentialRampToValueAtTime(){} }, connect(){} }; } }; };

const html = fs.readFileSync(__dirname + '/_game_new.html', 'utf-8');
const code = html.match(/<script>([\s\S]*?)<\/script>/)[1];

const test = `
const _fns = ['camelKey','adaptState','toast','apiCall','refreshState','applyServer','tick','isLocalHost','fmtCode','copyCode','openBindCode','openAccountsAdmin','flushResults','showResultModal','showRareModal','closeModal','maybeShowExploreFlow','submitName','acceptQuest','acceptBonus','acceptPriv','acceptGlass','forceFinish','sellMat','sellAll','buy','buyVit','buyCon','toggleTask','toggleMeal','addMulti','abandonQuest','cook','takeLegend','upSkill','buyCharm','equipItem','unequip','buyBlueprint','craft','doExplore','exploreReturn','exploreFinishCheck','useItem','useGale','feedWolf','feedPet','setCarryPet','evolvePet','evolveWolf','exportSave','importSaveFile','importSave','resetAll'];
const _miss = _fns.filter(function(f){ return eval('typeof ' + f) !== 'function'; });
console.log('缺失函数: ' + (_miss.length ? _miss.join(',') : '无 ✓ (共 ' + _fns.length + ' 个全部存在)'));
const _t = [
  ['tick 为服务端版', tick.toString().indexOf('refreshState') >= 0],
  ['acceptQuest → accept', acceptQuest.toString().indexOf('apiCall("accept"') >= 0],
  ['acceptBonus 带 idx', typeof acceptBonus === 'function' && acceptBonus.toString().indexOf('bonusQuests') >= 0],
  ['acceptPriv/acceptGlass 存在', acceptPriv.toString().indexOf('accept_priv') >= 0 && acceptGlass.toString().indexOf('accept_glass') >= 0],
  ['doExplore → explore', doExplore.toString().indexOf('apiCall("explore"') >= 0],
  ['exploreReturn → explore_return', exploreReturn.toString().indexOf('explore_return') >= 0],
  ['exploreFinishCheck 已置空', exploreFinishCheck.toString().length < 120],
  ['takeLegend → take_legend', takeLegend.toString().indexOf('take_legend') >= 0],
  ['useItem → use_item', useItem.toString().indexOf('use_item') >= 0],
  ['cook → cook', cook.toString().indexOf('apiCall("cook"') >= 0],
  ['craft → craft', craft.toString().indexOf('apiCall("craft"') >= 0],
  ['buyBlueprint → blueprint', buyBlueprint.toString().indexOf('"blueprint"') >= 0],
  ['sellAll → sell_all', sellAll.toString().indexOf('sell_all') >= 0],
  ['buy 批量版', buy.toString().indexOf('n:n') >= 0],
  ['toggleTask → checkin', toggleTask.toString().indexOf('"checkin"') >= 0],
  ['feedWolf → feed_wolf', feedWolf.toString().indexOf('feed_wolf') >= 0],
  ['setCarryPet → set_carry_pet', setCarryPet.toString().indexOf('set_carry_pet') >= 0],
  ['importSaveFile 存在', importSaveFile.toString().indexOf('import_save') >= 0],
  ['exportSave v1.38d 版', exportSave.toString().indexOf('delete snap.account') >= 0],
  ['maybeShowExploreFlow 含 explore_choice', maybeShowExploreFlow.toString().indexOf('explore_choice') >= 0],
  ['flushResults 含 pendingLegend', flushResults.toString().indexOf('pendingLegend') >= 0]
];
_t.forEach(function(row){ console.log((row[1] ? 'OK  ' : 'FAIL') + ' ' + row[0]); });
// toast 调用冒烟
try { toast('恢复验证'); console.log('OK  toast 可调用'); } catch(e){ console.log('FAIL toast: ' + e.message); }
// 时钟提醒区（镜像层保留）检查
console.log('checkReminders 类型: ' + typeof checkReminders);
console.log('remindSeen 类型: ' + typeof (typeof remindSeen !== 'undefined' ? remindSeen : null));
`;
eval(code + test);
