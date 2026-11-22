"""Sound recognizer #2: wav2vec2 XLSR-53 fine-tuned to output phonemes
(espeak IPA) for any language. Free, open source, can run on a phone."""
import numpy as np
import soundfile as sf
import torch
from transformers import AutoProcessor, Wav2Vec2ForCTC

MODEL = 'facebook/wav2vec2-xlsr-53-espeak-cv-ft'
_proc = _model = None


def recognize(path, chunk_s=20):
    global _proc, _model
    if _model is None:
        _proc = AutoProcessor.from_pretrained(MODEL)
        _model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    audio, sr = sf.read(path, dtype='float32')
    assert sr == 16000, 'expects 16 kHz mono'
    vocab = {v: k for k, v in _proc.tokenizer.get_vocab().items()}
    blank = _proc.tokenizer.pad_token_id
    phones = []
    for off in range(0, len(audio), chunk_s * sr):  # chunks keep memory low
        piece = audio[off:off + chunk_s * sr]
        if len(piece) < sr // 4:
            break
        inp = _proc(piece, sampling_rate=sr, return_tensors='pt')
        with torch.no_grad():
            ids = _model(inp.input_values).logits[0].argmax(-1).numpy()
        frame = len(piece) / sr / len(ids)
        last = None
        for i, tok in enumerate(ids):
            if tok != last and tok != blank:
                ph = vocab[int(tok)]
                if ph not in ('<s>', '</s>', '<unk>', '|'):
                    phones.append((off / sr + i * frame, ph))
            last = tok
    return phones
