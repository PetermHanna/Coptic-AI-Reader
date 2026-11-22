import { Matcher, tokenize } from './matcher.js';

const $ = (id) => document.getElementById(id);

// Book columns to match against for each recognizer language. No recognizer
// knows Coptic, but the Arabic one writes Coptic sounds in Arabic letters,
// which match the "Coptic in Arabic letters" text; same for English/Latin.
const MATCH_LANGS = {
  'ar-EG': ['ar', 'cop_ar'],
  'de-DE': ['de'],
  'en-US': ['en', 'cop_lat'],
};
const COPTIC_KEYS = ['cop', 'cop_lat', 'cop_ar'];
const COLUMN_NAMES = { en: 'English', de: 'Deutsch', cop: 'Ⲙⲉⲧⲣⲉⲙⲛ̀ⲭⲏⲙⲓ', ar: 'العربية' };

const settings = Object.assign(
  { thirdLang: 'en', copticScript: 'cop', speechLang: 'ar-EG', fontSize: 17, showWest: true, showCop: true, showAr: true },
  JSON.parse(localStorage.getItem('reader-settings') || '{}'),
);
const save = () => localStorage.setItem('reader-settings', JSON.stringify(settings));

let book, matcher, recognition, listening = false, wakeLock = null, demoTimer = null;
let cells = [];          // cells[para] = { west, cop, ar } -> { el, key, spans }
let autoFollow = true;   // false while the user scrolls away by hand

// ---------- rendering ----------

function columns() {
  const cols = [];
  if (settings.showWest) cols.push('west');
  if (settings.showCop) cols.push('cop');
  if (settings.showAr) cols.push('ar');
  return cols;
}

// Third column language: the chosen one, or English if the book lacks it.
function third() {
  const has = (l) => book?.languages?.[l] || book?.paragraphs?.some((p) => p.text[l]);
  return has(settings.thirdLang) ? settings.thirdLang : 'en';
}

// Which text key is shown in a column for paragraph p.
function keyFor(col, p) {
  if (col === 'west') return third();
  if (col === 'ar') return 'ar';
  const order = [settings.copticScript, ...COPTIC_KEYS.filter((k) => k !== settings.copticScript)];
  return order.find((k) => p.text[k]) || settings.copticScript;
}

const colLang = (col) => (col === 'west' ? third() : col);
const isRtl = (key) => key === 'ar' || key === 'cop_ar';

function localized(obj, lang) {
  if (!obj) return '';
  if (typeof obj === 'string') return obj;
  return obj[lang] || obj.en || Object.values(obj)[0] || '';
}

function renderHeader() {
  const head = $('colhead');
  head.innerHTML = '';
  for (const col of columns()) {
    const d = document.createElement('div');
    d.className = `cell col-${col}`;
    d.textContent = COLUMN_NAMES[colLang(col)];
    if (col === 'west' && third() !== settings.thirdLang) d.textContent += ` (no ${COLUMN_NAMES[settings.thirdLang]} in this book)`;
    if (col === 'ar') d.dir = 'rtl';
    head.append(d);
  }
  head.style.setProperty('--cols', columns().length || 1);
  $('westName').textContent = COLUMN_NAMES[settings.thirdLang];
}

function renderBook() {
  const main = $('book');
  main.innerHTML = '';
  main.style.setProperty('--cols', columns().length || 1);
  cells = [];
  const cols = columns();
  book.paragraphs.forEach((p, pi) => {
    if (p.section) {
      const h = document.createElement('div');
      h.className = 'row section';
      for (const col of cols) {
        const c = document.createElement('div');
        c.className = `cell col-${col}`;
        const lang = colLang(col);
        c.textContent = localized(p.section, lang === 'cop' ? 'cop' : lang) || localized(p.section, 'en');
        if (col === 'ar') c.dir = 'rtl';
        h.append(c);
      }
      main.append(h);
    }
    const row = document.createElement('div');
    row.className = 'row para';
    row.id = `p-${pi}`;
    row.onclick = () => { matcher.jumpTo(pi); autoFollow = true; highlight({ para: pi }, true); };
    cells[pi] = {};
    for (const col of cols) {
      const key = keyFor(col, p);
      const cell = document.createElement('div');
      cell.className = `cell col-${col} key-${key}`;
      if (isRtl(key)) cell.dir = 'rtl';
      if (p.role && book.roles?.[p.role]) {
        const r = document.createElement('div');
        r.className = 'role';
        r.textContent = localized(book.roles[p.role], colLang(col));
        cell.append(r);
      }
      const spans = [];
      const body = document.createElement('div');
      body.className = 'text';
      for (const w of (p.text[key] || '').split(/(\s+)/)) {
        if (!w.trim()) { body.append(w); continue; }
        const span = document.createElement('span');
        span.textContent = w;
        body.append(span);
        // one shown word can be several matcher tokens ("Lord's" -> lord, s)
        for (let i = 0; i < Math.max(1, tokenize(w).length); i++) spans.push(span);
      }
      if (!p.text[key]) body.classList.add('empty');
      cell.append(body);
      row.append(cell);
      cells[pi][col] = { key, spans };
    }
    main.append(row);
  });
  renderHeader();
  highlight(matcher.current, true);
}

// ---------- highlighting ----------

function highlight({ para, lang, idx }, instant = false) {
  document.querySelectorAll('.para.current').forEach((e) => e.classList.remove('current'));
  document.querySelectorAll('.word-now').forEach((e) => e.classList.remove('word-now'));
  const row = $(`p-${para}`);
  if (!row) return;
  row.classList.add('current');
  // mark the word in whichever column shows the text that was matched
  if (lang) {
    for (const c of Object.values(cells[para] || {})) {
      if (c.key === lang && c.spans[idx]) c.spans[idx].classList.add('word-now');
    }
  }
  if (autoFollow) scrollToRow(row, instant);
  else $('backToCurrent').hidden = false;
}

function scrollToRow(row, instant) {
  const top = row.getBoundingClientRect().top + window.scrollY;
  const offset = $('topbar').offsetHeight + $('colhead').offsetHeight + window.innerHeight * 0.18;
  programmaticScroll = true;
  window.scrollTo({ top: Math.max(0, top - offset), behavior: instant ? 'auto' : 'smooth' });
  clearTimeout(scrollTimer);
  scrollTimer = setTimeout(() => (programmaticScroll = false), 900);
}

// If the user scrolls by hand, stop auto-scrolling until they ask for it again.
let programmaticScroll = false, scrollTimer;
window.addEventListener('scroll', () => {
  if (programmaticScroll) return;
  const row = document.querySelector('.para.current');
  if (!row) return;
  const r = row.getBoundingClientRect();
  const visible = r.bottom > 0 && r.top < window.innerHeight;
  autoFollow = visible;
  $('backToCurrent').hidden = visible;
}, { passive: true });

$('backToCurrent').onclick = () => {
  autoFollow = true;
  $('backToCurrent').hidden = true;
  scrollToRow(document.querySelector('.para.current'));
};

// ---------- following ----------

function onHeard(text, languages = MATCH_LANGS[settings.speechLang]) {
  $('heard').textContent = text.split(/\s+/).slice(-9).join(' ');
  $('heard').classList.toggle('show', !!text);
  const r = matcher.locate(text, { languages });
  if (r) {
    highlight(r);
    setStatus(`Following · ${Math.round(Math.min(r.score, 1) * 100)}% sure`);
  }
}

function setStatus(s) { $('status').textContent = s; }

// Free speech recognition built into Chrome / Android / Safari.
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

function startListening() {
  stopDemo();
  if (!SR) { setStatus('No speech recognition in this browser. Use Chrome on Android.'); return; }
  recognition = new SR();
  recognition.lang = settings.speechLang;
  recognition.continuous = true;
  recognition.interimResults = true;
  let finalText = '';
  recognition.onresult = (e) => {
    let interim = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) finalText += ' ' + e.results[i][0].transcript;
      else interim += ' ' + e.results[i][0].transcript;
    }
    finalText = finalText.split(/\s+/).slice(-30).join(' ');
    onHeard((finalText + interim).trim());
  };
  recognition.onerror = (e) => {
    if (e.error === 'not-allowed') { stopListening(); setStatus('Microphone permission was denied.'); }
  };
  recognition.onend = () => { if (listening) setTimeout(() => recognition?.start(), 250); };
  recognition.start();
  listening = true;
  $('listen').setAttribute('aria-pressed', 'true');
  $('listenLabel').textContent = 'Stop';
  setStatus('Listening…');
  navigator.wakeLock?.request('screen').then((l) => (wakeLock = l)).catch(() => {});
}

function stopListening() {
  listening = false;
  recognition?.stop();
  recognition = null;
  wakeLock?.release();
  $('listen').setAttribute('aria-pressed', 'false');
  $('listenLabel').textContent = 'Listen';
  setStatus('Stopped');
}

// Demo: "read" the book aloud at speaking pace through the real matcher,
// switching language per row the way a service does.
function startDemo() {
  if (listening) stopListening();
  const plan = [];
  const langs = ['cop_lat', settings.thirdLang, 'ar'];
  book.paragraphs.forEach((p, i) => {
    // rotate the preferred language per row, use the first one the row has
    const prefer = langs.map((_, k) => langs[(i + k) % langs.length]);
    const lang = prefer.find((l) => p.text[l]);
    if (lang) for (const w of p.text[lang].split(/\s+/)) plan.push([w, lang]);
  });
  matcher.jumpTo(0);
  autoFollow = true;
  let i = 0, heard = [];
  $('demo').textContent = '■';
  setStatus('Demo: following a simulated service');
  demoTimer = setInterval(() => {
    if (i >= plan.length) { stopDemo(); setStatus('Demo finished'); return; }
    const [w, lang] = plan[i++];
    heard = [...heard.slice(-20), w];
    onHeard(heard.join(' '), [lang]);
  }, 380);
}

function stopDemo() {
  clearInterval(demoTimer);
  demoTimer = null;
  $('demo').textContent = '▶';
}

// ---------- settings ----------

function applySettings() {
  document.documentElement.style.setProperty('--font', settings.fontSize + 'px');
  for (const id of ['thirdLang', 'copticScript', 'speechLang', 'fontSize']) $(id).value = settings[id];
  for (const id of ['showWest', 'showCop', 'showAr']) $(id).checked = settings[id];
}

for (const id of ['thirdLang', 'copticScript', 'speechLang']) {
  $(id).onchange = () => {
    settings[id] = $(id).value; save();
    if (id === 'speechLang' && listening) { stopListening(); startListening(); }
    if (id !== 'speechLang') renderBook();
  };
}
for (const id of ['showWest', 'showCop', 'showAr']) {
  $(id).onchange = () => { settings[id] = $(id).checked; save(); renderBook(); };
}
$('fontSize').oninput = (e) => { settings.fontSize = +e.target.value; save(); applySettings(); };
$('menu').onclick = () => {
  const s = $('settings');
  s.hidden = !s.hidden;
  $('menu').setAttribute('aria-expanded', String(!s.hidden));
};
$('listen').onclick = () => (listening ? stopListening() : startListening());
$('demo').onclick = () => (demoTimer ? stopDemo() : startDemo());
$('simForm').onsubmit = (e) => { e.preventDefault(); onHeard($('simText').value, undefined); };
$('bookFile').onchange = async (e) => {
  const f = e.target.files[0];
  if (f) loadBook(JSON.parse(await f.text()));
};
document.addEventListener('visibilitychange', () => {
  if (listening && document.visibilityState === 'visible') {
    navigator.wakeLock?.request('screen').then((l) => (wakeLock = l)).catch(() => {});
  }
});

function loadBook(data) {
  book = data;
  matcher = new Matcher(book);
  $('bookTitle').textContent = book.title || 'Coptic AI Reader';
  renderBook();
}

// Books: the sample plus any collected library listed in books/tasbeha/index.json
async function listBooks() {
  try {
    const index = await (await fetch('books/tasbeha/index.json')).json();
    for (const b of index) {
      const o = document.createElement('option');
      o.value = `books/tasbeha/${b.file}`;
      o.textContent = `${b.title} (${b.hymns} hymns)`;
      $('bookSelect').append(o);
    }
  } catch { /* no library installed: sample only */ }
}

async function openBook(url) {
  setStatus('Opening book…');
  try {
    loadBook(await (await fetch(url)).json());
    settings.book = url; save();
    setStatus('Tap “Listen” when the service begins');
  } catch {
    setStatus('Could not open that book');
  }
}

$('bookSelect').onchange = () => openBook($('bookSelect').value);

applySettings();
await listBooks();
const startBook = [...$('bookSelect').options].some((o) => o.value === settings.book) ? settings.book : 'books/sample.json';
$('bookSelect').value = startBook;
await openBook(startBook);

// Offline support (only on https or localhost; ignored elsewhere)
if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
  navigator.serviceWorker.register('sw.js').catch(() => {});
}
