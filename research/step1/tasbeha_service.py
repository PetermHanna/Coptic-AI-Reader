"""Build a real Coptic test service from tasbeha.org's hymn library, whose
hymn pages time every line (and word) of the Coptic text against a recording.
- book.json: every line of every hymn (Coptic, English, Arabic), app format
- service.wav: the hymn recordings back to back
- truth.json: when each line is sung/said in service.wav
Usage: python tasbeha_service.py SERIES_PAGE_URL [SERIES_PAGE_URL ...] OUTDIR"""
import html
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = 'https://tasbeha.org'
SR = 16000


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'coptic-reader-research'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def text_of(fragment):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment))).strip()


def parse_hymn(page):
    title = text_of(re.search(r'<title>([^<|]*)', page).group(1))
    audio = re.search(r'<audio[^>]*src="([^"]+\.mp3)"|src="(/media/mp3/[^"]+\.mp3)"', page)
    audio = next(g for g in audio.groups() if g)
    timings = json.loads(html.unescape(re.search(r'data-timings="([^"]+)"', page).group(1)))
    timing = {t['idx']: t for t in timings}
    lines = []
    for m in re.finditer(r'<div class="sync-line row" data-idx="(\d+)"([\s\S]*?)<div class="sync-progress"', page):
        idx, body = int(m.group(1)), m.group(2)
        cop = ' '.join(text_of(w) for w in re.findall(r'<span class="w sync-coptic[^>]*>([\s\S]*?)</span>', body))
        en = re.search(r'<div class="sync-english">([\s\S]*?)</div>', body)
        ar = re.search(r'<div class="sync-arabic[^>]*>([\s\S]*?)</div>', body)
        t = timing.get(idx, {})
        lines.append(dict(idx=idx, cop=cop, en=text_of(en.group(1)) if en else '',
                          ar=text_of(ar.group(1)) if ar else '',
                          start=t.get('start', 0), end=t.get('end', 0)))
    return title, audio, lines


def main(*args):
    *series, out = args
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    views = []
    for s in series:
        page = get(s).decode('utf8', 'ignore')
        views += [v for v in re.findall(r'href="(/hymn_library/view/\d+\?mid=\d+)"', page) if v not in views]
    paragraphs, truth, pcm, offset = [], [], [], 0.0
    for n, v in enumerate(views):
        page = get(BASE + v).decode('utf8', 'ignore')
        try:
            title, audio, lines = parse_hymn(page)
        except (AttributeError, StopIteration, ValueError):
            print('skip (no timed text):', v); continue
        mp3 = out / f'{n:02d}.mp3'
        if not mp3.exists():
            mp3.write_bytes(get(BASE + audio.replace(' ', '%20')))
        raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', str(mp3), '-f', 's16le',
                              '-ar', str(SR), '-ac', '1', 'pipe:1'], capture_output=True, check=True).stdout
        dur = len(raw) / 2 / SR
        timed = 0
        for ln in lines:
            pid = f'h{n:02d}-{ln["idx"]}'
            paragraphs.append(dict(id=pid, section=title if ln is lines[0] else None,
                                   text={k: ln[k] for k in ('cop', 'en', 'ar') if ln[k]}))
            if ln['end'] > ln['start'] and ln['cop']:
                truth.append(dict(id=pid, lang='cop', start=offset + ln['start'], end=offset + ln['end']))
                timed += 1
        pcm.append(raw)
        offset += dur
        print(f'{n:02d} {title[:50]:50s} {dur / 60:4.1f} min, {timed}/{len(lines)} lines timed')
        time.sleep(1)  # be polite to the site
    for p in paragraphs:
        if not p['section']:
            del p['section']
    book = {'title': 'tasbeha.org timed hymns',
            'languages': {'cop': 'Coptic', 'en': 'English', 'ar': 'Arabic'}, 'paragraphs': paragraphs}
    (out / 'book.json').write_text(json.dumps(book, ensure_ascii=False, indent=0))
    (out / 'truth.json').write_text(json.dumps(sorted(truth, key=lambda r: r['start']), indent=1))
    import wave
    with wave.open(str(out / 'service.wav'), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b''.join(pcm))
    print(f'book {len(paragraphs)} lines, {len(truth)} timed, audio {offset / 60:.1f} min -> {out}')


if __name__ == '__main__':
    main(*sys.argv[1:])
