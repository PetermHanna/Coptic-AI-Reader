"""Follow a recording through the book and score how often the tracker
points at the right row.
Usage: python track.py AUDIO.wav TRUTH.json [--no-vowels] [--no-bias]"""
import argparse
import json

import numpy as np

from corpus import BOOK
from phonetics import CLASSES, VOWEL_CLASSES, ipa_to_classes, to_ipa

ALPHA = list(CLASSES) + ['#']
IDX = {c: i for i, c in enumerate(ALPHA)}
SEP = IDX['#']
# substitution costs: same group 0, vowel-for-vowel 0.5, anything else 1
COST = np.ones((len(ALPHA), len(ALPHA)))
for a in ALPHA:
    for b in ALPHA:
        if a == b and a != '#':
            COST[IDX[a], IDX[b]] = 0
        elif a in VOWEL_CLASSES and b in VOWEL_CLASSES:
            COST[IDX[a], IDX[b]] = 0.5


class Book:
    def __init__(self, rows, langs=('cop', 'de', 'ar'), vowels=True):
        self.vowels = vowels
        codes, owner, frac = [], [], []
        for ri, r in enumerate(rows):
            for lang in langs:
                if r.get(lang):
                    s = self.classes(to_ipa(r[lang], lang))
                    codes += [IDX[c] for c in s] + [SEP]
                    owner += [ri] * (len(s) + 1)
                    frac += [(k + 1) / len(s) for k in range(len(s))] + [1.0]
        self.text = np.array(codes)
        self.owner = np.array(owner)
        # reading coordinate of each sound: row number + fraction of the row
        self.coord = self.owner + np.array(frac)
        self.n_rows = len(rows)

    def classes(self, ipa):
        s = ipa_to_classes(ipa)
        return s if self.vowels else ''.join(c for c in s if c not in VOWEL_CLASSES)

    def row_costs(self, query):
        """Fuzzy-find `query` anywhere in the book (free start and end).
        Returns the cost of ending at each book position, per query sound."""
        q = [IDX[c] for c in query]
        n = len(self.text)
        prev = np.zeros(n + 1)
        ramp = np.arange(n + 1)
        for qi in q:
            e = np.empty(n + 1)
            e[0] = prev[0] + 1
            e[1:] = np.minimum(prev[:-1] + COST[qi, self.text], prev[1:] + 1)
            prev = ramp + np.minimum.accumulate(e - ramp)  # extra book sounds cost 1
        return prev[1:] / len(q)


def recognize(path):
    from allosaurus.app import read_recognizer
    out = read_recognizer().recognize(path, timestamp=True)
    phones = []
    for line in out.splitlines():
        start, _dur, ph = line.split(' ', 2)
        phones.append((float(start), ph))
    return phones


def prior(delta):
    """Extra cost for moving `delta` rows from the current reading position."""
    if -0.15 <= delta <= 1.5:
        return 0.0                                   # normal forward reading
    if delta > 1.5:
        return min(0.08 + 0.02 * (delta - 1.5), 0.25)  # skipping ahead
    return min(0.15 + 0.05 * -delta, 0.3)            # going back


def run(phones, book, truth, window=5.0, step=1.0, bias=True, max_cost=0.55):
    ids = [r['id'] for r in BOOK]
    end = truth[-1]['end']
    pos, pending, results = 0.0, None, []
    t = 2.0
    while t <= end + 0.5:
        heard = ''.join(p for s, p in phones if t - window <= s < t)
        q = book.classes(heard)
        if len(q) >= 6:
            cost = book.row_costs(q)
            score = cost + (np.vectorize(prior)(book.coord - pos) if bias else 0)
            j = int(np.argmin(score))
            if cost[j] < max_cost:
                jump = bias and not (-0.15 <= book.coord[j] - pos <= 1.5)
                if not jump or (pending is not None and abs(pending - book.coord[j]) < 0.6):
                    pos, pending = book.coord[j], None
                else:
                    pending = book.coord[j]  # big jump: wait for one more confirmation
        cur = min(int(pos - 1e-9), book.n_rows - 1)
        said = [r for r in truth if r['start'] <= t - 0.5]
        if said:
            results.append((t, said[-1]['id'], ids[cur]))
        t += step
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('audio'); ap.add_argument('truth')
    ap.add_argument('--no-vowels', action='store_true')
    ap.add_argument('--no-bias', action='store_true')
    ap.add_argument('--phones', help='cache file for recognized sounds')
    ap.add_argument('--verbose', action='store_true')
    a = ap.parse_args()
    truth = json.load(open(a.truth))
    try:
        phones = [tuple(x) for x in json.load(open(a.phones))]
    except (TypeError, FileNotFoundError):
        phones = recognize(a.audio)
        if a.phones:
            json.dump(phones, open(a.phones, 'w'))
    book = Book(BOOK, vowels=not a.no_vowels)
    res = run(phones, book, truth, bias=not a.no_bias)
    ok = sum(1 for _, want, got in res if want == got)
    if a.verbose:
        for t, want, got in res:
            print(f'{t:5.0f}s  reading {want:8s} app shows {got:8s} {"" if want == got else "  <-- wrong"}')
    # per-row: seconds until the app first points at the row after it starts
    lat = []
    for r in truth:
        hits = [t for t, want, got in res if want == r['id'] and got == r['id']]
        lat.append(f"{r['id']}:{(hits[0] - r['start']):.0f}s" if hits else f"{r['id']}:never")
    print(f'correct {ok}/{len(res)} = {ok / len(res):.0%} | time to lock on: ' + ' '.join(lat))


if __name__ == '__main__':
    main()
