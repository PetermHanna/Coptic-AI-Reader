// Score the app's real word matcher (src/matcher.js) on a recording:
// every second, feed it the words heard so far, like the phone would.
// Usage: node track_words.mjs BOOK.json WORDS.json TRUTH.json [--verbose]
import { readFileSync } from 'node:fs';
import { Matcher } from '../../src/matcher.js';

const [bookPath, wordsPath, truthPath] = process.argv.slice(2);
const verbose = process.argv.includes('--verbose');
const book = JSON.parse(readFileSync(bookPath, 'utf8'));
const words = JSON.parse(readFileSync(wordsPath, 'utf8'));
const truth = JSON.parse(readFileSync(truthPath, 'utf8'));

const m = new Matcher(book);
const ids = book.paragraphs.map((p) => p.id);
const end = truth.at(-1).end;
const res = [];
for (let t = 2; t <= end + 0.5; t += 1) {
  const heard = words.filter(([s]) => s < t && s >= t - 12).map(([, w]) => w).join(' ');
  m.locate(heard);
  const said = truth.filter((r) => r.start <= t - 0.5);
  if (said.length) res.push([t, said.at(-1).id, ids[m.current.para]]);
}
const ok = res.filter(([, a, b]) => a === b).length;
if (verbose) for (const [t, a, b] of res) console.log(`${t}s reading ${a} app shows ${b}${a === b ? '' : '  <-- wrong'}`);
const lock = truth.map((r) => {
  const hit = res.find(([t, a, b]) => a === r.id && b === r.id);
  return hit ? hit[0] - r.start : null;
});
const secs = lock.filter((x) => x !== null).sort((a, b) => a - b);
console.log(`correct ${ok}/${res.length} = ${Math.round((100 * ok) / res.length)}% | time to lock on: median ${secs.length ? Math.round(secs[secs.length >> 1]) : '-'}s, never found: ${lock.filter((x) => x === null).length}/${truth.length}`);
