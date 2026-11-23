"""Convert "The Holy Euchologion (Contemporary English Version)" (Coptic Orthodox
Diocese of the Midlands, UK; reproduced by permission of copticbook.net) from
its PDF into an app book: one row per stanza, English | Coptic | Arabic.

The PDF lays out three columns. Coptic uses the legacy "Athanasius" font
(Latin letters drawn as Coptic), converted here to Unicode Coptic. Arabic is
rebuilt from glyph positions (right to left), because the PDF stores some
Arabic runs out of order. Lines where an Arabic glyph could not be read are
listed for checking (never guessed).

Usage: python tools/kholagy_pdf.py euchologion.pdf books/kholagy.json [review.txt]"""
import json
import re
import sys
import unicodedata

import pymupdf

# ---- legacy Athanasius font -> Unicode Coptic (verified against tasbeha.org) ----
LOWER = dict(zip('abgdezhqiklm[noprctuvxyw]f\'\\jsy;', 'ⲁⲃⲅⲇⲉⲍⲏⲑⲓⲕⲗⲙⲝⲛⲟⲡⲣⲥⲧⲩⲫⲭⲯⲱϣϥϧϩϫϭⲯϯ'))
UPPER = dict(zip('ABGDEZHQIKLM{NOPRCTUVXYW}F"|JS:', 'ⲀⲂⲄⲆⲈⲌⲎⲐⲒⲔⲖⲘⲜⲚⲞⲠⲢⲤⲦⲨⲪⲬⲮⲰϢϤϦϨϪϬϮ'))
GRAVE, OVER = '̀', '̅'


def coptic(raw):
    out = []          # list of [letter, marks]
    jinkim = False
    for ch in raw:
        if ch in '`~':                 # jinkim on the next letter
            jinkim = True
            continue
        if ch == '/' and out:          # overline on the previous letter (abbreviations)
            out[-1][1] += OVER
            continue
        if ch == '?':                  # overline on the two previous letters (Ⲓⲏ̅ⲥ̅, Ⲡⲭ̅ⲥ̅)
            for item in [o for o in out if o[0].strip()][-2:]:
                item[1] += OVER
            continue
        if ch == '_':                  # "Lord" abbreviation: Ⲡ + ⲟ̅ⲥ̅
            out += [['ⲟ', OVER], ['ⲥ', OVER]]
            continue
        if ch == '>':                  # Coptic verse colon
            out.append([':', ''])
            continue
        letter = LOWER.get(ch) or UPPER.get(ch)
        if letter:
            out.append([letter, GRAVE if jinkim else ''])
            jinkim = False
        else:
            out.append([ch, ''])
            if not ch.isspace():
                jinkim = False
    return re.sub(r'\s+', ' ', ''.join(a + b for a, b in out)).strip()


# ---- Arabic: rebuild from glyph positions, normalise presentation forms ----
def arabic(chars):
    """chars: list of (x_center, x0, x1, c). Returns (text, suspicious_gap)."""
    chars = sorted(chars, key=lambda t: -t[0])           # visual right-to-left = logical
    text, gap = '', False
    prev_x0 = None
    for xc, x0, x1, c in chars:
        if prev_x0 is not None and c.strip() and prev_x0 - x1 > 9 and not text.endswith(' '):
            gap = True                                    # a glyph is probably missing here
        text += c
        if c.strip():
            prev_x0 = x0
    # Two ligature glyphs have no Unicode in the PDF; each is always the same
    # letters (checked on every occurrence): 0x95 = "لمج" (المجد، المجيد، المجتمعين…),
    # 0x9d = "نه" (لأنها، الأنهار، إنها…).
    text = text.replace('\x95', 'لمج').replace('\x9d', 'نه')
    # The PDF writes "الله" as alef + the Allah glyph, which already has its alef.
    text = re.sub('[اﺍ]\\s*ﷲ', 'ﷲ', text)
    text = unicodedata.normalize('NFKC', text).replace('ـ', '')  # drop tatweel
    if '�' in text or '•' in text or re.search('[\x00-\x1f\x7f-\x9f]', text):
        gap = True
    return re.sub(r'\s+', ' ', text).strip(), gap


def classify(span, x, y):
    f, size, italic = span['font'].split('+')[-1], span['size'], bool(span['flags'] & 2)
    if 'Athanasius' in f:
        return 'cop'
    if 'Arabic' in f or 'Tahoma' in f:
        return 'ar'
    if italic and size < 13 and y < 40:
        return 'header'
    if size < 13 and y > 735:
        return 'pageno'
    if x < 46 and 'Bold' in f:
        return 'role'
    if italic and size > 13:
        return 'rubric'
    if not italic and 'Bold' not in f and size > 13.5 and 'Garamond' in f and size in (14.4, 18.0, 21.8) or (not italic and 'Bold' not in f and round(size, 1) in (14.4, 18.0, 21.8)):
        return 'heading'
    return 'en'


ROLES = {'P': 'priest', 'D': 'deacon', 'C': 'people'}


def lines_of(page):
    """Group characters into lines per class: list of dict(cls, y, x0, text, gap)."""
    groups = {}
    for b in page.get_text('rawdict')['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                for ch in s['chars']:
                    x0, y0, x1, y1 = ch['bbox']
                    y = ch['origin'][1]
                    cls = classify(s, x0, y)
                    if cls == 'ar' and not ch['c'].strip() and False:
                        continue
                    key = (cls, round(y / 3))
                    groups.setdefault(key, []).append(((x0 + x1) / 2, x0, x1, ch['c'], y))
    out = []
    for (cls, _), chars in groups.items():
        y = min(c[4] for c in chars)
        x0 = min(c[1] for c in chars if c[3].strip()) if any(c[3].strip() for c in chars) else 0
        if cls == 'ar':
            text, gap = arabic([c[:4] for c in chars])
        else:
            chars.sort(key=lambda c: c[0])
            raw = ''
            prev = None
            for xc, a, bx, c, _ in chars:
                if prev is not None and a - prev > 2.5 and not raw.endswith(' ') and c != ' ':
                    raw += ' '                       # justified text: gaps are spaces
                raw += c
                prev = bx
            text = coptic(raw) if cls == 'cop' else re.sub(r'\s+', ' ', raw).strip()
            gap = False
        if text:
            out.append(dict(cls=cls, y=y, x0=x0, text=text, gap=gap))
    return sorted(out, key=lambda d: (d['y'], d['x0']))


def convert(pdf, first_page=11):
    doc = pymupdf.open(pdf)
    rows, review = [], []
    row = None
    pending_section, header, last_header = None, None, None
    pending_role = None
    for pno in range(first_page - 1, len(doc)):
        lines = lines_of(doc[pno])
        # running header: "Liturgy of Saint Basil – The Prayer of Preparation"
        for ln in lines:
            if ln['cls'] == 'header':
                header = ln['text']
        if header and header != last_header:
            pending_section = pending_section or header
            last_header = header
        # headings on the page (small caps split into big + small letters on one line)
        heads = {}
        for ln in lines:
            if ln['cls'] == 'heading':
                heads.setdefault(round(ln['y'] / 4), []).append(ln)
        heading_lines = sorted(
            (min(l['y'] for l in g), ' '.join(l['text'] for l in sorted(g, key=lambda l: l['x0'])))
            for g in heads.values())

        def new_row(kind, y):
            nonlocal row, pending_section, pending_role
            row = {'id': f'k{len(rows) + 1}', 'text': {}, '_y': y, '_page': pno + 1}
            if kind == 'rubric':
                row['kind'] = 'rubric'
            if pending_section:
                row['section'] = {'en': pending_section}
                pending_section = None
            if pending_role and kind != 'rubric':
                row['role'] = pending_role
            rows.append(row)

        anchors = []  # (y, kind) where a new row starts
        for ln in lines:
            if ln['cls'] == 'en' and 62 < ln['x0'] < 90:
                anchors.append((ln['y'], 'stanza'))
            elif ln['cls'] == 'cop' and 252 < ln['x0'] < 275:
                anchors.append((ln['y'], 'stanza'))
        events = sorted(
            [(y, 'heading', t) for y, t in heading_lines] +
            [(ln['y'], 'role', ln['text']) for ln in lines if ln['cls'] == 'role'] +
            [(y, 'anchor', None) for y, _ in anchors] +
            [(ln['y'], 'line', ln) for ln in lines if ln['cls'] in ('en', 'cop', 'ar', 'rubric')],
            key=lambda e: (e[0], {'heading': 0, 'role': 1, 'anchor': 2, 'line': 3}[e[1]]))
        last_anchor_y = -99
        for y, kind, val in events:
            if kind == 'heading':
                pending_section = re.sub(r'\s+', ' ', val).strip().title()
                row = None
            elif kind == 'role':
                letter = val.strip()[:1]
                if letter in ROLES:
                    pending_role = ROLES[letter]
            elif kind == 'anchor':
                if y - last_anchor_y > 6:          # English and Coptic starts of one stanza
                    new_row('stanza', y)
                last_anchor_y = y
            else:
                ln = val
                if ln['cls'] == 'rubric':
                    if not row or row.get('kind') != 'rubric' or y - row['_y'] > 40:
                        new_row('rubric', y)
                    row['_y'] = y
                    row['text']['en'] = (row['text'].get('en', '') + ' ' + ln['text']).strip()
                    continue
                if row is None or row.get('kind') == 'rubric':
                    new_row('stanza', y)
                key = ln['cls']
                row['text'][key] = (row['text'].get(key, '') + ' ' + ln['text']).strip()
                if ln['gap']:
                    row['check'] = True
    book_rows = []
    for r in rows:
        if not r['text']:
            continue
        r['text'] = {k: re.sub(r'\s+', ' ', v).strip() for k, v in r['text'].items()}
        if r.get('check'):
            review.append(f"page {r['_page']} {r['id']}: {r['text'].get('ar', '')}")
        r['page'] = r.pop('_page')
        r.pop('_y', None)
        book_rows.append(r)
    return book_rows, review


def main(pdf, out, review_path=None):
    rows, review = convert(pdf)
    book = {
        'title': 'Kholagi',
        'source': 'The Holy Euchologion (Contemporary English Version), Coptic Orthodox Diocese of the '
                  'Midlands, UK (ukmidcopts.org); reproduced by permission of Ihab Fanous (copticbook.net). '
                  'Converted from the PDF; rows marked "check" have an Arabic glyph that could not be read.',
        'languages': {'en': 'English', 'cop': 'Ⲙⲉⲧⲣⲉⲙⲛ̀ⲭⲏⲙⲓ', 'ar': 'عربي'},
        'roles': {'priest': {'en': 'Priest', 'de': 'Priester', 'ar': 'الكاهن', 'cop': 'Ⲡⲓⲟⲩⲏⲃ'},
                  'deacon': {'en': 'Deacon', 'de': 'Diakon', 'ar': 'الشماس', 'cop': 'Ⲡⲓⲇⲓⲁⲕⲱⲛ'},
                  'people': {'en': 'People', 'de': 'Gemeinde', 'ar': 'الشعب', 'cop': 'Ⲡⲓⲗⲁⲟⲥ'}},
        'paragraphs': rows,
    }
    with open(out, 'w', encoding='utf8') as f:
        json.dump(book, f, ensure_ascii=False, separators=(',', ':'))
    if review_path:
        with open(review_path, 'w', encoding='utf8') as f:
            f.write('\n'.join(review))
    n = len(rows)
    has = lambda k: sum(1 for r in rows if k in r['text'])
    print(f'{n} rows ({sum(1 for r in rows if r.get("kind") == "rubric")} rubrics), '
          f'en {has("en")}, cop {has("cop")}, ar {has("ar")}, with role {sum(1 for r in rows if "role" in r)}, '
          f'sections {sum(1 for r in rows if "section" in r)}, Arabic to check {len(review)}')


if __name__ == '__main__':
    main(*sys.argv[1:])
