"""Word recognizer for German / Arabic / English: Whisper with a time for
every word. Stands in for the phone's built-in recognizer in tests.
Usage: python words_whisper.py AUDIO.wav LANG OUT.json [model]"""
import json
import sys

import soundfile as sf
from transformers import pipeline


def main(audio, lang, out, model='openai/whisper-small'):
    asr = pipeline('automatic-speech-recognition', model=model, chunk_length_s=30)
    data, sr = sf.read(audio, dtype='float32')
    res = asr({'raw': data, 'sampling_rate': sr}, return_timestamps='word',
              generate_kwargs={'language': lang, 'task': 'transcribe'})
    words = [(c['timestamp'][0], c['text'].strip()) for c in res['chunks']
             if c['timestamp'][0] is not None]
    json.dump(words, open(out, 'w'), ensure_ascii=False)
    print(len(words), 'words')


if __name__ == '__main__':
    main(*sys.argv[1:])
