
/* ══════════════════════════════════════════════════
   ★ Flask 桥接层
   状态由服务端（SQLite + 补算引擎）权威提供。
   本段重定义原型的存档 / 补算 / 动作函数为 API 调用——同名函数声明，
   后声明生效，覆盖上方原型实现（原实现保留作参考，不再被调用）。
   ══════════════════════════════════════════════════ */

/* ── 状态适配：服务端 snake_case → 原型 S 结构 ── */
function camelKey(k){ return k.replace(/_([a-z])/g, function(_, c){ return c.toUpperCase(); }); }
function adaptState(sv){
  const out = {};
  for(const k in sv) out[camelKey(k)] = sv[k];
  // 日志：服务端 {ts,msg,cls} → 原型 {t,m,c}
  out.log = (sv.log || []).map(function(e){
    const d = new Date(e.ts);
    return { t:(d.getMonth()+1+"").padStart(2,"0")+"-"+(d.getDate()+"").padStart(2,"0")+" "+hhmm(d),
             m:e.msg, c:e.cls || "" };
  });
  out.results = sv.results || [];
  out.pendingRare = sv.pending_rare || [];
  out.exploreResult = sv.explore_result || null;
  out.pendingEvent = sv.pending_event || null;
  out.eventResult = sv.event_result || null;
  out.legendPool = null;
  return out;
}

/* ── 轻提示（展示服务端消息） ── */
let _toastEl = null, _toastTimer = null;
function toast(msg){
  if(!_toastEl){
    _toastEl = document.createElement("div");
    _toastEl.style.cssText = "position:fixed;left:50%;bottom:78px;transform:translateX(-50%);z-index:500;"
      + "background:rgba(28,28,38,.97);border:1px solid var(--line);border-radius:10px;padding:8px 16px;"
      + "font-size:12.5px;color:var(--gold2);max-width:86vw;text-align:center;pointer-events:none;opacity:0;transition:opacity .25s";
    document.body.appendChild(_toastEl);
  }
  _toastEl.textContent = msg;
  _toastEl.style.opacity = "1";
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(function(){ _toastEl.style.opacity = "0"; }, 2600);
}

/* ── API 通讯 ── */
async function apiCall(action, data){
  const r = await fetch("/api/action", { method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify(Object.assign({action:action}, data || {})) });
  const j = await r.json().catch(function(){ return { error:"无法连接服务器" }; });
  if(!j.state){
    showAlert(j.error || "无法连接服务器", "提示");
    if(j.gate) setTimeout(function(){ location.reload(); }, 1200);   // 口令失效 → 回访问验证页
    return j;
  }
  applyServer(j);
  if(j.error) showAlert(j.error);
  return j;
}
async function refreshState(){
  const r = await fetch("/api/state", {cache:"no-store"});
  const j = await r.json().catch(function(){ return {}; });
  if(!j.state){
    if(j.gate) setTimeout(function(){ location.reload(); }, 600);     // 口令失效 → 自动回验证页
    return j;
  }
  applyServer(j);
  return j;
}
function applyServer(j){
  S = adaptState(j.state);
  S.account = j.account || S.account;          // v1.37：账号（接入码）
  (j.msgs || []).forEach(function(m){ toast(m); });
  render();
  if(!S.name) showIntro(); else hideIntro();   // v1.37：接入码找回后自动进入游戏
  flushResults();
  maybeShowExploreFlow();
}
/* tick 覆盖：原型本地补算 → 服务端 catch_up */
async function tick(){ await refreshState(); }

/* ── 账号（v1.37：设备自动登录 + 接入码换绑） ── */
function isLocalHost(){ const h = location.hostname; return h === "localhost" || h === "127.0.0.1" || h === "::1" || h === ""; }
function fmtCode(c){ c = String(c || ""); return c.length === 8 ? c.slice(0,4) + "-" + c.slice(4) : c; }
function copyCode(){
  const c = (S.account || {}).code || "";
  if(!c) return showAlert("暂未获取到接入码，请刷新页面再试。", "账号");
  const txt = fmtCode(c);
  function fallback(){ showAlert("接入码：<b style='letter-spacing:2px'>" + txt + "</b><br><br>请手动记录（换设备时要用）", "账号"); }
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(function(){ toast("✅ 已复制 " + txt); }, fallback);
  } else fallback();
}
function openBindCode(){
  dlg("输入其他接入码",
    '<div class="muted" style="font-size:12px;line-height:1.8;margin-bottom:10px">'
    + '在<b>其他设备</b>的「冒险者信息 → 账号」页查看它的接入码（形如 K7F2-9QZ3）。<br>'
    + '输入后本设备将切换为该账号（当前若为全新空档会顺手清理）。</div>'
    + '<input id="bindCodeInput" maxlength="12" placeholder="K7F2-9QZ3（可不带分隔线）" autocomplete="off"'
    + ' style="width:100%;box-sizing:border-box;padding:11px;border-radius:9px;border:1px solid var(--line);background:var(--panel2);color:var(--txt);font-size:15px;text-align:center;letter-spacing:2px">',
    [{text:"取消"},
     {text:"绑定", cls:"pri", fn:function(){
        const el = document.getElementById("bindCodeInput");
        const v = el ? el.value : "";
        if(!v.trim()) return;
        apiCall("bind_code", { code: v });
     }}]);
}
function openAccountsAdmin(){
  fetch("/api/accounts").then(function(r){ return r.json(); }).then(function(j){
    if(!j.ok) return showAlert(j.error || "无法获取账号列表", "账号管理");
    let bh = '<div style="max-height:50vh;overflow-y:auto">';
    (j.accounts || []).forEach(function(a){
      const last = a.last_login ? new Date(a.last_login).toLocaleString() : "从未登录";
      bh += '<div style="padding:9px 2px;border-bottom:1px solid var(--line)">'
        + '<b>' + (a.name || "（未命名）") + '</b>　<span style="color:var(--gold2);letter-spacing:1px">' + fmtCode(a.code) + '</span>'
        + (a.migrated ? ' <span style="color:var(--orange);font-size:11px">待认领</span>' : '')
        + '<br><span class="muted" style="font-size:11px">最近登录：' + last + '</span></div>';
    });
    bh += '</div><div class="muted" style="font-size:11px;margin-top:8px;line-height:1.7">'
       + '仅本机（localhost）可见。把某人账号的接入码告诉他，他就能在新设备上找回自己的进度。</div>';
    dlg("🖥️ 本机账号管理", bh);
  }).catch(function(){ showAlert("无法连接服务器", "账号管理"); });
}

/* ── 结算结果 / 稀有事件弹窗队列（服务端驱动；播 3D 骰子后逐条展示） ── */
let _queueBusy = false, _resultResolve = null;
function flushResults(){
  if(_queueBusy) return;
  if(document.getElementById("modal").classList.contains("on")) return;
  _queueBusy = true;
  (async function(){
    let consumed = false;
    while(S.results && S.results.length){
      consumed = true;
      const r = S.results.shift();                 // UI 侧消费（消费完统一 ack）
      await queueRoll3D(r.roll);
      await questAnimWait(r);                      // v1.35：emoji 迷你动画
      await showResultModal(r);
    }
    while(S.pendingRare && S.pendingRare.length){
      consumed = true;
      const ev = S.pendingRare.shift();
      await showRareModal(ev);
    }
    if(S.pendingLegend){
      consumed = true;
      const pl = S.pendingLegend;
      S.pendingLegend = null;                      // 本地清空防重复；服务端随 results_ack 落库
      await new Promise(function(resolve){
        dlg("特殊事件",
          "<div style='text-align:center;font-size:15px;color:var(--gold);margin-bottom:8px'>⚡ 触发特殊事件！</div>"
          + (pl.preview
              ? "你隐约听见【" + pl.title + "】「" + pl.name + "」的低语——尚未达到参与条件，只能远远望见（仅预览）。<br><br>到「冒险者委托」页 · 特殊事件窗口查看详情。"
              : "【" + pl.title + "】「" + pl.name + "」已出现。<br><br>到「冒险者委托」页 · 特殊事件窗口查看详情并接取。"),
          [{text:"确定", cls:"pri", fn:resolve}]);
      });
    }
    _queueBusy = false;
    if(consumed){ await apiCall("results_ack"); return; }
    // 昨日快照（优先级最低）
    if(S.yesterday && !S.yesterdayShown && !document.getElementById("dlg").classList.contains("on")){
      showYesterday();
    }
  })();
}
function showResultModal(r){
  return new Promise(function(resolve){
    _resultResolve = resolve;
    showResult(r.name, r.roll, r.need, r.title, r.gold, r.exp, r.got, r.cls);
  });
}
function showRareModal(ev){
  return new Promise(function(resolve){
    dlg("稀有事件",
      "<div style='text-align:center;font-size:15px;color:var(--gold);margin-bottom:8px'>✨ " + ev.name + "</div>" + ev.msg,
      [{text:"确定", cls:"pri", fn:resolve}]);
  });
}
function closeModal(){
  document.getElementById("modal").classList.remove("on");
  const f = _resultResolve; _resultResolve = null;
  if(f) f();
  setTimeout(flushResults, 260);
}

/* ── 探索结果 / 探索事件弹窗流（服务端驱动） ── */
function maybeShowExploreFlow(){
  if(_queueBusy) return;
  if(document.getElementById("modal").classList.contains("on")) return;
  if(document.getElementById("dlg").classList.contains("on")) return;
  if(S.exploreResult){
    const er = S.exploreResult;
    dlg("探索 · " + er.region, '<div class="dlg-msg">' + er.msg + '</div>',
      [{text:"确定", cls:"pri", fn:function(){ apiCall("explore_ack"); }}]);
    return;
  }
  if(S.pendingEvent){
    const pe = S.pendingEvent;
    const btns = (pe.options && pe.options.length ? pe.options : [{label:"确定", accept:1, pri:1}]).map(function(o){
      return {text:o.label, cls:o.pri ? "pri" : "", fn:function(){ apiCall("explore_choice", {accept: o.accept ? 1 : 0}); }};
    });
    dlg(pe.title || ("🧭 " + pe.name), '<div class="dlg-msg">' + pe.text + '</div>', btns);
    return;
  }
  if(S.eventResult){
    const evr = S.eventResult;
    dlg(evr.title || "探索事件", '<div class="dlg-msg">' + evr.text + '</div>',
      [{text:"确定", cls:"pri", fn:function(){ apiCall("event_ack"); }}]);
    return;
  }
}

/* ── 动作（API 版：保留原型的前置校验与文案，状态变更交给服务端） ── */
function submitName(){
  const el = document.getElementById("nameInput");
  const v = (el.value || "").trim();
  if(!v) return showAlert("请输入冒险者之名");
  hideIntro();
  apiCall("name", {name:v.slice(0,12)});
}
function acceptQuest(idx){
  const q = S.pool && S.pool.list ? S.pool.list[idx] : null;
  if(!q) return;
  if(S.pool.taken) return showAlert("本次刷新已接取过了");
  if(poolExpired()) return showAlert("本批委托已失效。<br><br>接取窗口为刷新后 <b>30 分钟</b>内（本批刷新点："+S.pool.point.split("@")[1]+":00）。<br>等下一个刷新点再来。");
  const limit = dailyLimitNow();
  if(S.accepted >= limit) return showAlert("今日接取已达上限（"+limit+" 个）");
  const simCap = simCapNow();
  if(S.active.length >= simCap) return showAlert("同时进行的委托已达上限 "+simCap+" 个");
  const enCost = Math.max(1, Math.round(q[7] * (1 - gearEnCutFor(q[1]))));
  if(S.energy < enCost) return showAlert("精力不足：需要 "+enCost+"，当前 "+S.energy);
  apiCall("accept", {idx:idx});
}
function acceptBonus(idx){
  const q = S.bonusQuests && S.bonusQuests[idx];   // v1.38p：6 选 1
  if(!q) return;
  const enCost = Math.max(1, Math.round(q[7] * (1 - gearEnCutFor(q[1]))));
  if(S.energy < enCost) return showAlert("精力不足：需要 "+enCost+"，当前 "+S.energy, "公会额外委托");
  apiCall("accept_bonus", {idx:idx});
}
function acceptPriv(){
  const q = S.privQuest;                     // v1.38o：W 级公会特权委托（第 5 次名额）
  if(!q) return;
  const limit = dailyLimitNow();
  if(S.accepted >= limit) return showAlert("今日接取已达上限（"+limit+" 个）");
  const simCap = simCapNow();
  if(S.active.length >= simCap) return showAlert("同时进行的委托已达上限 "+simCap+" 个");
  const enCost = Math.max(1, Math.round(q[7] * (1 - gearEnCutFor(q[1]))));
  if(S.energy < enCost) return showAlert("精力不足：需要 "+enCost+"，当前 "+S.energy, "公会特权委托");
  apiCall("accept_priv");
}
function acceptGlass(){
  const q = S.glassQuest;                    // v1.38o：时间沙漏委托（装备特权名额）
  if(!q) return;
  const limit = dailyLimitNow();
  if(S.accepted >= limit) return showAlert("今日接取已达上限（"+limit+" 个）");
  const simCap = simCapNow();
  if(S.active.length >= simCap) return showAlert("同时进行的委托已达上限 "+simCap+" 个");
  const enCost = Math.max(1, Math.round(q[7] * (1 - gearEnCutFor(q[1]))));
  if(S.energy < enCost) return showAlert("精力不足：需要 "+enCost+"，当前 "+S.energy, "时间沙漏委托");
  apiCall("accept_glass");
}
function forceFinish(i){ /* 完成判定由服务端 catch_up 处理；保留函数名供调试 */
  refreshState();
}
function sellMat(name){
  if(!canTrade()) return showAlert("交易所尚未开放");
  if(!S.mats[name]) return;
  apiCall("sell", {name:name});
}
function sellAll(){
  if(!canTrade()) return showAlert("交易所尚未开放");
  let cnt = 0; for(const k in S.mats) cnt += S.mats[k];
  if(!cnt) return showAlert("背包里没有材料");
  apiCall("sell_all");
}
function buy(i, n){
  n = Math.max(1, Math.floor(+n || 1));
  const it = SHOP[i];
  if(S.money < it.c * n) return showAlert("铜币不足（需要 "+fmtMoney(it.c*n)+"，当前 "+fmtMoney(S.money)+"）");
  apiCall("buy", {idx:i, n:n});
}
function buyVit(i, n){
  n = Math.max(1, Math.floor(+n || 1));
  const it = VIT_SHOP[i];
  if(it.incense) n = 1;
  if(it.incense && (S.incense||0) + 1 !== it.incense)
    return showAlert("安眠薰香需要按顺序逐级升级（当前 "+(S.incense||0)+" 级）。", "安眠薰香");
  if(S.vit < it.vit * n) return showAlert("活力点不足（需要 "+it.vit*n+"，当前 "+S.vit+"）", "活力点兑换");
  apiCall("buy_vit", {idx:i, n:n}).then(function(j){
    if(!j.error) showAlert("已兑换「"+it.n+"」"+(n>1?" ×"+n:"")+"。" + (it.incense ? "<br><br>永久精力上限 +4（当前 薰香 "+j.state.incense+" 级）" : ""), "活力点兑换");
  });
}
function buyCon(i, n){
  n = Math.max(1, Math.floor(+n || 1));
  const it = CON_SHOP[i];
  if(S.con < it.con * n) return showAlert("贡献不足（需要 "+it.con*n+"，当前 "+S.con+"）", "贡献商店");
  apiCall("buy_con", {idx:i, n:n}).then(function(j){
    if(!j.error) showAlert("已兑换「"+it.n+"」"+(n>1?" ×"+n:"")+"。", "贡献商店");
  });
}
function toggleTask(i){
  const _scB = (S.health && S.health.score) || 0;      // v1.35：打卡反馈飘字
  const on = S.health.done[i];
  const win = CFG.taskWindows[i];
  if(!on && win && !inWindowNow(win))    // v1.28：窗口外预检（服务端同样校验）
    return showAlert("「"+CFG.tasks[i][0]+"」不在打卡时段。<br><br>可打卡时段："+win[0]+"–"+win[1], "健康打卡");
  apiCall("checkin", {idx:i}).then(function(){
    const _d = ((S.health && S.health.score) || 0) - _scB;
    if(_d) floatText((_d>0?"+":"") + _d + " 健康", _d>0 ? "var(--gold2)" : "var(--red)");
    if(_d > 0) sfxCheckin();                              // v1.38：打卡音效
  });
}
function toggleMeal(idx){
  const _scB = (S.health && S.health.score) || 0;      // v1.35：打卡反馈飘字
  const meals = (S.health && S.health.meals) || [0,0,0];
  const win = CFG.mealWindows[idx];
  if(!meals[idx] && !inWindowNow(win))   // v1.28：窗口外预检
    return showAlert("「"+MEAL_NAMES[idx]+"」不在打卡时段。<br><br>可打卡时段："+win[0]+"–"+win[1], "健康打卡");
  apiCall("meal", {idx:idx}).then(function(){
    const _d = ((S.health && S.health.score) || 0) - _scB;
    if(_d) floatText((_d>0?"+":"") + _d + " 健康", _d>0 ? "var(--gold2)" : "var(--red)");
    if(_d > 0) sfxCheckin();                              // v1.38：打卡音效
  });
}
function addMulti(i, delta){
  const _scB = (S.health && S.health.score) || 0;      // v1.35：打卡反馈飘字
  apiCall("multi", {idx:i, delta:delta}).then(function(){
    const _d = ((S.health && S.health.score) || 0) - _scB;
    if(_d) floatText((_d>0?"+":"") + _d + " 健康", _d>0 ? "var(--gold2)" : "var(--red)");
    if(_d > 0) sfxCheckin();                              // v1.38：打卡音效
  });
}
function abandonQuest(i){
  const a = S.active[i];
  if(!a) return;
  const isLegend = !!a.legend;
  const msg = "确定放弃「"+a.name+"」吗？<br><br>"
    + "· 立即释放进行中名额<br>"
    + "· <b style='color:var(--red)'>不返还</b>已扣除的精力<br>"
    + (isLegend ? "· <b style='color:var(--red)'>不返还</b>本周的传奇事件接取次数<br>" : "")
    + "· 无任何报酬 / 经验 / 声望";
  showConfirm(msg, function(){
    apiCall("abandon", {idx:i, name:a.name}).then(function(j){
      if(!j.error) showAlert("已放弃「"+a.name+"」。", "放弃委托");
    });
  }, "放弃委托");
}
function cook(i){
  const r = CFG.recipes[i];
  if(!canCook(r)) return showAlert("材料不足，无法烹饪「"+r.n+"」。<br><br>需要："+
    Object.keys(r.ing).map(function(k){ return k+" ×"+r.ing[k]; }).join("、"), "公会厨房");
  apiCall("cook", {idx:i});
}
function takeLegend(){
  const L = S.legendActive;
  if(!L) return;
  if(S.legendPreview) return showAlert("🔮 这只是低语中的幻影——尚未达到参与条件，传奇事件无法接取，也无法参与。<br><br>继续成长吧，它会在未来等你。", S.legendName);
  if(S.legendWeek === weekKey()) return showAlert("本周已经接取过"+S.legendName+"了。<br><br>每周最多接取 1 次，下周再来。", S.legendName);
  if(S.active.length >= simCapNow()) return showAlert("同时进行的委托已满。", S.legendName);
  apiCall("take_legend");
}
function upSkill(name){
  const cur = S.skills[name] || 0;
  if(cur >= 5) return showAlert("「"+name+"」已经满级了。", "技能树");
  if(skillTotal() >= skillCap()) return showAlert("技能树总级数已达当前公会等级的上限（"+skillCap()+" 级）。<br><br>提升公会等级可解锁更多级数。", "技能树");
  const cost = SKILL_COST[cur];
  if(S.con < cost) return showAlert("贡献不足（需要 "+cost+"，当前 "+S.con+"）", "技能树");
  apiCall("skill", {name:name});
}
function buyCharm(){
  const i = S.charm;
  if(i >= 5) return showAlert("冥念护符已满级。", "冥念护符");
  const c = CHARM[i];
  if(!charmUnlocked(i)) return showAlert("尚未解锁第 "+(i+1)+" 级。<br><br>需要：" + c.req, "冥念护符");
  if(S.vit < c.cost) return showAlert("活力点不足（需要 "+c.cost+"，当前 "+S.vit+"）", "冥念护符");
  apiCall("charm").then(function(j){
    if(!j.error) showAlert("冥念护符升至 <b>"+j.state.charm+" 级</b>。<br><br>委托报酬 +"+Math.round(c.pay*100)+"%<br>委托成功率 +"+Math.round(c.rate*100)+"%", "冥念护符");
  });
}
function equipItem(name){ apiCall("equip", {name:name}); }
function unequip(slot){ apiCall("unequip", {slot:slot}); }
function buyBlueprint(name){
  const g = gearDef(name); if(!g) return;
  if(g[5] === "—") return showAlert("「"+name+"」没有图纸，只能通过成就或事件获得。", "图纸");
  if(S.blueprints[name]) return showAlert("已经拥有「"+name+"图纸」了。", "图纸");
  const info = bpInfo(name);
  if(guildIdx() < info.guild)
    return showAlert("公会等级不足。<br><br>「"+name+"图纸」需要公会 <b>"+CFG.guildName[info.guild]+" 级</b>，当前 "+guildName()+" 级。", "图纸");
  if(S.money < info.price)
    return showAlert("钱不够。<br><br>需要 "+fmtMoneyFull(info.price)+"。", "图纸");
  apiCall("blueprint", {name:name}).then(function(j){
    if(!j.error) showAlert("已购买「"+name+"图纸」。<br><br>现在可以在「打造」栏打造这件装备了。", "图纸");
  });
}
function craft(name){
  const g = gearDef(name); if(!g) return;
  if(g[5] === "—") return showAlert("「"+name+"」不能打造，只能通过成就或事件获得。", "打造");
  if(!S.blueprints[name]) return showAlert("没有「"+name+"图纸」。<br><br>到公会商店（或铂金商店）购买图纸后才能打造。", "打造");
  const mm = craftMainMat(name);
  const cost = craftCost(g[1]) * 10000;
  const subCnt = subMatCount(g[1], g[2]);
  if((S.mats[mm.mat]||0) < mm.cnt)
    return showAlert("主材料不足。<br><br>需要「"+mm.mat+" ×"+mm.cnt+"」，当前 "+(S.mats[mm.mat]||0)+"。", "打造");
  const subs = pickSubMats(g[1], mm.mat, subCnt);
  if(!subs)
    return showAlert("副材料不足。<br><br>需要「"+subTiers(g[1]).join(" 或 ")+"」品阶的材料 ×"+subCnt+"（主材料不计入）。", "打造");
  if(S.money < cost) return showAlert("加工费不足。<br><br>需要 "+fmtMoneyFull(cost)+"。", "打造");
  apiCall("craft", {name:name}).then(function(j){
    if(!j.error) showAlert("打造成功：「"+name+"」<br><br>已放入冒险背包。", "打造");
  });
}
function doExplore(i){
  const r = REGIONS[i];
  if(S.lvIdx < 1) return showAlert("自由探索需要完成 9 次 Lv2 委托后解锁。", "探索");
  if(S.exploreActive) return showAlert("已经有一次探索正在进行中。<br><br>等待它完成，或中途返回（不会有任何收获）。", "探索");
  if(r.lv && S.lvIdx < r.lv - 1) return showAlert("「" + r.n + "」需要等级 <b>Lv" + r.lv + "</b> 才能进入。<br><br>当前等级：" + lvName(), "探索");
  if(prevHealthScore() < 60) return showAlert("前一日健康评分低于 60，今天不能探索。<br><br>先把作息调整好。", "探索");
  if(S.exploreUsed >= 2) return showAlert("今天已经探索 2 次了，明天再来。", "探索");
  if(S.explore < r.c) return showAlert("探索点不足。<br><br>「"+r.n+"」需要 " + r.c + " 点，当前只有 " + S.explore + " 点。", "探索");
  if(!inRegionTime(r.t)) return showAlert("「"+r.n+"」不在开放时间内。<br><br>开放时间：" + r.t, "探索");
  apiCall("explore", {idx:i});
}
/* Flask 版：探索中途返回（服务端清 explore_active，无任何掉落） */
function exploreReturn(){
  const ea = S.exploreActive;
  if(!ea) return;
  showConfirm("确定中途返回吗？<br><br>放弃「"+ea.n+"」的探索——<b>不会获得任何材料掉落</b>（探索点与次数也不退还）。", function(){
    apiCall("explore_return");
  }, "中途返回");
}
/* Flask 版：探索结算由服务端 catch_up 驱动 → 前端此函数置空（防本地重复结算） */
function exploreFinishCheck(){ /* 服务端驱动 */ }
function useItem(name){
  if(!S.items[name]) return;
  if(name === "疾风符咒"){
    if(!S.active.length) return showAlert("当前没有正在进行的委托。", "疾风符咒");
    const body = S.active.map(function(a,i){
      return '<div class="li" style="gap:8px"><div><b>'+a.name+'</b>'
           + '<div class="muted">成功率 '+Math.round(a.rate*100)+'%</div></div>'
           + '<button class="btn sm pri" onclick="clrDlg();useGale('+i+')">直接完成</button></div>';
    }).join("");
    dlg("疾风符咒 · 选择要完成的委托",
        '<div class="dlg-msg" style="font-size:13px">立即结算以下任一委托，跳过剩余等待时间：</div>'+body,
        [{text:"取消", fn:null}]);
    return;
  }
  apiCall("use_item", {name:name}).then(function(j){
    if(j.error) return;
    if(name === "清醒符咒") showAlert("已使用「清醒符咒」。<br><br>今日早起判定视为达成，+15 分。", "清醒符咒");
    if(name === "安眠护符") showAlert("已使用「安眠护符」。<br><br>今日早睡判定视为达成，+20 分。", "安眠护符");
    if(name === "活力药水") showAlert("已使用「活力药水」。<br><br>今日健康评分锁定为 <b>100 分</b>。", "活力药水");
    if(name === "命运骰子") showAlert("命运骰子掷出——<br><br>当前委托栏已<b>重新刷新</b>。", "命运骰子");
    if(name === "时之怀表") showAlert("怀表的指针缓缓倒转——<br><br>本批委托的接取窗口<b>重置为 30 分钟</b>。", "时之怀表");
    if(name === "幸运币") showAlert("幸运币在掌心化作一线金光——<br><br>下一次委托<b>成功率 +5%</b>。", "幸运币");
    if(name === "专注药剂") showAlert("药剂入喉，世界清晰了几分——<br><br>下一次委托<b>成功率 +3%</b>。", "专注药剂");
    if(name === "谈判卷轴") showAlert("卷轴上写满商会的暗语——<br><br>下一次委托<b>报酬 +15%</b>。", "谈判卷轴");
    if(name === "旅行干粮") showAlert("风干的肉脯与硬面包，嚼完浑身是劲——<br><br>精力 <b>+25</b>（不超过上限）。", "旅行干粮");
    if(name === "神秘地图") showAlert("一卷泛黄的旧地图，标着几处未名的角落——<br><br>探索点 <b>+4</b>。", "神秘地图");
  });
}
function useGale(i){
  const a = S.active[i];
  if(!a) return;
  apiCall("gale", {idx:i});
}
/* 宠物养成（服务端权威：喂食/变异由服务端结算） */
function feedWolf(name){
  const before = S.wolf ? S.wolf.stage : 0;
  apiCall("feed_wolf", {name:name}).then(function(j){
    if(j.error) return;
    const now = j.state.wolf ? j.state.wolf.stage : 0;
    if(now > before && now < 4){
      const st = WOLF_STAGES[now];
      showAlert("🎉 它长大了！<br><br>现在是 <b>"+st.name+"</b>——材料掉落率 <b>+"+Math.round(st.mat*100)+"%</b>"
        + (st.rate ? "、委托成功率 <b>+"+Math.round(st.rate*100)+"%</b>" : "") + "。", "宠物成长");
    } else {
      openWolfFeed();          // 重开喂食窗，刷新库存与成长值
    }
  });
}
/* v1.35：宠物养成扩充（可养成线）——服务端权威 */
function feedPet(n, foodName){
  const pd0 = (S.petData||{})[n];
  const before = pd0 ? pd0.stage : 0;
  apiCall("feed_pet", {name:n, food:foodName}).then(function(j){
    if(j.error) return;
    const pd = (j.state.pet_data || {})[n];
    const now = pd ? pd.stage : 0;
    if(now > before && now < 4){
      showAlert("🎉 它长大了！<br><br>「"+n+"」成长进阶——加成已提升（见背包·宠物）。", "宠物成长");
    } else {
      openPetFeed(n);
    }
  });
}
async function setCarryPet(n){                        // v1.38f：携带宠物（服务端权威）
  await apiCall("set_carry_pet", {name:n});
}
function evolvePet(n){
  showConfirm("它气息翻涌，血脉深处仿佛有什么在苏醒——<br><br>确定让它变异？", function(){
    apiCall("evolve_pet", {name:n}).then(function(j){
      if(!j.error) showAlert("🌌 变异成功！<br><br>加成已提升（见背包·宠物）。", "宠物变异");
    });
  }, "宠物变异");
}
function evolveWolf(){
  const w = S.wolf;
  if(!w || w.stage !== 3) return showAlert("只有巨狼可以进化为远古魔狼。", "宠物养成");
  if(w.growth < WOLF_STAGES[3].need)
    return showAlert("成长值尚未积满（"+w.growth+" / "+WOLF_STAGES[3].need+"）。<br><br>先用食材把成长值喂满吧。", "宠物养成");
  if((w.mutate || 0) < WOLF_MUTATE_NEED)
    return showAlert("变异值尚未积满（"+(w.mutate||0)+" / "+WOLF_MUTATE_NEED+"）。<br><br>继续喂食<b>高级特殊材料</b>：龙血 / 暗影草 +5、龙心 / 世界树汁液 +12 变异值。", "宠物养成");
  showConfirm("巨狼气息翻涌，血脉深处仿佛有什么在苏醒——<br><br>确定让它变异为「远古魔狼」？", function(){
    apiCall("evolve_wolf").then(function(j){
      if(!j.error) showAlert("🌌 变异成功！<br><br>它睁开金瞳，仰天长啸——<br><b>远古魔狼</b>：材料掉落率 <b>+8%</b>、委托成功率 <b>+3%</b>。", "远古魔狼");
    });
  }, "远古魔狼");
}

/* ── 存档（SQLite 后端） ── */
async function exportSave(){
  try{ await refreshState(); }catch(e){}
  const snap = Object.assign({}, S);          // v1.38d：导出 camel 存档（与原型创造版互通）
  delete snap.account;
  delete snap.legendPool;
  const data = JSON.stringify(snap, null, 2);
  const blob = new Blob([data], {type:"application/json"});
  const url = URL.createObjectURL(blob);
  const a2 = document.createElement("a");
  a2.href = url;
  a2.download = "健康的冒险者的一天_"+(S.name||"冒险者")+"_"+todayStr()+".json";
  document.body.appendChild(a2);
  a2.click();
  document.body.removeChild(a2);
  setTimeout(function(){ URL.revokeObjectURL(url); }, 1000);
  showAlert("已导出存档快照（JSON）。<br><br>该文件可导入原型创造版；正式备份请复制电脑上的 <b>Flask版/data/adventurer.db</b>。", "导出快照");
}
function importSaveFile(){                          // v1.38d：导入原型 / 快照 JSON（存档互通）
  const inp = document.createElement("input");
  inp.type = "file";
  inp.accept = ".json,application/json";
  inp.onchange = function(e){
    const f = e.target.files[0];
    if(!f) return;
    const r = new FileReader();
    r.onload = function(ev){
      let d;
      try{ d = JSON.parse(ev.target.result); }
      catch(err){ return showAlert("导入失败：不是有效的 JSON 文件"); }
      if(!d || typeof d !== "object" || Array.isArray(d))
        return showAlert("导入失败：存档格式不正确");
      showConfirm("导入将<b>覆盖当前账号的进度</b>（建议先「导出快照」备份），确定继续？", function(){
        apiCall("import_save", {data: d}).then(function(j){
          if(!j.error) showAlert("已导入存档：「" + ((j.state && j.state.name) || "未命名") + "」", "导入存档");
        });
      }, "导入存档");
    };
    r.readAsText(f);
  };
  inp.click();
}
function importSave(){
  showAlert("存档保存在电脑的 SQLite 数据库：<b>Flask版/data/adventurer.db</b><br><br>"
    + "· 备份 / 恢复：复制或替换该文件即可<br>"
    + "· 电脑与手机访问的是同一份存档<br>"
    + "· 「导出快照」下载的 JSON 仅用于查阅", "数据说明");
}
function resetAll(){
  showConfirm("确定清空所有进度重新开始？<br>此操作不可撤销。<br><br>建议先备份电脑上的 data/adventurer.db 文件。", function(){
    apiCall("reset").then(function(){
      document.getElementById("nameInput").value = "";
      showIntro();
    });
  }, "重置存档");
}
