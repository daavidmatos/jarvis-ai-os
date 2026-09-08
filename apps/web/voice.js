(() => {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  const inputEl = document.getElementById('input');
  const sendBtn = document.getElementById('send');
  const composer = document.querySelector('.composer');
  const actions = document.querySelector('.actions');
  const messages = document.getElementById('messages');
  if (!inputEl || !sendBtn || !composer || !actions || !messages) return;

  const terminalStyle = document.createElement('style');
  terminalStyle.textContent = `
    :root{font-family:"SFMono-Regular",Consolas,"Liberation Mono",Menlo,monospace!important;background:#020504!important;color:#d8ffe3!important}
    html,body{background:#020504!important}
    body{background:#020504!important}
    .shell{max-width:none!important;margin:0!important;padding:max(10px,env(safe-area-inset-top)) 12px max(10px,env(safe-area-inset-bottom))!important}
    .top{margin:0!important;padding:4px 0 10px!important;border-bottom:1px solid rgba(127,255,169,.18)!important;align-items:center!important}
    .brand{letter-spacing:.18em!important;color:#86ffad!important;font-size:15px!important}
    .top .small{font-size:9px!important;color:#7ea68a!important;opacity:1!important}
    .status{color:#8cffad!important;font-size:9px!important}
    .dot{width:6px!important;height:6px!important;box-shadow:none!important}
    .dot.on{background:#78ff9f!important;box-shadow:0 0 8px rgba(120,255,159,.55)!important}
    .actions{gap:4px!important}
    button,.buttonlink{font-family:inherit!important;border-radius:0!important;background:transparent!important;color:#9effbc!important;border:1px solid rgba(127,255,169,.22)!important;box-shadow:none!important;font-weight:600!important;padding:7px 9px!important}
    button:hover,.buttonlink:hover,.ghost.active{background:rgba(127,255,169,.06)!important;border-color:rgba(127,255,169,.55)!important;box-shadow:none!important}
    .mainlayout{gap:8px!important}
    .panel{background:transparent!important;border:0!important;border-radius:0!important;backdrop-filter:none!important;box-shadow:none!important}
    #messages{padding:14px 0 18px!important}
    .m{position:relative!important;max-width:100%!important;width:100%!important;margin:0!important;padding:5px 0!important;border:0!important;border-radius:0!important;background:transparent!important;line-height:1.55!important;font-size:14px!important;color:#d7f8df!important;white-space:pre-wrap!important}
    .m.u{margin-left:0!important;color:#b7d7c0!important}
    .m.u::before{content:"> ";color:#7dff9f!important;font-weight:700!important}
    .m.a::before{content:"JARVIS> ";color:#7dff9f!important;font-weight:700!important}
    .m.jarvis-progress{color:#7ea68a!important;font-style:italic!important}
    .m.jarvis-progress::before{content:"JARVIS> ";color:#6bb883!important}
    .m>div:first-child{display:inline!important}
    .meta{display:none!important}
    .msgactions{display:flex!important;gap:6px!important;margin:8px 0 3px 0!important;padding-left:0!important}
    .msgactions a,.msgactions button{font-size:10px!important;padding:6px 8px!important}
    .composer{position:relative!important;background:#020504!important;border-top:1px solid rgba(127,255,169,.18)!important;padding:9px 0 0!important;gap:6px!important}
    .composer::before{content:">";display:flex;align-items:center;color:#7dff9f;font-weight:800;padding:0 1px 0 0}
    textarea{background:transparent!important;border:0!important;border-radius:0!important;color:#e7ffed!important;font-family:inherit!important;padding:10px 5px!important;min-height:46px!important;box-shadow:none!important}
    textarea::placeholder{color:#557660!important}
    .send{width:auto!important;min-width:70px!important}
    #voiceBtn,#micBtn{white-space:nowrap!important}
    .workbench{border-radius:0!important;background:#030806!important;border:1px solid rgba(127,255,169,.2)!important;box-shadow:none!important}
    .workhead,.workbody{font-family:inherit!important}
    .setup,.integration{border-radius:0!important;background:#030806!important;font-family:inherit!important}
    .overlay{backdrop-filter:none!important;background:rgba(1,4,3,.94)!important}
    @media(max-width:760px){
      .shell{padding:max(8px,env(safe-area-inset-top)) 10px max(8px,env(safe-area-inset-bottom))!important}
      .top{align-items:flex-start!important}.actions{max-width:68%!important;justify-content:flex-end!important}
      .actions button{font-size:9px!important;padding:6px 7px!important}
      .panel{height:calc(100dvh - 58px)!important}
      #messages{padding:10px 0 14px!important}
      .m{font-size:13px!important;padding:4px 0!important}
      .composer{padding-top:7px!important}
      .send{min-width:62px!important;padding:8px 7px!important}
    }
  `;
  document.head.appendChild(terminalStyle);

  let voiceEnabled = localStorage.getItem('jarvis.voice.enabled') !== 'false';
  let voiceArmed = false;
  let listening = false;
  let recognition = null;
  let audioCtx = null;
  let activeSource = null;
  let naturalBusy = false;
  let progressAbort = null;
  const naturalQueue = [];

  const voiceBtn = document.createElement('button');
  voiceBtn.className = 'ghost';
  voiceBtn.id = 'voiceBtn';
  voiceBtn.type = 'button';
  voiceBtn.title = 'Voz natural em português brasileiro';
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
    window.isLocalIntent = text => {
      const t = String(text || '').toLowerCase();
      return originalLocalIntent(text) || t.includes('uber');
    };
  }

  function updateVoiceButton() {
    voiceBtn.textContent = voiceEnabled ? 'VOICE:ON' : 'VOICE:OFF';
    voiceBtn.classList.toggle('active', voiceEnabled);
  }
  updateVoiceButton();

  function cleanForSpeech(text) {
    return String(text || '')
      .replace(/https?:\/\/\S+/g, '')
      .replace(/[`*_#>|]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function userFacing(text) {
    const clean = String(text || '').trim();
    if (!clean || /^erro:/i.test(clean) || /processando|atualizando workbench/i.test(clean)) return clean;
    if (/\bsenhor\b/i.test(clean)) return clean;
    return `Senhor, ${clean}`;
  }

  function exactBrazilianVoice() {
    if (!synth) return null;
    const voices = synth.getVoices() || [];
    return voices.find(v => /^pt[-_]BR$/i.test(v.lang)) || null;
  }

  function ensureAudioContext() {
    if (!AudioContextCtor) return null;
    if (!audioCtx) audioCtx = new AudioContextCtor();
    if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
    return audioCtx;
  }

  function unlockVoice() {
    voiceArmed = true;
    ensureAudioContext();
    if (synth) {
      try { synth.resume(); } catch (_) {}
    }
  }

  function fallbackSpeak(text) {
    if (!voiceEnabled || !voiceArmed || !synth) return;
    const clean = cleanForSpeech(text);
    if (!clean) return;
    try { synth.cancel(); } catch (_) {}
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.lang = 'pt-BR';
    utterance.rate = 0.94;
    utterance.pitch = 0.92;
    const ptBR = exactBrazilianVoice();
    if (ptBR) utterance.voice = ptBR;
    try { synth.speak(utterance); } catch (_) {}
  }

  function base64ToBytes(value) {
    const raw = atob(value);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    return bytes;
  }

  async function fetchNaturalBuffer(text, progress, signal) {
    const response = await fetch('/v1/tools/voice.synthesize/execute', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({args: {text, progress}}),
      signal,
    });
    if (!response.ok) throw new Error(`voice http ${response.status}`);
    const payload = await response.json();
    if (!payload.ok || !payload.result?.audio_base64) throw new Error(payload.error || 'voice unavailable');
    const ctx = ensureAudioContext();
    if (!ctx) throw new Error('Web Audio unavailable');
    const bytes = base64ToBytes(payload.result.audio_base64);
    const copied = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    return await ctx.decodeAudioData(copied);
  }

  function stopNaturalAudio() {
    if (progressAbort) {
      try { progressAbort.abort(); } catch (_) {}
      progressAbort = null;
    }
    naturalQueue.length = 0;
    if (activeSource) {
      try { activeSource.stop(); } catch (_) {}
      activeSource = null;
    }
    naturalBusy = false;
  }

  async function drainNaturalQueue() {
    if (naturalBusy || !naturalQueue.length || !voiceEnabled || !voiceArmed) return;
    naturalBusy = true;
    const item = naturalQueue.shift();
    let controller = null;
    if (item.progress) {
      controller = new AbortController();
      progressAbort = controller;
    }
    try {
      const buffer = await fetchNaturalBuffer(item.text, item.progress, controller?.signal);
      if (!voiceEnabled || !voiceArmed) return;
      const ctx = ensureAudioContext();
      if (!ctx) throw new Error('audio context unavailable');
      await new Promise(resolve => {
        const source = ctx.createBufferSource();
        activeSource = source;
        source.buffer = buffer;
        source.connect(ctx.destination);
        source.onended = () => {
          if (activeSource === source) activeSource = null;
          resolve();
        };
        source.start(0);
      });
    } catch (error) {
      if (error?.name !== 'AbortError') fallbackSpeak(item.text);
    } finally {
      if (controller && progressAbort === controller) progressAbort = null;
      naturalBusy = false;
      setTimeout(drainNaturalQueue, 10);
    }
  }

  function speak(text, {interrupt = false, progress = false} = {}) {
    if (!voiceEnabled || !voiceArmed) return;
    const clean = cleanForSpeech(text);
    if (!clean || /^erro:/i.test(clean) || /processando|atualizando workbench/i.test(clean)) return;
    if (interrupt) stopNaturalAudio();
    naturalQueue.push({text: clean, progress});
    drainNaturalQueue();
  }

  if (synth) {
    synth.addEventListener?.('voiceschanged', exactBrazilianVoice);
    try { synth.getVoices(); } catch (_) {}
  }

  function typeReply(body, text) {
    if (!body || body.dataset.jarvisTyping === '1') return;
    if (!text || /^Processando…$/i.test(text) || /^Erro:/i.test(text)) return;
    body.dataset.jarvisTyping = '1';
    body.textContent = '';
    let index = 0;
    const length = text.length;
    const step = () => {
      if (!body.isConnected) return;
      const burst = length > 1000 ? 5 : length > 450 ? 3 : 2;
      index = Math.min(length, index + burst);
      body.textContent = text.slice(0, index);
      messages.scrollTop = messages.scrollHeight;
      if (index < length) {
        const char = text[index - 1] || '';
        const delay = /[.!?]/.test(char) ? 60 : /[,;:]/.test(char) ? 34 : 17;
        setTimeout(step, delay);
      }
    };
    setTimeout(step, 20);
  }

  let progressNode = null;
  function clearProgress({abortVoice = true} = {}) {
    if (progressNode?.isConnected) progressNode.remove();
    progressNode = null;
    if (abortVoice && progressAbort) {
      try { progressAbort.abort(); } catch (_) {}
      progressAbort = null;
    }
  }

  function progressMessage(text) {
    const t = String(text || '').toLowerCase();
    if (!t.trim()) return null;
    if (/pesquis|procure|busque|encontre|internet|web/.test(t)) return 'Pesquisando, senhor. Um instante.';
    if (/analise|analisa|avali|estatíst|relatório|compare/.test(t)) return 'Analisando, senhor. Um instante.';
    if (/uber|corrida/.test(t)) return 'Certo, senhor. Preparando a corrida.';
    if (/abra|abrir|navegador|guia/.test(t)) return 'Certo, senhor. Abrindo.';
    if (/crie|criar|figma|photoshop|illustrator|blender|after effects|premiere|campanha/.test(t)) return 'Entendido, senhor. Inicializando.';
    if (/gmail|email|e-mail|calend|agenda|trello|planilha|documento|monitore|monitorar|execute|publique/.test(t)) return 'Certo, senhor. Processando.';
    return null;
  }

  function showProgress(text) {
    const status = progressMessage(text);
    if (!status) return;
    clearProgress();
    const node = document.createElement('div');
    node.className = 'm a jarvis-progress';
    node.dataset.jarvisProgress = '1';
    const body = document.createElement('div');
    body.textContent = status;
    node.appendChild(body);
    messages.appendChild(node);
    progressNode = node;
    messages.scrollTop = messages.scrollHeight;
    speak(status, {interrupt: true, progress: true});
  }

  const observer = new MutationObserver(mutations => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (!(node instanceof HTMLElement) || !node.classList.contains('a')) continue;
        if (node.dataset.jarvisProgress === '1') continue;
        clearProgress({abortVoice: true});
        const body = node.firstElementChild;
        if (!body) continue;
        const original = body.textContent || '';
        const styled = userFacing(original);
        if (styled !== original) body.textContent = styled;
        typeReply(body, styled);
        speak(styled);
      }
    }
  });
  observer.observe(messages, {childList: true});

  function setListening(on) {
    listening = on;
    micBtn.textContent = on ? 'LISTENING' : 'MIC';
    micBtn.classList.toggle('active', on);
  }

  function recognitionErrorMessage(code) {
    if (code === 'not-allowed' || code === 'service-not-allowed') return 'Microfone bloqueado. Permita o acesso ao microfone do JARVIS no Safari.';
    if (code === 'audio-capture') return 'Não consegui acessar o microfone do aparelho.';
    if (code === 'network') return 'A transcrição por voz ficou indisponível por rede. Tente novamente.';
    return 'Não consegui transcrever o áudio. Tente novamente.';
  }

  function startRecognition() {
    unlockVoice();
    stopNaturalAudio();
    if (synth) {
      try { synth.cancel(); } catch (_) {}
    }
    if (!SpeechRecognition) {
      if (typeof window.add === 'function') window.add('A transcrição de voz não está disponível neste navegador. No iPhone, abra o JARVIS diretamente no Safari e verifique se a Siri está ativada.', 'a');
      return;
    }
    if (listening && recognition) {
      recognition.stop();
      return;
    }

    recognition = new SpeechRecognition();
    recognition.lang = 'pt-BR';
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    let finalText = '';

    recognition.onstart = () => setListening(true);
    recognition.onresult = event => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const text = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += text;
        else interim += text;
      }
      inputEl.value = (finalText || interim).trim();
      inputEl.dispatchEvent(new Event('input', {bubbles: true}));
    };
    recognition.onerror = event => {
      setListening(false);
      if (typeof window.add === 'function') window.add(recognitionErrorMessage(event.error), 'a');
    };
    recognition.onend = () => {
      setListening(false);
      const text = inputEl.value.trim();
      if (text && finalText.trim()) setTimeout(() => sendBtn.click(), 120);
    };
    try { recognition.start(); } catch (_) { setListening(false); }
  }

  micBtn.addEventListener('click', startRecognition);
  voiceBtn.addEventListener('click', () => {
    unlockVoice();
    voiceEnabled = !voiceEnabled;
    localStorage.setItem('jarvis.voice.enabled', String(voiceEnabled));
    if (!voiceEnabled) {
      stopNaturalAudio();
      if (synth) try { synth.cancel(); } catch (_) {}
    }
    updateVoiceButton();
    if (voiceEnabled) speak('Voz natural ativada, senhor.', {interrupt: true, progress: true});
  });

  // Add an immediate operational acknowledgement before the slower network/model
  // path begins. Capture phase ensures we read the command before the app clears it.
  sendBtn.addEventListener('click', () => {
    unlockVoice();
    showProgress(inputEl.value);
  }, true);
  sendBtn.addEventListener('pointerdown', unlockVoice, true);
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      unlockVoice();
      showProgress(inputEl.value);
    }
  }, true);
  document.addEventListener('pointerdown', unlockVoice, {once: true, capture: true});
})();
