"""Build a real-voice test from a Multilingual LibriSpeech parquet file
(real people reading books aloud, with exact text).
- book.json: every passage in the file is one row (many wrong places to go)
- service.wav: N passages read in book order, with one skipped section,
  plus hall echo and light noise; truth.json says when each passage is read.
Usage: python make_reading_test.py FILE.parquet LANG OUTDIR [N]"""
import io
import json
import subprocess
import sys
import wave
from pathlib import Path

import pyarrow.parquet as pq

SR = 16000
GAP = 1.0


def decode(audio_bytes):
    r = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', 'pipe:0', '-f', 's16le',
                        '-ar', str(SR), '-ac', '1', 'pipe:1'],
                       input=audio_bytes, capture_output=True, check=True)
    return r.stdout


def main(parquet, lang, out, n=40):
    n = int(n)
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    rows = sorted(pq.read_table(parquet).to_pylist(), key=lambda r: r['id'])
    book = {'title': f'{lang} reading test', 'languages': {lang: lang},
            'paragraphs': [{'id': r['id'], 'text': {lang: r['transcript']}} for r in rows]}
    (out / 'book.json').write_text(json.dumps(book, ensure_ascii=False, indent=0))
    # read passages in order from row 20, then skip 30 rows (a jump) halfway
    picked = list(range(20, 20 + n // 2))
    picked += list(range(picked[-1] + 31, picked[-1] + 31 + n - len(picked)))
    picked = [i for i in picked if i < len(rows)]
    pcm, truth, t = [], [], 0.0
    for i in picked:
        data = decode(rows[i]['audio']['bytes'])
        dur = len(data) / 2 / SR
        truth.append(dict(id=rows[i]['id'], lang=lang, start=t, end=t + dur))
        pcm += [data, b'\0\0' * int(SR * GAP)]
        t += dur + GAP
    clean = out / 'service_clean.wav'
    with wave.open(str(clean), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b''.join(pcm))
    subprocess.run([
        'ffmpeg', '-y', '-loglevel', 'error', '-i', str(clean),
        '-f', 'lavfi', '-i', f'anoisesrc=color=pink:amplitude=0.012:sample_rate={SR}',
        '-filter_complex', '[0]aecho=0.8:0.5:60|120:0.25|0.15[e];[e][1]amix=inputs=2:duration=first[m]',
        '-map', '[m]', '-ar', str(SR), '-ac', '1', str(out / 'service_hall.wav')], check=True)
    (out / 'truth.json').write_text(json.dumps(truth, indent=1))
    print(f'book: {len(rows)} rows; service: {len(truth)} passages, {t / 60:.1f} min -> {out}')


if __name__ == '__main__':
    main(*sys.argv[1:])
