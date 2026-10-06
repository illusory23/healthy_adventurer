// 3D物理骰子 — 与 /dice3d 掷骰界面同引擎（dice-engine-v3 + three + cannon-es，小窗口模式）
let diceBox = null;
let overlayEl = null;
let panelEl = null;
let stageEl = null;
let rollBtnEl = null;   // 玩家主动点击的"掷骰"按钮
let closeBtnEl = null;  // 标题栏关闭按钮
let titleEl = null;     // v1.48c：标题栏标题（显示当前委托名）
let resultEl = null;    // 掷骰结果展示
let isRolling = false;
let ready = false;
let _initPromise = null;

// 交互状态机
let phase = 'idle';        // 'waiting' 等待玩家点击 | 'rolling' 物理掷骰中
let cancelRequested = false; // 玩家请求中断
let abortRequested = false;  // 关闭按钮触发的中断标志（任何阶段立即生效）
let pendingResolve = null;   // 等待点击阶段的 resolve

// 小窗口动画样式（注入一次）
let _styleInjected = false;
function injectStyles() {
    if (_styleInjected) return;
    _styleInjected = true;
    var st = document.createElement('style');
    st.textContent = `
        @keyframes dicePanelIn {
            from { opacity: 0; transform: translateY(14px) scale(0.94); }
            to   { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes diceFadeIn {
            from { opacity: 0; }
            to   { opacity: 1; }
        }
        .dice3d-overlay-anim { animation: diceFadeIn .18s ease-out; }
        .dice3d-panel-anim   { animation: dicePanelIn .2s cubic-bezier(.2,.8,.3,1.1); }
    `;
    document.head.appendChild(st);
}

export async function initDiceOverlay() {
    if (ready) return;
    if (_initPromise) return _initPromise;

    _initPromise = (async function() {
        injectStyles();

        // 遮罩
        overlayEl = document.createElement('div');
        overlayEl.id = 'dice3dOverlay';
        overlayEl.style.cssText = 'display:none;position:fixed;inset:0;z-index:9999;background:rgba(5,8,18,0.72);align-items:center;justify-content:center;padding:20px;';
        document.body.appendChild(overlayEl);

        // 小窗口
        panelEl = document.createElement('div');
        panelEl.id = 'dice3dPanel';
        panelEl.style.cssText = 'width:min(94vw,660px);max-height:96vh;display:flex;flex-direction:column;background:linear-gradient(165deg,#222b40 0%,#161d30 60%,#121625 100%);border:1px solid rgba(212,168,96,0.42);border-radius:18px;box-shadow:0 26px 100px rgba(0,0,0,0.7),0 2px 0 rgba(255,255,255,0.07) inset;overflow:hidden;font-family:inherit;';
        overlayEl.appendChild(panelEl);

        // 标题栏
        var header = document.createElement('div');
        header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;padding:14px 18px 12px;border-bottom:1px solid rgba(255,255,255,0.08);';
        panelEl.appendChild(header);

        titleEl = document.createElement('span');
        titleEl.textContent = '🎲 3D 掷骰';
        titleEl.style.cssText = 'color:#e8d9b8;font-size:1rem;font-weight:600;letter-spacing:1px;text-shadow:0 0 14px rgba(212,168,96,0.35);';
        header.appendChild(titleEl);

        closeBtnEl = document.createElement('button');
        closeBtnEl.id = 'dice3d-close-btn';
        closeBtnEl.textContent = '✕';
        closeBtnEl.title = '关闭';
        closeBtnEl.style.cssText = 'width:30px;height:30px;border:none;border-radius:8px;background:rgba(255,255,255,0.06);color:#8fa3ba;font-size:0.9rem;cursor:pointer;font-family:inherit;line-height:1;';
        closeBtnEl.addEventListener('mouseenter', function() { closeBtnEl.style.background = 'rgba(255,255,255,0.14)'; closeBtnEl.style.color = '#fff'; });
        closeBtnEl.addEventListener('mouseleave', function() { closeBtnEl.style.background = 'rgba(255,255,255,0.06)'; closeBtnEl.style.color = '#8fa3ba'; });
        header.appendChild(closeBtnEl);

        // 骰子舞台
        stageEl = document.createElement('div');
        stageEl.id = 'dice-stage';
        stageEl.style.cssText = 'margin:10px 12px 0;height:min(64vh,480px);border-radius:12px;position:relative;background:radial-gradient(ellipse at 50% 38%,#2e3a58 0%,#181f34 68%,#111527 100%);border:1px solid rgba(255,255,255,0.09);box-shadow:0 0 38px rgba(0,0,0,0.5) inset;';
        panelEl.appendChild(stageEl);

        // 底部操作区
        var footer = document.createElement('div');
        footer.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:10px;padding:14px 16px 18px;';
        panelEl.appendChild(footer);

        resultEl = document.createElement('div');
        resultEl.id = 'dice3d-result';
        resultEl.style.cssText = 'display:none;min-height:1.6rem;color:#ffd700;font-size:1.4rem;font-weight:bold;letter-spacing:1px;text-shadow:0 0 16px rgba(255,215,0,0.45);';
        footer.appendChild(resultEl);

        var btnRow = document.createElement('div');
        btnRow.style.cssText = 'display:flex;align-items:center;gap:14px;';
        footer.appendChild(btnRow);

        rollBtnEl = document.createElement('button');
        rollBtnEl.id = 'dice3d-roll-btn';
        rollBtnEl.textContent = '🎲 掷骰';
        rollBtnEl.style.cssText = 'padding:11px 44px;border:none;border-radius:11px;background:linear-gradient(135deg,#e6c57f 0%,#c9973a 55%,#b8860b 100%);color:#241703;font-size:1.08rem;font-weight:bold;cursor:pointer;font-family:inherit;box-shadow:0 6px 24px rgba(212,168,96,0.4),0 1px 0 rgba(255,255,255,0.3) inset;transition:transform .08s ease,box-shadow .15s ease;';
        rollBtnEl.addEventListener('mousedown', function() { if (!rollBtnEl.disabled) rollBtnEl.style.transform = 'translateY(1px) scale(0.98)'; });
        rollBtnEl.addEventListener('mouseup', function() { rollBtnEl.style.transform = ''; });
        rollBtnEl.addEventListener('mouseleave', function() { rollBtnEl.style.transform = ''; });
        btnRow.appendChild(rollBtnEl);

        // 常驻监听（任何阶段都可点击，不再一次性清理）
        rollBtnEl.addEventListener('click', onRollClicked);
        closeBtnEl.addEventListener('click', onCloseClicked);

        // 必须在 DOM 可见时 init
        overlayEl.style.display = 'flex';
        overlayEl.style.opacity = '0.01'; // 几乎不可见，但DOM认为可见
        await new Promise(function(r) { setTimeout(r, 120); });

        var DiceBox = (await import('./dice-engine-v3/index.js')).default;
        // 与 /dice3d 掷骰界面完全一致的物理参数
        diceBox = new DiceBox('#dice-stage', {
            assetPath: './dice-engine-v3/',
            sounds: false,
            theme_surface: 'blue-felt',
            theme_colorset: 'white',
            theme_material: 'glass',
            gravity_multiplier: 400,
            light_intensity: 0.7,
            strength: 1
        });

        await diceBox.initialize();

        // 强制 canvas 匹配容器尺寸
        if (diceBox.canvas) {
            var w = stageEl.clientWidth;
            var h = stageEl.clientHeight;
            diceBox.canvas.style.width = w + 'px';
            diceBox.canvas.style.height = h + 'px';
            if (diceBox.canvas.width !== w) diceBox.canvas.width = w;
            if (diceBox.canvas.height !== h) diceBox.canvas.height = h;
        }

        overlayEl.style.display = 'none';
        overlayEl.style.opacity = '';
        ready = true;
        _initPromise = null;
    })();
    return _initPromise;
}

// 玩家点击"掷骰"：仅在等待阶段生效
function onRollClicked() {
    if (phase !== 'waiting' || !pendingResolve) return;
    var r = pendingResolve;
    pendingResolve = null;
    phase = 'rolling';
    r({ type: 'roll' });
}

// 玩家点击关闭（右上角 ✕）：等待阶段直接取消；滚动阶段隐藏界面但让骰子自然停稳
function onCloseClicked() {
    abortRequested = true;
    if (phase === 'waiting' && pendingResolve) {
        var r = pendingResolve;
        pendingResolve = null;
        phase = 'idle';
        r({ type: 'cancel' });
        return;
    }
    // 滚动中或结果阶段：只隐藏视觉界面，不重置状态
    // 让 roll3D 等待骰子自然停稳后自行清理，避免 fallback 到随机数
    if (overlayEl) {
        overlayEl.style.display = 'none';
        overlayEl.dataset.done = '1';
    }
}

function showOverlay() {
    if (!overlayEl) return;
    overlayEl.style.display = 'flex';
    overlayEl.style.opacity = '';
    overlayEl.style.pointerEvents = '';
    overlayEl.classList.remove('dice3d-overlay-anim');
    if (panelEl) { panelEl.classList.remove('dice3d-panel-anim'); }
    void overlayEl.offsetWidth; // 强制 reflow 重启动画
    overlayEl.classList.add('dice3d-overlay-anim');
    if (panelEl) { panelEl.classList.add('dice3d-panel-anim'); }
}

export function hideDiceOverlay() {
    if (overlayEl) {
        overlayEl.style.display = 'none';
        overlayEl.dataset.done = '1';
    }
    isRolling = false;
    phase = 'idle';
    cancelRequested = false;
    pendingResolve = null;
    if (rollBtnEl) { rollBtnEl.disabled = false; rollBtnEl.style.display = ''; rollBtnEl.textContent = '🎲 掷骰'; }
}

// 与 /dice3d 页面一致的确定性标注：API 先算出结果，动画按结果摆放骰子
function buildDetNotation(apiResult, notation) {
    var m = String(notation).match(/d(\d+)/i);
    var sides = m ? (parseInt(m[1]) || 20) : 20;
    var rolls = apiResult.rolls || [];
    if (sides === 100) {
        var total = apiResult.total || 0;
        var tens = Math.floor(total / 10) % 10, ones = total % 10;
        if (tens === 0) tens = 10;
        if (ones === 0) ones = 10;
        return '2d10@' + tens + ',' + ones;
    }
    return (rolls.length || 1) + 'd' + sides + '@' + (rolls.join(',') || '0');
}

// 播放确定性动画（结果已由 API 确定；动画带超时兜底，避免引擎异常时卡住流程）
function rollDetAnimation(dn) {
    return Promise.race([
        diceBox.roll(dn, {theme:{theme_colorset:'white'}}).catch(function(e) {
            console.warn('[dice-bridge] dice-engine roll 异常:', e);
        }),
        new Promise(function(r) { setTimeout(r, 8000); })
    ]);
}

// presetTotal：由调用方（本地掷骰逻辑）预先算好的结果，这里只负责播放 3D 动画
export async function roll3D(notation, presetTotal, titleText) {
    if (isRolling) return null;
    isRolling = true;
    if (!ready) await initDiceOverlay();
    showOverlay();
    if (titleEl) titleEl.textContent = titleText ? ('🎲 ' + titleText) : '🎲 3D 掷骰';   // v1.48c：标题显示对应委托名
    overlayEl.dataset.done = '';
    cancelRequested = false;
    abortRequested = false;

    try {
        // 重置 UI：等待玩家主动点击"掷骰"键
        if (rollBtnEl) { rollBtnEl.style.display = ''; rollBtnEl.disabled = false; rollBtnEl.textContent = '🎲 掷骰'; }
        if (resultEl) { resultEl.style.display = 'none'; resultEl.textContent = ''; }
        phase = 'waiting';

        // 等待玩家点击掷骰键（onRollClicked / onCloseClicked 驱动）
        var action = await new Promise(function(resolve) {
            pendingResolve = resolve;
        });
        pendingResolve = null;
        if (action.type === 'cancel' || abortRequested) {
            hideDiceOverlay();
            return null; // 玩家取消 → 上层回退为文本掷骰
        }

        // 掷骰中：掷骰按钮禁用（标题栏 ✕ 仍可中断关闭）
        if (rollBtnEl) { rollBtnEl.disabled = true; rollBtnEl.textContent = '🎲 掷骰中...'; }

        if (diceBox.clearDice) { try { diceBox.clearDice(); } catch(e) {} }
        // 结果由调用方传入（本地掷骰逻辑已算好），这里只播放 3D 物理动画
        var total = (typeof presetTotal === 'number' && presetTotal >= 1 && presetTotal <= 100)
            ? presetTotal
            : (Math.floor(Math.random() * 100) + 1);
        var dn = buildDetNotation({ total: total, rolls: [total] }, notation);
        await rollDetAnimation(dn);

        // 清理状态
        hideDiceOverlay();

        if (typeof total !== 'number' || total < 1) {
            console.warn('[dice-bridge] 骰子结果无效');
            return null;
        }

        // 如果界面还在（正常流程），短暂显示结果
        if (!abortRequested && !cancelRequested && resultEl) {
            resultEl.textContent = notation + ' = ' + total;
            resultEl.style.display = 'block';
            if (rollBtnEl) { rollBtnEl.disabled = false; rollBtnEl.textContent = '🎲 掷骰'; }
            // 正常展示后自动关闭
            overlayEl.dataset.done = '1';
            setTimeout(function() {
                if (overlayEl) overlayEl.style.display = 'none';
            }, 2500);
        }

        return { total: total };
    } catch(e) {
        hideDiceOverlay();
        throw e;
    }
}

window.roll3DDice = roll3D;
