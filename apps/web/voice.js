(() => {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;
  const inputEl = document.getElementById('input');
  const sendBtn = document.getElementById('send');
  const composer = document.querySelector('.composer');
  const actions = document.querySelector('.actions');
  const messages = document.getElementById('messages');
  if (!inputEl || !sendBtn || !composer || !actions || !messages) return;

  const terminalStyle = document.createElement('style');
  terminalStyle.textContent = `
    :root{font-family:"SFMono-Regular",Consolas,"Liberation Mono",Menlo,monospace!important;background:#020504!important;color:#d8ffe3!important}
    html,body{background:#020504!important}body{background:#020504!important}
    .shell{max-width:none!important;margin:0!important;padding:max(10px,env(safe-area-inset-top)) 12px max(10px,env(safe-area-inset-bottom))!important}
    .top{margin:0!important;padding:4px 0 10px!important;border-bottom:1px solid rgba(127,255,169,.18)!important;align-items:center!important}
    .brand{letter-spacing:.18em!important;color:#86ffad!important;font-size:15px!important}.top .small{font-size:9px!important;color:#7ea68a!important;opacity:1!important}.status{color:#8cffad!important;font-size:9px!important}
    .dot{width:6px!important;height:6px!important;box-shadow:none!important}.dot.on{background:#78ff9f!important;box-shadow:0 0 8px rgba(120,255,159,.55)!important}.actions{gap:4px!important}
    button,.buttonlink{font-family:inherit!important;border-radius:0!important;background:transparent!important;color:#9effbc!important;border:1px solid rgba(127,255,169,.22)!important;box-shadow:none!important;font-weight:600!important;padding:7px 9px!important}
    button:hover,.buttonlink:hover,.ghost.active{background:rgba(127,255,169,.06)!important;border-color:rgba(127,255,169,.55)!important;box-shadow:none!important}
    .mainlayout{gap:8px!important}.panel{background:transparent!important;border:0!important;border-radius:0!important;backdrop-filter:none!important;box-shadow:none!important}#messages{padding:14px 0 18px!important}
    .m{position:relative!important;max-width:100%!important;width:100%!important;margin:0!important;padding:5px 0!important;border:0!important;border-radius:0!important;background:transparent!important;line-height:1.55!important;font-size:14px!important;color:#d7f8df!important;white-space:pre-wrap!important}
    .m.u{margin-left:0!important;color:#b7d7c0!important}.m.u::before{content:"> ";color:#7dff9f!important;font-weight:700!important}.m.a::before{content:"JARVIS> ";color:#7dff9f!important;font-weight:700!important}
    .m.jarvis-progress{color:#7ea68a!important;font-style:italic!important}.m.jarvis-progress::before{content:"JARVIS> ";color:#6bb883!important}.m>div:first-child{display:inline!important}.meta{display:none!important}
    .msgactions{display:flex!important;gap:6px!important;margin:8px 0 3px 0!important;padding-left:0!important}.msgactions a,.msgactions button{font-size:10px!important;padding:6px 8px!important}
    .composer{position:relative!important;background:#020504!important;border-top:1px solid rgba(127,255,169,.18)!important;padding:9px 0 0!important;gap:6px!important}.composer::before{content:">";display:flex;align-items:center;color:#7dff9f;font-weight:800;padding:0 1px 0 0}
    textarea{background:transparent!important;border:0!important;border-radius:0!important;color:#e7ffed!important;font-family:inherit!important;padding:10px 5px!important;min-height:46px!important;box-shadow:none!important}textarea::placeholder{color:#557660!important}
    .send{width:auto!important;min-width:70px!important}#voiceBtn,#micBtn{white-space:nowrap!important}.workbench{border-radius:0!important;background:#030806!important;border:1px solid rgba(127,255,169,.2)!important;box-shadow:none!important}.workhead,.workbody{font-family:inherit!important}.setup,.integration{border-radius:0!important;background:#030806!important;font-family:inherit!important}.overlay{backdrop-filter:none!important;background:rgba(1,4,3,.94)!important}
    @media(max-width:760px){.shell{padding:max(8px,env(safe-area-inset-top)) 10px max(8px,env(safe-area-inset-bottom))!important}.top{align-items:flex-start!important}.actions{max-width:68%!important;justify-content:flex-end!important}.actions button{font-size:9px!important;padding:6px 7px!important}.panel{height:calc(100dvh - 58px)!important}#messages{padding:10px 0 14px!important}.m{font-size:13px!important;padding:4px 0!important}.composer{padding-top:7px!important}.send{min-width:62px!important;padding:8px 7px!important}}
  `;
  document.head.appendChild(terminalStyle);

  let voiceEnabled = localStorage.getItem('jarvis.voice.enabled') !== 'false';
  let voiceArmed = false;
  let recognition = null;
  let listening = false;
  let fallbackRecording = false;
  let mediaRecorder = null;
  let mediaStream = null;
  let chunks = [];
  let recordTimer = null;
  let ttsAbort = null;
  let progressNode = null;
  let audioEl = null;
  let activeAudioUrl = null;

  const voiceBtn = document.createElement('button');
  voiceBtn.className = 'ghost';
  voiceBtn.id = 'voiceBtn';
  voiceBtn.type = 'button';
  const micBtn = document.createElement('button');
  micBtn.className = 'ghost';
  micBtn.id = 'micBtn';
  micBtn.type = 'button';
  micBtn.textContent = 'MIC';
  micBtn.style.minWidth = '48px';
  composer.insertBefore(micBtn, sendBtn);
  actions.insertBefore(voiceBtn, actions.firstChild);

  const originalLocalIntent = window.isLocalIntent;
  if (typeof originalLocalIntent === 'function') {
    window.isLocalIntent = text => originalLocalIntent(text) || String(text || '').toLowerCase().includes('uber');
  }

  function updateVoiceButton(){voiceBtn.textContent=voiceEnabled?'VOICE:ON':'VOICE:OFF';voiceBtn.classList.toggle('active',voiceEnabled)}
  updateVoiceButton();

  function cleanForSpeech(text){return String(text||'').replace(/https?:\/\/\S+/g,'').replace(/[`*_#>|]/g,' ').replace(/\s+/g,' ').trim()}
  function userFacing(text){const clean=String(text||'').trim();if(!clean||/^erro:/i.test(clean)||/processando|atualizando workbench/i.test(clean))return clean;if(/\bsenhor\b/i.test(clean))return clean;return `Senhor, ${clean}`}
  function exactBrazilianVoice(){if(!synth)return null;return (synth.getVoices()||[]).find(v=>/^pt[-_]BR$/i.test(v.lang))||null}

  function ensureAudio(){if(audioEl)return audioEl;audioEl=document.createElement('audio');audioEl.preload='auto';audioEl.setAttribute('playsinline','');audioEl.style.display='none';document.body.appendChild(audioEl);return audioEl}
  function armVoice(){voiceArmed=true;if(synth)try{synth.resume()}catch(_){};ensureAudio()}
  function fallbackSpeak(text){if(!voiceEnabled||!voiceArmed||!synth)return;const voice=exactBrazilianVoice();if(!voice)return;const u=new SpeechSynthesisUtterance(cleanForSpeech(text));u.voice=voice;u.lang='pt-BR';u.rate=.94;u.pitch=.94;try{synth.cancel();synth.speak(u)}catch(_){}}
  function stopVoice(){if(ttsAbort){try{ttsAbort.abort()}catch(_){};ttsAbort=null}if(audioEl)try{audioEl.pause();audioEl.currentTime=0}catch(_){};if(activeAudioUrl){URL.revokeObjectURL(activeAudioUrl);activeAudioUrl=null}if(synth)try{synth.cancel()}catch(_){}}
  function b64Blob(value,mime='audio/wav'){const raw=atob(value);const bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);return new Blob([bytes],{type:mime})}

  async function speak(text,{interrupt=false,progress=false}={}){
    if(!voiceEnabled||!voiceArmed)return;const clean=cleanForSpeech(text);if(!clean||/^erro:/i.test(clean))return;if(interrupt)stopVoice();
    const controller=new AbortController();ttsAbort=controller;
    try{
      const r=await fetch('/v1/tools/voice.synthesize/execute',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({args:{text:clean,progress}}),signal:controller.signal});
      if(!r.ok)throw new Error('tts');const d=await r.json();if(!d.ok||!d.result?.audio_base64)throw new Error('tts');if(controller.signal.aborted)return;
      const el=ensureAudio();if(activeAudioUrl)URL.revokeObjectURL(activeAudioUrl);activeAudioUrl=URL.createObjectURL(b64Blob(d.result.audio_base64,d.result.mime_type||'audio/wav'));el.src=activeAudioUrl;el.volume=1;await el.play();
    }catch(e){if(e?.name!=='AbortError')fallbackSpeak(clean)}finally{if(ttsAbort===controller)ttsAbort=null}
  }

  function typeReply(body,text){if(!body||body.dataset.jarvisTyping==='1'||!text||/^Processando…$/i.test(text)||/^Erro:/i.test(text))return;body.dataset.jarvisTyping='1';body.textContent='';let i=0;const len=text.length;const step=()=>{if(!body.isConnected)return;const burst=len>1000?5:len>450?3:2;i=Math.min(len,i+burst);body.textContent=text.slice(0,i);messages.scrollTop=messages.scrollHeight;if(i<len){const c=text[i-1]||'';setTimeout(step,/[.!?]/.test(c)?55:/[,;:]/.test(c)?28:12)}};setTimeout(step,10)}

  function clearProgress(abort=true){if(progressNode?.isConnected)progressNode.remove();progressNode=null;if(abort)stopVoice()}
  function progressMessage(text){const t=String(text||'').toLowerCase();if(/pesquis|procure|busque|encontre|internet|web/.test(t))return'Pesquisando, senhor. Um instante.';if(/analise|analisa|avali|estatíst|relatório|compare/.test(t))return'Analisando, senhor. Um instante.';if(/ifood|pedido|carrinho/.test(t))return'Certo, senhor. Abrindo e preparando.';if(/uber|corrida/.test(t))return'Certo, senhor. Preparando a corrida.';if(/abra|abrir|navegador|guia/.test(t))return'Certo, senhor. Abrindo.';if(/crie|criar|figma|photoshop|illustrator|blender|after effects|premiere|campanha/.test(t))return'Entendido, senhor. Inicializando.';if(/gmail|email|e-mail|calend|agenda|trello|planilha|documento|monitore|monitorar|execute|publique/.test(t))return'Certo, senhor. Processando.';return null}
  function showProgress(text){const status=progressMessage(text);if(!status)return;clearProgress();const node=document.createElement('div');node.className='m a jarvis-progress';node.dataset.jarvisProgress='1';const body=document.createElement('div');body.textContent=status;node.appendChild(body);messages.appendChild(node);progressNode=node;messages.scrollTop=messages.scrollHeight;fallbackSpeak(status)}

  const observer=new MutationObserver(ms=>{for(const m of ms){for(const node of m.addedNodes){if(!(node instanceof HTMLElement)||!node.classList.contains('a')||node.dataset.jarvisProgress==='1')continue;clearProgress(true);const body=node.firstElementChild;if(!body)continue;const original=body.textContent||'';const styled=userFacing(original);if(styled!==original)body.textContent=styled;typeReply(body,styled);speak(styled)}}});
  observer.observe(messages,{childList:true});

  function setMic(label,active=false){micBtn.textContent=label;micBtn.classList.toggle('active',active)}
  function setTranscript(text){inputEl.value=String(text||'').trim();inputEl.dispatchEvent(new Event('input',{bubbles:true}))}
  function autoSendTranscript(text){const clean=String(text||'').trim();if(!clean)return;setTranscript(clean);setMic('MIC',false);setTimeout(()=>{armVoice();showProgress(clean);sendBtn.click()},70)}

  function recognitionErrorMessage(code){if(code==='not-allowed'||code==='service-not-allowed')return'Microfone bloqueado. Permita o microfone do JARVIS no Safari.';if(code==='audio-capture')return'Não consegui acessar o microfone.';return'Vou usar a transcrição alternativa, senhor.'}

  async function transcribeBlob(blob){
    setMic('TRANSCRIBINDO',true);
    const b64=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onerror=()=>reject(reader.error);reader.onload=()=>resolve(String(reader.result||'').split(',',2)[1]||'');reader.readAsDataURL(blob)});
    const mime=(blob.type||'audio/mp4').split(';')[0];
    const r=await fetch('/v1/tools/voice.transcribe/execute',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({args:{audio_base64:b64,mime_type:mime}})});
    const d=await r.json();if(!r.ok||!d.ok||!d.result?.text)throw new Error(d.error||'transcription failed');
    autoSendTranscript(d.result.text);
  }

  async function startRecorderFallback(){
    if(fallbackRecording){try{mediaRecorder?.stop()}catch(_){};return}
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){setMic('MIC');return}
    try{
      mediaStream=await navigator.mediaDevices.getUserMedia({audio:true});chunks=[];const preferred=['audio/mp4','audio/webm;codecs=opus','audio/webm'].find(x=>MediaRecorder.isTypeSupported?.(x));mediaRecorder=new MediaRecorder(mediaStream,preferred?{mimeType:preferred}:undefined);fallbackRecording=true;setMic('PARAR',true);
      mediaRecorder.ondataavailable=e=>{if(e.data?.size)chunks.push(e.data)};
      mediaRecorder.onstop=async()=>{fallbackRecording=false;clearTimeout(recordTimer);setMic('TRANSCRIBINDO',true);const type=mediaRecorder?.mimeType||chunks[0]?.type||'audio/mp4';const blob=new Blob(chunks,{type});for(const t of mediaStream?.getTracks?.()||[])t.stop();mediaStream=null;try{await transcribeBlob(blob)}catch(_){setMic('MIC');fallbackSpeak('Não consegui transcrever. Tente novamente, senhor.')}};
      mediaRecorder.start();recordTimer=setTimeout(()=>{if(fallbackRecording)try{mediaRecorder.stop()}catch(_){}},6500);
    }catch(_){setMic('MIC');fallbackSpeak('O microfone está bloqueado, senhor.')}
  }

  function startInstantRecognition(){
    armVoice();stopVoice();
    if(!SpeechRecognition){startRecorderFallback();return}
    if(listening&&recognition){try{recognition.stop()}catch(_){};return}
    recognition=new SpeechRecognition();recognition.lang='pt-BR';recognition.continuous=false;recognition.interimResults=true;recognition.maxAlternatives=1;let finalText='';let hadResult=false;
    recognition.onstart=()=>{listening=true;setMic('OUVINDO',true)};
    recognition.onresult=e=>{hadResult=true;let interim='';for(let i=e.resultIndex;i<e.results.length;i++){const text=e.results[i][0].transcript;if(e.results[i].isFinal)finalText+=(finalText?' ':'')+text;else interim+=text}setTranscript(finalText||interim);if(finalText.trim()){try{recognition.stop()}catch(_){}}};
    recognition.onerror=e=>{listening=false;setMic('MIC');if(e.error==='not-allowed'||e.error==='service-not-allowed'){fallbackSpeak(recognitionErrorMessage(e.error));return}startRecorderFallback()};
    recognition.onend=()=>{listening=false;setMic('MIC');if(finalText.trim()){autoSendTranscript(finalText);return}if(!hadResult&&inputEl.value.trim()){autoSendTranscript(inputEl.value);return}};
    try{recognition.start()}catch(_){startRecorderFallback()}
  }

  micBtn.addEventListener('click',()=>{if(fallbackRecording){try{mediaRecorder.stop()}catch(_){};return}startInstantRecognition()});
  voiceBtn.addEventListener('click',()=>{armVoice();voiceEnabled=!voiceEnabled;localStorage.setItem('jarvis.voice.enabled',String(voiceEnabled));if(!voiceEnabled)stopVoice();updateVoiceButton();if(voiceEnabled)speak('Voz natural ativada, senhor.',{interrupt:true,progress:true})});

  sendBtn.addEventListener('pointerdown',armVoice,true);
  sendBtn.addEventListener('click',()=>{armVoice();showProgress(inputEl.value)},true);
  inputEl.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){armVoice();showProgress(inputEl.value)}},true);
  document.addEventListener('pointerdown',armVoice,{once:true,capture:true});
})();
