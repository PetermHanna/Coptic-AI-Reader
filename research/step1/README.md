# Step 1: Can a free AI follow a Coptic service by sound?

**Idea.** The app doesn't need to understand Coptic. It only needs to find its place in a text it already has. So:

1. A free, open-source model turns the audio into *sounds* (phonemes), whatever the language.
2. The book text is turned into sounds too. Coptic uses pronunciation rules (`phonetics.py`, Greco-Bohairic church pronunciation); German and Arabic use espeak-ng.
3. Every second, the last 5 s of heard sounds are fuzzy-matched against the whole book. Similar sounds count as equal (b/p, s/ʃ, e/ɛ…).
4. The position moves forward through the book. Jumping elsewhere costs extra and needs a second confirmation (`track.py`).

## Results on a synthetic service (computer voice)

12 rows (9 Coptic, 1 German, 2 Arabic), about 5 s each, with a skip of two rows. Score = share of 1-second ticks where the app shows the row being read. Most remaining misses are the 1–3 s it takes to lock on at the start of each new row.

| Audio | Allosaurus (2020, 40 MB) | wav2vec2 XLSR-53 phoneme (300M params) |
|---|---|---|
| clean | 64% | **79%** |
| hall echo | 49% | **81%** |
| echo + light noise | 49% | **74%** |
| heavy echo + noise | 37% | 46% |

With wav2vec2, every row is found within 1–3 s, including the German and Arabic rows and the skipped section.

**Caveat.** This is synthetic speech, and the Coptic audio was generated from the same pronunciation rules used for matching, which flatters the result. **The real test is a recording of an actual service**, which is the next step.

## Real recordings (archangelmichaelchurch.net audio library)

**St. Gregory Liturgy, Fr. Sidrak Ibrahim, part 1 (57 min, old cassette transfer)**

- Whisper (free speech AI) transcribes the **Arabic** parts well, e.g. the Gospel at 20:00 and the Prayer of Reconciliation at 30:00. On **Coptic chant** it produces nonsense ("no, no, no…"). Ordinary speech AI can't follow Coptic.
- The wav2vec2 sound model hears only **2.3 sounds/s** (normal speech has about 10–12). The recording has almost no treble: the band above 3 kHz is 29 dB below the average level, and consonants live there. Spotting 12 well-known responses (`spot.py`) did no better than reversed or shuffled controls. **This recording is too degraded to follow.**
- Next: a 2011 digital recording (Fr. Ishak Shokry), with only a 10–16 dB treble gap.

## Run

```bash
pip install allosaurus transformers soundfile   # + apt install espeak-ng ffmpeg
python -m allosaurus.bin.download_model -m uni2005
python synth.py OUT                         # make test audio + truth.json
HF_HUB_DISABLE_XET=1 python track.py OUT/service_hall.wav OUT/truth.json --model w2v --verbose
```
