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

**tasbeha.org timed hymns: Liturgy of St. Basil in Coptic (Higher Institute of Coptic Studies)**

21 sections, 71 min, 277 Coptic lines, each timed against the recording by the site (`tasbeha_service.py`).

| Measure | Result |
|---|---|
| exact line shown | 27% |
| right line or a neighbour | 53% |
| **Creed (recited fast, 4.9 sounds/s)** | **99% within one line, 100% right hymn** |
| Pi-nishti, Aspasmos Adam, Evshes (moderate chant, 0.8–1.5 sounds/s) | 54–97% within one line, 75–100% right hymn |
| long melismatic chants (Tay-shory, Sotees Amen, Alleluia; 0.2–0.4 sounds/s) | 0% |

**Conclusion.** Sound matching follows *spoken and lightly chanted* Coptic well. Long melismatic hymns hold single vowels for many seconds, so there are almost no sounds to match. Those need a different method: match the *melody* of the live audio against reference recordings of the same hymn (chroma features + dynamic time warping, as in music score-following). tasbeha.org has timed reference recordings by several cantors.

## German with real voices (Multilingual LibriSpeech, `make_reading_test.py`)

Book = 241 passages read aloud by real people; service = 40 passages in order (10.6 min) with one skipped section, plus hall echo and noise.

| Method | Right passage shown | Lock-on |
|---|---|---|
| words (Whisper-small + the app's `src/matcher.js`, `track_words.mjs`) | **94%** | median 1 s, all 40 found |
| sounds (wav2vec2 + `track.py`), clean | 90% | median 1 s, all 40 found |
| sounds, hall echo + noise | 90% | median 1 s, all 40 found |

German can be followed reliably. English uses the same path (`phonetics.py` already supports `en`).

## Run

```bash
pip install allosaurus transformers soundfile   # + apt install espeak-ng ffmpeg
python -m allosaurus.bin.download_model -m uni2005
python synth.py OUT                         # make test audio + truth.json
HF_HUB_DISABLE_XET=1 python track.py OUT/service_hall.wav OUT/truth.json --model w2v --verbose
```
