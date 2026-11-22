// Score the app's JS sound tracker (src/sounds.js) on recognized phones.
// Usage: node track_sounds.mjs BOOK.json PHONES.json TRUTH.json [minutes]
import { readFileSync } from 'node:fs';
import { SoundTracker } from '../../src/sounds.js';
const [bookPath, phonesPath, truthPath, minutes = '9999'] = process.argv.slice(2);
const book = JSON.parse(readFileSync(bookPath, 'utf8'));
const limit = +minutes * 60;
const phones = JSON.parse(readFileSync(phonesPath, 'utf8')).filter(([t]) => t < limit);
const truth = JSON.parse(readFileSync(truthPath, 'utf8')).filter((r) => r.end <= limit);
const tr = new SoundTracker(book);
const ids = book.paragraphs.map((p) => p.id), idx = Object.fromEntries(ids.map((id, i) => [id, i]));
const res = []; let ms = 0;
for (let t = 2; t <= truth.at(-1).end + 0.5; t += 1) {
  const heard = phones.filter(([s]) => s >= t - 5 && s < t).map(([, p]) => p);
  const t0 = performance.now(); tr.locate(heard); ms += performance.now() - t0;
  const said = truth.filter((r) => r.start <= t - 0.5);
  if (said.length) res.push([said.at(-1).id, ids[tr.para]]);
}
const n = res.length, hymn = (id) => id.split('-')[0];
console.log(`within 1 line ${Math.round(100 * res.filter(([a, b]) => Math.abs(idx[a] - idx[b]) <= 1).length / n)}%, ` +
  `right hymn ${Math.round(100 * res.filter(([a, b]) => hymn(a) === hymn(b)).length / n)}%, ` +
  `${(ms / n).toFixed(1)} ms per step, book ${book.paragraphs.length} rows`);
