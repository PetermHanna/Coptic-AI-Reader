// Coptic by sound: the phone's AI model turns audio into sounds (IPA phones);
// this file turns the book's Coptic text into the same sounds and finds where
// in the book the heard sounds are. Port of research/step1/{phonetics,track}.py.

// ---- Coptic -> IPA (Greco-Bohairic church pronunciation, simplified) ----
const DIGRAPHS = { 'ⲟⲩ': 'u', 'ⲁⲩ': 'av', 'ⲉⲩ': 'ev', 'ⲏⲩ': 'iv' };
const LETTERS = {
  'ⲁ': 'a', 'ⲃ': 'v', 'ⲅ': 'g', 'ⲇ': 'd', 'ⲉ': 'e', 'ⲍ': 'z', 'ⲏ': 'i', 'ⲑ': 'θ', 'ⲓ': 'i',
  'ⲕ': 'k', 'ⲗ': 'l', 'ⲙ': 'm', 'ⲛ': 'n', 'ⲝ': 'ks', 'ⲟ': 'o', 'ⲡ': 'p', 'ⲣ': 'r', 'ⲥ': 's',
  'ⲧ': 't', 'ⲩ': 'i', 'ⲫ': 'f', 'ⲭ': 'x', 'ⲯ': 'ps', 'ⲱ': 'o', 'ϣ': 'ʃ', 'ϥ': 'f', 'ϧ': 'x',
  'ϩ': 'h', 'ϫ': 'dʒ', 'ϭ': 'tʃ', 'ϯ': 'ti',
};
const VOWELS = new Set('ⲁⲉⲏⲓⲟⲩⲱ');
const JINKIM = '̀';

export function copticToIpa(text) {
  const t = text.toLowerCase().normalize('NFD');
  let out = '';
  for (let i = 0; i < t.length; i++) {
    const ch = t[i], next = t[i + 1];
    const pair = ch + (next || '');
    if (DIGRAPHS[pair]) { out += DIGRAPHS[pair]; i++; continue; }
    if (LETTERS[ch]) {
      if (next === JINKIM && !VOWELS.has(ch)) out += 'e'; // jinkim: short e before the consonant
      out += ch === 'ⲅ' && 'ⲅⲕⲭ'.includes(next || '-') ? 'n' : LETTERS[ch];
    } else if (/[\s:.,;]/.test(ch)) out += ' ';
  }
  return out.replace(/\s+/g, ' ').trim();
}

// ---- shared sound groups: similar sounds count as the same letter ----
const CLASSES = {
  A: 'aɑæɐʌ', E: 'eɛəɘœøɜ', I: 'iɪyʏɨj', O: 'oɔɒ', U: 'uʊɯw',
  P: 'pb', T: 'tdʈɖθð', K: 'kgqɡcɟ', F: 'fvɸβ', S: 'szʃʒɕʂʑç',
  H: 'xχħhɣʁɦʕ', M: 'm', N: 'nŋɲɳɴ', L: 'lɫɭʎ', R: 'rɾɹʀɽ',
};
const ALPHA = [...Object.keys(CLASSES), '#'];
const CODE = Object.fromEntries(ALPHA.map((c, i) => [c, i]));
const CHAR2CLASS = {};
for (const [k, chars] of Object.entries(CLASSES)) for (const c of chars) CHAR2CLASS[c] = k;
const VOWEL = new Set('AEIOU');
const SEP = CODE['#'];

export function ipaToClasses(ipa) {
  let out = '';
  for (const ch of ipa.replace(/ç/g, 'ʃ').normalize('NFD')) {
    const k = CHAR2CLASS[ch];
    if (k && !(VOWEL.has(k) && out.endsWith(k))) out += k; // merge long vowels
  }
  return out;
}

// substitution cost: same group 0, vowel-for-vowel 0.5, otherwise 1
const N = ALPHA.length;
const COST = new Float32Array(N * N).fill(1);
for (let a = 0; a < N; a++) for (let b = 0; b < N; b++) {
  if (a === b && a !== SEP) COST[a * N + b] = 0;
  else if (VOWEL.has(ALPHA[a]) && VOWEL.has(ALPHA[b])) COST[a * N + b] = 0.5;
}

function prior(delta) { // extra cost for moving `delta` rows from where we are
  if (delta >= -0.15 && delta <= 1.5) return 0;            // reading on
  if (delta > 1.5) return Math.min(0.08 + 0.02 * (delta - 1.5), 0.25); // skipping ahead
  return Math.min(0.15 + 0.05 * -delta, 0.3);                // going back
}

export class SoundTracker {
  /** book: app book JSON. Uses each row's Coptic text (cop, else none). */
  constructor(book, { maxCost = 0.55 } = {}) {
    const codes = [], coord = [], row = [];
    book.paragraphs.forEach((p, ri) => {
      const cop = p.text?.cop;
      if (!cop) return;
      const s = ipaToClasses(copticToIpa(cop));
      for (let k = 0; k < s.length; k++) { codes.push(CODE[s[k]]); row.push(ri); coord.push(ri + (k + 1) / s.length); }
      codes.push(SEP); row.push(ri); coord.push(ri + 1);
    });
    this.text = Int8Array.from(codes);
    this.row = Int32Array.from(row);
    this.coord = Float32Array.from(coord);
    this.maxCost = maxCost;
    this.pos = 0;        // reading position: row + fraction of the row
    this.pending = null; // a big jump waits for one confirmation
  }

  jumpTo(rowIndex) { this.pos = rowIndex; this.pending = null; }

  /**
   * phones: IPA phone strings heard in the last few seconds (oldest first).
   * Returns { para } when the position is known, else null.
   */
  locate(phones) {
    const q = ipaToClasses(phones.join(''));
    if (q.length < 6 || !this.text.length) return null;
    const n = this.text.length, T = this.text;
    let prev = new Float32Array(n + 1), cur = new Float32Array(n + 1);
    for (const ch of q) { // fuzzy search with free start and end in the book
      const qi = CODE[ch] * N;
      cur[0] = prev[0] + 1;
      for (let j = 1; j <= n; j++) {
        const diag = prev[j - 1] + COST[qi + T[j - 1]];
        const up = prev[j] + 1;
        const left = cur[j - 1] + 1;
        cur[j] = diag < up ? (diag < left ? diag : left) : (up < left ? up : left);
      }
      [prev, cur] = [cur, prev];
    }
    let best = -1, bestScore = Infinity;
    for (let j = 0; j < n; j++) {
      const s = prev[j + 1] / q.length + prior(this.coord[j] - this.pos);
      if (s < bestScore) { bestScore = s; best = j; }
    }
    const cost = prev[best + 1] / q.length;
    if (cost >= this.maxCost) return null;
    const c = this.coord[best], delta = c - this.pos;
    const jump = !(delta >= -0.15 && delta <= 1.5);
    if (!jump || (this.pending !== null && Math.abs(this.pending - c) < 0.6)) {
      this.pos = c; this.pending = null;
    } else {
      this.pending = c;
      return null;
    }
    return { para: this.row[best], cost };
  }

  get para() { return this.text.length ? Math.max(0, Math.ceil(this.pos) - 1) : 0; }
}
