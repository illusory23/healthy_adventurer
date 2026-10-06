// 一次性分析：装备词条阶梯矩阵（node _probe_ladder.js）——为新增装备选词条用
const fs = require('fs');
global.localStorage = { _d:{}, getItem(k){return this._d[k]||null;}, setItem(k,v){this._d[k]=v;}, removeItem(k){delete this._d[k];} };
const fakeEl = () => ({ textContent:"", innerHTML:"", style:{}, value:"", classList:{add(){},remove(){},contains(){return false;}}, onclick:null, focus(){}, addEventListener(){}, dataset:{}, querySelectorAll(){return [];} });
const elCache = {}, qsCache = {};
global.document = { getElementById:(id)=>(elCache[id]=elCache[id]||fakeEl()), querySelector:(s)=>(qsCache[s]=qsCache[s]||fakeEl()), querySelectorAll:()=>[], addEventListener:()=>{} };
global.alert=()=>{}; global.confirm=()=>true; global.setInterval=()=>0;
const html = fs.readFileSync(__dirname + '/../Flask版/static/game.html', 'utf-8');
let code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const _bi = code.indexOf('(async function boot(){');
code = code.slice(0, _bi);
const test = `
(function(){
const q = s => console.log(s);
const QO = ["精良","稀有","史诗","传说"];
const pat = /^(.*?)(成功率|精力消耗|委托报酬|报酬|经验|贡献|探索点|材料获取|事件概率)\\s*([+-]\\d+)%?(\\/天)?$/;
const mat = {};
GEAR.forEach(g => {
  if(g[4] === "—") return;
  g[4].split("；").forEach(part => {
    const m = pat.exec(part.trim());
    if(!m) return;
    const key = m[1] + "|" + m[2] + (m[4] ? "/天" : "");
    mat[key] = mat[key] || {};
    (mat[key][g[1]] = mat[key][g[1]] || []).push(+m[3]);
  });
});
q("=== 词条阶梯矩阵（前缀|效果 → 品阶: 值列表）===");
Object.keys(mat).sort().forEach(k => {
  const byq = mat[k];
  const seg = QO.filter(x => byq[x]).map(x => x + ":" + byq[x].sort((a,b)=>a-b).join(",")).join("  →  ");
  q("  " + k + "   " + seg);
});
q("");
q("=== 词条未解析的装备（检查新装备可用的写法）===");
const bad = [];
GEAR.forEach(g => { if(g[4]==="—") return; g[4].split("；").forEach(part => { if(!pat.exec(part.trim())) bad.push(g[0] + "(" + g[1] + "): " + part.trim()); }); });
bad.forEach(s => q("  " + s));
q("共 " + bad.length + " 条未解析");
})();
`;
try { eval(code + test); } catch(e) { console.log("加载异常:", e.message); if(e.stack) console.log(e.stack.split("\n").slice(0,4).join("\n")); }
