(function(){
  var cep=window.__adobe_cep__;
  var env={}; try{env=JSON.parse(cep.getHostEnvironment());}catch(e){}
  var appCode=env.appName||'';
  var appName=appCode==='ILST'?'illustrator':appCode==='AEFT'?'after_effects':'unknown';
  document.getElementById('host').textContent=appName==='illustrator'?'Adobe Illustrator':appName==='after_effects'?'Adobe After Effects':'Host não suportado: '+appCode;
  var ws=null;
  var clientId=localStorage.getItem('jarvis_client_id')||('adobe-'+appName+'-'+Date.now()+'-'+Math.random().toString(16).slice(2));
  localStorage.setItem('jarvis_client_id',clientId);
  function status(text,ok){var e=document.getElementById('status');e.textContent=text;e.className=ok===true?'ok':ok===false?'bad':'';}
  function wsUrl(server,token){var u=new URL(server);u.protocol=u.protocol==='https:'?'wss:':'ws:';u.pathname='/ws/desktop-bridge';u.search='?token='+encodeURIComponent(token||'');return u.toString();}
  function send(obj){if(ws&&ws.readyState===1)ws.send(JSON.stringify(obj));}
  function jsxString(value){return '"'+String(value||'').replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/\r/g,'\\r').replace(/\n/g,'\\n')+'"';}
  function encodeArgs(args){var parts=[];Object.keys(args||{}).forEach(function(k){var v=args[k];if(v===null||v===undefined)return;if(typeof v==='object')return;parts.push(encodeURIComponent(k)+'='+encodeURIComponent(String(v)));});return parts.join('&');}
  function evalScript(script){return new Promise(function(resolve){cep.evalScript(script,function(result){resolve(result);});});}
  async function snapshot(){var raw=await evalScript('JARVIS_AI.snapshot()');var state={};try{state=JSON.parse(raw);}catch(e){state={adapter:{name:'jarvis-adobe-cep',write:false},error:'Snapshot inválido: '+String(raw).slice(0,300)};}return state;}
  async function sendState(type,extra){var state=await snapshot();var doc=state.active_document&&state.active_document.name?state.active_document.name:null;send(Object.assign({type:type||'state',apps:[appName],active_app:appName,active_document:doc,state:state},extra||{}));return state;}
  async function execute(command){var plan=command.plan||{};var action=String(plan.action||'');var encoded=encodeArgs(plan.arguments||{});var raw=await evalScript('JARVIS_AI.execute('+jsxString(action)+','+jsxString(encoded)+')');var result;try{result=JSON.parse(raw);}catch(e){throw new Error('Resposta inválida do host Adobe: '+String(raw).slice(0,400));}if(!result.ok)throw new Error(result.error||'Falha no adaptador Adobe');return result.result||{};}
  function connect(){if(appName==='unknown'){status('Este painel precisa estar no Illustrator ou After Effects.',false);return;}if(ws)try{ws.close();}catch(e){}var server=document.getElementById('server').value.trim(),token=document.getElementById('token').value.trim();if(!server){status('Informe o servidor.',false);return;}try{ws=new WebSocket(wsUrl(server,token));}catch(e){status(String(e),false);return;}ws.onopen=async function(){status('Conectado ao JARVIS',true);var state=await snapshot();send({type:'hello',client_id:clientId,platform:'adobe-cep',apps:[appName],active_app:appName,active_document:state.active_document?state.active_document.name:null,state:state});};ws.onclose=function(){status('Desconectado',false);};ws.onerror=function(){status('Erro de conexão',false);};ws.onmessage=async function(ev){var m;try{m=JSON.parse(ev.data);}catch(e){return;}if(m.type!=='command')return;try{var result=await execute(m);await sendState('result',{command_id:m.command_id,ok:true,result:result});}catch(e){await sendState('result',{command_id:m.command_id,ok:false,error:String(e&&e.message?e.message:e),result:{}});}};}
  var stored={};try{stored=JSON.parse(localStorage.getItem('jarvis_bridge')||'{}');}catch(e){}document.getElementById('server').value=stored.server_url||'';document.getElementById('token').value=stored.token||'';
  document.getElementById('save').onclick=function(){var cfg={server_url:document.getElementById('server').value.trim(),token:document.getElementById('token').value.trim()};localStorage.setItem('jarvis_bridge',JSON.stringify(cfg));status('Configuração salva',true);};
  document.getElementById('connect').onclick=function(){document.getElementById('save').click();connect();};
  setInterval(function(){if(ws&&ws.readyState===1)sendState('state').catch(function(){});},4000);
})();
