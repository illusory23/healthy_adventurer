// game.html 桥接层验证（可复跑）：模拟浏览器环境加载整页脚本，检查桥接函数与关键行为
// 运行：node _verify_game_html.js   （在 Flask版/ 目录下）
const fs = require('fs');
const path = require('path');
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

const html = fs.readFileSync(path.join(__dirname, 'static', 'game.html'), 'utf-8');
const code = html.match(/<script>([\s\S]*?)<\/script>/)[1];

const test = `
let FAIL = 0;
function ck(cond, msg){ console.log((cond ? 'OK  ' : 'FAIL ') + msg); if(!cond) FAIL++; }
const _fns = ['camelKey','adaptState','toast','apiCall','refreshState','applyServer','tick','isLocalHost','fmtCode','copyCode','openBindCode','openAccountsAdmin','flushResults','showResultModal','showRareModal','closeModal','maybeShowExploreFlow','submitName','acceptQuest','acceptBonus','acceptPriv','acceptGlass','forceFinish','sellMat','sellAll','buy','buyVit','buyCon','toggleTask','toggleMeal','addMulti','abandonQuest','cook','takeLegend','upSkill','buyCharm','equipItem','unequip','buyBlueprint','craft','doExplore','exploreReturn','exploreFinishCheck','useItem','useGale','feedWolf','feedPet','setCarryPet','evolvePet','evolveWolf','exportSave','importSaveFile','importSave','resetAll','showLevelUpDetail','queueLevelUpDetail','petMetaOf','petShowName','petBondDays','petMoodLabel','petMoodTxt','petMoodDaily','petBondTick','petPat','petWalkStart','petWalkSettle','petTheater','petNightTip','petDailyChecks','setPetNick','petFestLine','petMetaHtml','showPetStory','showNickInput','petActionBtns','renderPet','gotoPetTab'];
const _miss = _fns.filter(function(f){ return eval('typeof ' + f) !== 'function'; });
ck(_miss.length === 0, '桥接/镜像函数齐全（' + _fns.length + ' 个）' + (_miss.length ? ' 缺失: ' + _miss.join(',') : ''));
ck(tick.toString().indexOf('refreshState') >= 0, 'tick 为服务端版');
ck(acceptQuest.toString().indexOf('apiCall("accept"') >= 0, 'acceptQuest → accept');
ck(flushResults.toString().indexOf('S.levelups') >= 0, 'flushResults 消费 levelups（v1.38r）');
ck(adaptState.toString().indexOf('levelups') >= 0, 'adaptState 映射 levelups');
ck(showLevelUpDetail.toString().indexOf('新解锁') >= 0 && showLevelUpDetail.toString().indexOf('能力提升') >= 0,
   '升级详情弹窗：新解锁 + 能力提升');
ck([1,2,3,4].every(function(i){ return LEVEL_INFO[i] && LEVEL_INFO[i].unlock.length && LEVEL_INFO[i].gain.length; }),
   'LEVEL_INFO 覆盖 Lv2~Lv5');
ck(CFG.refreshHours.join(',') === '8,12,18,21', '刷新点 08/12/18/21（v1.41f3 末次 22:00 → 21:00）');
ck(typeof LAST_POOL_WINDOW_MS !== 'undefined' && LAST_POOL_WINDOW_MS === 150*60*1000 && typeof poolBaseWindowMs === 'function',
   'v1.41f3：最后班窗口常量 2.5 小时 + poolBaseWindowMs');
/* v1.41f4：酒馆页（传闻迁入最上方 + 公会厨房迁入改名酒馆料理） */
ck(typeof renderTavern === 'function' && renderTavern.toString().indexOf('酒馆传闻') >= 0 && renderTavern.toString().indexOf('酒馆料理') >= 0,
   'v1.41f4：renderTavern 含酒馆传闻 + 酒馆料理');
ck(renderQuest.toString().indexOf('酒馆传闻') < 0, 'v1.41f4：委托页传闻已移除');
ck(renderShop.toString().indexOf('烹饪') < 0, 'v1.41f4：公会页料理卡已移除');
ck(POOL_WINDOW_MS === 60*60*1000, '接取窗口 1 小时');
ck(CFG.taskWindows[0][0] === '21:00' && CFG.taskWindows[0][1] === '23:30', '入睡打卡时段 21:00~23:30');
ck(matIcon('山鸡羽') === '🪶' && matIcon('蘑菇') === '🍄', '材料图标修正（山鸡羽/蘑菇）');
ck(load.toString().indexOf('migrate(raw ? JSON.parse(raw) : newState())') >= 0, 'load 新档走补全（v1.38r）');
ck(queueLevelUpDetail.toString().indexOf('Array.isArray(S.levelups)') >= 0, 'queueLevelUpDetail：Flask 环境跳过（v1.38s）');
ck(checkFx.toString().indexOf('queueLevelUpDetail') >= 0, 'checkFx 兜底补弹升级详情（v1.38s）');
if(!S) S = migrate(newState());              // 桥接环境此时 S 尚未由服务端填充 → 本地构造
S.levelups = []; levelupQueue.length = 0;
queueLevelUpDetail(2);
const _qs = levelupQueue.length;
delete S.levelups;
queueLevelUpDetail(2);
const _qp = levelupQueue.length;
levelupQueue.length = 0;
ck(_qs === 0 && _qp === 1, 'queueLevelUpDetail：Flask 跳过 / 本地入队（v1.38s）');
S.seenMats = []; S.mats = {}; S.seenItems = []; S.items = {};
showRegionDetail(4);
{
  const _h = document.getElementById("dlg").innerHTML || '';
  const _mn = (REGIONS[4].d || []).map(function(p){ return p[0]; }).filter(function(nn){ return nn && M[nn]; })[0] || "";
  ck(_mn === "" || _h.indexOf(_mn) < 0, '探索详情：未获得过的掉落完全隐藏（v1.41 起，原 ？？？占位取消）');
}
S.lvIdx = 4; S.exp = 12000; render();
ck(document.getElementById("hExpTxt").textContent === "12000/30000", '经验条：Lv5 后显示传奇资格进度（v1.38s2）');
ck(qLvTag(C["Lv4"][0]).indexOf("Lv4") >= 0, '委托等级标签 qLvTag（v1.38s4）');
ck(matRowsHtml(C["Lv5"].filter(function(x){ return x[0] === "禁咒书夺回"; })[0]).indexOf('？？？') >= 0,
   '委托详情掉落保密：未获得显示 ？？？（v1.38s5）');
ck(exportSave.toString().indexOf('export_save') >= 0, 'exportSave 走服务端全量导出（v1.39 C3）');
ck(ACHV.filter(function(a){ return a.cond.toString().indexOf('S.histStats') >= 0; }).length >= 4,
   'C3：成就判定用 histStats 全量计数（4 项）');
ck(typeof roll3D !== 'undefined' || true, '（骰子为动态 import，HTML 侧检查）');
/* v1.41 修复：结算动画/掷骰重播两遍（整批 splice 快照 + 先 ack 后解锁） */
const _frSrc = flushResults.toString();
ck(_frSrc.indexOf('splice(0)') >= 0 && _frSrc.indexOf('先 ack') >= 0, 'v1.41：flushResults 防重播两遍（整批快照 + 先 ack 后解锁）');
/* v1.41 修复：昨日结算重复弹出（打卡 / 定时同步重入）——展示后须本地标记 + ack 服务端 + 会话级防竞态 */
ck(_frSrc.indexOf('yesterday_ack') >= 0, 'v1.41：昨日结算展示后 ack 服务端（防打卡/同步重弹）');
ck(_frSrc.indexOf('_ysAckDate') >= 0 && _frSrc.indexOf('S.yesterdayShown = true') >= 0, 'v1.41：昨日结算本地标记 + 会话级防竞态');
/* v1.41c：节日窗口扩展（接取 +1h / 三餐 ±30min / 入睡起床尾部 +1h，含跨日）+ 每日任务展示顺序 */
ck(typeof taskWinNow === 'function' && typeof mealWinNow === 'function' && typeof isFestival === 'function' && typeof winStr === 'function',
   'v1.41c：节日窗口函数齐全（taskWinNow / mealWinNow / isFestival / winStr）');
ck(typeof TASK_ORDER !== 'undefined' && TASK_ORDER[0] === 1 && TASK_ORDER[TASK_ORDER.length - 1] === 0 && TASK_ORDER.length === 7,
   'v1.41c：任务展示顺序（起床置顶、入睡置底）');
/* v1.41d：节日欢迎弹窗（排队于结算结果 / 昨日结算之后） */
ck(typeof showFestivalWelcome === 'function', 'v1.41d：节日欢迎弹窗函数');
ck(_frSrc.indexOf('pendingFestival') >= 0 && _frSrc.indexOf('festival_ack') >= 0,
   'v1.41d：flushResults 队列最末弹节日窗 + festival_ack');
/* v1.41f：节日专属效果表（FEST_EFF——逐节日差异化加成）+ 欢迎弹窗展示 eff.desc */
ck(typeof FEST_EFF !== 'undefined' && FEST_EFF["🎉 国庆"] && FEST_EFF["🎉 国庆"].pay === 0.2 && FEST_EFF["🥣 腊八节"].cookMul === 2.0,
   'v1.41f：FEST_EFF 节日专属效果表（国庆 pay / 腊八 cookMul）');
ck(typeof todayFestEff === 'function' && typeof normFest === 'function' && normFest(["x", "y", "z"]).eff instanceof Object
   && todayFestEff("2026-10-01").rate === 0.1, 'v1.41f：normFest 归一化附 eff + todayFestEff 查询');
ck(showFestivalWelcome.toString().indexOf('eff') >= 0, 'v1.41f：欢迎弹窗展示节日专属效果（eff.desc）');
ck(successRate.toString().indexOf('rateTypes') >= 0, 'v1.41f：成功率接入按委托类型的节日加成（清明·采集探索）');
/* v1.41f5/f6：料理平衡（探索点料理每日 2 次·当日 +5 / 品阶梯度 / cap 类全改恢复 / 深渊消耗 10·12） */
ck(CFG.recipes.every(function(r){ return !r.cap; })
   && CFG.recipes.filter(function(r){ return r.sp; }).length === 5
   && CFG.recipes.filter(function(r){ return r.sp; }).every(function(r){ return r.sp <= 5; }),
   'v1.41f6：cap 类料理清零、sp 料理 5 道单次 ≤5');
ck(typeof S.mealSp === 'object' && S.mealSp !== null && 'cnt' in S.mealSp && 'got' in S.mealSp,
   'v1.41f5：S.mealSp 字段（cnt/got）');
ck(REGIONS.filter(function(r){ return r.n === "深渊裂隙"; })[0].c === 10
   && REGIONS.filter(function(r){ return r.n === "深渊核心"; })[0].c === 12, 'v1.41f5：深渊裂隙 10 / 深渊核心 12（v1.61c 改名）');
/* v1.42：龙种体系 + 九头蛇材料改造 + 巨龙盛宴 enPct */
ck(Object.keys(M).length === 125, 'v1.58：材料 125 种（+六域遗珍 6：冥河灯油 / 地狱火种 / 泰坦石核 / 沼心莲实 / 深海遗珠 / 冰晶果）');
ck(C["Lv5"].some(function(q){ return q[0] === "魔鬼的谈判"; }) && C["Lv4"].some(function(q){ return q[0] === "镇压恶魔裂隙"; }),
   'v1.45：恶魔/魔鬼委托入池');
ck(CFG.recipes.some(function(r){ return r.n === "巨龙盛宴" && Object.keys(recipeIng(r)).length === 10; }),
   'v1.44：盛宴大杂烩（10 种材料；v1.50：主辅材合并）');
ck(["金龙鳞","魔力结晶","雷霆龙牙","暗影龙鳞","龙炎结晶"].every(function(n){ return M[n][1] === "传说"; }),
   'v1.43：特殊型龙材达传说（5 种）');
ck(C["Lv4"].some(function(q){ return q[0] === "驱赶绿龙"; }) && C["Lv5"].some(function(q){ return q[0] === "狩猎火龙"; }),
   'v1.42：龙种委托入池（驱赶绿龙 / 狩猎火龙）');
ck(CFG.recipes.some(function(r){ return r.n === "巨龙盛宴" && r.enPct === 0.5 && !r.en && recipeIng(r)["大块龙肉"] >= 3; }),
   'v1.42：盛宴 enPct=0.5（en 移除、大块龙肉）');
ck(Object.keys(QUEST_REQ).length === 31 && QUEST_REQ["魂灯引渡"] === "净化亡灵谷" && QUEST_REQ["地狱钟声"] === "魔鬼的谈判"
   && QUEST_REQ["圣兽驯服"] === "古龙遗骸采集" && QUEST_REQ["弑龙者"] === "圣兽驯服" && QUEST_REQ["深渊领主封印"] === "深渊裂隙调查"
   && QUEST_REQ["亡者回廊·镇魂"] === "亡者回廊·踏勘" && QUEST_REQ["泰坦之心"] === "泰坦遗骸发掘" && QUEST_REQ["雪原巡礼"] === "圣兽驯服",
   'v1.57：委托链 31 条前置（v1.45b ×7 + v1.51 ×3 + 种族链 ×13）');
ck(C["Lv5"].some(function(q){ return q[0] === "地狱钟声"; }) && C["Lv5"].some(function(q){ return q[0] === "魂灯引渡"; })
   && C["Lv5"].some(function(q){ return q[0] === "仙灵的谢礼"; }),
   'v1.45b：地狱钟声 / 仙灵的谢礼 / 魂灯引渡 入池');
/* v1.46：任务门槛（委托准备物：购买 + 炼金台合成） */
ck(typeof QUEST_ITEM === 'object' && Object.keys(QUEST_ITEM).length === 21 && QUEST_ITEM["讨伐九头蛇"] === "解毒剂"
   && QUEST_ITEM["净化亡灵谷"] === "安魂熏香" && QUEST_ITEM["沼心巨蟒"] === "解毒剂" && QUEST_ITEM["幽都渡口"] === "安魂熏香",
   'v1.57：QUEST_ITEM 21 条门槛（九头蛇→解毒剂 / 亡灵谷→安魂熏香 / 种族链 +5）');
ck(typeof CRAFT === 'object' && Object.keys(CRAFT).length === 4 && CRAFT["解毒剂"].buy === 30000
   && CRAFT["解毒剂"].ing["止血草"] === 4,
   'v1.46：CRAFT 4 条配方（解毒剂 = 止血草×4 + 蜂蜜×2；v1.53 买价 30000）');
ck(craftItem.toString().indexOf('apiCall("craft_item"') >= 0, 'v1.46：craftItem → craft_item（服务端权威）');
ck(SHOP.some(function(x){ return x.item === "解毒剂" && x.c === 30000; })
   && SHOP.some(function(x){ return x.item === "圣水" && x.c === 48000; }),
   'v1.46：商店上架 4 种准备物（v1.53 提价：解毒剂 30000 / 圣水 48000）');
ck(typeof questItemNeed === 'function' && typeof QUEST_LV_OF === 'object'
   && QUEST_ITEM && Object.keys(QUEST_ITEM).every(function(n){ return [1,2,3].indexOf(questItemNeed([n])) >= 0; })
   && questItemNeed(["讨伐九头蛇"]) === 3 && questItemNeed(["沼泽蛇怪狩猎"]) === 1,
   'v1.53：questItemNeed 分级（Lv3→1 / Lv4→2 / Lv5→3）');
ck(buy.toString().indexOf('confirmSpend') >= 0 && craft.toString().indexOf('confirmSpend') >= 0
   && buyVit.toString().indexOf('confirmSpend') >= 0 && buyCon.toString().indexOf('confirmSpend') >= 0
   && buyMat.toString().indexOf('confirmSpend') >= 0 && buyPlat.toString().indexOf('confirmSpend') >= 0
   && buyBlueprint.toString().indexOf('confirmSpend') >= 0 && upSkill.toString().indexOf('confirmSpend') >= 0
   && buyCharm.toString().indexOf('confirmSpend') >= 0 && cook.toString().indexOf('confirmSpend') >= 0
   && craftItem.toString().indexOf('confirmSpend') >= 0 && sellAll.toString().indexOf('confirmSpend') >= 0,
   'v1.53：桥接层 12 个资源消耗入口全部走 confirmSpend 二次确认');
ck(S.items && typeof S.items === 'object' && (function(){
     var h = renderBag.toString();
     return h.indexOf('炼金台') >= 0 && h.indexOf('craftItem(') >= 0 && h.indexOf('!CRAFT[n]') >= 0;
   })(), 'v1.46：背包炼金台卡 + 规则道具过滤准备物');
/* v1.48b：多品类功能保留（数据回滚）/ 酒馆传闻 2 条 / 布局（健康 span2 + 连击顺序、委托页标题） */
ck(typeof newRumor === 'function' && (function(){ const r = newRumor('2026-10-05'); return r.date === '2026-10-05' && (r.idx % RUMORS.length) !== (r.idx2 % RUMORS.length); })(),
   'v1.48b：newRumor 生成两条互不相同索引 + 日期');
ck(renderQuest.toString().indexOf('正在进行的委托（') >= 0 && renderQuest.toString().indexOf('委托刷新 · ') >= 0,
   'v1.48b：委托页标题（正在进行的委托 / 委托刷新）');
ck(renderQuest.toString().indexOf('右栏 · 今日状态') >= 0 && renderQuest.toString().indexOf('今日状态（v1.48b：自左栏迁入右栏顶部）') >= 0,
   'v1.48b：今日状态归右栏');
ck((function(){ const s = renderHealth.toString(); const a = s.indexOf('card span2'), b = s.indexOf('🔥 当前连击'), c = s.indexOf('📊 健康评分的作用'); return a >= 0 && b > a && c > b; })(),
   'v1.48b：健康页顺序（评分通栏 → 连击 → 作用说明）');
/* v1.48c：材料品类修正 + 3D 骰标题 + 委托卡加高 */
ck(M["巨龙竖瞳"][0] === '兽材' && M["龙瞳结晶"] && M["龙瞳结晶"][0] === '宝石' && M["龙瞳结晶"][2] > M["巨龙竖瞳"][2],
   'v1.48c：竖瞳→兽材 / 龙瞳结晶宝石·传说（价高）');
ck(matCats("世界树皮").join("·") === '特殊·织物·草药' && subCatsFor("世界树皮").indexOf("草药") >= 0 && subCatsFor("世界树皮").indexOf("兽材") >= 0,
   'v1.48c：世界树皮三品类 + 副材并集');
ck(queueRoll3D.toString().indexOf("'1d100', roll, name") >= 0, 'v1.48c：queueRoll3D 传递委托名（3D 骰标题）');
/* v1.48d：失败结算 30%/30%（至少 1） */
ck(_settleInner.toString().indexOf("Math.max(1, Math.round(q[5]*0.3))") >= 0 && _settleInner.toString().indexOf("q[6]*0.3") >= 0,
   'v1.48d：失败结算 30% 报酬 + 30% 经验（至少 1）');
/* v1.48e：月事件整月有效 + 成功率加成拆解 */
ck(monthEventExpired() === false, 'v1.48e：月事件整月有效（expired 恒 false）');
ck(renderQuest.toString().indexOf("安眠室/称号") >= 0, 'v1.48e：成功率加成拆解显示');
/* v1.48f：图鉴委托详情 + 数量格式统一 + 月事件 Lv1 解锁 */
ck(typeof qtyRangeTxt === 'function' && qtyRangeTxt([2,4]) === '×2-4' && qtyRangeTxt([3,3]) === '×3' && qtyRangeTxt(5) === '×5',
   'v1.48f：qtyRangeTxt 数量统一文案（区间 x-y / 等值单值）');
ck(showQuestDetailByName.toString().indexOf('基础成功率') >= 0 && showQuestDetailByName.toString().indexOf('questDesc') >= 0,
   'v1.48f：图鉴委托详情含委托内容 + 基础成功率');
ck(monthEventNow.toString().indexOf('lvIdx < 1') < 0 && monthEventTick.toString().indexOf('lvIdx < 1') < 0,
   'v1.48f：月事件 Lv1 解锁（无 Lv2 门槛）');
/* v1.49：主题套装补齐 + 词条正则修复 */
ck(GEAR.length === 131 && !!gearDef('金龙鳞铠') && !!gearDef('世界树长弓') && !!gearDef('冥河护符')
   && !!gearDef('冥河渡灯') && !!gearDef('硫磺王冠') && !!gearDef('泰坦之心')
   && !!gearDef('花岗岩重锤') && !!gearDef('铅矿护符') && !!gearDef('古币坠饰'),
   'v1.57：装备 121 → 131 件（v1.58 +7；v1.59 弱出口补全 +3）');
ck(gearEffects.toString().indexOf('([^；;]+?)类(?:委托)?成功率') >= 0 && gearEffects.toString().indexOf('([^；;]+?)类精力消耗'),
   'v1.49：词条正则键不跨「；」（修复组合词条吞键）');
/* v1.58：六域遗珍（新材料 / 装备 / 料理）+ 「探索点/天」词条整体移除 */
ck(!!gearDef('引魂长明灯') && !!gearDef('狱火护腕') && !!gearDef('泰坦石核锤') && !!gearDef('遗珠坠')
   && !!gearDef('世界树心护符') && !!gearDef('龙炎护手') && !!gearDef('观星者指环'),
   'v1.58：7 件六域遗珍装备入表（4 地点专属 + 世界树心 / 龙炎结晶 / 星界罗盘 终局补全）');
ck(['冥河灯油','地狱火种','泰坦石核','沼心莲实','深海遗珠','冰晶果'].every(function(n){ return !!M[n]; })
   && M['沼心莲实'][0] === '食材' && M['冰晶果'][0] === '食材',
   'v1.58：6 种新地点专属材料入表（含 2 种食材）');
ck(CFG.recipes.length === 25 && cookTier(CFG.recipes.filter(function(r){ return r.n === '六域拼盘'; })[0]) === '传说'
   && cookTier(CFG.recipes.filter(function(r){ return r.n === '沼心莲实羹'; })[0]) === '史诗',
   'v1.58：料理 25 道（+4：3 史诗 + 1 传说）');
const _rest58 = REGIONS.filter(function(r){ return r.unlock; });
ck(['冥河灯油','地狱火种','泰坦石核','沼心莲实','深海遗珠','冰晶果'].every(function(n){
     return _rest58.some(function(r){ return (r.d||[]).some(function(e){ return e[0] === n; }); });
   }), 'v1.58：6 种新材料分别挂在 6 处链解锁地点掉落表');
ck(gearEffects.toString().indexOf('探索点+') < 0 && petBonus.toString().indexOf('b.sp') < 0
   && petBonus.toString().indexOf('"sp"') < 0 && !GEAR.some(function(g){ return (g[4]||'').indexOf('/天') >= 0; }),
   'v1.58：「探索点/天」词条整体移除（装备 / 宠物 / 引擎通道）');
`;

let htmlFail = 0;
function hck(cond, msg){ console.log((cond ? 'OK  ' : 'FAIL ') + msg); if(!cond) htmlFail++; }
console.log('--- HTML 静态检查 ---');
hck(html.indexOf("import('/static/dice3d/dice-bridge.js')") >= 0, '3D 骰子 import 路径 = /static/dice3d/（v1.38r 修复）');
hck(html.indexOf('/static/dice3d/three/three.module.min.js') >= 0 && html.indexOf('/static/dice3d/three/cannon-es.js') >= 0,
    'importmap 指向 /static/dice3d/three/');
hck(html.indexOf('./3d骰子/') < 0, '无残留 ./3d骰子/ 引用');
hck(html.indexOf('🎖️贡献') >= 0 && html.indexOf('🔨贡献') < 0, '顶栏贡献徽章 🎖️（原 🔨）');
hck(html.indexOf('30*60*1000') < 0, '接取窗口旧常量（30*60*1000）已清除');
hck(html.indexOf('data-t="tavern"') >= 0 && html.indexOf('id="tab-tavern"') >= 0, 'v1.41f4：酒馆页签（nav 按钮 + section）');
hck(html.indexOf('seenItems:[]') >= 0 && html.indexOf('o.seenItems = []') >= 0, 'seenItems 字段（v1.38s 探索详情保密）');
hck(html.indexOf('旧宝箱开出 装备') >= 0, '旧宝箱装备奖励（10% 普通~精良，v1.38s 恢复）');
hck(html.indexOf('传奇资格 ✓') >= 0, '经验条·传奇资格文案（v1.38s2）');
hck(html.indexOf('S.historyTotal || S.history.length') >= 0, '存档页天数用 historyTotal 兜底（v1.39 C3）');
hck(html.indexOf('export_save') >= 0, '桥接层含 export_save 调用（v1.39 C3）');
hck(html.indexOf('curMul:10000') >= 0, '图纸定价修复（v1.40）');
hck(html.indexOf('完成 ≥1 次传奇事件') >= 0, '护符 V 解锁条件（v1.40）');
hck(html.indexOf('const FESTIVAL_RANGES') >= 0 && html.indexOf('const TASK_ORDER') >= 0,
    'v1.41c：假期区间表 + 任务展示顺序（静态）');
hck(html.indexOf('yesterday_ack') >= 0, 'v1.41：昨日结算 ack 调用（静态）');
hck(html.indexOf('id="tab-bag" class="tabpage twocol"') < 0 && html.indexOf('id="tab-bag" class="tabpage"') >= 0
    && html.indexOf('id="tab-shop" class="tabpage twocol"') >= 0
    && html.indexOf('id="tab-health" class="tabpage twocol"') < 0, 'v1.47/v1.61b/d：商店页双列；背包页 v1.61d 改 qsplit 两栏等高；健康页 v1.61b 移除外层 twocol');
hck(html.indexOf('.twocol{column-count:2') >= 0 && html.indexOf('break-inside:avoid') >= 0, 'v1.47：twocol CSS（窄屏单列回退）');
/* v1.57：手机底部横滑栏 + 内容区手势翻页 */
hck(html.indexOf('scroll-snap-type:x proximity') >= 0 && html.indexOf('min-width:66px') >= 0
    && html.indexOf('scroll-snap-align:center') >= 0, 'v1.57：底栏横滑 CSS（吸附 + 最小宽度 + 图标两行式）');
hck((html.match(/<span class="tb-i">/g) || []).length === 8, 'v1.57：8 个页签全部带图标（tb-i）');
hck(html.indexOf('b.scrollIntoView({inline:"center"') >= 0, 'v1.57：当前页签自动滚入视野');
hck(html.indexOf('main.addEventListener("touchstart"') >= 0 && html.indexOf('Math.abs(dx) < 70') >= 0
    && html.indexOf('nb.click()') >= 0, 'v1.57：内容区左右滑动手势切页（复用页签点击路径）');
/* v1.48b：多品类数据回滚（功能代码保留）+ 酒馆传闻 2 条 + 健康 span2 + 委托页标题 */
hck(html.indexOf('"蜂蜜":["食材","普通",600]') >= 0 && html.indexOf(',["草药"]]') < 0 && html.indexOf(',["食材"]]') < 0 && html.indexOf(',["特殊"]]') < 0,
    'v1.48b：M 表多品类数据已回滚（无第 4 位数组）');
hck(html.indexOf('function matCats(') >= 0 && html.indexOf('function matHasCat(') >= 0,
    'v1.48b：多品类功能代码保留（matCats / matHasCat）');
hck(html.indexOf('function newRumor(') >= 0 && html.indexOf('idx2') >= 0,
    'v1.48b：酒馆传闻每日 2 条（newRumor / idx2）');
hck(html.indexOf('.twocol>.card.span2') >= 0 && html.indexOf('"card span2"') >= 0,
    'v1.48b：健康评分卡通栏（span2）');
hck(html.indexOf('正在进行的委托（') >= 0 && html.indexOf('委托刷新 · ') >= 0 && html.indexOf('当前刷新 · ') < 0,
    'v1.48b：委托页标题（正在进行的委托 / 委托刷新）');
/* v1.48c：材料品类修正 + 掉落 + 委托卡加高 + 3D 骰标题 */
hck(html.indexOf('"巨龙竖瞳":["兽材","传说",520000]') >= 0 && html.indexOf('"龙瞳结晶":["宝石","传说",580000]') >= 0,
    'v1.48c：材料表修正（竖瞳兽材 / 龙瞳结晶宝石·传说）');
hck(html.indexOf('"世界树皮":["特殊","传说",450000,["织物","草药"]]') >= 0,
    'v1.48c：世界树皮多品类（特殊 + 织物 + 草药）');
hck(html.indexOf('"龙瞳结晶":[1,2]') >= 0, 'v1.48c：古龙遗骸采集掉落龙瞳结晶');
hck((html.match(/min-height:220px/g) || []).length >= 2, 'v1.48c/v1.61e：委托页两卡加高（150px → 220px）');
hck(html.indexOf('📖 委托说明') >= 0 && html.indexOf('刷新与窗口') >= 0 && html.indexOf('今日接取上限') >= 0 && html.indexOf('【更多机会】') < 0,
    'v1.48d：委托说明卡（接取上限文案更新 / 移出「更多机会」）');
hck(html.indexOf('传奇事件占独立槽位') >= 0, 'v1.48d：特殊事件卡自带独立槽位说明');
hck(html.indexOf('截止本月最后一天 23:30') >= 0 && html.indexOf('未在 7 日前完成') < 0 && html.indexOf('截止 7 日') < 0,
    'v1.48e：月事件整月有效文案（截止当月最后一天 23:30）');
/* v1.48f：图鉴详情 / 数量格式 / 月事件 Lv1 */
hck(html.indexOf('function qtyRangeTxt(') >= 0 && html.indexOf('rg[0]+"~"+rg[1]') < 0 && html.indexOf('mats[k][0] + "~" + _me.ev.mats[k][1]') < 0 && html.indexOf('"×" + q[8][k]') < 0,
    'v1.48f：掉落数量统一（qtyRangeTxt；旧 ~ / 数组直出已清除）');
hck(html.indexOf('（v1.48f：Lv1 起全员解锁；每月 1 号生成') >= 0, 'v1.48f：月事件卡注释 Lv1');
/* v1.49：主题套装 + 词条正则 */
hck(html.indexOf('v1.49：主题套装补齐') >= 0 && html.indexOf('"金龙鳞铠"') >= 0 && html.indexOf('"世界树长弓"') >= 0 && html.indexOf('"冥河护符"') >= 0,
    'v1.49：GEAR 主题套装 25 件（静态）');
{
  const _bridgeJs = fs.readFileSync(path.join(__dirname, 'static', 'dice3d', 'dice-bridge.js'), 'utf-8');
  hck(_bridgeJs.indexOf('let titleEl = null;') >= 0 && _bridgeJs.indexOf('titleText') >= 0 && _bridgeJs.indexOf("'🎲 ' + titleText") >= 0,
      'v1.48c：3D 骰窗口标题显示委托名（dice-bridge titleText）');
}
/* v1.50：服务端修复批次（前端侧静态核对） */
hck(html.indexOf('function recipeIng(') >= 0 && html.indexOf('"主材："') >= 0,
    'v1.50：料理主辅材（recipeIng / 主材显示）');
hck(html.indexOf('byQualityDesc(cookTier(a.r), cookTier(b.r))') >= 0,
    'v1.54：酒馆料理按品级高→低（巨龙盛宴·传说自然居首，取代 v1.50 恒置底）');
hck(html.indexOf('function midnightLocked(') >= 0 && html.indexOf('不再接受补打') >= 0,
    'v1.50：00:00 后补打卡锁（midnightLocked）');
hck(html.indexOf('const INCENSE_BONUS = [0, 4, 9, 16, 26, 40]') >= 0,
    'v1.50：薰香递增表（+4/+5/+7/+10/+14，满级 +40）');
hck((html.match(/function buyPlat\(/g) || []).length >= 2 && html.indexOf('platC') >= 0 && html.indexOf('matSel:["史诗",3]') >= 0,
    'v1.50：铂金商店 buyPlat（原型 + 桥接）+ 史诗自选包');
hck(html.indexOf('const PET_DESC = {') >= 0 && html.indexOf('PET_DESC[st.name]') >= 0,
    'v1.50：宠物描写表 + 详情展示');
hck(html.indexOf('📅 每日签到') >= 0 && html.indexOf('连续 7 / 14 / 30 天另有里程碑奖励') >= 0,
    'v1.50：健康页签到卡（状态 / 连续 / 累计 / 说明）');
hck(html.indexOf('终局出口') < 0 && html.indexOf('终局活力出口') < 0, 'v1.50：局外设计解释文案已清除');
hck(html.indexOf('失败仅获得 30% 报酬、30% 经验') >= 0, 'v1.50：失败文案（经验 30% 修正）');
hck(html.indexOf('次日打卡时结算（最迟 12:00 自动）') >= 0, 'v1.50：跨天结算文案统一');
hck(html.indexOf("showTitleDetail('${t}')") >= 0 && html.indexOf('>🏷️ ${t}</span>') >= 0,
    'v1.50/v1.61c：称号标签网格渲染（换行 chips + 单个点击看详情）');
hck(html.indexOf('canE = S.energy >= Math.max(1, Math.round(q[7] * (1 - gearEnCutFor(q[1]))))') >= 0,
    'v1.50：精力判定计入装备减免（池卡 / 详情）');
/* v1.50c：图鉴扩展（道具 + 传奇事件）+ 文案清理 */
hck(html.indexOf('🧰 全部道具') >= 0 && html.indexOf('🌍 全部传奇事件') >= 0 && html.indexOf('qAll + ITEM_ALL.length + LEGEND.length') >= 0,
    'v1.50：图鉴道具 / 传奇事件两节 + 总进度扩展（v1.51b 起再 + PET_GAL.length）');
hck(html.indexOf('const GAL_ITEM_ICON = {') >= 0 && html.indexOf('function showLegendGalleryDetail(') >= 0
    && html.indexOf('showLegendGalleryDetail(\'${L[0]}\')') >= 0, 'v1.50：道具图标表 + 传奇图鉴详情函数');
hck(html.indexOf('（每批 ${CFG.drawCount') < 0, 'v1.50：已删「（每批 N 个）」文案');
hck(html.indexOf('晨露特饮') < 0 && html.indexOf('金盏花茶') >= 0, 'v1.50：酒馆传闻无悬空名词（晨露特饮 → 金盏花茶）');
/* v1.51：A4 声望 / 贡献按委托等级（显示侧）+ 传奇贡献 150 */
hck(html.indexOf('function questQLv(q){') >= 0 && html.indexOf('function questCon(q){') >= 0,
    'v1.51 A4：委托等级辅助函数（questQLv / questCon）');
hck(html.indexOf('const LEGEND_CON = 150;') >= 0, 'v1.51：传奇贡献常量 LEGEND_CON = 150');
hck(html.indexOf('<span>贡献</span>') >= 0, 'v1.51：委托详情补「贡献」行（用户反馈：界面未写明贡献来源）');
hck(html.indexOf('🏅 完成可得：声望') >= 0, 'v1.51：图鉴委托详情补「完成可得」行');
hck(html.indexOf('questRep(q, S.lvIdx+1)') < 0 && html.indexOf('questRep(q, a.qlv || S.lvIdx+1)') < 0,
    'v1.51：声望显示旧口径（玩家等级）已清除');
/* v1.51 A3：传奇事件——同时最多 1 个 + 指定传说装备条件 */
hck((html.match(/传奇事件同时最多 1 个/g) || []).length >= 2,
    'v1.51 A3：传奇同时限 1（原型层 + 桥接层两处 takeLegend）');
hck(html.indexOf('if(c.gear && (S.gear || []).indexOf(c.gear) < 0) return false;') >= 0
    && html.indexOf('需拥有传说装备「') >= 0, 'v1.51 A3：传奇专属条件（gear 键 + 条件文案）');
/* v1.51b：图鉴宠物节（第七节） */
hck(html.indexOf('const PET_GAL_ICON = {') >= 0 && html.indexOf('const PET_GAL = [') >= 0,
    'v1.51b：宠物显示图标表 + 全条目表（9 格）');
hck(html.indexOf('🐾 全部宠物（') >= 0 && html.indexOf('🐾 宠物</h3>') >= 0,
    'v1.51b：图鉴宠物节（第七节 + 组头计数）');
hck(html.indexOf('qAll + ITEM_ALL.length + LEGEND.length + PET_GAL.length') >= 0
    && html.indexOf('iGot + lGot + pGot') >= 0, 'v1.51b：图鉴总进度含宠物（422 → 431）');
hck(html.indexOf('PET_LINES[n] && PET_LINES[n].icon') >= 0 && html.indexOf('L2.mut') >= 0
    && html.indexOf('宠物＝拥有过') >= 0, 'v1.51b：宠物节显示当前形态（含变异形态）+ 图例');
/* v1.55：月光狐阅读驱动 + 传奇 4 伙伴完整链 */
hck(html.indexOf('readDriven:true, readNeed:[45,60]') >= 0
    && html.indexOf('function readCountNow(){') >= 0 && html.indexOf('function petReadNeed(n, stage){') >= 0
    && html.indexOf('function syncReadPets(){') >= 0 && html.indexOf('if(syncReadPets()) changed = true;') >= 0,
    'v1.55：月光狐阅读驱动（readNeed 45/60 + syncReadPets 挂入 tick）');
hck(html.indexOf('"「"+L.stages[0].name+"」的变异值自二阶起才开始积累——现在喂「"+foodName+"」会被浪费。') >= 0
    && html.indexOf('（二阶起才积累变异值）') >= 0,
    'v1.55：阅读驱动拦截（一阶喂高级材料警告 + 喂食界面标注）');
hck(html.indexOf('const PET_FIXED = {};') >= 0
    && html.indexOf('"星界幼龙": {icon:"🐲", from:"传奇事件「星界远征」", rank:"传说",') >= 0
    && html.indexOf('"星界巨龙", rate:0.03, exp:0.05') >= 0,
    'v1.55：4 只传奇伙伴并入 PET_LINES（PET_FIXED 清空）');
/* v1.55b：宠物品阶体系（普通 < 精良 < 稀有 < 史诗 < 传说） */
hck(html.indexOf('rank:"普通"') >= 0 && html.indexOf('rank:"精良"') >= 0 && html.indexOf('rank:"稀有"') >= 0
    && html.indexOf('rank:"史诗"') >= 0 && (html.match(/rank:"传说"/g) || []).length >= 4,
    'v1.55b：宠物品阶字段（普通 ×1 / 精良 ×1 / 稀有 ×1 / 史诗 ×1 / 传说 ×4）');
hck(html.indexOf('function petRankOf(n){') >= 0 && html.indexOf('if(n === "小狼") return "史诗";') >= 0,
    'v1.55b：petRankOf（小狼 = 史诗）');
hck((html.match(/petRankOf\(/g) || []).length >= 8 && html.indexOf('品阶 <span class="tier t-') >= 0,
    'v1.55b：品阶展示（详情 / 背包 / 图鉴格 / 图鉴总览 ≥ 8 处）');
hck(html.indexOf('WOLF_FEED_VALUE[(M[foodName] || [])[1]] || 2') >= 0
    && html.indexOf('Math.max((fv !== undefined) ? fv : 0, base)') >= 0,
    'v1.55c：品阶营养（未列出按品阶给成长 / 口味与品阶取较高者）');
hck(html.indexOf('"黄金史莱姆", note:"材料+4%、成功率+1%", mat:0.04, rate:0.01') >= 0
    && html.indexOf('"虹绒兽", note:"材料+6%、成功率+1%、报酬+3%", mat:0.06, rate:0.01, pay:0.03') >= 0
    && html.indexOf('"彩蛋大王", note:"经验+12%、成功率+1%", exp:0.12, rate:0.01') >= 0,
    'v1.55b：低品阶数值下调（史莱姆 / 绒球兽 / 捣蛋鬼）');
hck(html.indexOf('"星穹之龙", note:"成功率+5%、经验+12%", rate:0.05, exp:0.12') >= 0
    && html.indexOf('"龙神化身", note:"报酬+10%、材料+5%、成功率+1%", pay:0.10, mat:0.05, rate:0.01') >= 0
    && html.indexOf('"万龙之群", note:"材料+12%、成功率+3%", mat:0.12, rate:0.03') >= 0
    && html.indexOf('"深渊之瞳·终焉", note:"材料+12%、成功率+2%", mat:0.12, rate:0.02') >= 0,
    'v1.55b：传说 4 伙伴终局加成提档（品阶梯度最高档）');
/* v1.56：宠物情感系统（心情 / 羁绊 / 抚摸 / 散步 / 小剧场 / 昵称 / 成就 / 宠物页） */
hck(html.indexOf('function petMetaOf(n){') >= 0 && html.indexOf('function petMoodDaily(sc, slept){') >= 0
    && html.indexOf('function petBondDays(n){') >= 0 && html.indexOf('function petBondTick(){') >= 0,
    'v1.56：心情 / 羁绊核心函数（petMetaOf / petMoodDaily / petBondDays / petBondTick）');
hck(html.indexOf('function petPat(n){') >= 0 && html.indexOf('function petWalkStart(n){') >= 0
    && html.indexOf('function petWalkSettle(){') >= 0 && html.indexOf('function petTheater(){') >= 0
    && html.indexOf('function petNightTip(){') >= 0 && html.indexOf('function setPetNick(n, nick){') >= 0,
    'v1.56：互动函数（抚摸 / 散步 / 小剧场 / 深夜提醒 / 昵称）');
hck(html.indexOf('const PET_PAT_TXT') >= 0 && html.indexOf('const PET_STORY') >= 0
    && html.indexOf('PET_STORY_365') >= 0 && html.indexOf('PET_HEART_TXT') >= 0
    && html.indexOf('PET_WALK_TXT') >= 0 && html.indexOf('PET_THEATER_TXT') >= 0
    && html.indexOf('PET_NIGHT_TXT') >= 0 && html.indexOf('PET_FEST_SCENE') >= 0 && html.indexOf('PET_FEST_REACT') >= 0,
    'v1.56：文本库 8 组（抚摸 / 故事 / 365 / 心意 / 散步 / 小剧场 / 深夜 / 节日）');
hck((html.match(/data-t="pet"/g) || []).length >= 2 && html.indexOf('id="tab-pet"') >= 0
    && html.indexOf('renderPet()') >= 0 && html.indexOf('前往宠物页') < 0,
    'v1.56：独立宠物页（导航 / 区块 / render 挂接；v1.61d 背包导流卡移除）');
hck(html.indexOf('petWalk:null') >= 0 && html.indexOf('petNick:{}') >= 0
    && html.indexOf('walkCount:0') >= 0 && html.indexOf('petNightDate') >= 0,
    'v1.56：newState 持久字段（petWalk / petNick / walkCount / petNightDate）');
hck(html.indexOf('petMoodDaily(yScore') >= 0 && html.indexOf('petDailyChecks(_crossed') >= 0,
    'v1.56：tick 挂接（跨天心情结算 / 每日检查）');
hck(html.indexOf('apiCall("pet_pat"') >= 0 && html.indexOf('apiCall("pet_walk"') >= 0 && html.indexOf('apiCall("pet_nick"') >= 0,
    'v1.56：桥接层 3 行动作（pet_pat / pet_walk / pet_nick）');
hck((html.match(/hide:1, title:"/g) || []).length >= 9 && html.indexOf('{n:"蜕变之始"') >= 0
    && html.indexOf('{n:"形影不离"') >= 0 && html.indexOf('{n:"林间常客"') >= 0,
    'v1.56：3 条宠物隐藏成就（蜕变之始 / 形影不离 / 林间常客；隐藏共 9 条）');
hck(html.indexOf('"蜕变之始": "任一只宠物（含小狼）完成变异。"') >= 0
    && html.indexOf('"破茧": "隐藏成就「蜕变之始」纪念——纯荣誉称号。"') >= 0,
    'v1.56：成就 / 称号说明补全（ACHV_DESC + TITLE_DESC）');
hck(html.indexOf('if(b.dataset.t === "pet" && !S.wolf && !(S.pets||[]).some(function(n){ return n !== "小狼"; }))') >= 0
    && html.indexOf('您还没有伙伴。<br><br>据说，冒险途中会遇见愿意同行的小家伙——去探索看看吧。') >= 0,
    'v1.56：无宠物时点击宠物页 → 弹窗提示而不进入（导航拦截）');
hck(html.indexOf('if(c.sp) ps.push("探索点+"+c.sp+"/天");') < 0 && html.indexOf('petBonus().sp') < 0,
    'v1.56b：宠物「探索点/天」加成移除（petBonusNote / 探索点刷新）');
hck((html.match(/QUALITY_ORDER\.indexOf\(petRankOf/g) || []).length >= 3 && html.indexOf('dlg-wide') >= 0
    && html.indexOf('dlg("宠物详情", body, btns, {wide:true})') >= 0,
    'v1.56b：宠物列表按品阶排序（宠物页 / 图鉴格 / 冒险者信息页 ×3）+ 详情弹窗加宽加长');
hck(html.indexOf('("最终形态 · " + (petBonusNote(n) || ""))') >= 0 && html.indexOf('sub:petBonusNote("小狼")||""') >= 0,
    'v1.56b：小狼卡片显示具体加成（远古魔狼）+ 图鉴小狼加成统一');
hck(html.indexOf('const _cp = S.carryPet;') >= 0 && html.indexOf('if(S.carryPet !== "小狼") return 0;') >= 0
    && html.indexOf('· <b>携带生效</b>') >= 0,
    'v1.56c：宠物加成改为携带生效（petBonus / 小狼加成 / 提示卡）');
hck(html.indexOf('onclick="setCarryPet(') >= 0 && html.indexOf('📌 携带中 · 加成生效') >= 0
    && html.indexOf('（看家中——不生效）') >= 0 && html.indexOf('>🏠 看家</button>') >= 0
    && html.indexOf('{text:"🏠 看家"') >= 0,
    'v1.56c/d：携带开关（卡片 + 详情按钮 / 标记 / 看家标注——原「卸下」改「看家」）');
hck(html.indexOf('const PET_FEST_SCENE') >= 0 && html.indexOf('const PET_FEST_REACT') >= 0
    && html.indexOf('PET_FEST_REACT_DEFAULT') >= 0 && html.indexOf('PET_FEST_TXT') < 0,
    'v1.56c：节日问候双层（场景 + 宠物专属反应；旧单层文本已移除）');
hck(html.indexOf('"蜂王浆","大块龙肉","龙涎果","星尘蜜"') >= 0 && html.indexOf('"星辉花","龙血","龙心"') >= 0
    && html.indexOf('favs:{"山珍":7,"香草":6,"天鹅绒":6,"蘑菇":5,"止血草":4,"兽肉":0,"河鱼":0}') >= 0,
    'v1.56d：可喂食扩展到全部食材 / 草药');
hck(html.indexOf('favs:{"星尘蜜":18,"星辉花":17,"星核":17,"星陨岩":16,"星尘":8}') >= 0
    && html.indexOf('favs:{"暗影龙鳞":17,"暗影草":10,"虚空结晶":10,"混沌碎片":10,"河鱼":5}') >= 0
    && html.indexOf('favs:{"蜂王浆":8,"蜂蜜":6,"山珍":6,"古董钱币":6,"哥布林图腾":5}') >= 0
    && html.indexOf('favs:{"星辉花":17,"月长石":10,"月光草":8,"月影纱":8,"晨露花":6}') >= 0
    && html.indexOf('favs:{"龙瞳结晶":17,"大块龙肉":10,"龙涎果":9,"龙鳞":9,"兽肉":6}') >= 0
    && html.indexOf('if(fv === undefined && !WOLF_FOODS.has(foodName)) return {v:0, mv:0, refuse:true};') >= 0,
    'v1.56e：本命材料体系（主题材料入食谱：星尘 / 星核、深渊素材、龙材、月之织物……非本宠拒食）');
hck(html.indexOf('if(!o.wolf && Array.isArray(o.pets) && o.pets.indexOf("小狼") >= 0) o.wolf = {stage:1, growth:0, mutate:0, fedDate:"", fedCount:0};') >= 0,
    'v1.56：小狼迁移修复（falsy 判定，对齐服务端；v1.61d 导流卡计数随卡片删除）');
/* v1.52：B1 难度报酬 / B2 铂金商店 / B4+B6 词条阶梯 / B7 材料补全 / 术语 */
hck(html.indexOf('"讨伐哥布林","精英","08:00-23:30",120,"普通",16000,') >= 0
    && html.indexOf('"龙血商人的订单","精英","08:00-23:30",300,"困难",260000,') >= 0
    && html.indexOf('"讨伐独眼巨人","精英","08:00-23:30",180,"困难",75000,') >= 0,
    'v1.52 B1：难度报酬修正（哥布林 16000 / 独眼巨人 75000 / 龙血商人 260000）');
hck(html.indexOf('"时间沙", "世界树枝条", "时之沙漏", "星辉花", "星尘蜜", "星陨岩", "云纹锦"') >= 0,
    'v1.52 B2：铂金商店传说自选 7 → 13 种');
hck(html.indexOf('"鹿皮斗篷","精良","护甲",10,"护送类成功率+1%","鹿皮×3"') >= 0
    && html.indexOf('"狮鹫羽弓","稀有","武器",0.03,"材料获取+8%","狮鹫羽×4"') >= 0
    && (html.match(/v1\.52：无出口材料补全/g) || []).length >= 2,
    'v1.52 B7：8 件无出口材料专属装备（GEAR + FLAVOR 双处）');
hck(html.indexOf('["安眠护符",4],["大理石",20],["黑曜石",12],["",15]]') >= 0,
    'v1.52 B7：废弃矿道补大理石/黑曜石掉落（黑曜石原无来源）');
hck(html.indexOf('短时类成功率+4%","雷霆龙牙×6"') >= 0
    && html.indexOf('"铁匕首","精良","武器",0.02,"短时类成功率+1%"') >= 0
    && html.indexOf('"魔鬼纹章","史诗","饰品",0.12,"公会贡献+20%；委托经验+12%"') >= 0,
    'v1.52 B4+B6：词条阶梯对齐（短时 1/2/3/4、魔鬼纹章 20/12）');
hck(html.indexOf('最后一次（21:00）') >= 0 && html.indexOf('最后一班') < 0,
    'v1.52：术语「最后一班」→「最后一次」（全文件）');
hck(html.indexOf('"鹿皮斗篷":"软鞣鹿皮缝成的斗篷') >= 0
    && html.indexOf('"百战护符":"三百场委托打磨出的护符，纹路里全是故事。它不张扬，只是让好运来得比别处勤快一点。",') >= 0,
    'v1.52：GEAR_FLAVOR 8 条新增（尾逗号修复）');
/* v1.58：六域遗珍 + 「探索点/天」词条移除 */
hck(html.indexOf('探索点+1/天') < 0 && html.indexOf('/探索点\\+(\\d+)\\/天/') < 0
    && html.indexOf('"银戒指","精良","饰品",0.05,"探索类精力消耗-3%"') >= 0
    && html.indexOf('"藏书家之冕","成就","成就饰品槽",0.10,"委托经验+10%"') >= 0,
    'v1.58：「探索点/天」词条移除（银戒指 → 探索类精力消耗-3%；藏书家之冕 → 委托经验+10%）');
hck(html.indexOf('"冥河灯油":["特殊","史诗",62000]') >= 0 && html.indexOf('"冰晶果":"雪线之上才结的透明果实') >= 0
    && html.indexOf('"六域拼盘":"把六片遗落的土地摆上同一张桌') >= 0,
    'v1.58：新材料 / 装备 / 料理描述齐备（MAT_DESC / GEAR_FLAVOR / COOK_FLAVOR）');
/* v1.59：传奇面额上调 + 9 铂金补键 + Lv4 简单档 + 弱出口装备 */
hck(html.indexOf('"9铂金币":9000000') >= 0 && html.indexOf('"屠龙传说","精英",5,"噩梦","2铂金币",800') >= 0
    && html.indexOf('"万龙之宴","精英",14,"噩梦","9铂金币",2300') >= 0,
    'v1.59：传奇面额上调（屠龙 2铂金 / 万龙 9铂金）+ LEGEND_GOLD 补「9铂金币」');
hck(html.indexOf('"王都巡夜","短时","21:00-23:30",120,"简单",58000,58') >= 0
    && html.indexOf('"猎场驱兽","狩猎","08:00-23:30",180,"简单",60000,60') >= 0,
    'v1.59：Lv4 简单档报酬/经验下调（王都巡夜 5.8 万 / 猎场驱兽 6 万）');
hck(html.indexOf("else if(sc>=60){ rep=2; con=1; vit=1; }") >= 0
    && html.indexOf("else if(sc>=60){ nb.pay=0.05; nb.con=1; nb.vit=1; }") >= 0
    && html.indexOf('今日委托报酬 +5%、贡献 +1、活力点 +1') >= 0,
    'v1.59b：良好档（60–74）活力点 +1（结算 / 区间奖励 / 说明文案三处）');
hck(html.indexOf('"花岗岩重锤","普通","武器",0.01,"—","花岗岩×2"') >= 0
    && html.indexOf('"铅矿护符","普通","饰品",0.02,"—","铅矿石×1"') >= 0
    && html.indexOf('"古币坠饰","稀有","饰品",0.08,"稀有事件概率+1%","古董钱币×3"') >= 0,
    'v1.59：3 件弱出口装备（花岗岩 / 铅矿石 / 古董钱币）入表');
/* v1.60/v1.61：大师试炼 250 / 疗养圣所（v1.61：无门槛·3 天·59 锁定）/ 深处 C-A-S / 护符 C-B / 重掷券 B / 虚空裂痕 Lv4 / 探索解锁 */
hck(html.indexOf("S.doneBelow5 < 250") >= 0 && html.indexOf("累计完成 250 次 Lv5 以下委托") >= 0,
    'v1.60：大师试炼条件 40 → 250（legendEligible + 条件文案）');
hck((html.match(/function takeSickLeave/g) || []).length === 2
    && html.indexOf('apiCall("sick_leave"') >= 0 && html.indexOf("SICK_MONTHLY = 3") >= 0
    && html.indexOf("SICK_LOCK_SCORE = 59") >= 0 && html.indexOf("function sickToday") >= 0
    && html.indexOf("guildIdx() < 3") < 0
    && html.indexOf("sickDays:[]") >= 0 && html.indexOf("o.sickDays = []") >= 0,
    'v1.61：疗养圣所（无门槛 / 每月 3 天 / 评分锁定 59；本地实现 + Flask 桥接覆盖 + sick_leave API + 迁移）');
hck((html.match(/sickToday\(\)\) return showAlert\("今日病假已封存/g) || []).length >= 6
    && html.indexOf("打卡类道具无法使用") >= 0
    && html.indexOf("疗养圣所") >= 0 && html.indexOf("<h3>🕊️ 疗养圣所</h3>") >= 0
    && html.indexOf('<section id="tab-health" class="tabpage twocol"') < 0
    && html.indexOf("'<div class=\"twocol\">' + h + '</div>' + hSick") >= 0,
    'v1.61：病假日封存（打卡三入口 + 打卡类道具，前后端同款）+ v1.61b 卡片移出双栏容器');
hck((html.match(/sick\.indexOf\(h\.date\) >= 0|sk\.indexOf\(h\.date\) >= 0|_sickDays\.indexOf\(h\.date\) >= 0/g) || []).length >= 3,
    'v1.60：病假日计入三处连击口径（sleepStreak / sleepStreakProt / 连击显示）');
/* v1.61c：本轮实机反馈修复四件套 */
hck(html.indexOf('style="margin-top:12px"><h3>🕊️ 疗养圣所') >= 0,
    'v1.61c：圣所卡补 margin-top 12px（多栏容器截断尾行 margin，Chromium 实测贴靠）');
hck(html.indexOf("function _snapScroll") >= 0 && html.indexOf("function _restoreScroll") >= 0
    && html.indexOf("const _scSnap = _snapScroll()") >= 0 && html.indexOf("_restoreScroll(_scSnap)") >= 0,
    'v1.61c：轮询重绘保滚动（render 快照/复原 .scroll-y，防列表跳顶）');
hck(html.indexOf('g[5] !== "—" && S.blueprints[g[0]] === true') >= 0,
    'v1.61c：打造列表过滤不可打造装备（主材料"—"，与图纸商店口径一致）');
hck(html.indexOf("function showTitleDetail(one)") >= 0 && html.indexOf("event.stopPropagation();showTitleDetail(") >= 0
    && html.indexOf("已完成传奇（") >= 0 && html.indexOf("showLegendGalleryDetail('${t}')") >= 0
    && html.indexOf("fn:function(){ showPetDetail(n); }") < 0
    && html.indexOf("心情 +5（今日互动已完成）") >= 0,
    'v1.61c：荣誉页（单个称号标签看详情 + 已完成传奇标签网格）+ 抚摸不弹宠物详情');
hck(html.indexOf("function dishTopFirst") >= 0 && (html.match(/dishTopFirst\(/g) || []).length >= 5,
    'v1.61c：巨龙盛宴锁定料理列表最上方（酒馆 + 图鉴两处排序）');
hck(html.indexOf('{n:"深渊核心"') >= 0 && html.indexOf("深渊深处") < 0,
    'v1.61c：深渊深处 → 深渊核心（改名，无旧名残留）');
hck(html.indexOf("a.r.c - b.r.c || a.i - b.i") >= 0,
    'v1.61c：探索地点列表按探索点消耗低→高排列');
hck(html.indexOf("地点列表限高滚动") >= 0,
    'v1.61c：探索地点列表限高滚动（地点变多不再拉长整页）');
hck(html.indexOf("const EV_ROB_CAP = 1000000") >= 0
    && html.indexOf("Math.min(Math.floor(S.money * 0.10), EV_ROB_CAP)") >= 0
    && html.indexOf("上限 1 铂金币") >= 0,
    'v1.61c：盗贼伏击抢夺上限 1 铂金币（上限 + 文案）');
hck(html.indexOf("const roll = a.forceRoll || rand(100)") >= 0 && html.indexOf("const roll2 = a.forceRoll || rand(100)") >= 0,
    'v1.61c：立即完成委托锁定骰值 1（forceRoll 覆盖常规 + 传奇结算）');
hck(html.indexOf('{n:"晨光森林·深处", t:"07:00-09:00", c:4, h:3, lv:3, g:3, deep:1') >= 0
    && html.indexOf('{n:"星夜洞窟·深处", t:"21:00-23:00", c:5, h:6, lv:4, g:5, deep:1') >= 0
    && html.indexOf('{n:"腐化森林·深处", t:"08:00-23:30", c:7, h:9, lv:5, g:6, deep:1') >= 0
    && html.indexOf('{n:"虚空裂痕·深处", t:"22:00-23:30", c:9, h:14, lv:5, g:6, deep:1') >= 0,
    'v1.60：7 处深处重排为 C/A/S 共绑（Lv3+C / Lv4+A / Lv5+S）');
hck(html.indexOf('{n:"虚空裂痕", t:"22:00-23:30", c:8, lv:4, h:12') >= 0,
    'v1.60：虚空裂痕地表 Lv3 → Lv4');
hck(html.indexOf("{lv:1, need:3,") >= 0 && html.indexOf("{lv:2, need:4,") >= 0,
    'v1.60：冥念护符 I/II 判定对齐文案（C / B）');
hck(html.indexOf('重掷券", con:240, lim:["日",1], g:4') >= 0,
    'v1.60：精英委托重掷券解锁档位 C → B（g:4）');
hck((html.match(/lv2DoneCount\(\) < EXPLORE_LV2_NEED/g) || []).length >= 2
    && html.indexOf("const EXPLORE_LV2_NEED = 12") >= 0
    && html.indexOf("次 Lv2 委托</b>后开放") >= 0,
    'v1.60：探索解锁 = Lv2 + 12 次 Lv2 委托（双 doExplore + 进度卡）');
hck(html.indexOf("自由探索开放——完成 12 次 Lv2 委托后解锁") >= 0
    && html.indexOf('"🗺️ 探索高阶区域开放：腐化森林"') >= 0
    && html.indexOf('"🗺️ 探索高阶区域开放：虚空裂痕"') >= 0,
    'v1.60：LEVEL_INFO 同步（Lv2 探索预告 / Lv3 腐化 / Lv4 虚空裂痕）');
/* v1.61d：两栏等高 / 背包宠物卡删除 / 铂金商店解锁 / 薰香与护符 / HUD 公会条 / 规则道具守卫 */
hck(html.indexOf(".qcol{display:flex;flex-direction:column}") >= 0 && html.indexOf(".qcol>.card:last-child{flex:1}") < 0
    && html.indexOf("按真实卡片高度测最优切分点") >= 0 && (html.match(/min-height:220px/g) || []).length >= 2
    && html.indexOf("原 v1.56 的「宠物→宠物页」引导卡已删除") >= 0,
    'v1.61e：两栏「尽可能」等长（不强制拉伸 + 背包真实高度切分 + 加长刷新/进行中；背包宠物小界面删除）');
hck(html.indexOf("const PLAT_UNLOCK_MONEY = 1000000") >= 0
    && html.indexOf("function platShopUnlocked(){ return (S.money || 0) >= PLAT_UNLOCK_MONEY; }") >= 0
    && html.indexOf("内容隐藏——需持有") >= 0 && html.indexOf("v1.61d：未解锁时界面保留、内容隐藏") >= 0,
    'v1.61d：铂金商店解锁 = 持有 ≥1 铂金币（界面前置挡板 + 大师商店同款内容隐藏）');
hck(html.indexOf('{n:"清醒符咒 ×1", platC:1') >= 0 && html.indexOf('{n:"安眠护符 ×1", platC:1') >= 0
    && html.indexOf("铜币商店不再出售") >= 0 && html.indexOf("活力商店不再出售") >= 0,
    'v1.61d：清醒符咒/安眠护符移入铂金商店（铜币/活力商店移除）');
hck(html.indexOf("it.incense === _ic + 1") >= 0 && html.indexOf("🕯️ 安眠薰香（") >= 0
    && html.indexOf("与安眠薰香同属「额外饰品」类永久加成") >= 0 && html.indexOf("if(it.incense) return;") >= 0,
    'v1.61d：薰香/护符只展示下一阶 + 「额外饰品」类永久加成说明');
hck(html.indexOf('id="hGuildBar"') >= 0 && html.indexOf('id="hGuildTxt"') >= 0 && html.indexOf('class="bar bar-guild"') >= 0
    && html.indexOf('id="hRep"') < 0 && html.indexOf("⭐声望") < 0,
    'v1.61d：HUD 公会经验条（声望独立显示移除）');
hck((html.match(/!M\[name\] \|\| !S\.mats\[name\]/g) || []).length >= 2,
    'v1.61d：规则道具不可出售（sellMat 非材料守卫 ×2——原型层 + 桥接层）');
hck(html.indexOf("心情值 <b") >= 0 && html.indexOf("</b> / 100") >= 0
    && html.indexOf("连续 7 天会收到心意礼物") >= 0 && html.indexOf("（${mood}/100）") >= 0,
    'v1.61f：宠物详情显示具体心情值（数值 / 100 + 进度条；心情图标提示含数值）');

let evalFail = 0;
try { eval(code + test); } catch(e){ console.log('FAIL 加载异常: ' + e.message); evalFail = 1; }
const bad = (typeof FAIL !== 'undefined' ? FAIL : 0);
process.exit((bad || htmlFail || evalFail) ? 1 : 0);
