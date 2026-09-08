(() => {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;
  const inputEl = document.getElementById('input');
  const sendBtn = document.getElementById('send');
  const composer = document.querySelector('.composer');
  const actions = document.querySelector('.actions');
  if (!inputEl || !sendBtn || !composer || !actions) return;

  let voiceEnabled = localStorage.getItem('jarvis.voice.enabled') !== 'false';
  let voiceArmed = false;
  let listening = false;
  let recognition = null;

  const voiceBtn = document.createElement('button');
  voiceBtn.className = 'ghost';
  voiceBtn.id = 'voiceBtn';
  const micBtn = document.createElement('button');
  micBtn.className = 'ghost';
  micBtn.id = 'micBtn';
  micBtn.type = 'button';
  micBtn.textContent = 'MIC';
  micBtn.style.minWidth = '58px';
  composer.insertBefore(micBtn, sendBtn);
  actions.insertBefore(voiceBtn, actions.firstChild);

  function updateVoiceButton() {
    voiceBtn.textContent = voiceEnabled ? 'VOZ ON' : 'VOZ OFF';
    voiceBtn.classList.toggle('active', voiceEnabled);
  }
  updateVoiceButton();

  function preferredVoice() {
    if (!synth) return null;
    const voices = synth.getVoices();
    const pt = voices.filter(v => /^pt(-|_)?BR/i.test(v.lang) || /^pt/i.test(v.lang));
    const preferredNames = ['felipe', 'daniel', 'joão', 'joao', 'thiago', 'antonio', 'antônio'];
    return pt.find(v => preferredNames.some(n => v.name.toLowerCase().includes(n))) || pt[0] || voices[0] || null;
  }

  function cleanForSpeech(text) {
    return String(text || '')
      .replace(/https?:\/\/\S+/g, '')
      .replace(/[`*_#>|]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function speak(text) {
    if (!voiceEnabled || !voiceArmed || !synth) return;
    const clean = cleanForSpeech(text);
    if (!clean || /^erro:/i.test(clean) || /processando|atualizando workbench/i.test(clean)) return;
    synth.cancel();
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.lang = 'pt-BR';
    utterance.rate = 1.03;
    utterance.pitch = 0.92;
    const voice = preferredVoice();
    if (voice) utterance.voice = voice;
    synth.speak(utterance);
  }

  if (synth) {
    synth.addEventListener?.('voiceschanged', preferredVoice);
  }

  const originalAdd = window.add;
  if (typeof originalAdd === 'function') {
    window.add = function(text, cls, meta = '', messageActions = []) {
      const result = originalAdd(text, cls, meta, messageActions);
      if (cls === 'a') speak(text);
      return result;
    };
  }

  function setListening(on) {
    listening = on;
    micBtn.textContent = on ? 'OUVINDO' : 'MIC';
    micBtn.classList.toggle('active', on);
  }

  function recognitionErrorMessage(code) {
    if (code === 'not-allowed' || code === 'service-not-allowed') return 'Microfone bloqueado. Permita o acesso ao microfone do JARVIS no Safari.';
    if (code === 'audio-capture') return 'Não consegui acessar o microfone do aparelho.';
    if (code === 'network') return 'A transcrição por voz ficou indisponível por rede. Tente novamente.';
    return 'Não consegui transcrever o áudio. Tente novamente.';
  }

  function startRecognition() {
    voiceArmed = true;
    if (synth) synth.cancel();
    if (!SpeechRecognition) {
      if (typeof window.add === 'function') window.add('Senhor, a transcrição de voz não está disponível neste navegador. No iPhone, abra o JARVIS diretamente no Safari e verifique se a Siri está ativada.', 'a');
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
      if (typeof window.add === 'function') window.add('Senhor, ' + recognitionErrorMessage(event.error), 'a');
    };
    recognition.onend = () => {
      setListening(false);
      const text = inputEl.value.trim();
      if (text && finalText.trim()) {
        setTimeout(() => {
          if (typeof window.send === 'function') window.send();
          else sendBtn.click();
        }, 120);
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
    voiceArmed = true;
    voiceEnabled = !voiceEnabled;
    localStorage.setItem('jarvis.voice.enabled', String(voiceEnabled));
    if (!voiceEnabled && synth) synth.cancel();
    updateVoiceButton();
  });
  sendBtn.addEventListener('click', () => { voiceArmed = true; }, true);
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) voiceArmed = true;
  }, true);

  // A first tap anywhere in the app authorizes later speech synthesis on mobile Safari.
  document.addEventListener('pointerdown', () => { voiceArmed = true; }, { once: true, capture: true });
})();
