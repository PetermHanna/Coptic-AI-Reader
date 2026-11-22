"""Collect the hymn texts of tasbeha.org's hymn library into app books.

Step 1 (list): read sitemap.xml, visit the audio pages (mp3/...) it lists and
  collect every linked hymn page (/hymn_library/view/ID?mid=M).
Step 2 (fetch): download each hymn page once (cached on disk).
Step 3 (build): parse Coptic / Latin-letter Coptic / English / Arabic lines,
  roles, the site's category path, and line timings, and write books.
Polite: one request per second, honours robots.txt disallows, caches.
Usage: python tools/tasbeha_crawl.py CACHE_DIR OUT_DIR"""
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = 'https://tasbeha.org'
UA = {'User-Agent': 'coptic-reader-app (church prayer book research)'}
DISALLOWED = ('/community/entry/', '/hymn_library/search', '/api/')


def get(url, cache: Path):
    assert not any(url.replace(BASE, '').startswith(d) for d in DISALLOWED)
    f = cache / re.sub(r'[^A-Za-z0-9._-]+', '_', url.replace(BASE, ''))[:180]
    if f.exists():
        return f.read_text('utf8')
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                text = r.read().decode('utf8', 'ignore')
            break
        except Exception as e:  # network hiccup: back off and retry
            if attempt == 3:
                print('  failed', url, e)
                return ''
            time.sleep(5 * (attempt + 1))
    f.write_text(text, 'utf8')
    time.sleep(1)
    return text


def text_of(fragment):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment))).strip()


def list_hymns(cache):
    sitemap = get(BASE + '/sitemap.xml', cache)
    pages = [u for u in re.findall(r'<loc>([^<]+)</loc>', sitemap) if '/mp3/' in u]
    views = {}
    for i, u in enumerate(pages):
        for v in re.findall(r'href="(/hymn_library/view/(\d+)\?mid=\d+)"', get(u, cache)):
            views.setdefault(v[1], v[0])  # one media version per hymn is enough for the text
        if i % 50 == 0:
            print(f'  audio pages {i}/{len(pages)}, hymns so far {len(views)}')
    return views


ROLE_WORDS = {
    'priest': ('priest', 'الكاهن', 'ⲡⲓⲟⲩⲏⲃ'), 'deacon': ('deacon', 'الشماس', 'ⲡⲓⲇⲓⲁⲕⲱⲛ'),
    'people': ('people', 'congregation', 'الشعب', 'ⲡⲓⲗⲁⲟⲥ'),
}


def role_of(line):
    """Lines like 'Deacon:' / 'الشماس:' only name who speaks next."""
    words = (line['en'] + ' ' + line['ar']).lower().replace(':', ' ').split()
    if 0 < len(words) <= 4:
        for role, keys in ROLE_WORDS.items():
            if any(k in words for k in keys):
                return role
    return None


def parse(page):
    title_m = re.search(r'<title>([^<]*)</title>', page)
    if not title_m or 'sync-line' not in page:
        return None
    title = html.unescape(title_m.group(1)).split('|')[0].strip()
    crumbs = [text_of(c) for c in re.findall(r'<a[^>]+href="/hymn_library/cat/\d+"[^>]*>([\s\S]*?)</a>', page)]
    audio = re.search(r'src="(/media/mp3/[^"]+\.mp3)"', page)
    tm = re.search(r'data-timings="([^"]+)"', page)
    timing = {t['idx']: t for t in json.loads(html.unescape(tm.group(1)))} if tm else {}
    lines = []
    for m in re.finditer(r'<div class="sync-line row" data-idx="(\d+)"([\s\S]*?)<div class="sync-progress"', page):
        idx, body = int(m.group(1)), m.group(2)
        cop = ' '.join(text_of(w) for w in re.findall(r'<span class="w sync-coptic[^>]*>([\s\S]*?)</span>', body))
        lat = ' '.join(text_of(w) for w in re.findall(r'<span class="w sync-translit[^>]*>([\s\S]*?)</span>', body))
        en = re.search(r'<div class="sync-english">([\s\S]*?)</div>', body)
        ar = re.search(r'<div class="sync-arabic[^>]*>([\s\S]*?)</div>', body)
        t = timing.get(idx, {})
        lines.append(dict(idx=idx, cop=cop, cop_lat=lat, en=text_of(en.group(1)) if en else '',
                          ar=text_of(ar.group(1)) if ar else '', start=t.get('start', 0), end=t.get('end', 0)))
    return dict(title=title, path=crumbs, audio=audio.group(1) if audio else None, lines=lines)


def build(hymns, out: Path):
    """One book per top-level service (e.g. 'The Divine Liturgy'), hymns in site order."""
    out.mkdir(parents=True, exist_ok=True)
    books, timings = {}, {}
    for hid, h in hymns.items():
        group = h['path'][1] if len(h['path']) > 1 else (h['path'][0] if h['path'] else 'Other')
        paras, role = books.setdefault(group, []), None
        first = True
        for ln in h['lines']:
            r = role_of(ln)
            if r:
                role = r
                continue
            text = {k: ln[k] for k in ('cop', 'cop_lat', 'en', 'ar') if ln[k]}
            if not text:
                continue
            p = {'id': f't{hid}-{ln["idx"]}', 'text': text}
            if role:
                p['role'] = role
            if first:
                p['section'] = {'en': h['title'], 'path': ' › '.join(h['path'])}
                first = False
            paras.append(p)
            if ln['end'] > ln['start']:
                timings[p['id']] = [h['audio'], ln['start'], ln['end']]
    roles = {'priest': {'en': 'Priest', 'de': 'Priester', 'ar': 'الكاهن', 'cop': 'Ⲡⲓⲟⲩⲏⲃ'},
             'deacon': {'en': 'Deacon', 'de': 'Diakon', 'ar': 'الشماس', 'cop': 'Ⲡⲓⲇⲓⲁⲕⲱⲛ'},
             'people': {'en': 'People', 'de': 'Gemeinde', 'ar': 'الشعب', 'cop': 'Ⲡⲓⲗⲁⲟⲥ'}}
    index = []
    for i, (group, paras) in enumerate(sorted(books.items(), key=lambda kv: -len(kv[1]))):
        name = f'tasbeha-{i:02d}.json'
        (out / name).write_text(json.dumps({
            'title': group, 'source': 'tasbeha.org hymn library',
            'languages': {'en': 'English', 'cop': 'Ⲙⲉⲧⲣⲉⲙⲛ̀ⲭⲏⲙⲓ', 'cop_lat': 'Coptic (Latin letters)', 'ar': 'عربي'},
            'roles': roles, 'paragraphs': paras}, ensure_ascii=False, separators=(',', ':')), 'utf8')
        index.append({'file': name, 'title': group, 'lines': len(paras),
                      'hymns': sum(1 for p in paras if 'section' in p)})
    (out / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1), 'utf8')
    (out / 'timings.json').write_text(json.dumps(timings, ensure_ascii=False, separators=(',', ':')), 'utf8')
    return index


def main(cache, out):
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    print('step 1: listing hymns')
    views = list_hymns(cache)
    print(f'  {len(views)} hymns')
    print('step 2: fetching hymn pages')
    hymns = {}
    for i, (hid, path) in enumerate(sorted(views.items(), key=lambda kv: int(kv[0]))):
        h = parse(get(BASE + path, cache))
        if h and h['lines']:
            hymns[hid] = h
        if i % 50 == 0:
            print(f'  {i}/{len(views)} fetched, {len(hymns)} with text')
    print('step 3: building books')
    for b in build(hymns, Path(out)):
        print(f"  {b['file']}: {b['title']} — {b['hymns']} hymns, {b['lines']} lines")


if __name__ == '__main__':
    main(*sys.argv[1:])
