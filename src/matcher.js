// Matcher: finds where in the prayer book the spoken words are.
// Pure JS, no dependencies, works in the browser and in Node (for tests).
//
// Idea: every language column of the book is flattened into one long word
// stream. The last few recognized words are compared against sliding windows
// of that stream using character-trigram similarity, which tolerates
// misrecognized words, missing diacritics and spelling variants. Positions
// just ahead of the current reading position get a bonus, because people read
// forward.

const ARABIC_FIXES = [
  [/[أإآٱ]/g, 'ا'],
  [/ة/g, 'ه'],
  [/ى/g, 'ي'],
  [/ؤ/g, 'و'],
  [/ئ/g, 'ي'],
  [/ـ/g, ''], // tatweel
];

export function normalize(text) {
  let t = String(text).toLowerCase().normalize('NFD').replace(/\p{M}/gu, '');
  for (const [re, rep] of ARABIC_FIXES) t = t.replace(re, rep);
  return t.replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

export function tokenize(text) {
  const n = normalize(text);
  return n ? n.split(' ') : [];
}

function trigrams(str) {
  const s = ` ${str} `;
  const grams = new Map();
  for (let i = 0; i < s.length - 2; i++) {
    const g = s.slice(i, i + 3);
    grams.set(g, (grams.get(g) || 0) + 1);
  }
  return grams;
}

function dice(a, b) {
  let inter = 0, sizeA = 0, sizeB = 0;
  for (const v of a.values()) sizeA += v;
  for (const [g, v] of b) {
    sizeB += v;
    const av = a.get(g);
    if (av) inter += Math.min(av, v);
  }
  return sizeA + sizeB === 0 ? 0 : (2 * inter) / (sizeA + sizeB);
}

export class Matcher {
  /**
   * @param {object} book  { paragraphs: [{ id, text: { en, ar, ... } }] }
   * @param {object} opts
   */
  constructor(book, opts = {}) {
    this.opts = {
      windowWords: 8,       // how many of the latest spoken words to match
      minScore: 0.45,       // below this we don't move
      localBehind: 2,       // paragraphs behind current considered "local"
      localAhead: 6,        // paragraphs ahead considered "local"
      localBonus: 0.08,
      ...opts,
    };
    this.paragraphs = book.paragraphs;
    // streams[lang] = [{ word, para, idx }]
    this.streams = {};
    book.paragraphs.forEach((p, pi) => {
      for (const [lang, text] of Object.entries(p.text || {})) {
        const s = (this.streams[lang] ||= []);
        tokenize(text).forEach((word, idx) => s.push({ word, para: pi, idx }));
      }
    });
    this.current = { para: 0, lang: null, idx: 0 };
  }

  languages() {
    return Object.keys(this.streams);
  }

  /** Feed the recognized transcript (can be the whole running text). */
  locate(transcript, { languages } = {}) {
    const words = tokenize(transcript).slice(-this.opts.windowWords);
    if (words.length < 2) return null;
    const qGrams = trigrams(words.join(' '));
    const langs = languages?.length ? languages : this.languages();

    const scan = (from, to) => {
      let best = null;
      for (const lang of langs) {
        const s = this.streams[lang];
        if (!s) continue;
        for (let i = 0; i < s.length; i++) {
          const p = s[i].para;
          if (p < from || p > to) continue;
          // compare windows of similar length (± 2 words for dropped/extra words)
          for (const len of [words.length - 1, words.length, words.length + 1]) {
            if (len < 1 || i + len > s.length) continue;
            const win = s.slice(i, i + len);
            let score = dice(qGrams, trigrams(win.map((w) => w.word).join(' ')));
            const endPara = win[win.length - 1].para;
            const d = endPara - this.current.para;
            if (d >= -this.opts.localBehind && d <= this.opts.localAhead) {
              score += this.opts.localBonus;
            }
            if (!best || score > best.score) {
              const last = win[win.length - 1];
              best = { score, para: last.para, idx: last.idx, lang };
            }
          }
        }
      }
      return best;
    };

    const c = this.current.para;
    let best = scan(c - this.opts.localBehind, c + this.opts.localAhead);
    // Only skip the whole-book search when the nearby match is near-perfect:
    // repeated prayers (e.g. the Trisagion verses) look "good" but differ at the end.
    if (!best || best.score - this.opts.localBonus < 0.9) {
      const global = scan(0, this.paragraphs.length - 1);
      if (global && (!best || global.score > best.score)) best = global;
    }
    if (!best || best.score < this.opts.minScore) return null;
    this.current = { para: best.para, lang: best.lang, idx: best.idx };
    return { ...best, paragraph: this.paragraphs[best.para] };
  }

  jumpTo(paraIndex) {
    this.current = { para: paraIndex, lang: null, idx: 0 };
  }
}
