const fs = require('fs');
global.localStorage = { _d:{}, getItem(k){return this._d[k]||null;}, setItem(k,v){this._d[k]=v;}, removeItem(k){delete this._d[k];} };
const fakeEl = () => ({ textContent:"", innerHTML:"", style:{}, value:"", classList:{add(){},remove(){},contains(){return false;}}, onclick:null, focus(){}, addEventListener(){}, dataset:{}, querySelectorAll(){return [];} });
const elCache = {}, qsCache = {};
global.document = { getElementById:(id)=>(elCache[id]=elCache[id]||fakeEl()), querySelector:(s)=>(qsCache[s]=qsCache[s]||fakeEl()), querySelectorAll:()=>[], addEventListener:()=>{} };
global.alert=()=>{}; global.confirm=()=>true; global.setInterval=()=>0;
const html = fs.readFileSync(__dirname + '/../Flask版/static/game.html', 'utf-8');
let code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
code = code.slice(0, code.indexOf('(async function boot(){'));
try { eval(code + `
(function(){
const agg = {};
GEAR.forEach(g => { const k = g[1] + "·" + g[2]; agg[k] = agg[k] || {}; agg[k][g[3]] = (agg[k][g[3]]||0)+1; });
Object.keys(agg).sort().forEach(k => console.log(k + "  " + JSON.stringify(agg[k])));
})();
`); } catch(e) { console.log("ERR", e.message); }
