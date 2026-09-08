(() => {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;
  const inputEl = document.getElementById('input');
  const sendBtn = document.getElementById('send');
  const composer = document.querySelector('.composer');
  const actions = document.querySelector('.actions');
  const messages = document.getElementById('messages');
  if (!inputEl || !sendBtn || !composer || !actions || !messages) return;

  // -------------------------------------------------------------------------
  // Terminal-first interface: the default surface should feel like a command
  // console, not a dashboard full of cards. Workbenches/overlays remain available
  // when a task genuinely needs a visual workspace.
  // -------------------------------------------------------------------------
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
  let activeUtterance = null;
  const speechQueue = [];

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

  // Uber commands need an ephemeral device location before the request reaches
  // the backend. This never turns the coordinates into long-term memory.
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

  function preferredVoice() {
    if (!synth) return null;
    const voices = synth.getVoices() || [];
    const pt = voices.filter(v => /^pt(-|_)?BR/i.test(v.lang) || /^pt/i.test(v.lang));
    const preferredNames = ['felipe', 'daniel', 'joão', 'joao', 'thiago', 'antonio', 'antônio', 'ricardo'];
    return pt.find(v => preferredNames.some(n => v.name.toLowerCase().includes(n))) || pt[0] || voices[0] || null;
  }

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

  function speechChunks(text) {
    const clean = cleanForSpeech(text);
    if (!clean) return [];
    const sentences = clean.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [clean];
    const chunks = [];
    let current = '';
    for (const sentence of sentences) {
      const next = (current + ' ' + sentence.trim()).trim();
      if (next.length > 210 && current) {
        chunks.push(current);
        current = sentence.trim();
      } else {
        current = next;
      }
    }
    if (current) chunks.push(current);
    return chunks;
  }

  function unlockVoice() {
    voiceArmed = true;
    if (!synth) return;
    try { synth.resume(); } catch (_) {}
  }

  function speakNext() {
    if (!voiceEnabled || !voiceArmed || !synth || activeUtterance || !speechQueue.length) return;
    const text = speechQueue.shift();
    if (!text) return speakNext();
    const utterance = new SpeechSynthesisUtterance(text);
    activeUtterance = utterance; // keep a strong reference for Safari/iOS
    utterance.lang = 'pt-BR';
    utterance.rate = 1.02;
    utterance.pitch = 0.9;
    const voice = preferredVoice();
    if (voice) utterance.voice = voice;
    utterance.onend = utterance.onerror = () => {
      activeUtterance = null;
      setTimeout(speakNext, 20);
    };
    try {
      synth.resume();
      synth.speak(utterance);
    } catch (_) {
      activeUtterance = null;
    }
  }

  function speak(text, { interrupt = false } = {}) {
    if (!voiceEnabled || !voiceArmed || !synth) return;
    const clean = cleanForSpeech(text);
    if (!clean || /^erro:/i.test(clean) || /processando|atualizando workbench/i.test(clean)) return;
    if (interrupt) {
      speechQueue.length = 0;
      activeUtterance = null;
      try { synth.cancel(); } catch (_) {}
    }
    speechQueue.push(...speechChunks(clean));
    speakNext();
  }

  if (synth) {
    synth.addEventListener?.('voiceschanged', preferredVoice);
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
        const delay = /[.!?]/.test(char) ? 55 : /[,;:]/.test(char) ? 30 : 16;
        setTimeout(step, delay);
      }
    };
    setTimeout(step, 30);
  }

  // Every assistant response is rendered progressively and spoken. This keeps
  // tool, mission, local-search and collaborative replies consistent with chat.
  const observer = new MutationObserver(mutations => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (!(node instanceof HTMLElement) || !node.classList.contains('a')) continue;
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
  observer.observe(messages, { childList: true });

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
    if (synth) {
      try { synth.cancel(); } catch (_) {}
      activeUtterance = null;
      speechQueue.length = 0;
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
      inputEl.dispatchEvent(new Event('input', { bubbles: true }));
    };
    recognition.onerror = event => {
      setListening(false);
      if (typeof window.add === 'function') window.add(recognitionErrorMessage(event.error), 'a');
    };
    recognition.onend = () => {
      setListening(false);
      const text = inputEl.value.trim();
      if (text && finalText.trim()) {
        setTimeout(() => sendBtn.click(), 120);
      }
    };
    try {
      recognition.start();
    } catch (_) {
      setListening(false);
    }
  }

  micBtn.addEventListener('click', startRecognition);
  voiceBtn.addEventListener('click', () => {
    unlockVoice();
    voiceEnabled = !voiceEnabled;
    localStorage.setItem('jarvis.voice.enabled', String(voiceEnabled));
    if (!voiceEnabled && synth) {
      speechQueue.length = 0;
      activeUtterance = null;
      synth.cancel();
    }
    updateVoiceButton();
    if (voiceEnabled) speak('Voz ativada, senhor.', { interrupt: true });
  });

  // Explicit user gestures arm iOS speech synthesis before the asynchronous model
  // response arrives. This is the critical step for reliable Safari playback.
  sendBtn.addEventListener('pointerdown', unlockVoice, true);
  sendBtn.addEventListener('click', unlockVoice, true);
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) unlockVoice();
  }, true);
  document.addEventListener('pointerdown', unlockVoice, { once: true, capture: true });
})();
