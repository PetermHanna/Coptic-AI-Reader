import { Matcher, tokenize } from './matcher.js';

const $ = (id) => document.getElementById(id);
const RTL = new Set(['ar', 'cop_ar']);
// Which book columns to match against for each recognizer language.
// Coptic has no speech recognizer, but the Arabic recognizer writes Coptic
// sounds in Arabic letters, which we match against the "Coptic in Arabic
// letters" column. Same idea for English + Coptic in Latin letters.
const MATCH_LANGS = {
  'en-US': ['en', 'cop_lat'],
  'ar-EG': ['ar', 'cop_ar'],
};

let book, matcher, recognition, listening = false, wakeLock = null;
let shownLangs = new Set();
const wordEls = []; // wordEls[para][lang] = [span per token]

async function loadBook(data) {
  book = data;
  matcher = new Matcher(book);
  const langs = Object.keys(book.languages || {}).filter((l) => matcher.streams[l]);
  shownLangs = new Set(langs.filter((l) => l !== 'cop_lat'));
  renderColumnToggles(langs);
  renderBook();
}

function renderColumnToggles(langs) {
  const box = $('columns');
  box.innerHTML = 'Show: ';
  for (const l of langs) {
    const label = document.createElement('label');
    label.className = 'chip';
    const cb = Object.assign(document.createElement('input'), { type: 'checkbox', checked: shownLangs.has(l) });
    cb.onchange = () => { cb.checked ? shownLangs.add(l) : shownLangs.delete(l); renderBook(); };
    label.append(cb, ' ', book.languages[l] || l);
    box.append(label);
  }
}

function renderBook() {
  const main = $('book');
  main.innerHTML = '';
  wordEls.length = 0;
  const langs = Object.keys(book.languages).filter((l) => shownLangs.has(l));
  main.style.setProperty('--cols', langs.length || 1);
  book.paragraphs.forEach((p, pi) => {
    if (p.section) {
      const h = document.createElement('h2');
      h.textContent = p.section;
      main.append(h);
    }
    const row = document.createElement('div');
    row.className = 'para';
    row.id = `p-${pi}`;
    row.onclick = () => { matcher.jumpTo(pi); highlight({ para: pi }); };
    wordEls[pi] = {};
    for (const l of langs) {
      const cell = document.createElement('div');
      cell.className = `cell lang-${l}`;
      if (RTL.has(l)) cell.dir = 'rtl';
      const spans = (wordEls[pi][l] = []);
      for (const w of (p.text[l] || '').split(/(\s+)/)) {
        if (!w.trim()) { cell.append(w); continue; }
        const span = document.createElement('span');
        span.textContent = w;
        cell.append(span);
        // one display word may hold several tokens (e.g. "Lord's" → lord, s)
        for (let i = 0; i < Math.max(1, tokenize(w).length); i++) spans.push(span);
      }
      row.append(cell);
    }
    main.append(row);
  });
  highlight(matcher.current);
}

function highlight({ para, lang, idx }) {
  document.querySelectorAll('.para.current').forEach((e) => e.classList.remove('current'));
  document.querySelectorAll('span.word-now').forEach((e) => e.classList.remove('word-now'));
  const row = $(`p-${para}`);
  if (!row) return;
  row.classList.add('current');
  const span = lang && wordEls[para]?.[lang]?.[idx];
  if (span) span.classList.add('word-now');
  row.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function onHeard(text) {
  $('heard').textContent = '“' + text.split(/\s+/).slice(-10).join(' ') + '”';
  const r = matcher.locate(text, { languages: MATCH_LANGS[$('speechLang').value] });
  if (r) {
    highlight(r);
    $('status').textContent = `Following (${Math.round(Math.min(r.score, 1) * 100)}% match)`;
  }
}

// ---- Speech recognition (free, built into Chrome / Edge / Safari) ----
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

function startListening() {
  if (!SR) {
    $('status').textContent = 'This browser has no built-in speech recognition. Please use Chrome, Edge or Safari.';
    return;
  }
  recognition = new SR();
  recognition.lang = $('speechLang').value;
  recognition.continuous = true;
  recognition.interimResults = true;
  let finalText = '';
  recognition.onresult = (e) => {
    let interim = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) finalText += ' ' + e.results[i][0].transcript;
      else interim += ' ' + e.results[i][0].transcript;
    }
    finalText = finalText.split(/\s+/).slice(-30).join(' '); // keep it short
    onHeard((finalText + interim).trim());
  };
  recognition.onerror = (e) => {
    if (e.error === 'not-allowed') { stopListening(); $('status').textContent = 'Microphone permission was denied.'; }
  };
  // Browsers stop recognition after silence; restart while the user wants it on.
  recognition.onend = () => { if (listening) setTimeout(() => recognition?.start(), 250); };
  recognition.start();
  listening = true;
  $('listen').textContent = '⏹ Stop';
  $('status').textContent = 'Listening…';
  navigator.wakeLock?.request('screen').then((l) => (wakeLock = l)).catch(() => {});
}

function stopListening() {
  listening = false;
  recognition?.stop();
  recognition = null;
  wakeLock?.release();
  $('listen').textContent = '🎤 Start listening';
  $('status').textContent = 'Stopped.';
}

$('listen').onclick = () => (listening ? stopListening() : startListening());
$('speechLang').onchange = () => { if (listening) { stopListening(); startListening(); } };
$('fontSize').oninput = (e) => document.documentElement.style.setProperty('--font', e.target.value + 'px');
$('simForm').onsubmit = (e) => { e.preventDefault(); onHeard($('simText').value); };
$('bookFile').onchange = async (e) => {
  const f = e.target.files[0];
  if (f) loadBook(JSON.parse(await f.text()));
};
document.addEventListener('visibilitychange', () => {
  if (listening && document.visibilityState === 'visible') navigator.wakeLock?.request('screen').then((l) => (wakeLock = l)).catch(() => {});
});

loadBook(await (await fetch('books/sample.json')).json());
