"""Real-audio test without a full book: search a recording for well-known
Coptic/Greek responses that occur in every liturgy, and report where they are
heard. A reversed copy of each phrase is searched as a control for false hits.
Usage: python spot.py PHONES.json"""
import json
import sys

import numpy as np

from phonetics import coptic_to_ipa, ipa_to_classes
from track import COST, IDX

PHRASES = {
    'Kyrie eleison': 'Ⲕⲩⲣⲓⲉ ⲉ̀ⲗⲉⲏ̀ⲥⲟⲛ',
    'Ke to pnevmati sou (and with your spirit)': 'Ⲕⲉ ⲧⲱ ⲡ̀ⲛⲉⲩⲙⲁⲧⲓ ⲥⲟⲩ',
    'Epi proseuchi stathite (stand for prayer)': 'Ⲉ̀ⲡⲓ ⲡ̀ⲣⲟⲥⲉⲩⲭⲏ ⲥ̀ⲧⲁⲑⲏⲧⲉ',
    'Irini pasi (peace be with all)': 'Ⲓ̀ⲣⲏⲛⲏ ⲡⲁⲥⲓ',
    'Trisagion': 'Ⲁⲅⲓⲟⲥ ⲟ̀ Ⲑⲉⲟⲥ ⲁ̀ⲅⲓⲟⲥ ⲓⲥⲭⲩⲣⲟⲥ ⲁ̀ⲅⲓⲟⲥ ⲁ̀ⲑⲁⲛⲁⲧⲟⲥ',
    'Doxa si Kyrie (glory to you O Lord)': 'Ⲇⲟⲝⲁ ⲥⲓ Ⲕⲩⲣⲓⲉ',
    'Doxa Patri': 'Ⲇⲟⲝⲁ Ⲡⲁⲧⲣⲓ ⲕⲉ Ⲩⲓⲱ ⲕⲉ ⲁ̀ⲅⲓⲱ ⲡ̀ⲛⲉⲩⲙⲁⲧⲓ',
    'Axion ke dikeon (it is meet and right)': 'Ⲁ̀ⲝⲓⲟⲛ ⲕⲉ ⲇⲓⲕⲉⲟⲛ',
    'Sanctus (Agios Kyrios Sabaoth)': 'Ⲁⲅⲓⲟⲥ ⲁ̀ⲅⲓⲟⲥ ⲁ̀ⲅⲓⲟⲥ Ⲕⲩⲣⲓⲟⲥ ⲥⲁⲃⲁⲱⲑ',
    'Eleos irinis (a mercy of peace)': 'Ⲉ̀ⲗⲉⲟⲥ ⲓ̀ⲣⲏⲛⲏⲥ ⲑⲩⲥⲓⲁ ⲉ̀ⲛⲉⲥⲉⲱⲥ',
    'Ton Kyrion proskynisate': 'Ⲧⲟⲛ Ⲕⲩⲣⲓⲟⲛ ⲡ̀ⲣⲟⲥⲕⲩⲛⲏⲥⲁⲧⲉ',
    'Lords Prayer (Coptic)': 'Ⲡⲉⲛⲓⲱⲧ ⲉⲧϧⲉⲛ ⲛⲓⲫⲏⲟⲩⲓ ⲙⲁⲣⲉϥⲧⲟⲩⲃⲟ ⲛ̀ϫⲉ ⲡⲉⲕⲣⲁⲛ',
}


def search(query, text):
    """Cost of the best match of `query` ending at each position of `text`."""
    n = len(text)
    prev = np.zeros(n + 1)
    ramp = np.arange(n + 1)
    for qi in query:
        e = np.empty(n + 1)
        e[0] = prev[0] + 1
        e[1:] = np.minimum(prev[:-1] + COST[qi, text], prev[1:] + 1)
        prev = ramp + np.minimum.accumulate(e - ramp)
    return prev[1:] / len(query)


def hits(cost, times, thr, gap=8.0):
    """Local minima below threshold, at least `gap` seconds apart."""
    out = []
    for j in np.argsort(cost):
        if cost[j] > thr:
            break
        t = times[j]
        if all(abs(t - u) > gap for u, _ in out):
            out.append((t, cost[j]))
    return sorted(out)


def main(path, thr=0.30):
    phones = json.load(open(path))
    times, codes = [], []
    for t, ph in phones:
        for c in ipa_to_classes(ph):
            times.append(t); codes.append(IDX[c])
    text, times = np.array(codes), np.array(times)
    for name, cop in PHRASES.items():
        q = [IDX[c] for c in ipa_to_classes(coptic_to_ipa(cop))]
        real = hits(search(q, text), times, thr)
        ctrl = hits(search(q[::-1], text), times, thr)
        stamps = ' '.join(f'{int(t // 60)}:{int(t % 60):02d}' for t, _ in real[:12])
        print(f'{name:45s} found {len(real):3d}x  (control {len(ctrl):2d}x)  {stamps}')


if __name__ == '__main__':
    main(sys.argv[1], *(float(x) for x in sys.argv[2:]))
