"""Build a synthetic test service: speak rows of the book with espeak-ng,
record when each row starts/ends, and make a 'church' copy with echo + noise.
Usage: python synth.py OUTDIR"""
import json
import subprocess
import sys
import wave
from pathlib import Path

from corpus import BOOK
from phonetics import coptic_to_ipa

# Service order: follows the book but skips two rows (a jump) to test recovery.
ORDER = ['cross', 'lord1', 'lord2', 'lord3', 'lord4', 'tri1', 'tri2', 'tri3',
         'doxa', 'kyrie', 'mary', 'risen']
SR = 16000
GAP = 1.0  # seconds of silence between rows

KIRSHENBAUM = {'θ': 'T', 'ʃ': 'S', 'dʒ': 'dZ', 'tʃ': 'tS', 'x': 'x'}


def ipa_to_espeak(ipa):
    for a, b in KIRSHENBAUM.items():
        ipa = ipa.replace(a, b)
    return ' '.join(f'[[{w}]]' for w in ipa.split())


def speak(text, voice, path, phonemes=False):
    subprocess.run(['espeak-ng', '-v', voice, '-s', '135', '-w', str(path),
                    ipa_to_espeak(text) if phonemes else text], check=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(path),
                    '-ar', str(SR), '-ac', '1', str(path) + '.16k.wav'], check=True)
    return Path(str(path) + '.16k.wav')


def main(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    rows = {r['id']: r for r in BOOK}
    frames, truth, t = [], [], 0.0
    silence = b'\0\0' * int(SR * GAP)
    for rid in ORDER:
        r = rows[rid]
        lang = r['say']
        if lang == 'cop':
            wav = speak(coptic_to_ipa(r['cop']), 'el', out / f'{rid}.wav', phonemes=True)
        else:
            wav = speak(r[lang], lang, out / f'{rid}.wav')
        with wave.open(str(wav)) as w:
            data = w.readframes(w.getnframes())
        dur = len(data) / 2 / SR
        truth.append(dict(id=rid, lang=lang, start=t, end=t + dur))
        frames += [data, silence]
        t += dur + GAP
    clean = out / 'service_clean.wav'
    with wave.open(str(clean), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b''.join(frames))
    # 'church': hall echo + crowd-like background noise + slight speed change
    subprocess.run([
        'ffmpeg', '-y', '-loglevel', 'error', '-i', str(clean),
        '-f', 'lavfi', '-i', f'anoisesrc=color=pink:amplitude=0.04:sample_rate={SR}',
        '-filter_complex',
        '[0]aecho=0.8:0.6:70|140|230:0.35|0.25|0.15[e];[e][1]amix=inputs=2:duration=first:weights=1 1[m]',
        '-map', '[m]', '-ar', str(SR), '-ac', '1', str(out / 'service_church.wav')], check=True)
    (out / 'truth.json').write_text(json.dumps(truth, indent=1))
    print(f'{len(truth)} rows, {t:.0f} s of audio -> {out}')


if __name__ == '__main__':
    main(sys.argv[1])
