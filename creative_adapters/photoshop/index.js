const photoshop = require('photoshop');
const { app, action, core } = photoshop;

const ACTIONS = [
  'inspect_document','create_document','create_text_layer','create_rectangle_shape',
  'create_group','rename_layer','set_layer_opacity','translate_layer','create_marketing_canvas','undo'
];
let ws = null;
let clientId = localStorage.getItem('jarvis_client_id') || ('photoshop-' + Date.now() + '-' + Math.random().toString(16).slice(2));
localStorage.setItem('jarvis_client_id', clientId);

function setStatus(text, ok) {
  const el = document.getElementById('status');
  el.textContent = text;
  el.className = ok === true ? 'ok' : ok === false ? 'bad' : '';
}
function wsUrl(server, token) {
  const u = new URL(server);
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
  u.pathname = '/ws/desktop-bridge';
  u.search = '?token=' + encodeURIComponent(token || '');
  return u.toString();
}
function send(obj) { if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj)); }
function num(v) { try { return Number(v && v._value !== undefined ? v._value : v); } catch (e) { return null; } }
function activeDoc() { try { return app.activeDocument || null; } catch (e) { return null; } }
function layerState(layer) {
  return { id: layer.id, name: layer.name, kind: String(layer.kind || ''), visible: layer.visible, opacity: layer.opacity };
}
function getState() {
  const doc = activeDoc();
  return {
    adapter: { name: 'jarvis-photoshop-uxp', write: true, version: '0.2.0', actions: ACTIONS },
    document_count: app.documents.length,
    active_document: doc ? { id: doc.id, title: doc.title, width: num(doc.width), height: num(doc.height), resolution: doc.resolution } : null,
    layers: doc ? Array.from(doc.layers).slice(0, 120).map(layerState) : [],
    active_layers: doc ? Array.from(doc.activeLayers || []).map(layerState) : []
  };
}
function findLayer(name) {
  const doc = activeDoc();
  if (!doc) return null;
  const wanted = String(name || '').toLowerCase();
  return Array.from(doc.layers).find(x => String(x.name || '').toLowerCase() === wanted) || null;
}
function rgb(hex) {
  const value = String(hex || '#111111').replace('#','');
  const n = parseInt(value,16);
  return { red:(n>>16)&255, green:(n>>8)&255, blue:n&255 };
}
async function makeRectangle(args) {
  const c = rgb(args.fill_hex || '#111111');
  const left = Number(args.x), top = Number(args.y), right = left + Number(args.width), bottom = top + Number(args.height);
  await action.batchPlay([{
    _obj:'make', _target:[{_ref:'contentLayer'}],
    using:{ _obj:'contentLayer', type:{_obj:'solidColorLayer',color:{_obj:'RGBColor',red:c.red,grain:c.green,blue:c.blue}},
      shape:{_obj:'rectangle', top:{_unit:'pixelsUnit',_value:top}, left:{_unit:'pixelsUnit',_value:left}, bottom:{_unit:'pixelsUnit',_value:bottom}, right:{_unit:'pixelsUnit',_value:right}, unitValueQuadVersion:1} }
  }], {});
  const doc = activeDoc();
  const layer = doc && doc.activeLayers && doc.activeLayers[0];
  if (layer && args.name) layer.name = args.name;
  return layer ? layerState(layer) : { created:true };
}
async function marketingCanvas(args) {
  const doc = await app.createDocument({ name: args.name, width: args.width, height: args.height, resolution:72, mode:'RGBColorMode', fill:'white' });
  const w = Number(args.width), h = Number(args.height);
  await makeRectangle({name:'Background',x:0,y:0,width:w,height:h,fill_hex:args.background_hex || '#F7F3EE'});
  await doc.createTextLayer({ name:'Headline', contents:args.headline, fontSize:Math.max(42,Math.min(120,w*0.065)), position:{x:w*0.08,y:h*0.34} });
  if (args.subheadline) await doc.createTextLayer({ name:'Subheadline', contents:args.subheadline, fontSize:Math.max(20,Math.min(48,w*0.025)), position:{x:w*0.08,y:h*0.48} });
  if (args.cta) {
    await makeRectangle({name:'CTA',x:w*0.08,y:h*0.58,width:w*0.25,height:h*0.09,fill_hex:args.accent_hex || '#111111'});
    await doc.createTextLayer({ name:'CTA Label', contents:args.cta, fontSize:Math.max(18,Math.min(36,w*0.02)), position:{x:w*0.105,y:h*0.64} });
  }
  return { document_id:doc.id, title:doc.title, width:w, height:h };
}
async function execute(plan) {
  const actionName = String(plan.action || '');
  const args = plan.arguments || {};
  if (!ACTIONS.includes(actionName)) throw new Error('Ação não permitida: ' + actionName);
  if (actionName === 'inspect_document') return getState();
  return await core.executeAsModal(async () => {
    if (actionName === 'create_document') {
      const doc = await app.createDocument({name:args.name,width:args.width,height:args.height,resolution:args.resolution||72,mode:'RGBColorMode',fill:'white'});
      return {id:doc.id,title:doc.title,width:num(doc.width),height:num(doc.height)};
    }
    const doc = activeDoc();
    if (!doc && actionName !== 'create_marketing_canvas') throw new Error('Nenhum documento ativo.');
    if (actionName === 'create_text_layer') {
      const layer = await doc.createTextLayer({name:args.name||'JARVIS Text',contents:args.text,fontSize:args.font_size||32,position:{x:args.x,y:args.y}}); return layerState(layer);
    }
    if (actionName === 'create_rectangle_shape') return await makeRectangle(args);
    if (actionName === 'create_group') { const layer = await doc.createLayerGroup({name:args.name}); return layerState(layer); }
    if (actionName === 'rename_layer') { const layer=findLayer(args.layer_name); if(!layer) throw new Error('Camada não encontrada.'); layer.name=args.new_name; return layerState(layer); }
    if (actionName === 'set_layer_opacity') { const layer=findLayer(args.layer_name); if(!layer) throw new Error('Camada não encontrada.'); layer.opacity=args.opacity; return layerState(layer); }
    if (actionName === 'translate_layer') { const layer=findLayer(args.layer_name); if(!layer) throw new Error('Camada não encontrada.'); await layer.translate(args.dx,args.dy); return layerState(layer); }
    if (actionName === 'create_marketing_canvas') return await marketingCanvas(args);
    if (actionName === 'undo') { await action.batchPlay([{_obj:'undo'}],{}); return {undone:true}; }
    throw new Error('Ação não implementada.');
  }, {commandName:'JARVIS ' + actionName});
}
function sendState(type='state', extra={}) {
  const state=getState();
  send({type,apps:['photoshop'],active_app:'photoshop',active_document:state.active_document?state.active_document.title:null,state,...extra});
}
function connect() {
  if (ws) try { ws.close(); } catch(e) {}
  const server=document.getElementById('server').value.trim(), token=document.getElementById('token').value.trim();
  if(!server){setStatus('Informe o servidor.',false);return;}
  try { ws=new WebSocket(wsUrl(server,token)); } catch(e){setStatus(String(e),false);return;}
  ws.onopen=()=>{setStatus('Conectado ao JARVIS',true);send({type:'hello',client_id:clientId,platform:'photoshop-uxp',apps:['photoshop'],active_app:'photoshop',active_document:getState().active_document?.title||null,state:getState()});};
  ws.onclose=()=>setStatus('Desconectado',false); ws.onerror=()=>setStatus('Erro de conexão',false);
  ws.onmessage=async ev=>{let m;try{m=JSON.parse(ev.data)}catch(e){return;} if(m.type!=='command')return; try{const result=await execute(m.plan||{});sendState('result',{command_id:m.command_id,ok:true,result});}catch(e){sendState('result',{command_id:m.command_id,ok:false,error:String(e&&e.message?e.message:e),result:{}});} };
}
const stored=JSON.parse(localStorage.getItem('jarvis_bridge')||'{}');
document.getElementById('server').value=stored.server_url||'';document.getElementById('token').value=stored.token||'';
document.getElementById('save').onclick=()=>{const cfg={server_url:document.getElementById('server').value.trim(),token:document.getElementById('token').value.trim()};localStorage.setItem('jarvis_bridge',JSON.stringify(cfg));setStatus('Configuração salva',true);};
document.getElementById('connect').onclick=()=>{document.getElementById('save').click();connect();};
setInterval(()=>{if(ws&&ws.readyState===WebSocket.OPEN)sendState();},4000);
